from app.models.user import User


def test_request_access_creates_pending_user(client, db_session, mock_email):
    r = client.post("/auth/request-access", json={"email": "new@example.com"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

    user = db_session.query(User).filter(User.email == "new@example.com").one()
    assert user.password_hash is None
    assert user.is_active is False
    assert user.role == "reviewer"


def test_request_access_notifies_owners(client, make_user, mock_email):
    owner = make_user(role="owner", is_active=True)
    r = client.post("/auth/request-access", json={"email": "new@example.com"})
    assert r.status_code == 200

    assert len(mock_email["notifications"]) == 1
    requester_email, owner_emails = mock_email["notifications"][0]
    assert requester_email == "new@example.com"
    assert owner_emails == [owner.email]


def test_request_access_notifies_only_owners(client, make_user, mock_email):
    owner1 = make_user(role="owner", is_active=True)
    owner2 = make_user(role="owner", is_active=True)
    make_user(role="admin", is_active=True)
    make_user(role="reviewer", is_active=True)

    r = client.post("/auth/request-access", json={"email": "new@example.com"})
    assert r.status_code == 200

    assert len(mock_email["notifications"]) == 1
    _, owner_emails = mock_email["notifications"][0]
    assert set(owner_emails) == {owner1.email, owner2.email}


def test_request_access_duplicate_email_no_enumeration(
    client, db_session, make_user, mock_email
):
    make_user(role="owner", is_active=True)
    email = "dupe@example.com"

    r1 = client.post("/auth/request-access", json={"email": email})
    r2 = client.post("/auth/request-access", json={"email": email})

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json() == {"status": "ok"}

    rows = db_session.query(User).filter(User.email == email).all()
    assert len(rows) == 1
    assert len(mock_email["notifications"]) == 1


def test_request_access_duplicate_active_user_no_enumeration(
    client, db_session, make_user, mock_email
):
    make_user(role="owner", is_active=True)
    existing = make_user(email="active@example.com", role="reviewer", is_active=True)
    original_hash = existing.password_hash

    r = client.post("/auth/request-access", json={"email": existing.email})
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

    assert mock_email["notifications"] == []
    db_session.refresh(existing)
    assert existing.password_hash == original_hash
    assert existing.is_active is True
