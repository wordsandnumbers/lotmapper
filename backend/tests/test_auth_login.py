def test_login_pending_user_returns_401(client, make_user):
    user = make_user(is_active=False, password=None)

    r = client.post(
        "/auth/login",
        json={"email": user.email, "password": "anything-here"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect email or password"


def test_login_active_user_succeeds(client, make_user):
    user = make_user(is_active=True, password="hunter22a")

    r = client.post(
        "/auth/login",
        json={"email": user.email, "password": "hunter22a"},
    )
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    assert r.json()["access_token"]
