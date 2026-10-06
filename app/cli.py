"""Database connectivity and serialized deployment migrations."""

import click
from alembic import command
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import text

from app.extensions import db
from app.services.deployment import database_failure_message


class DeploymentSafetyError(Exception):
    """Only fixed, nonsecret messages from our deployment safety checks."""


@click.command("check-db")
@with_appcontext
def check_db():
    """Confirm that the configured PostgreSQL database accepts a query."""
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as error:
        raise click.ClickException(database_failure_message(error, connecting=True)) from None
    click.echo("PostgreSQL connection OK.")


@click.command("deploy-upgrade")
@with_appcontext
def deploy_upgrade():
    """Apply transactional migrations once, with a shared deployment lock."""
    connecting = False
    try:
        config = current_app.extensions["migrate"].migrate.get_config()
        heads = set(ScriptDirectory.from_config(config).get_heads())
        if len(heads) != 1:
            raise DeploymentSafetyError("Deployment requires exactly one migration head.")
        connecting = True
        with db.engine.begin() as connection:
            connecting = False
            if not connection.scalar(text("SELECT pg_try_advisory_xact_lock(20261001)")):
                raise DeploymentSafetyError("Another deployment migration is running.")
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '120s'"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            if set(MigrationContext.configure(connection).get_current_heads()) != heads:
                raise DeploymentSafetyError("Database revision does not match the release.")
    except DeploymentSafetyError as error:
        raise click.ClickException(str(error)) from None
    except Exception as error:
        # Connection errors and SQL parameters can contain credentials or student data.
        raise click.ClickException(
            "Migration failed; deployment blocked. "
            + database_failure_message(error, connecting=connecting)
        ) from None
    click.echo("Database upgraded to the release head.")
