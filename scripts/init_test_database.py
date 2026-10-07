"""Provision ONLY a disposable loopback SQL Server test database and test login.

Creates no application tables: pytest applies Alembic. Never used in production.
"""

import os
import re
import sys

import pyodbc
from sqlalchemy.engine import make_url


def provision():
    url = make_url(os.environ["TEST_DATABASE_URL"])
    if (
        url.drivername != "mssql+pyodbc"
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or not re.fullmatch(r"[a-zA-Z0-9_]+_test", url.database or "")
        or not re.fullmatch(r"[a-zA-Z0-9_]+_test", url.username or "")
        or not url.password
        or set(url.query) != {"driver", "Encrypt", "TrustServerCertificate"}
        or url.query["driver"] != "ODBC Driver 18 for SQL Server"
    ):
        raise ValueError("Only a dedicated loopback SQL Server test target is allowed.")
    admin = os.environ["TEST_SQL_ADMIN_PASSWORD"].replace("}", "}}")
    pyodbc.pooling = False
    connect = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={url.host},{url.port or 1433};"
        f"DATABASE=master;UID=sa;PWD={{{admin}}};Encrypt=yes;TrustServerCertificate=yes"
    )
    connection = pyodbc.connect(connect, autocommit=True, timeout=5)
    try:
        cursor = connection.cursor()
        database, user = url.database, url.username
        password = url.password.replace("'", "''")
        if not cursor.execute("SELECT DB_ID(?)", database).fetchval():
            cursor.execute(f"CREATE DATABASE [{database}]")
            cursor.execute(f"ALTER DATABASE [{database}] SET READ_COMMITTED_SNAPSHOT ON")
        if not cursor.execute("SELECT SUSER_ID(?)", user).fetchval():
            cursor.execute(f"CREATE LOGIN [{user}] WITH PASSWORD=N'{password}', CHECK_POLICY=OFF")
        cursor.execute(f"USE [{database}]")
        if not cursor.execute("SELECT USER_ID(?)", user).fetchval():
            cursor.execute(f"CREATE USER [{user}] FOR LOGIN [{user}] WITH DEFAULT_SCHEMA=dbo")
        cursor.execute(f"GRANT CONNECT, CREATE TABLE TO [{user}]")
        cursor.execute(f"GRANT CONTROL ON SCHEMA::dbo TO [{user}]")
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        provision()
    except Exception:
        sys.exit("Test SQL Server provisioning failed; details suppressed to protect credentials.")
    print("Dedicated SQL Server test database ready.")
