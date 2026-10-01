"""Extensions are bound only by create_app."""

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


def init_socketio(app):
    # SocketIO holds its server on the extension object. Keep one per app so
    # factories/tests cannot accidentally broadcast into another app's rooms.
    socketio = SocketIO()
    socketio.init_app(
        app,
        async_mode="threading",
        max_http_buffer_size=4096,
        logger=False,
        engineio_logger=False,
    )
    from app.realtime import connect

    socketio.on_event("connect", connect)
