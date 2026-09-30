"""Application models, imported by the factory for migration discovery."""

from app.models.help_session import HelpSession
from app.models.instructor import Instructor

__all__ = ["HelpSession", "Instructor"]
