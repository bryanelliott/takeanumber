"""Take A Number application factory."""

from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from app.config import Config, configure_database
from app.extensions import csrf, db, login_manager, migrate


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

    from app.auth import blueprint as auth_blueprint
    from app.auth.rate_limit import init_auth_rate_limit
    from app.auth.services import load_instructor
    from app.instructor import blueprint as instructor_blueprint

    # Count authentication POST attempts even when CSRF rejects the request.
    init_auth_rate_limit(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.user_loader(load_instructor)

    from app.cli import check_db
    from app.health import blueprint

    app.register_blueprint(blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(instructor_blueprint)
    app.cli.add_command(check_db)
    return app
