"""Local single-process Socket.IO server; production deployment is separate."""

import argparse

from app import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    app = create_app()
    app.extensions["socketio"].run(
        app,
        host=args.host,
        port=args.port,
        debug=args.debug,
        allow_unsafe_werkzeug=True,  # explicitly a local development entry point
    )


if __name__ == "__main__":
    main()
