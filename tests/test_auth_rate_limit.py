from concurrent.futures import ThreadPoolExecutor

from app.auth.rate_limit import AuthRateLimiter


def test_rate_limit_is_atomic_and_expires():
    now = [0]
    limiter = AuthRateLimiter(3, 60, clock=lambda: now[0])
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: limiter.retry_after("one"), range(10)))
    assert results.count(0) == 3
    assert results.count(60) == 7
    assert limiter.retry_after("two") == 0
    now[0] = 60
    assert limiter.retry_after("one") == 0


def test_rate_limit_fails_closed_when_full():
    limiter = AuthRateLimiter(20, 60)
    limiter.attempts = {str(index): 1 for index in range(10000)}
    assert limiter.retry_after("new-address") > 0
    assert len(limiter.attempts) == 10000


def test_post_limit_covers_login_signup_and_ignores_forwarded_headers(app, client):
    limiter = app.extensions["auth_rate_limiter"]
    limiter.limit = 2
    assert client.post("/auth/login").status_code == 400
    assert client.post("/auth/signup").status_code == 400
    response = client.post("/auth/login", headers={"X-Forwarded-For": "203.0.113.10"})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert client.get("/auth/login").status_code == 200
    assert client.get("/health").status_code == 200
