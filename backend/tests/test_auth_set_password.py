import secrets
from datetime import datetime, timedelta

from app.core.security import decode_token


def _seed_token(db_session, user, *, expires_in=timedelta(hours=72)) -> str:
    token = secrets.token_urlsafe(24)
    user.signup_token = token
    user.signup_token_expires_at = datetime.utcnow() + expires_in
    db_session.commit()
    return token


def test_set_password_with_valid_token_logs_in(client, make_user, db_session):
    user = make_user(is_active=False, password=None)
    token = _seed_token(db_session, user)

    r = client.post(
        "/auth/set-password",
        json={"token": token, "password": "longenough"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"

    payload = decode_token(body["access_token"])
    assert payload is not None
    assert payload["sub"] == str(user.id)

    db_session.refresh(user)
    assert user.password_hash is not None
    assert user.is_active is True
    assert user.signup_token is None
    assert user.signup_token_expires_at is None


def test_set_password_rejects_expired_token(client, make_user, db_session):
    user = make_user(is_active=False, password=None)
    token = _seed_token(db_session, user, expires_in=timedelta(hours=-1))

    r = client.post(
        "/auth/set-password",
        json={"token": token, "password": "longenough"},
    )
    assert r.status_code == 400


def test_set_password_rejects_replay(client, make_user, db_session):
    user = make_user(is_active=False, password=None)
    token = _seed_token(db_session, user)

    r1 = client.post(
        "/auth/set-password", json={"token": token, "password": "longenough"}
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/auth/set-password", json={"token": token, "password": "different1"}
    )
    assert r2.status_code == 400


def test_set_password_rejects_short_password(client, make_user, db_session):
    user = make_user(is_active=False, password=None)
    token = _seed_token(db_session, user)

    r = client.post(
        "/auth/set-password", json={"token": token, "password": "short1"}
    )
    assert r.status_code == 400


def test_set_password_rejects_unknown_token(client):
    r = client.post(
        "/auth/set-password",
        json={"token": "totally-bogus-token", "password": "longenough"},
    )
    assert r.status_code == 400
