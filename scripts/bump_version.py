#!/usr/bin/env python3
"""Auto-bump version in pyproject.toml based on commit message tags, environment variables, or CLI arguments.

Supported bump types:
- major: 0.1.1b1 -> 1.0.0a0
- minor: 0.1.1b1 -> 0.2.0a0
- micro / patch: 0.1.1b1 -> 0.1.2a0
- release: 0.1.1b1 -> 0.1.1 (strips pre-release label)
- a / alpha: 0.1.1b1 -> 0.1.1a1 (or 0.1.1a1 -> 0.1.1a2)
- b / beta: 0.1.1b1 -> 0.1.1b2 (or 0.1.1 -> 0.1.1b1)
- rc: 0.1.1b1 -> 0.1.1rc1 (or 0.1.1rc1 -> 0.1.1rc2)
- num / build / after-label-number: 0.1.1b1 -> 0.1.1b2 (or 0.1.1 -> 0.1.2a0 if no label)
- skip / none: does not bump version

Commit Message Tag Syntax:
  git commit -m "my commit message [bump:minor]"
  git commit -m "hotfix [bump:micro]"
  git commit -m "prep release [bump:release]"
  git commit -m "docs only [bump:skip]"

Environment Variable:
  BUMP=minor git commit -m "add feature"
"""

import argparse
import os
import re
import sys
from pathlib import Path

PYPROJECT_PATH = Path(__file__).resolve().parent.parent / "pyproject.toml"

# PEP 440 version regex: major.minor.micro[label][num]
VERSION_PATTERN = re.compile(
    r'^(?P<prefix>version\s*=\s*")(?P<major>\d+)\.(?P<minor>\d+)\.(?P<micro>\d+)(?:(?P<label>[a-zA-Z]+)(?P<num>\d+))?(?P<suffix>".*)$',
    re.MULTILINE,
)

TAG_PATTERN = re.compile(
    r"\[bump:(major|minor|micro|patch|release|b|beta|rc|a|alpha|build|num|after-label-number|skip|none)\]",
    re.IGNORECASE,
)


def bump_version(current_version: str, bump_type: str) -> str:
    """Calculate the next version string based on current version and bump type."""
    match = re.match(
        r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<micro>\d+)(?:(?P<label>[a-zA-Z]+)(?P<num>\d+))?$",
        current_version.strip(),
    )
    if not match:
        raise ValueError(f"Unsupported version format: '{current_version}'")

    major = int(match.group("major"))
    minor = int(match.group("minor"))
    micro = int(match.group("micro"))
    label = match.group("label") or ""
    num = int(match.group("num")) if match.group("num") is not None else None

    b_type = bump_type.lower().strip()

    if b_type == "major":
        return f"{major + 1}.0.0a0"
    elif b_type == "minor":
        return f"{major}.{minor + 1}.0a0"
    elif b_type in ("micro", "patch"):
        return f"{major}.{minor}.{micro + 1}a0"
    elif b_type == "release":
        return f"{major}.{minor}.{micro}"
    elif b_type in ("a", "alpha"):
        if label.lower() in ("a", "alpha") and num is not None:
            return f"{major}.{minor}.{micro}a{num + 1}"
        return f"{major}.{minor}.{micro}a1"
    elif b_type in ("b", "beta"):
        if label.lower() in ("b", "beta") and num is not None:
            return f"{major}.{minor}.{micro}b{num + 1}"
        return f"{major}.{minor}.{micro}b1"
    elif b_type == "rc":
        if label.lower() == "rc" and num is not None:
            return f"{major}.{minor}.{micro}rc{num + 1}"
        return f"{major}.{minor}.{micro}rc1"
    elif b_type in ("num", "build", "after-label-number", "default"):
        if label and num is not None:
            return f"{major}.{minor}.{micro}{label}{num + 1}"
        return f"{major}.{minor}.{micro + 1}a0"
    elif b_type in ("skip", "none"):
        return current_version
    else:
        raise ValueError(f"Unknown bump type: '{bump_type}'")


def update_pyproject_version(
    pyproject_path: Path, bump_type: str
) -> tuple[str, str] | None:
    """Update version in pyproject.toml and return (old_version, new_version), or None if skipped."""
    if bump_type.lower() in ("skip", "none"):
        return None

    content = pyproject_path.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(content)
    if not match:
        raise ValueError(f"Could not find valid 'version = ...' in {pyproject_path}")

    major = match.group("major")
    minor = match.group("minor")
    micro = match.group("micro")
    label = match.group("label") or ""
    num = match.group("num") or ""
    old_version = f"{major}.{minor}.{micro}{label}{num}"

    new_version = bump_version(old_version, bump_type)
    if new_version == old_version:
        return None

    replacement = f'\\g<prefix>{new_version}\\g<suffix>'
    new_content = VERSION_PATTERN.sub(replacement, content, count=1)
    pyproject_path.write_text(new_content, encoding="utf-8")
    return old_version, new_version


def resolve_bump_type(commit_msg_file: str | None = None, cli_type: str | None = None) -> str:
    """Determine bump type from CLI, environment, commit message tag, or fallback to default."""
    if cli_type:
        return cli_type

    env_bump = os.environ.get("BUMP") or os.environ.get("GIT_BUMP")
    if env_bump:
        return env_bump

    if commit_msg_file and Path(commit_msg_file).exists():
        try:
            msg = Path(commit_msg_file).read_text(encoding="utf-8")
            tag_match = TAG_PATTERN.search(msg)
            if tag_match:
                return tag_match.group(1).lower()
        except Exception:
            pass

    return "default"


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-bump version in pyproject.toml")
    parser.add_argument(
        "commit_msg_file",
        nargs="?",
        default=None,
        help="Path to git commit message file (passed by git hook)",
    )
    parser.add_argument(
        "commit_source",
        nargs="?",
        default=None,
        help="Git commit source (message, template, merge, squash, etc.)",
    )
    parser.add_argument(
        "--type",
        "-t",
        dest="bump_type",
        default=None,
        help="Explicit bump type (major, minor, micro, patch, release, a, b, rc, num, skip)",
    )
    parser.add_argument(
        "--file",
        dest="pyproject_file",
        default=str(PYPROJECT_PATH),
        help="Path to pyproject.toml file",
    )
    args = parser.parse_args()

    # If this is a merge or squash commit and no explicit tag is passed, skip auto-bumping
    if args.commit_source in ("merge", "squash") and not (
        os.environ.get("BUMP") or os.environ.get("GIT_BUMP") or args.bump_type
    ):
        print(f"[version-bump] Skipping auto-bump for {args.commit_source} commit.")
        return 0

    bump_type = resolve_bump_type(args.commit_msg_file, args.bump_type)
    target_path = Path(args.pyproject_file)

    try:
        result = update_pyproject_version(target_path, bump_type)
        if result:
            old_ver, new_ver = result
            print(f"[version-bump] Updated {target_path.name}: {old_ver} -> {new_ver} (bump:{bump_type})")
        else:
            print(f"[version-bump] No version bump performed (type: {bump_type}).")
    except Exception as e:
        print(f"[version-bump] Error updating version: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
