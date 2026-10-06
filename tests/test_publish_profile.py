import base64
import io
import json
from unittest.mock import Mock

import pytest

from scripts import check_publish_profile as preflight

PROFILE = (
    '<publishData><publishProfile publishMethod="MSDeploy" '
    'publishUrl="queue.scm.azurewebsites.net:443" msdeploySite="queue" '
    'userName="$queue" userPWD="test-publishing-password" /></publishData>'
)


@pytest.fixture
def scm(monkeypatch):
    opener = Mock()
    monkeypatch.setattr(preflight.urllib.request, "build_opener", lambda *args: opener)

    def respond(settings):
        opener.open.return_value = io.StringIO(json.dumps(settings))
        return opener

    return respond


@pytest.mark.parametrize(
    "endpoint",
    ["queue.scm.azurewebsites.net:443", "https://queue-unique.scm.canadacentral-01.azurewebsites.net"],
)
def test_preflight_uses_profile_over_https(scm, endpoint):
    opener = scm({"SCM_DO_BUILD_DURING_DEPLOYMENT": "true"})
    preflight.check_build_settings(
        PROFILE.replace("queue.scm.azurewebsites.net:443", endpoint), "queue"
    )
    request = opener.open.call_args.args[0]
    assert request.full_url.startswith("https://")
    assert request.full_url.endswith("/api/settings")
    assert opener.open.call_args.kwargs["timeout"] == 30
    encoded = request.get_header("Authorization").removeprefix("Basic ")
    assert base64.b64decode(encoded).decode() == "$queue:test-publishing-password"


@pytest.mark.parametrize(
    "settings",
    [
        {},
        {"SCM_DO_BUILD_DURING_DEPLOYMENT": "false"},
        {"SCM_DO_BUILD_DURING_DEPLOYMENT": "true", "WEBSITE_RUN_FROM_PACKAGE": "1"},
        {"SCM_DO_BUILD_DURING_DEPLOYMENT": "true", "WEBSITE_RUN_FROM_PACKAGE": "https://blob"},
    ],
)
def test_preflight_blocks_unsafe_build_configuration(scm, settings):
    scm(settings)
    with pytest.raises(ValueError):
        preflight.check_build_settings(PROFILE, "queue")


@pytest.mark.parametrize(
    "original,replacement",
    [
        ("queue.scm.azurewebsites.net:443", "http://queue.scm.azurewebsites.net"),
        ("queue.scm.azurewebsites.net:443", "queue.scm.azurewebsites.net.attacker.example"),
        ("queue.scm.azurewebsites.net:443", "queue.azurewebsites.net"),
        ("queue.scm.azurewebsites.net:443", "queue.scm.azurewebsites.net:80"),
        ("queue.scm.azurewebsites.net:443", "queue.scm.azurewebsites.net/path"),
        ('msdeploySite="queue"', 'msdeploySite="other"'),
        ('userName="$queue"', 'userName="$other"'),
    ],
)
def test_preflight_rejects_invalid_profile_before_network(scm, original, replacement):
    opener = scm({})
    with pytest.raises(ValueError):
        preflight.check_build_settings(PROFILE.replace(original, replacement), "queue")
    opener.open.assert_not_called()


def test_preflight_does_not_follow_redirects():
    assert preflight.NoRedirect().redirect_request(
        None, None, 302, "Redirect", {}, "https://attacker.example"
    ) is None


@pytest.mark.parametrize("failure", ["network", "malformed-profile", "missing-profile"])
def test_preflight_errors_do_not_disclose_secrets(monkeypatch, capsys, scm, failure):
    monkeypatch.setenv("APP_NAME", "queue")
    monkeypatch.setenv("AZURE_WEBAPP_PUBLISH_PROFILE", PROFILE)
    if failure == "network":
        scm({}).open.side_effect = OSError("test-publishing-password and private settings")
    elif failure == "malformed-profile":
        monkeypatch.setenv("AZURE_WEBAPP_PUBLISH_PROFILE", "test-publishing-password")
    else:
        monkeypatch.delenv("AZURE_WEBAPP_PUBLISH_PROFILE")
    assert preflight.main() == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "Publish-profile preflight failed; check SCM access and build settings.\n"
    )
