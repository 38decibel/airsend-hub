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


def strip_empty_sections(block):
    """Drop any '### ' subsection heading in block that has no content
    line before the next '### ' / '## ' heading (or the end of block)."""

    lines = block.split("\n")
    kept = []
    i = 0
    total = len(lines)

    while i < total:
        line = lines[i]
        if not line.startswith("### "):
            kept.append(line)
            i += 1
            continue

        j = i + 1
        has_content = False
        while j < total and not lines[j].startswith("### ") and not lines[j].startswith("## "):
            if lines[j].strip():
                has_content = True
            j += 1

        if has_content:
            kept.extend(lines[i:j])
        i = j

    return "\n".join(kept)


def split_version_block(text, heading):
    """Return (before, block, after) where block spans from heading up to
    (not including) the next '## ' heading, or the end of text."""

    start = text.index(heading)
    rest = text[start:]
    next_heading = rest.find("\n## ", len(heading))
    if next_heading == -1:
        block, after = rest, ""
    else:
        block, after = rest[:next_heading], rest[next_heading:]
    return text[:start], block, after


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


version_heading = f"## {new} - {today}"

text = text.replace(
    "## Unreleased",
    version_heading,
    1
)

before, released_block, after = split_version_block(text, version_heading)
released_block = strip_empty_sections(released_block)
text = before + released_block + after


text = "## Unreleased\n\n" + text


CHANGELOG.write_text(text)


print(new)
