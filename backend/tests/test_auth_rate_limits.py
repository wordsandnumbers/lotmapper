"""Rate-limit tests for /auth/login and /auth/request-access.

Default conftest disables limiting; these tests opt back in via the
`enable_rate_limits` fixture.
"""


def test_login_ip_limit_returns_429_after_5_attempts(
    client, make_user, enable_rate_limits
):
    """5/minute per IP — 6th attempt should 429."""
    user = make_user(is_active=True, password="hunter22a")

    # Five wrong-password attempts within the window — all 401, not throttled
    for _ in range(5):
        r = client.post(
            "/auth/login", json={"email": user.email, "password": "wrong"}
        )
        assert r.status_code == 401

    # 6th hit (same IP) should be rate-limited
    r = client.post(
        "/auth/login", json={"email": user.email, "password": "wrong"}
    )
    assert r.status_code == 429


def test_login_email_limit_returns_429_at_21st_attempt(
    client, make_user, enable_rate_limits, monkeypatch
):
    """20/hour per email — disable the stricter IP limit to isolate."""
    from app.core.limiter import limiter

    limiter.enabled = False  # only test the email limiter here
    user = make_user(is_active=True, password="hunter22a")

    for i in range(20):
        r = client.post(
            "/auth/login", json={"email": user.email, "password": "wrong"}
        )
        assert r.status_code == 401, f"unexpected at attempt {i}: {r.status_code}"

    r = client.post(
        "/auth/login", json={"email": user.email, "password": "wrong"}
    )
    assert r.status_code == 429


def test_request_access_ip_limit_returns_429_after_3(
    client, enable_rate_limits
):
    """3/hour per IP — 4th request should 429."""
    for i in range(3):
        r = client.post(
            "/auth/request-access", json={"email": f"req-{i}@example.com"}
        )
        assert r.status_code == 200

    r = client.post(
        "/auth/request-access", json={"email": "req-overflow@example.com"}
    )
    assert r.status_code == 429


def test_request_access_email_limit_returns_429_on_second_same_email(
    client, enable_rate_limits
):
    """1/day per email — second request with the same email is throttled.

    Disable IP limiter so we isolate the email check.
    """
    from app.core.limiter import limiter

    limiter.enabled = False

    r1 = client.post(
        "/auth/request-access", json={"email": "same@example.com"}
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/auth/request-access", json={"email": "same@example.com"}
    )
    assert r2.status_code == 429
