"""Validate release evidence and network placement before any migration connection."""

import os
import re
import sys


def validate_inputs(environment):
    mode = environment.get("MIGRATION_MODE")
    migrated_sha = environment.get("MIGRATED_SHA", "")
    if mode == "manual":
        if not re.fullmatch(r"[0-9a-f]{40}", migrated_sha) or migrated_sha != environment.get(
            "GITHUB_SHA"
        ):
            raise ValueError(
                "Manual migration requires the exact successfully migrated release SHA."
            )
    elif mode == "runner":
        if migrated_sha:
            raise ValueError("Runner migration must not include a manual migration SHA.")
        network = environment.get("MIGRATION_DATABASE_NETWORK", "private")
        if network not in {"private", "public"}:
            raise ValueError("MIGRATION_DATABASE_NETWORK must be private or public.")
        if network == "private" and environment.get("RUNNER_ENVIRONMENT") != "self-hosted":
            raise ValueError(
                "Private PostgreSQL cannot use the standard GitHub-hosted runner. "
                "Run deploy-upgrade on an authorized private network and select manual mode, "
                "or use a self-hosted runner with verified private DNS/routing."
            )
    else:
        raise ValueError("Select manual or runner migration mode.")


if __name__ == "__main__":
    try:
        validate_inputs(os.environ)
    except ValueError as error:
        sys.exit(str(error))
