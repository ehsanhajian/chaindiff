import json
from datetime import datetime, timezone

from chaindiff.cli import main


def _clients() -> dict:
    return {
        "schema_version": 1,
        "clients": [
            {
                "id": "geth",
                "name": "Geth",
                "role": "execution",
                "github": "ethereum/go-ethereum",
                "versioning": "semver",
            },
            {
                "id": "lighthouse",
                "name": "Lighthouse",
                "role": "consensus",
                "github": "sigp/lighthouse",
                "versioning": "semver",
            },
        ],
    }


def _releases(client: str, tags: list[tuple[str, bool]]) -> dict:
    return {
        "schema_version": 1,
        "client": client,
        "github": "example/example",
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ignored_tag_count": 0,
        "releases": [
            {
                "tag": tag,
                "name": tag,
                "published_at": "2026-01-01T00:00:00Z",
                "prerelease": prerelease,
                "url": f"https://example.test/{client}/{tag}",
            }
            for tag, prerelease in tags
        ],
    }


def _advisories(items: list[dict]) -> dict:
    return {"schema_version": 1, "advisories": items}


def _network(*, order: str | None = None, order_summary: str = "No upgrade order is stated for mainnet.") -> dict:
    return {
        "schema_version": 1,
        "id": "ethereum",
        "name": "Ethereum mainnet",
        "upgrade": {
            "name": "Glamsterdam",
            "activation": None,
            "source": "https://example.test/glamsterdam",
            "summary": "Fixture summary.",
            "order": order,
            "order_summary": order_summary,
            "warning": "Fixture warning.",
            "required": {"execution": {}, "consensus": {}},
        },
    }


def _write(
    tmp_path,
    *,
    geth_tags: list[tuple[str, bool]],
    lighthouse_tags: list[tuple[str, bool]],
    geth_advisories: list[dict] | None = None,
    lighthouse_advisories: list[dict] | None = None,
    order: str | None = None,
    order_summary: str = "No upgrade order is stated for mainnet.",
) -> None:
    (tmp_path / "clients.json").write_text(json.dumps(_clients()))
    releases = tmp_path / "releases"
    releases.mkdir()
    (releases / "geth.json").write_text(json.dumps(_releases("geth", geth_tags)))
    (releases / "lighthouse.json").write_text(json.dumps(_releases("lighthouse", lighthouse_tags)))
    advisories = tmp_path / "advisories"
    advisories.mkdir()
    (advisories / "geth.json").write_text(json.dumps(_advisories(geth_advisories or [])))
    (advisories / "lighthouse.json").write_text(json.dumps(_advisories(lighthouse_advisories or [])))
    networks = tmp_path / "networks"
    networks.mkdir()
    (networks / "ethereum.json").write_text(json.dumps(_network(order=order, order_summary=order_summary)))


def _pair(*extra: str) -> list[str]:
    return [
        "check",
        "--execution",
        "geth",
        "--execution-version",
        "1.0.0",
        "--consensus",
        "lighthouse",
        "--consensus-version",
        "2.0.0",
        *extra,
    ]


def _none(version: str) -> dict:
    return {
        "version": version,
        "severity": "none",
        "summary": "Reviewed.",
        "source": "https://example.test/notes",
    }


