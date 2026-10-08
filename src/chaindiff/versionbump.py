"""Bump the patch version when the catalog gains a stable client tag."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_VERSION_LINE = re.compile(r'(?m)^version = "(\d+\.\d+\.\d+)"\s*$')
_INIT_LINE = re.compile(r'(?m)^__version__ = "(\d+\.\d+\.\d+)"\s*$')
_PATCH = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def stable_tags(releases_dir: Path) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    if not releases_dir.is_dir():
        return found
    for path in sorted(releases_dir.glob("*.json")):
        payload = json.loads(path.read_text())
        tags = {
            str(item.get("tag", ""))
            for item in payload.get("releases", [])
            if item.get("tag") and not item.get("prerelease")
        }
        found[path.stem] = tags
    return found


def new_stable_tags(
    before: dict[str, set[str]],
    after: dict[str, set[str]],
) -> list[tuple[str, str]]:
    fresh: list[tuple[str, str]] = []
    for client in sorted(after):
        added = after[client] - before.get(client, set())
        fresh.extend((client, tag) for tag in sorted(added))
    return fresh


def bump_patch(version: str) -> str:
    matched = _PATCH.fullmatch(version.strip())
    if matched is None:
        raise ValueError(f"{version} is not a major.minor.patch version")
    major, minor, patch = matched.groups()
    return f"{major}.{minor}.{int(patch) + 1}"


def _read_version(text: str, pattern: re.Pattern[str], path: Path) -> str:
    matched = pattern.search(text)
    if matched is None:
        raise ValueError(f"{path} has no major.minor.patch version")
    return matched.group(1)


def bump_project(root: Path) -> str:
    pyproject_path = root / "pyproject.toml"
    init_path = root / "src" / "chaindiff" / "__init__.py"
    pyproject = pyproject_path.read_text()
    init = init_path.read_text()
    current = _read_version(pyproject, _VERSION_LINE, pyproject_path)
    init_version = _read_version(init, _INIT_LINE, init_path)
    if current != init_version:
        raise ValueError(f"pyproject.toml is {current} and __init__.py is {init_version}")
    updated = bump_patch(current)
    pyproject_path.write_text(_VERSION_LINE.sub(f'version = "{updated}"', pyproject, count=1))
    init_path.write_text(_INIT_LINE.sub(f'__version__ = "{updated}"', init, count=1))
    return updated


def release_notes(tags: list[tuple[str, str]], version: str) -> str:
    lines = [
        f"ChainDiff {version} includes new stable client tags.",
        "",
        "New stable releases:",
    ]
    lines.extend(f"- {client} {tag}" for client, tag in tags)
    lines.extend(
        [
            "",
            "These tags are in the catalog. They are not reviewed.",
            "A check that targets one of them stays review required until an advisory is added.",
            "",
        ]
    )
    return "\n".join(lines)


def _releases_dir(root: Path) -> Path:
    return root / "src" / "chaindiff" / "data" / "releases"


def snapshot(root: Path, destination: Path) -> None:
    payload = {client: sorted(tags) for client, tags in stable_tags(_releases_dir(root)).items()}
    destination.write_text(json.dumps(payload))


def _load_snapshot(path: Path) -> dict[str, set[str]]:
    payload = json.loads(path.read_text())
    return {str(client): set(tags) for client, tags in payload.items()}


def bump_if_new(root: Path, before_path: Path, notes_path: Path) -> str | None:
    fresh = new_stable_tags(_load_snapshot(before_path), stable_tags(_releases_dir(root)))
    if not fresh:
        return None
    version = bump_project(root)
    notes = release_notes(fresh, version)
    notes_path.write_text(notes)
    notes_path.with_name("new-version.txt").write_text(version + "\n")
    commit_path = notes_path.with_name("new-stable-commit.txt")
    commit_path.write_text(
        "Refresh the catalog for new stable client releases.\n\n" + notes
    )
    return version


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 3 and args[0] == "snapshot":
        snapshot(Path(args[1]), Path(args[2]))
        return 0
    if len(args) == 4 and args[0] == "bump-if-new":
        try:
            version = bump_if_new(Path(args[1]), Path(args[2]), Path(args[3]))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if version is None:
            print("No new stable client tag.")
        else:
            print(f"Patch version is {version}.")
        return 0
    print(
        "usage: python -m chaindiff.versionbump snapshot ROOT DEST\n"
        "       python -m chaindiff.versionbump bump-if-new ROOT BEFORE NOTES",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
