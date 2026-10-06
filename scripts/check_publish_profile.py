"""Read the SCM build settings with app-scoped publishing credentials, without Azure CLI."""

import base64
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward publishing credentials to a redirected endpoint.
        return None


def check_build_settings(profile_xml, app_name):
    profiles = ET.fromstring(profile_xml).findall("publishProfile")
    profile = next(p for p in profiles if p.get("publishMethod") in {"MSDeploy", "ZipDeploy"})
    endpoint = profile.attrib["publishUrl"]
    url = urlsplit(endpoint if "://" in endpoint else "https://" + endpoint)
    # App Service hostnames may include a generated suffix and region. Bind the
    # credential to the configured app as well as requiring a public Azure SCM host.
    if (
        not app_name
        or profile.get("msdeploySite", app_name).lower() != app_name.lower()
        or profile.attrib["userName"].lower() != "$" + app_name.lower()
        or url.scheme != "https"
        or ".scm." not in (url.hostname or "")
        or not (url.hostname or "").endswith(".azurewebsites.net")
        or url.port not in {None, 443}
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise ValueError("Unexpected publish profile target.")
    credentials = f"{profile.attrib['userName']}:{profile.attrib['userPWD']}"
    token = base64.b64encode(credentials.encode()).decode("ascii")
    request = urllib.request.Request(
        f"https://{url.hostname}/api/settings",
        headers={"Authorization": f"Basic {token}"},
    )
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
        settings = json.load(response)
    if str(settings.get("SCM_DO_BUILD_DURING_DEPLOYMENT", "")).lower() != "true":
        raise ValueError("Build automation must be enabled.")
    if str(settings.get("WEBSITE_RUN_FROM_PACKAGE", "")).lower() not in {"", "0", "false"}:
        raise ValueError("Run-from-package must be disabled for the source build.")


def main():
    try:
        check_build_settings(os.environ["AZURE_WEBAPP_PUBLISH_PROFILE"], os.environ["APP_NAME"])
    except Exception:
        # XML, HTTP errors, headers and settings may contain secrets. Never print them.
        print(
            "Publish-profile preflight failed; check SCM access and build settings.",
            file=sys.stderr,
        )
        return 1
    print("Publish-profile access and source-build settings verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
