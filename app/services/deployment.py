"""Fixed, credential-safe diagnostic categories for SQL Server operator commands."""

import socket
import ssl

from sqlalchemy.exc import DBAPIError

from app.database import native_codes


def database_failure_category(error, *, connecting):
    original = error.orig if isinstance(error, DBAPIError) else error
    codes = native_codes(error)
    state = original.args[0] if original.args else ""
    if codes & {229, 230, 262, 2760, 15151}:
        return "database-privileges"
    if codes & {18456, 18452, 4060} or state == "28000":
        return "database-authentication"
    if codes & {1222, 1205}:
        return "migration-timeout"
    if isinstance(original, socket.gaierror) or codes & {11001, 11004}:
        return "dns-resolution"
    if isinstance(original, ssl.SSLError):
        return "tls-verification"
    # ODBC connection errors do not always carry distinct SQLSTATEs. Inspect in
    # memory only, never output driver text or SQLAlchemy SQL/parameter wrappers.
    message = " ".join(str(arg) for arg in original.args).lower()
    if connecting and any(
        word in message
        for word in (
            "certificate",
            "ssl provider",
            "tls",
            "hostname mismatch",
        )
    ):
        return "tls-verification"
    if isinstance(original, TimeoutError) or state in {"HYT00", "HYT01"}:
        return "network-timeout" if connecting else "migration-timeout"
    if connecting or state in {"08S01", "08001", "08003"}:
        return "database-connection"
    return "alembic-migration"


FAILURE_GUIDANCE = {
    "dns-resolution": "DNS resolution failed. Check the SQL Server hostname.",
    "network-timeout": "Connection timed out. Check firewall/routing or serverless resume.",
    "tls-verification": "TLS verification failed. Check trusted roots and server hostname.",
    "database-authentication": "SQL authentication failed. Check application user and database.",
    "database-privileges": "Insufficient database/schema privileges for the application user.",
    "migration-timeout": "Database lock/query timeout or deadlock; startup blocked.",
    "database-connection": "Connection failed. Check driver, database availability and network.",
    "alembic-migration": "Alembic revision/migration failed. Check release and database revisions.",
}


def database_failure_message(error, *, connecting):
    category = database_failure_category(error, connecting=connecting)
    return f"[{category}] {FAILURE_GUIDANCE[category]}"
