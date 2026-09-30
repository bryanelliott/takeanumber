"""Public student queue interface; no student authentication."""

from app.queue.routes import blueprint

__all__ = ["blueprint"]
