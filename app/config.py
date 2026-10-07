"""Environment configuration and database safety checks."""

import os
import re

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.pool import NullPool


class Config:
    TESTING = False
    MAX_CONTENT_LENGTH = 64 * 1024
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "poolclass": NullPool,
        "hide_parameters": True,
        "connect_args": {"timeout": 5},
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
            "APP_ENV": os.getenv("APP_ENV", "development"),
            "TRUSTED_HOSTS": [
                host.strip() for host in os.getenv("TRUSTED_HOSTS", "").split(",") if host.strip()
            ]
            or None,
            "PROXY_FIX_X_FOR": proxy_hops(),
            "SECRET_KEY": os.getenv("SECRET_KEY"),
            "DATABASE_URL": os.getenv("DATABASE_URL"),
            "TEST_DATABASE_URL": os.getenv("TEST_DATABASE_URL"),
            "SESSION_COOKIE_SECURE": secure == "true",
            "AUTH_RATE_LIMIT": positive_integer("AUTH_RATE_LIMIT", 20),
            "AUTH_RATE_WINDOW_SECONDS": positive_integer("AUTH_RATE_WINDOW_SECONDS", 900),
            "STUDENT_COOKIE_MAX_AGE": positive_integer("STUDENT_COOKIE_MAX_AGE", 15552000),
        }


def proxy_hops():
    value = os.getenv("PROXY_FIX_X_FOR", "0")
    if value not in {"0", "1", "2", "3"}:
        raise ValueError("PROXY_FIX_X_FOR must be 0, 1, 2, or 3.")
    return int(value)


def validate_production(config):
    if config["APP_ENV"] not in {"development", "production"}:
        raise ValueError("APP_ENV must be development or production.")
    if config["APP_ENV"] != "production":
        return
    if (
        config["TESTING"]
        or config["DEBUG"]
        or os.getenv("FLASK_DEBUG", "0") not in {"0", "false", "False"}
    ):
        raise ValueError("Production cannot enable testing or debug mode.")
    if not config["SESSION_COOKIE_SECURE"]:
        raise ValueError("Production requires SESSION_COOKIE_SECURE=true.")
    if len(config["SECRET_KEY"]) < 32 or config["SECRET_KEY"].startswith("replace-with-"):
        raise ValueError(
            "Production SECRET_KEY must be a generated secret of at least 32 characters."
        )
    hosts = config["TRUSTED_HOSTS"]
    if not hosts or not all(
        re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host) for host in hosts
    ):
        raise ValueError(
            "Production requires explicit TRUSTED_HOSTS hostnames (no wildcards or URLs)."
        )
    url = config["SQLALCHEMY_DATABASE_URI"]
    if not url.host.endswith(".database.windows.net"):
        raise ValueError("Production DATABASE_URL must use an Azure SQL Database hostname.")
    if (
        url.query.get("Encrypt", "").lower() != "yes"
        or url.query.get("TrustServerCertificate", "").lower() != "no"
    ):
        raise ValueError(
            "Production DATABASE_URL requires Encrypt=yes and TrustServerCertificate=no."
        )


def positive_integer(name, default):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} must be a positive integer.") from None
    if value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def sqlserver_url(value, setting):
    """Validate without including credentials in configuration errors."""
    if not value:
        raise ValueError(f"{setting} is required.")
    try:
        url = make_url(value)
        port = url.port
    except (ArgumentError, TypeError, ValueError):
        raise ValueError(f"{setting} must be a valid SQL Server URL.") from None
    if url.drivername != "mssql+pyodbc":
        raise ValueError(f"{setting} must use SQL Server with pyodbc.")
    if not all((url.host, url.database, url.username, url.password)):
        raise ValueError(f"{setting} must include host, database, username, and password.")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError(f"{setting} has an invalid port.")
    # Disallow DSNs, odbc_connect, host/user/database overrides and alternate authentication.
    if (
        set(url.query) != {"driver", "Encrypt", "TrustServerCertificate"}
        or any(not isinstance(value, str) for value in url.query.values())
        or url.query.get("driver") != "ODBC Driver 18 for SQL Server"
        or url.query.get("Encrypt", "").lower() != "yes"
        or url.query.get("TrustServerCertificate", "").lower() not in {"yes", "no"}
        or any(char in url.host + url.database for char in ";{}")
    ):
        raise ValueError(
            f"{setting} requires Driver 18, Encrypt=yes and TrustServerCertificate=yes/no only."
        )
    return url


def configure_database(config):
    """Select exactly one SQL Server database before initializing any engine."""
    if config.get("SQLALCHEMY_BINDS"):
        raise ValueError("Additional database binds are not supported.")

    setting = "TEST_DATABASE_URL" if config["TESTING"] else "DATABASE_URL"
    url = sqlserver_url(config.get(setting), setting)
    if config["TESTING"]:
        # Only the dedicated local SQL Server and test login/database are permitted.
        if (
            url.host not in {"localhost", "127.0.0.1", "::1"}
            or not url.database.endswith("_test")
            or not url.username.endswith("_test")
        ):
            raise ValueError(
                "TEST_DATABASE_URL requires a loopback host, database and username ending in _test."
            )
        if config.get("DATABASE_URL"):
            development = sqlserver_url(config["DATABASE_URL"], "DATABASE_URL")
            if url.database == development.database:
                raise ValueError("Test and development database names must differ.")

    # A SQLALCHEMY_DATABASE_URI override must not bypass the selection above.
    config["SQLALCHEMY_DATABASE_URI"] = url.update_query_dict({"ConnectRetryCount": "0"})
