"""Read alert policy and atomically save the authenticated instructor's preferences."""

from dataclasses import dataclass, fields

from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models import HelpSession, InstructorSetting
from app.realtime import publish_queue_changed


@dataclass(frozen=True)
class AlertPreferences:
    alert_next_enabled: bool = True
    alert_serving_enabled: bool = True
    visual_alert_enabled: bool = True
    sound_alert_enabled: bool = True
    vibration_enabled: bool = True
    advance_warning_count: int = 1

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name == "advance_warning_count":
                if type(value) is not int or not 1 <= value <= 3:
                    raise ValueError("Warning distance must be 1, 2, or 3.")
            elif type(value) is not bool:
                raise ValueError("Alert preferences must be true or false.")

    def permits(self, alert_state):
        if alert_state == "serving":
            return self.alert_serving_enabled
        return self.alert_next_enabled and alert_state in ("next_up", "advance_warning")

    @property
    def policy_key(self):
        return ":".join(str(int(getattr(self, field.name))) for field in fields(self))


def get_preferences(instructor_id):
    row = db.session.scalar(
        db.select(InstructorSetting)
        .where(InstructorSetting.instructor_id == instructor_id)
        .execution_options(populate_existing=True)
    )
    # Read-only fallback for an account provisioned outside the registration service.
    return (
        AlertPreferences(
            **{field.name: getattr(row, field.name) for field in fields(AlertPreferences)}
        )
        if row
        else AlertPreferences()
    )


def save_preferences(instructor_id, preferences):
    """The caller supplies the authenticated actor, never a submitted owner ID."""
    values = {field.name: getattr(preferences, field.name) for field in fields(AlertPreferences)}
    AlertPreferences(**values)
    try:
        statement = insert(InstructorSetting).values(instructor_id=instructor_id, **values)
        db.session.execute(
            statement.on_conflict_do_update(
                constraint="uq_instructor_setting_instructor",
                set_={**values, "updated_at": db.func.clock_timestamp()},
            )
        )
        codes = list(
            db.session.scalars(
                db.select(HelpSession.public_code).where(
                    HelpSession.instructor_id == instructor_id, HelpSession.status == "active"
                )
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    for code in codes:
        publish_queue_changed(code)
