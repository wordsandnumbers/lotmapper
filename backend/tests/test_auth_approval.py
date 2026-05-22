def test_owner_can_approve_pending_user(
    client, make_user, auth_headers, mock_email, db_session
):
    owner = make_user(role="owner", is_active=True)
    pending = make_user(role="reviewer", is_active=False, password=None)

    r = client.patch(
        f"/auth/users/{pending.id}",
        json={"is_active": True},
        headers=auth_headers(owner),
    )
    assert r.status_code == 200
    db_session.refresh(pending)
    assert pending.is_active is True

    assert len(mock_email["signup_links"]) == 1
    sent = mock_email["signup_links"][0]
    assert sent["recipient"] == pending.email
    assert sent["invited_by"] is None
    assert "/set-password?token=" in sent["link"]


def test_admin_cannot_approve_pending_user(
    client, make_user, auth_headers, mock_email
):
    admin = make_user(role="admin", is_active=True)
    pending = make_user(role="reviewer", is_active=False, password=None)

    r = client.patch(
        f"/auth/users/{pending.id}",
        json={"is_active": True},
        headers=auth_headers(admin),
    )
    assert r.status_code == 403
    assert mock_email["signup_links"] == []


def test_reviewer_cannot_approve_pending_user(
    client, make_user, auth_headers, mock_email
):
    reviewer = make_user(role="reviewer", is_active=True)
    pending = make_user(role="reviewer", is_active=False, password=None)

    r = client.patch(
        f"/auth/users/{pending.id}",
        json={"is_active": True},
        headers=auth_headers(reviewer),
    )
    assert r.status_code == 403
    assert mock_email["signup_links"] == []


def test_approval_with_existing_password_does_not_send_email(
    client, make_user, auth_headers, mock_email, db_session
):
    owner = make_user(role="owner", is_active=True)
    inactive_with_pw = make_user(role="reviewer", is_active=False, password="hunter22a")

    r = client.patch(
        f"/auth/users/{inactive_with_pw.id}",
        json={"is_active": True},
        headers=auth_headers(owner),
    )
    assert r.status_code == 200
    db_session.refresh(inactive_with_pw)
    assert inactive_with_pw.is_active is True
    assert mock_email["signup_links"] == []


def test_admin_can_change_reviewer_to_admin(
    client, make_user, auth_headers, db_session
):
    admin = make_user(role="admin", is_active=True)
    target = make_user(role="reviewer", is_active=True)

    r = client.patch(
        f"/auth/users/{target.id}",
        json={"role": "admin"},
        headers=auth_headers(admin),
    )
    assert r.status_code == 200
    db_session.refresh(target)
    assert target.role == "admin"


def test_owner_can_change_reviewer_to_admin(
    client, make_user, auth_headers, db_session
):
    owner = make_user(role="owner", is_active=True)
    target = make_user(role="reviewer", is_active=True)

    r = client.patch(
        f"/auth/users/{target.id}",
        json={"role": "admin"},
        headers=auth_headers(owner),
    )
    assert r.status_code == 200
    db_session.refresh(target)
    assert target.role == "admin"


def test_admin_cannot_promote_to_owner(client, make_user, auth_headers, db_session):
    admin = make_user(role="admin", is_active=True)
    target = make_user(role="reviewer", is_active=True)

    r = client.patch(
        f"/auth/users/{target.id}",
        json={"role": "owner"},
        headers=auth_headers(admin),
    )
    assert r.status_code == 403
    db_session.refresh(target)
    assert target.role == "reviewer"


def test_admin_cannot_change_owner_role(client, make_user, auth_headers, db_session):
    admin = make_user(role="admin", is_active=True)
    target = make_user(role="owner", is_active=True)

    r = client.patch(
        f"/auth/users/{target.id}",
        json={"role": "reviewer"},
        headers=auth_headers(admin),
    )
    assert r.status_code == 403
    db_session.refresh(target)
    assert target.role == "owner"


def test_owner_can_promote_to_owner(client, make_user, auth_headers, db_session):
    owner = make_user(role="owner", is_active=True)
    target = make_user(role="reviewer", is_active=True)

    r = client.patch(
        f"/auth/users/{target.id}",
        json={"role": "owner"},
        headers=auth_headers(owner),
    )
    assert r.status_code == 200
    db_session.refresh(target)
    assert target.role == "owner"


def test_owner_can_change_another_owner_role(
    client, make_user, auth_headers, db_session
):
    owner = make_user(role="owner", is_active=True)
    target = make_user(role="owner", is_active=True)

    r = client.patch(
        f"/auth/users/{target.id}",
        json={"role": "admin"},
        headers=auth_headers(owner),
    )
    assert r.status_code == 200
    db_session.refresh(target)
    assert target.role == "admin"


def test_reviewer_cannot_change_role(client, make_user, auth_headers):
    reviewer = make_user(role="reviewer", is_active=True)
    target = make_user(role="reviewer", is_active=True)

    r = client.patch(
        f"/auth/users/{target.id}",
        json={"role": "admin"},
        headers=auth_headers(reviewer),
    )
    assert r.status_code == 403
