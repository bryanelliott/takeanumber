"""Read-only database connectivity check."""

import click
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
