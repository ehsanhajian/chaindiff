import json
from pathlib import Path

import pytest

from chaindiff.versionbump import (
    bump_if_new,
    bump_patch,
    bump_project,
    new_stable_tags,
    snapshot,
    stable_tags,
)


def _catalog(root: Path, releases: dict[str, list[dict]]) -> None:
    directory = root / "src" / "chaindiff" / "data" / "releases"
    directory.mkdir(parents=True, exist_ok=True)
    for client, items in releases.items():
        payload = {"schema_version": 1, "client": client, "releases": items}
        (directory / f"{client}.json").write_text(json.dumps(payload))


def _project(root: Path, version: str = "0.3.0") -> None:
    (root / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n')
    init = root / "src" / "chaindiff" / "__init__.py"
    init.parent.mkdir(parents=True, exist_ok=True)
    init.write_text(f'__version__ = "{version}"\n')


def test_stable_tags_skip_prereleases(tmp_path):
    _catalog(
        tmp_path,
        {
            "geth": [
                {"tag": "v1.17.8", "prerelease": False},
                {"tag": "v1.17.9-rc.1", "prerelease": True},
            ]
        },
    )
    assert stable_tags(tmp_path / "src" / "chaindiff" / "data" / "releases") == {
        "geth": {"v1.17.8"}
    }


def test_new_stable_tags_ignore_an_unchanged_catalog():
    before = {"geth": {"v1.17.7"}}
    after = {"geth": {"v1.17.7", "v1.17.8"}, "lighthouse": {"v8.2.4"}}
    assert new_stable_tags(before, after) == [("geth", "v1.17.8"), ("lighthouse", "v8.2.4")]
    assert new_stable_tags(before, {"geth": {"v1.17.7"}}) == []


def test_bump_patch_increments_the_last_component():
    assert bump_patch("0.3.0") == "0.3.1"
    assert bump_patch("0.3.9") == "0.3.10"
    with pytest.raises(ValueError):
        bump_patch("0.3")


def test_bump_project_keeps_the_two_version_files_together(tmp_path):
    _project(tmp_path, "0.3.1")
    assert bump_project(tmp_path) == "0.3.2"
    assert 'version = "0.3.2"' in (tmp_path / "pyproject.toml").read_text()
    assert '__version__ = "0.3.2"' in (tmp_path / "src/chaindiff/__init__.py").read_text()


def test_bump_if_new_writes_notes_only_for_a_new_stable_tag(tmp_path):
    _project(tmp_path)
    _catalog(tmp_path, {"geth": [{"tag": "v1.17.7", "prerelease": False}]})
    before = tmp_path / "before.json"
    notes = tmp_path / "notes.txt"
    snapshot(tmp_path, before)
    assert bump_if_new(tmp_path, before, notes) is None
    assert not notes.exists()
    assert 'version = "0.3.0"' in (tmp_path / "pyproject.toml").read_text()

    _catalog(
        tmp_path,
        {
            "geth": [
                {"tag": "v1.17.7", "prerelease": False},
                {"tag": "v1.17.8", "prerelease": False},
                {"tag": "v1.17.9-rc.1", "prerelease": True},
            ],
            "lighthouse": [{"tag": "v8.2.4", "prerelease": False}],
        },
    )
    assert bump_if_new(tmp_path, before, notes) == "0.3.1"
    text = notes.read_text()
    assert "geth v1.17.8" in text
    assert "lighthouse v8.2.4" in text
    assert "v1.17.9-rc.1" not in text
    assert "not reviewed" in text
    assert (tmp_path / "new-version.txt").read_text().strip() == "0.3.1"
