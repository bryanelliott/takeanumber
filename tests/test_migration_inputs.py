import pytest

from scripts.check_migration_inputs import validate_inputs

SHA = "a" * 40


@pytest.mark.parametrize("runner", ["github-hosted", "self-hosted"])
def test_manual_migration_needs_only_matching_release_evidence(runner):
    validate_inputs(
        {
            "MIGRATION_MODE": "manual",
            "MIGRATED_SHA": SHA,
            "GITHUB_SHA": SHA,
            "RUNNER_ENVIRONMENT": runner,
        }
    )


@pytest.mark.parametrize("sha", ["", "b" * 40, "main", "a" * 7])
def test_manual_migration_rejects_missing_or_wrong_sha(sha):
    with pytest.raises(ValueError, match="exact successfully migrated release SHA"):
        validate_inputs({"MIGRATION_MODE": "manual", "MIGRATED_SHA": sha, "GITHUB_SHA": SHA})


@pytest.mark.parametrize("network", [None, "private"])
def test_hosted_runner_cannot_attempt_private_database(network):
    env = {"MIGRATION_MODE": "runner", "RUNNER_ENVIRONMENT": "github-hosted"}
    if network:
        env["MIGRATION_DATABASE_NETWORK"] = network
    with pytest.raises(ValueError, match="Private PostgreSQL"):
        validate_inputs(env)


@pytest.mark.parametrize(
    "runner,network",
    [
        ("self-hosted", "private"),
        ("github-hosted", "public"),
        ("self-hosted", "public"),
    ],
)
def test_runner_mode_allows_appropriate_network_placement(runner, network):
    validate_inputs(
        {
            "MIGRATION_MODE": "runner",
            "RUNNER_ENVIRONMENT": runner,
            "MIGRATION_DATABASE_NETWORK": network,
        }
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"MIGRATION_MODE": "unknown"},
        {"MIGRATED_SHA": SHA},
        {"MIGRATION_DATABASE_NETWORK": "unknown"},
    ],
)
def test_invalid_runner_inputs_fail_closed(overrides):
    with pytest.raises(ValueError):
        validate_inputs(
            {
                "MIGRATION_MODE": "runner",
                "RUNNER_ENVIRONMENT": "self-hosted",
                **overrides,
            }
        )
