"""Shared fixtures for auth tests.

These tests run against the configured Postgres database (the User table has no
PostGIS dependencies, but other models in the schema do, so SQLite is not
viable). Each test runs inside a transaction that is rolled back at teardown,
so tests are isolation-safe in any order.

Run with:
    cd backend && python -m pytest tests/test_auth_*.py -v
"""
from __future__ import annotations

import uuid
from typing import Callable, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.auth import router as auth_router
from app.core.security import create_access_token, get_password_hash
from app.database import SessionLocal, engine, get_db
from app.models.user import User


@pytest.fixture
def db_session():
    """Transactional session that rolls back at the end of the test.

    Uses SAVEPOINT-based nesting so that endpoint code calling `db.commit()`
    only commits to the outer transaction, which we then roll back.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, autocommit=False)
    session.begin_nested()

    from sqlalchemy import event

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        event.remove(session, "after_transaction_end", restart_savepoint)
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient wired to the transactional session.

    Mounts only the auth router (skipping the main app's RabbitMQ lifespan).
    """
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_email(monkeypatch):
    """Capture outbound emails instead of sending them.

    Returns a dict with two lists:
        notifications: [(requester_email, owner_emails), ...]
        signup_links:  [{recipient, link, invited_by}, ...]
    """
    captured = {"notifications": [], "signup_links": []}

    def fake_notify(requester_email: str, owner_emails: list[str]) -> None:
        captured["notifications"].append((requester_email, list(owner_emails)))

    def fake_signup_link(recipient_email, signup_link, *, invited_by=None):
        captured["signup_links"].append(
            {"recipient": recipient_email, "link": signup_link, "invited_by": invited_by}
        )

    from app.api import auth as auth_module
    from app.services import email as email_module

    monkeypatch.setattr(
        email_module, "send_access_request_notification", fake_notify
    )
    monkeypatch.setattr(email_module, "send_signup_link_email", fake_signup_link)
    monkeypatch.setattr(
        auth_module.email_service, "send_access_request_notification", fake_notify
    )
    monkeypatch.setattr(
        auth_module.email_service, "send_signup_link_email", fake_signup_link
    )
    return captured


@pytest.fixture
def make_user(db_session) -> Callable[..., User]:
    """Factory for creating users in the DB with arbitrary state."""

    def _make(
        *,
        email: Optional[str] = None,
        role: str = "reviewer",
        is_active: bool = True,
        password: Optional[str] = "password123",
    ) -> User:
        user = User(
            email=email or f"user-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=get_password_hash(password) if password else None,
            role=role,
            is_active=is_active,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make


@pytest.fixture
def auth_headers() -> Callable[[User], dict]:
    """Returns a callable that mints a real access token for a User."""

    def _headers(user: User) -> dict:
        token = create_access_token(
            data={"sub": str(user.id), "email": user.email, "role": user.role}
        )
        return {"Authorization": f"Bearer {token}"}

    return _headers
