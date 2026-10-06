"""Credential-safe diagnostics for operator database commands."""

import socket
import ssl

import psycopg
from sqlalchemy.exc import DBAPIError


def database_failure_category(error, *, connecting):
    """Return a fixed label, never driver text, SQL, parameters, or server details."""
    original = error.orig if isinstance(error, DBAPIError) else error
    state = getattr(original, "sqlstate", None)
    if state == "42501":
        return "database-privileges"
    if state in {"55P03", "57014"}:
        return "migration-timeout"
    if state in {"28000", "28P01"}:
        return "postgres-authentication"
    if isinstance(original, socket.gaierror):
        return "dns-resolution"
    if isinstance(original, (TimeoutError, psycopg.errors.ConnectionTimeout)):
        return "network-timeout"
    if isinstance(original, ssl.SSLError):
        return "tls-verification"

    # libpq connection failures often have no SQLSTATE. Examine only the driver
    # message in memory; neither it nor SQLAlchemy's SQL/parameter wrapper is output.
    if isinstance(original, psycopg.OperationalError) and connecting:
        message = str(original).lower()
        if any(
            part in message
            for part in (
                "could not translate host name",
                "name or service not known",
                "temporary failure in name resolution",
                "getaddrinfo failed",
                "nodename nor servname provided",
            )
        ):
            return "dns-resolution"
        if any(
            part in message
            for part in (
                "certificate verify failed",
                "certificate verification failed",
                "root certificate",
                "sslrootcert",
                "does not match host name",
                "ssl error",
                "tls error",
                "server does not support ssl",
            )
        ):
            return "tls-verification"
        if "permission denied" in message:
            return "database-privileges"
        if "no pg_hba.conf entry" in message:
            return "network-access-policy"
        if any(
            part in message
            for part in (
                "password authentication failed",
                "authentication failed",
                "no password supplied",
                "role is not permitted to log in",
            )
        ):
            return "postgres-authentication"
        if "timeout" in message or "timed out" in message:
            return "network-timeout"
    if connecting or (isinstance(state, str) and state.startswith("08")):
        return "database-connection"
    return "alembic-migration"


FAILURE_GUIDANCE = {
    "dns-resolution": "DNS resolution failed. Check hostname and private DNS/VPN access.",
    "network-timeout": "Database connection timed out. Check routing, firewall and private access.",
    "tls-verification": "TLS verification failed. Check the CA file and canonical server hostname.",
    "postgres-authentication": "PostgreSQL authentication failed. Check migration credentials.",
    "database-privileges": "Insufficient database/schema privileges or migration object ownership.",
    "migration-timeout": "Database lock/statement timeout or cancellation; review before retrying.",
    "network-access-policy": "PostgreSQL rejected network access. Check firewall/access policy.",
    "database-connection": "Database connection failed. Check server availability and network.",
    "alembic-migration": "Alembic revision/migration failed. Check release and database revisions.",
}


def database_failure_message(error, *, connecting):
    category = database_failure_category(error, connecting=connecting)
    return f"[{category}] {FAILURE_GUIDANCE[category]}"
