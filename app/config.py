"""Environment configuration and database safety checks."""

import os

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Config:
    TESTING = False
    MAX_CONTENT_LENGTH = 64 * 1024
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "connect_args": {"connect_timeout": 5},
    }
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    @staticmethod
    def from_environment():
        # Read at factory invocation, not import time, so app instances are independent.
        secure = os.getenv("SESSION_COOKIE_SECURE", "false").lower()
        if secure not in {"true", "false"}:
            raise ValueError("SESSION_COOKIE_SECURE must be true or false.")
        return {
            "SECRET_KEY": os.getenv("SECRET_KEY"),
            "DATABASE_URL": os.getenv("DATABASE_URL"),
            "TEST_DATABASE_URL": os.getenv("TEST_DATABASE_URL"),
            "SESSION_COOKIE_SECURE": secure == "true",
            "AUTH_RATE_LIMIT": positive_integer("AUTH_RATE_LIMIT", 20),
            "AUTH_RATE_WINDOW_SECONDS": positive_integer("AUTH_RATE_WINDOW_SECONDS", 900),
            "STUDENT_COOKIE_MAX_AGE": positive_integer("STUDENT_COOKIE_MAX_AGE", 15552000),
        }


def positive_integer(name, default):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} must be a positive integer.") from None
    if value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def postgres_url(value, setting):
    """Validate without including credentials in configuration errors."""
    if not value:
        raise ValueError(f"{setting} is required.")
    try:
        url = make_url(value)
        port = url.port
    except (ArgumentError, TypeError, ValueError):
        raise ValueError(f"{setting} must be a valid PostgreSQL URL.") from None
    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise ValueError(f"{setting} must use PostgreSQL with psycopg.")
    if not all((url.host, url.database, url.username, url.password)):
        raise ValueError(f"{setting} must include host, database, username, and password.")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError(f"{setting} has an invalid port.")
    return url.set(drivername="postgresql+psycopg")


def configure_database(config):
    """Select exactly one PostgreSQL database before initializing any engine."""
    if config.get("SQLALCHEMY_BINDS"):
        raise ValueError("Additional database binds are not supported.")

    setting = "TEST_DATABASE_URL" if config["TESTING"] else "DATABASE_URL"
    url = postgres_url(config.get(setting), setting)
    if config["TESTING"]:
        # Query parameters could redirect libpq to a different host/database/service.
        if (
            url.host not in {"localhost", "127.0.0.1", "::1"}
            or not url.database.endswith("_test")
            or not url.username.endswith("_test")
            or url.query
        ):
            raise ValueError(
                "TEST_DATABASE_URL requires a loopback host, database and username "
                "ending in _test, and no query parameters."
            )
        if config.get("DATABASE_URL"):
            development = postgres_url(config["DATABASE_URL"], "DATABASE_URL")
            if url.database == development.database:
                raise ValueError("Test and development database names must differ.")

    # A SQLALCHEMY_DATABASE_URI override must not bypass the selection above.
    config["SQLALCHEMY_DATABASE_URI"] = url
