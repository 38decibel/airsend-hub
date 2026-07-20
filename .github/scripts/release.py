from pathlib import Path
import re
from datetime import date

from semver import bump


CONFIG = Path(
    "addons/airsend-hub/config.yaml"
)

CHANGELOG = Path(
    "addons/airsend-hub/CHANGELOG.md"
)


def get_version():

    text = CONFIG.read_text()

    m = re.search(
        r'version:\s*"?(.*?)"?$',
        text,
        re.MULTILINE
    )

    return m.group(1)


def set_version(version):

    text = CONFIG.read_text()

    text = re.sub(
        r'version:\s*.*',
        f'version: "{version}"',
        text
    )

    CONFIG.write_text(text)


def detect_level():

    import subprocess

    files = subprocess.check_output(
        [
            "git",
            "diff",
            "HEAD~1",
            "--name-only"
        ],
        text=True
    ).splitlines()


    if any(
        "requirements.txt" in x
        or "Dockerfile" in x
        for x in files
    ):
        return "patch"


    if any(
        x.endswith(".py")
        for x in files
    ):
        return "minor"


    return "patch"



old = get_version()

level = detect_level()

new = bump(
    old,
    level
)


set_version(new)


today = date.today().isoformat()


text = CHANGELOG.read_text()


text = text.replace(
    "## Unreleased",
    f"## {new} - {today}",
    1
)


text = (
    "## Unreleased\n\n"
    "### Added\n\n"
    "### Changed\n\n"
    "### Fixed\n\n"
    "### Dependencies\n\n"
    + text
)


CHANGELOG.write_text(text)


print(new)
