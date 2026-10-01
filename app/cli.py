"""Database connectivity and serialized deployment migrations."""

import click
from alembic import command
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db


@click.command("check-db")
@with_appcontext
def check_db():
    """Confirm that the configured PostgreSQL database accepts a query."""
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise click.ClickException("PostgreSQL connection failed.") from None
    click.echo("PostgreSQL connection OK.")


@click.command("deploy-upgrade")
@with_appcontext
def deploy_upgrade():
    """Apply transactional migrations once, with a shared deployment lock."""
    config = current_app.extensions["migrate"].migrate.get_config()
    heads = set(ScriptDirectory.from_config(config).get_heads())
    if len(heads) != 1:
        raise click.ClickException("Deployment requires exactly one migration head.")
    try:
        with db.engine.begin() as connection:
            if not connection.scalar(text("SELECT pg_try_advisory_xact_lock(20261001)")):
                raise click.ClickException("Another deployment migration is running.")
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '120s'"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            if set(MigrationContext.configure(connection).get_current_heads()) != heads:
                raise click.ClickException("Database revision does not match the release.")
    except click.ClickException:
        raise
    except Exception:
        # Connection errors and SQL parameters can contain credentials or student data.
        raise click.ClickException(
            "Migration failed; deployment blocked. Inspect protected database logs."
        ) from None
    click.echo("Database upgraded to the release head.")
