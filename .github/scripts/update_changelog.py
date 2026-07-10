from pathlib import Path
import os
import re


CHANGELOG = Path("addons/airsend/CHANGELOG.md")


title = os.environ["PR_TITLE"]


match = re.match(
    r"Bump (.+) from (.+) to (.+)",
    title
)


if match:
    package, old, new = match.groups()

    if "ghcr.io" in package:
        category = "Docker"
    else:
        category = "Python"

    line = (
        f"- ⬆️ {category} : "
        f"`{package}` {old} → {new}"
    )

else:
    line = f"- {title}"


content = CHANGELOG.read_text()


if line in content:
    exit(0)


marker = "### Dependencies"


if marker not in content:

    content = content.replace(
        "## Unreleased",
        "## Unreleased\n\n### Dependencies\n"
    )


content = content.replace(
    marker,
    f"{marker}\n{line}",
    1
)


CHANGELOG.write_text(content)
