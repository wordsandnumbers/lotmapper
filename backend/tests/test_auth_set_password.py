from datetime import datetime, timedelta

from jose import jwt

from app.config import get_settings
from app.core.security import (
    create_access_token,
    create_signup_token,
    decode_token,
)

settings = get_settings()


def test_set_password_with_valid_token_logs_in(client, make_user, db_session):
    user = make_user(is_active=False, password=None)
    token = create_signup_token(user.id)

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


def test_set_password_rejects_expired_token(client, make_user):
    user = make_user(is_active=False, password=None)
    expired = jwt.encode(
        {
            "sub": str(user.id),
            "type": "signup",
            "exp": datetime.utcnow() - timedelta(hours=1),
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )

    r = client.post(
        "/auth/set-password",
        json={"token": expired, "password": "longenough"},
    )
    assert r.status_code == 400


def test_set_password_rejects_wrong_type_token(client, make_user):
    user = make_user(is_active=False, password=None)
    access = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role}
    )

    r = client.post(
        "/auth/set-password",
        json={"token": access, "password": "longenough"},
    )
    assert r.status_code == 400


def test_set_password_rejects_replay(client, make_user):
    user = make_user(is_active=False, password=None)
    token = create_signup_token(user.id)

    r1 = client.post(
        "/auth/set-password", json={"token": token, "password": "longenough"}
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/auth/set-password", json={"token": token, "password": "different1"}
    )
    assert r2.status_code == 400


def test_set_password_rejects_short_password(client, make_user):
    user = make_user(is_active=False, password=None)
    token = create_signup_token(user.id)

    r = client.post(
        "/auth/set-password", json={"token": token, "password": "short1"}
    )
    assert r.status_code == 400


def test_set_password_rejects_garbage_token(client):
    r = client.post(
        "/auth/set-password",
        json={"token": "not-a-jwt", "password": "longenough"},
    )
    assert r.status_code == 400
