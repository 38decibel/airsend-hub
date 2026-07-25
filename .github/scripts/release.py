from pathlib import Path
import re
import subprocess
from datetime import date

from semver import bump


CONFIG = Path(
    "config.yaml"
)

CHANGELOG = Path(
    "CHANGELOG.md"
)

RELEASE_NOTES = Path(
    "/tmp/release_notes.md"
)

SEPARATOR = "---"

DEFAULT_ENTRY = "_No description provided for this release._"

TYPE_TO_SECTION = {
    "feat": "Added",
    "fix": "Fixed",
    "deps": "Dependencies",
}

SECTION_ICONS = {
    "Added": "🚀",
    "Changed": "♻️",
    "Fixed": "🐛",
    "Dependencies": "📦",
}

CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|deps|chore|docs|refactor|test|ci|perf|style|build)"
    r"(?:\(([^)]+)\))?!?:\s*(.+)$"
)

BUMP_RE = re.compile(r"^Bump (.+) from (.+) to (.+)$")

PR_SUFFIX_RE = re.compile(r"^(.*)\s\(#(\d+)\)$")

DEPENDABOT_AUTHOR = "dependabot[bot]"


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


def get_last_commit():
    """Return (subject, author_name) for the commit that triggered this
    release -- the squash-merge commit that GitHub just pushed to
    main."""

    subject = subprocess.check_output(
        ["git", "log", "-1", "--pretty=%s"],
        text=True,
    ).strip()

    author = subprocess.check_output(
        ["git", "log", "-1", "--pretty=%an"],
        text=True,
    ).strip()

    return subject, author


def section_header(section):
    return f"### {SECTION_ICONS[section]} {section}"


def build_entry(subject, author):
    """Categorize the triggering commit the same way a PR title used to
    be categorized, and return (section, changelog_line)."""

    is_dependabot = author == DEPENDABOT_AUTHOR

    match = PR_SUFFIX_RE.match(subject)
    title, pr_number = match.groups() if match else (subject, None)
    suffix = f" (#{pr_number})" if pr_number else ""

    if is_dependabot:
        bump_match = BUMP_RE.match(title)
        if bump_match:
            package, old, new = bump_match.groups()
            category = "Docker" if "ghcr.io" in package else "Python"
            text = f"⬆️ {category} : `{package}` {old} → {new}"
        else:
            text = title
        return "Dependencies", f"- {text}{suffix}"

    conv_match = CONVENTIONAL_RE.match(title)
    if conv_match:
        commit_type, scope, description = conv_match.groups()
        section = TYPE_TO_SECTION.get(commit_type, "Changed")
        text = f"**{scope}:** {description}" if scope else description
    else:
        section, text = "Changed", title

    return section, f"- {text}{suffix}"


def build_body(subject, author):
    if not subject.strip():
        return DEFAULT_ENTRY

    section, line = build_entry(subject, author)
    return f"{section_header(section)}\n{line}\n"


def detect_level():

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


subject, author = get_last_commit()
body = build_body(subject, author)

version_heading = f"## {new} - {today}"

existing = CHANGELOG.read_text() if CHANGELOG.exists() else ""

new_block = f"{SEPARATOR}\n\n{version_heading}\n\n{body}\n"

CHANGELOG.write_text(new_block + existing)


RELEASE_NOTES.write_text(body + "\n")


print(new)