def test_pair_is_safe_only_when_both_ranges_are_reviewed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _write(
        tmp_path,
        geth_tags=[("v1.0.0", False), ("v1.0.1", False)],
        lighthouse_tags=[("v2.0.0", False), ("v2.0.1", False)],
        geth_advisories=[_none("1.0.1")],
        lighthouse_advisories=[_none("2.0.1")],
    )
    assert main(_pair("--json")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "safe"
    assert payload["execution"]["verdict"] == "safe"
    assert payload["consensus"]["verdict"] == "safe"
    assert payload["order"] is None
    assert "compatibility" not in json.dumps(payload).lower()
    assert any("https://example.test/glamsterdam" in step for step in payload["steps"])


def test_pair_stays_review_when_one_range_is_unreviewed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _write(
        tmp_path,
        geth_tags=[("v1.0.0", False), ("v1.0.1", False)],
        lighthouse_tags=[("v2.0.0", False), ("v2.0.1", False)],
        geth_advisories=[_none("1.0.1")],
    )
    assert main(_pair()) == 1
    output = capsys.readouterr().out
    assert "REVIEW REQUIRED" in output
    assert "No upgrade order is stated for mainnet." in output
    assert "until every release in both ranges has a review" in output
    assert "SAFE" not in output.split("Verdict: ", 1)[1].split("\n", 1)[0]


def test_pair_is_not_safe_when_one_range_is_breaking(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _write(
        tmp_path,
        geth_tags=[("v1.0.0", False), ("v1.0.1", False)],
        lighthouse_tags=[("v2.0.0", False), ("v2.0.1", False)],
        geth_advisories=[
            {
                "version": "1.0.1",
                "severity": "breaking",
                "summary": "A flag was removed.",
                "action": "Drop the flag.",
                "source": "https://example.test/geth",
            }
        ],
        lighthouse_advisories=[_none("2.0.1")],
        order="execution-first",
        order_summary="Upgrade the execution client before the consensus client.",
    )
    assert main(_pair()) == 2
    output = capsys.readouterr().out
    assert "NOT SAFE" in output
    assert "Upgrade the execution client before the consensus client." in output
    assert "Geth: v1.0.1: Drop the flag." in output


def test_pair_refuses_a_prerelease_target(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _write(
        tmp_path,
        geth_tags=[("v1.0.0", False), ("v1.0.1", False)],
        lighthouse_tags=[("v2.0.0", False), ("v2.1.0-rc.0", True)],
        geth_advisories=[_none("1.0.1")],
        lighthouse_advisories=[_none("2.1.0-rc.0")],
    )
    assert main(_pair("--consensus-to", "v2.1.0-rc.0")) == 2
    assert "PRERELEASE" in capsys.readouterr().out


def test_pair_already_current(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _write(
        tmp_path,
        geth_tags=[("v1.0.0", False)],
        lighthouse_tags=[("v2.0.0", False)],
        geth_advisories=[_none("1.0.0")],
        lighthouse_advisories=[_none("2.0.0")],
    )
    assert main(_pair()) == 0
    output = capsys.readouterr().out
    assert "ALREADY CURRENT" in output
    assert "No upgrade to plan." in output


def test_shipped_mainnet_schedule_states_no_order(capsys):
    assert (
        main(
            [
                "check",
                "--execution",
                "geth",
                "--execution-version",
                "1.17.7",
                "--execution-to",
                "1.17.7",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
                "--consensus-to",
                "8.2.3",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "ALREADY CURRENT" in output
    assert "No upgrade order between the execution client and the consensus client is stated for mainnet." in output
    assert "https://blog.ethereum.org/2026/09/17/glamsterdam-testnet-announcement" in output


def test_pair_rejects_an_op_stack_client(capsys):
    assert (
        main(
            [
                "check",
                "--execution",
                "op-reth",
                "--execution-version",
                "2.4.4",
                "--consensus",
                "op-node",
                "--consensus-version",
                "1.19.8",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "does not include op-reth, op-node" in error
    assert "Glamsterdam" not in error
    assert "blog.ethereum.org" not in error


def test_network_check_rejects_an_op_stack_client(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "ethereum",
                "--execution",
                "op-geth",
                "--execution-version",
                "1.101702.2",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "does not include op-geth" in error
    assert "Glamsterdam" not in error


def test_pair_rejects_a_consensus_client_as_execution(capsys):
    assert (
        main(
            [
                "check",
                "--execution",
                "lighthouse",
                "--execution-version",
                "8.2.3",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            ]
        )
        == 3
    )
    assert "consensus client" in capsys.readouterr().err
