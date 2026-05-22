from app.models.user import User


def test_owner_can_invite_new_email(client, make_user, auth_headers, mock_email, db_session):
    owner = make_user(role="owner", is_active=True)

    r = client.post(
        "/auth/invite",
        json={"email": "newcomer@example.com"},
        headers=auth_headers(owner),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "newcomer@example.com"
    assert body["is_active"] is True

    user = db_session.query(User).filter(User.email == "newcomer@example.com").one()
    assert user.password_hash is None
    assert user.is_active is True

    assert len(mock_email["signup_links"]) == 1
    sent = mock_email["signup_links"][0]
    assert sent["recipient"] == "newcomer@example.com"
    assert sent["invited_by"] == owner.email
    assert "/set-password?token=" in sent["link"]


def test_invite_rejects_existing_active_user(
    client, make_user, auth_headers, mock_email
):
    owner = make_user(role="owner", is_active=True)
    existing = make_user(email="active@example.com", is_active=True, password="abcdefgh")

    r = client.post(
        "/auth/invite",
        json={"email": existing.email},
        headers=auth_headers(owner),
    )
    assert r.status_code == 409
    assert "already has an account" in r.json()["detail"]
    assert mock_email["signup_links"] == []


def test_invite_rejects_existing_pending_request(
    client, make_user, auth_headers, mock_email
):
    owner = make_user(role="owner", is_active=True)
    pending = make_user(
        email="pending@example.com", is_active=False, password=None
    )

    r = client.post(
        "/auth/invite",
        json={"email": pending.email},
        headers=auth_headers(owner),
    )
    assert r.status_code == 409
    assert "approve it instead" in r.json()["detail"]
    assert mock_email["signup_links"] == []


def test_invite_rejects_existing_pending_invite(
    client, make_user, auth_headers, mock_email
):
    owner = make_user(role="owner", is_active=True)
    pending_invite = make_user(
        email="invited@example.com", is_active=True, password=None
    )

    r = client.post(
        "/auth/invite",
        json={"email": pending_invite.email},
        headers=auth_headers(owner),
    )
    assert r.status_code == 409
    assert "Invite already sent" in r.json()["detail"]
    assert mock_email["signup_links"] == []


def test_admin_cannot_invite(client, make_user, auth_headers, mock_email):
    admin = make_user(role="admin", is_active=True)

    r = client.post(
        "/auth/invite",
        json={"email": "anyone@example.com"},
        headers=auth_headers(admin),
    )
    assert r.status_code == 403
    assert mock_email["signup_links"] == []


def test_reviewer_cannot_invite(client, make_user, auth_headers, mock_email):
    reviewer = make_user(role="reviewer", is_active=True)

    r = client.post(
        "/auth/invite",
        json={"email": "anyone@example.com"},
        headers=auth_headers(reviewer),
    )
    assert r.status_code == 403
    assert mock_email["signup_links"] == []


def test_unauthenticated_cannot_invite(client, mock_email):
    r = client.post("/auth/invite", json={"email": "anyone@example.com"})
    assert r.status_code in (401, 403)
    assert mock_email["signup_links"] == []
