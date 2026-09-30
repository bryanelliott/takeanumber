"""Process liveness, independent of database availability."""

from app.health import blueprint


@blueprint.get("/health")
def health():
    return {"status": "ok"}
