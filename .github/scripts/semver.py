def bump(version, level):

    major, minor, patch = map(
        int,
        version.split(".")
    )

    if level == "major":
        return f"{major+1}.0.0"

    if level == "minor":
        return f"{major}.{minor+1}.0"

    return f"{major}.{minor}.{patch+1}"
  
