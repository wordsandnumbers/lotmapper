from datetime import datetime, timedelta

from jose import jwt

from app.config import get_settings
from app.core.security import (
    create_access_token,
    create_reset_token,
    create_signup_token,
)

settings = get_settings()


def test_request_reset_sends_link_for_active_user(client, make_user, mock_email):
    user = make_user(email="active@example.com", is_active=True)

    r = client.post("/auth/request-password-reset", json={"email": user.email})
    assert r.status_code == 200
    assert "message" in r.json()

    assert len(mock_email["password_resets"]) == 1
    sent = mock_email["password_resets"][0]
    assert sent["recipient"] == user.email
    assert "/reset-password?token=" in sent["link"]


def test_request_reset_silent_for_unknown_email(client, mock_email):
    r = client.post("/auth/request-password-reset", json={"email": "nobody@example.com"})
    assert r.status_code == 200
    assert mock_email["password_resets"] == []


def test_request_reset_silent_for_inactive_user(client, make_user, mock_email):
    make_user(email="pending@example.com", is_active=False, password=None)

    r = client.post("/auth/request-password-reset", json={"email": "pending@example.com"})
    assert r.status_code == 200
    assert mock_email["password_resets"] == []


def test_request_reset_rate_limited_silently(
    client, make_user, mock_email, enable_rate_limits
):
    user = make_user(email="ratelimited@example.com", is_active=True)

    for _ in range(5):
        r = client.post("/auth/request-password-reset", json={"email": user.email})
        assert r.status_code == 200

    r = client.post("/auth/request-password-reset", json={"email": user.email})
    assert r.status_code == 200

    assert len(mock_email["password_resets"]) == 5


def test_reset_password_updates_hash(client, make_user, db_session):
    user = make_user(email="reset@example.com", is_active=True, password="oldpassword")
    original_hash = user.password_hash
    token = create_reset_token(user.id, user.password_hash)

    r = client.post(
        "/auth/reset-password",
        json={"token": token, "password": "brand-new-pw"},
    )
    assert r.status_code == 200
    assert "Please log in" in r.json()["message"]

    db_session.refresh(user)
    assert user.password_hash != original_hash

    bad = client.post(
        "/auth/login", json={"email": user.email, "password": "oldpassword"}
    )
    assert bad.status_code == 401

    good = client.post(
        "/auth/login", json={"email": user.email, "password": "brand-new-pw"}
    )
    assert good.status_code == 200


def test_reset_password_rejects_expired_token(client, make_user):
    from app.core.security import _hash_fingerprint

    user = make_user(is_active=True)
    expired = jwt.encode(
        {
            "sub": str(user.id),
            "type": "reset",
            "fp": _hash_fingerprint(user.password_hash),
            "exp": datetime.utcnow() - timedelta(minutes=1),
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )

    r = client.post(
        "/auth/reset-password",
        json={"token": expired, "password": "longenough"},
    )
    assert r.status_code == 400


def test_reset_password_rejects_replay_after_successful_reset(
    client, make_user, db_session
):
    """A reset token bound to the old password_hash should fail once it's been
    consumed (i.e. once the password has been changed)."""
    user = make_user(email="replay@example.com", is_active=True, password="originalpw")
    token = create_reset_token(user.id, user.password_hash)

    r1 = client.post(
        "/auth/reset-password",
        json={"token": token, "password": "newpassword1"},
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/auth/reset-password",
        json={"token": token, "password": "evenrnewer1"},
    )
    assert r2.status_code == 400


def test_reset_password_rejects_replay_after_password_change(
    client, make_user, db_session
):
    """A reset token issued before the user changed their password through any
    other channel must also become invalid."""
    from app.core.security import get_password_hash

    user = make_user(email="rotated@example.com", is_active=True, password="originalpw")
    token = create_reset_token(user.id, user.password_hash)

    user.password_hash = get_password_hash("changed-out-of-band")
    db_session.commit()

    r = client.post(
        "/auth/reset-password",
        json={"token": token, "password": "attacker-pw"},
    )
    assert r.status_code == 400


def test_reset_password_rejects_signup_token(client, make_user):
    user = make_user(is_active=True)
    signup_token = create_signup_token(user.id)

    r = client.post(
        "/auth/reset-password",
        json={"token": signup_token, "password": "longenough"},
    )
    assert r.status_code == 400


def test_reset_password_rejects_access_token(client, make_user):
    user = make_user(is_active=True)
    access = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role}
    )

    r = client.post(
        "/auth/reset-password",
        json={"token": access, "password": "longenough"},
    )
    assert r.status_code == 400


def test_reset_password_rejects_short_password(client, make_user):
    user = make_user(is_active=True)
    token = create_reset_token(user.id, user.password_hash)

    r = client.post(
        "/auth/reset-password",
        json={"token": token, "password": "short"},
    )
    assert r.status_code == 400


def test_reset_password_rejects_inactive_user(client, make_user):
    """Inactive user with a real password_hash — fingerprint matches but the
    user isn't allowed to log in, so reset must also be blocked."""
    user = make_user(is_active=False, password="oldpw")
    token = create_reset_token(user.id, user.password_hash)

    r = client.post(
        "/auth/reset-password",
        json={"token": token, "password": "longenough"},
    )
    assert r.status_code == 400


def test_reset_password_rejects_garbage_token(client):
    r = client.post(
        "/auth/reset-password",
        json={"token": "not-a-jwt", "password": "longenough"},
    )
    assert r.status_code == 400
