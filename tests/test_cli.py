import json

from chaindiff.cli import main


def _catalog(tmp_path, releases: list[dict], advisories: list[dict] | None = None) -> None:
    (tmp_path / "clients.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "clients": [
                    {
                        "id": "geth",
                        "name": "Geth",
                        "role": "execution",
                        "github": "ethereum/go-ethereum",
                        "versioning": "semver",
                    }
                ],
            }
        )
    )
    release_dir = tmp_path / "releases"
    release_dir.mkdir()
    (release_dir / "geth.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "client": "geth",
                "github": "ethereum/go-ethereum",
                "fetched_at": "2026-10-01T00:00:00Z",
                "ignored_tag_count": 0,
                "releases": releases,
            }
        )
    )
    if advisories is not None:
        advisory_dir = tmp_path / "advisories"
        advisory_dir.mkdir()
        (advisory_dir / "geth.json").write_text(
            json.dumps({"schema_version": 1, "advisories": advisories})
        )


def _release(tag: str, name: str | None = None) -> dict:
    return {
        "tag": tag,
        "name": name or tag,
        "published_at": "2026-01-01T00:00:00Z",
        "prerelease": "rc" in tag,
        "url": f"https://example.test/{tag}",
    }


def test_check_review_required(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _catalog(tmp_path, [_release("v1.2.0"), _release("v1.2.1")])
    assert main(["check", "--client", "geth", "--from", "v1.2.0"]) == 1
    output = capsys.readouterr().out
    assert "REVIEW REQUIRED" in output
    assert "v1.2.1" in output


def test_check_not_safe_on_major(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _catalog(tmp_path, [_release("v1.9.0"), _release("v2.0.0")])
    assert main(["check", "--client", "Geth", "--from", "1.9.0", "--to", "v2.0.0"]) == 2


def test_plan_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _catalog(
        tmp_path,
        [_release("v1.2.0"), _release("v1.2.1")],
        advisories=[
            {
                "version": "1.2.1",
                "severity": "none",
                "summary": "Patch only.",
                "source": "https://example.test/notes",
            }
        ],
    )
    assert main(["plan", "--client", "geth", "--from", "v1.2.0", "--to", "v1.2.1", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "safe"
    assert payload["steps"]


def test_unknown_client(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _catalog(tmp_path, [_release("v1.2.0")])
    assert main(["versions", "--client", "lodestar"]) == 3
    assert "Unknown client" in capsys.readouterr().err
