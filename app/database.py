"""SQL Server connections, clocks, locks and safe driver error inspection."""

import re
import time
from contextvars import ContextVar

import pyodbc
from sqlalchemy import event, func
from sqlalchemy.exc import DBAPIError
from sqlalchemy.types import DateTime

# Must precede the first ODBC connection, including connections outside SQLAlchemy.
pyodbc.pooling = False
connect_attempts = ContextVar("connect_attempts", default=3)
TRANSIENT_CODES = {40197, 40501, 40613, 10928, 10929, 49918, 49919, 49920}


def native_codes(error):
    original = error.orig if isinstance(error, DBAPIError) else error
    # Parse in memory only: ODBC error text can contain credentials and SQL values.
    return {int(code) for arg in original.args for code in re.findall(r"\((\d+)\)", str(arg))}


def unique_violation(error, constraint):
    return bool(native_codes(error) & {2601, 2627}) and any(
        f"'{constraint}'" in str(arg) for arg in error.orig.args
    )


def utc_now():
    return func.sysdatetimeoffset(type_=DateTime(timezone=True))


def configure_engine(engine):
    @event.listens_for(engine, "do_connect")
    def connect(dialect, connection_record, cargs, cparams):
        # Retry opening a connection only. Never replay statements or transactions.
        for attempt in range(connect_attempts.get()):
            try:
                connection = dialect.dbapi.connect(*cargs, **cparams)
                connection.timeout = 30
                return connection
            except pyodbc.Error as error:
                state = error.args[0] if error.args else ""
                transient = bool(native_codes(error) & TRANSIENT_CODES) or state in {
                    "HYT00",
                    "HYT01",
                }
                if not transient or attempt + 1 == connect_attempts.get():
                    raise
                time.sleep(min(2**attempt, 5))

    @event.listens_for(engine, "connect")
    def session_settings(connection, connection_record):
        cursor = connection.cursor()
        try:
            # Required SET options for filtered indexes, on every new connection.
            cursor.execute(
                "SET ANSI_NULLS ON; SET ANSI_PADDING ON; SET ANSI_WARNINGS ON; "
                "SET ARITHABORT ON; SET CONCAT_NULL_YIELDS_NULL ON; "
                "SET QUOTED_IDENTIFIER ON; SET NUMERIC_ROUNDABORT OFF; SET LOCK_TIMEOUT 5000;"
            )
        finally:
            cursor.close()
