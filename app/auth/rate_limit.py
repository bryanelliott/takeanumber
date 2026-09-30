"""Bounded, thread-safe per-address throttling for the initial single process."""

from math import ceil
from threading import Lock
from time import monotonic

from flask import render_template, request


class AuthRateLimiter:
    def __init__(self, limit, window, clock=monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self.started_at = clock()
        self.attempts = {}
        self.lock = Lock()

    def retry_after(self, address):
        with self.lock:
            now = self.clock()
            if now - self.started_at >= self.window:
                self.attempts.clear()
                self.started_at = now
            count = self.attempts.get(address, 0)
            # Fail closed for new addresses at capacity instead of evicting limits.
            if count >= self.limit or (
                address not in self.attempts and len(self.attempts) >= 10000
            ):
                return max(1, ceil(self.window - (now - self.started_at)))
            self.attempts[address] = count + 1
            return 0


def init_auth_rate_limit(app):
    limiter = AuthRateLimiter(app.config["AUTH_RATE_LIMIT"], app.config["AUTH_RATE_WINDOW_SECONDS"])
    app.extensions["auth_rate_limiter"] = limiter

    @app.before_request
    def protect_authentication():
        if request.method == "POST" and request.endpoint in {"auth.login", "auth.signup"}:
            # Do not trust client-supplied forwarding headers without a trusted proxy setup.
            retry = limiter.retry_after(request.remote_addr or "unknown")
            if retry:
                return render_template("auth/rate_limited.html"), 429, {"Retry-After": str(retry)}
