"""Take A Number application factory."""

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Config, configure_database, validate_production
from app.extensions import csrf, db, init_socketio, login_manager, migrate


def create_app(config=None):
    """Create an independent app; explicit configuration overrides the environment."""
    if os.getenv("APP_ENV") != "production":
        load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config.update(Config.from_environment())
    if config is not None:
        app.config.update(config)

    if not app.config.get("SECRET_KEY"):
        raise ValueError("SECRET_KEY is required.")
    configure_database(app.config)
    validate_production(app.config)

    db.init_app(app)
    migrate.init_app(app, db)

    from app.auth import blueprint as auth_blueprint
    from app.auth.rate_limit import init_auth_rate_limit
    from app.auth.services import load_instructor
    from app.instructor import blueprint as instructor_blueprint
    from app.queue import blueprint as queue_blueprint

    # Count authentication POST attempts even when CSRF rejects the request.
    init_auth_rate_limit(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.user_loader(load_instructor)

    from app.cli import check_db, deploy_upgrade
    from app.health import blueprint

    app.register_blueprint(blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(instructor_blueprint)
    app.register_blueprint(queue_blueprint)
    app.cli.add_command(check_db)
    app.cli.add_command(deploy_upgrade)
    init_socketio(app)
    if app.config["APP_ENV"] == "production":
        # App Service terminates TLS. Trust one scheme header, but never forwarded Host.
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=app.config["PROXY_FIX_X_FOR"],
            x_proto=1,
            x_host=0,
            x_port=0,
            x_prefix=0,
        )
    return app
