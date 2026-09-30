"""Take A Number application factory."""

from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from app.config import Config, configure_database
from app.extensions import csrf, db, migrate


def create_app(config=None):
    """Create an independent app; explicit configuration overrides the environment."""
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config.update(Config.from_environment())
    if config is not None:
        app.config.update(config)

    if not app.config.get("SECRET_KEY"):
        raise ValueError("SECRET_KEY is required.")
    configure_database(app.config)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    from app.cli import check_db
    from app.health import blueprint

    app.register_blueprint(blueprint)
    app.cli.add_command(check_db)
    return app
