"""Insert a changelog entry for the current PR into the '## Unreleased'
section of CHANGELOG.md, in the section matching the PR title's
Conventional Commit type.

Dependabot PRs keep their existing "Bump X from Y to Z" formatting and
always land under Dependencies. Human PRs must use a
'type(scope): description' title (enforced by the pr-title-lint
workflow); the type maps to a changelog section:

    feat  -> Added
    fix   -> Fixed
    deps  -> Dependencies
    other -> Changed (chore, docs, refactor, test, ci, perf, style, build)

Entries are tagged with "(#<pr_number>)" so that editing a PR's title
(which re-triggers this script) replaces the old entry instead of
duplicating it.

Section headers carry an icon (e.g. "### 🚀 Added") and are only created
on demand, the first time an entry needs them: an empty "## Unreleased"
block starts with no subsections at all. release.py mirrors this by
stripping any subsection left empty once a version is cut.
"""

from pathlib import Path
import os
import re


CHANGELOG = Path("addons/airsend-hub/CHANGELOG.md")

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


def build_entry(title, pr_number, is_dependabot):
    if is_dependabot:
        match = BUMP_RE.match(title)
        if match:
            package, old, new = match.groups()
            category = "Docker" if "ghcr.io" in package else "Python"
            text = f"⬆️ {category} : `{package}` {old} → {new}"
        else:
            text = title
        return "Dependencies", f"- {text} (#{pr_number})"

    match = CONVENTIONAL_RE.match(title)
    if match:
        commit_type, scope, description = match.groups()
        section = TYPE_TO_SECTION.get(commit_type, "Changed")
        text = f"**{scope}:** {description}" if scope else description
    else:
        section, text = "Changed", title

    return section, f"- {text} (#{pr_number})"


def split_unreleased(content):
    """Return (before, unreleased_block, after), where unreleased_block
    spans from the '## Unreleased' header up to (not including) the next
    '## ' heading."""

    header = "## Unreleased"
    start = content.index(header)
    rest = content[start:]
    next_heading = rest.find("\n## ", len(header))
    if next_heading == -1:
        unreleased_block, after = rest, ""
    else:
        unreleased_block, after = rest[:next_heading], rest[next_heading:]
    return content[:start], unreleased_block, after


def remove_existing_entry(unreleased_block, pr_number):
    marker = f"(#{pr_number})"
    lines = unreleased_block.splitlines(keepends=True)
    return "".join(line for line in lines if marker not in line)


def strip_empty_sections(unreleased_block):
    """Drop any '### ' subsection heading (icon or legacy plain form) that
    has no content line before the next '### ' heading or the end of the
    block. Runs on every invocation so a section emptied by
    remove_existing_entry, or a legacy header predating the icons, never
    lingers in the changelog."""

    lines = unreleased_block.split("\n")
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
        while j < total and not lines[j].startswith("### "):
            if lines[j].strip():
                has_content = True
            j += 1

        if has_content:
            kept.extend(lines[i:j])
        i = j

    return "\n".join(kept)


def section_header(section):
    return f"### {SECTION_ICONS[section]} {section}"


def insert_entry(unreleased_block, section, line):
    marker = section_header(section)
    if marker not in unreleased_block:
        unreleased_block = unreleased_block.rstrip("\n") + f"\n\n{marker}\n"
    return unreleased_block.replace(marker, f"{marker}\n{line}", 1)


def main():
    title = os.environ["PR_TITLE"]
    pr_number = os.environ["PR_NUMBER"]
    pr_author = os.environ.get("PR_AUTHOR", "")
    is_dependabot = pr_author == "dependabot[bot]"

    section, line = build_entry(title, pr_number, is_dependabot)

    content = CHANGELOG.read_text()
    before, unreleased_block, after = split_unreleased(content)

    unreleased_block = remove_existing_entry(unreleased_block, pr_number)
    unreleased_block = strip_empty_sections(unreleased_block)

    if line in unreleased_block:
        return

    unreleased_block = insert_entry(unreleased_block, section, line)

    CHANGELOG.write_text(before + unreleased_block + after)


if __name__ == "__main__":
    main()