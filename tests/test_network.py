import json

import pytest

from chaindiff.catalog import load_network
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


def _schedule(
    *,
    activation: str | None = "2026-12-03T00:00:00Z",
    order: str | None = None,
    required_execution: dict | None = None,
    required_consensus: dict | None = None,
) -> dict:
    return {
        "schema_version": 1,
        "id": "ethereum",
        "name": "Ethereum mainnet",
        "upgrade": {
            "name": "Glamsterdam",
            "activation": activation,
            "source": "https://example.test/glamsterdam",
            "summary": "Fixture summary.",
            "order": order,
            "order_summary": "Fixture order.",
            "warning": "Fixture warning.",
            "required": {
                "execution": {"geth": "1.18.0"} if required_execution is None else required_execution,
                "consensus": {"lighthouse": "8.3.0"} if required_consensus is None else required_consensus,
            },
        },
    }


def _write(tmp_path, schedule: dict) -> None:
    (tmp_path / "clients.json").write_text(json.dumps(_clients()))
    network_dir = tmp_path / "networks"
    network_dir.mkdir()
    (network_dir / "ethereum.json").write_text(json.dumps(schedule))


def _check(*args: str) -> list[str]:
    return ["check", "--network", "ethereum", *args]


def test_mainnet_requirement_is_not_announced(capsys):
    assert (
        main(
            _check(
                "--execution",
                "geth",
                "--execution-version",
                "1.17.7",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            )
        )
        == 1
    )
    output = capsys.readouterr().out
    assert "Ethereum mainnet" in output
    assert "Next upgrade: Glamsterdam" in output
    assert "Mainnet activation: not scheduled" in output
    assert "https://blog.ethereum.org/2026/09/17/glamsterdam-testnet-announcement" in output
    assert "requirement not announced" in output
    assert "No upgrade order" in output
    assert "Sepolia activates at 2026-10-06 13:53:36 UTC" in output
    assert "REVIEW REQUIRED" in output
    assert "SAFE" not in output
    assert "2026-12" not in output
    assert "required 1.17.7" not in output
    assert "required 8.2.3" not in output


def test_mainnet_prerelease_is_refused(capsys):
    assert (
        main(
            _check(
                "--execution",
                "geth",
                "--execution-version",
                "1.17.7",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.3.0-rc.0",
            )
        )
        == 2
    )
    output = capsys.readouterr().out
    assert "PRERELEASE" in output
    assert "8.3.0-rc.0" in output
    assert "Don't run it on a mainnet node." in output


def test_unknown_network(capsys):
    assert main(["check", "--network", "gnosis", "--execution", "geth", "--execution-version", "1.17.7", "--consensus", "lighthouse", "--consensus-version", "8.2.3"]) == 3
    assert "Unknown network" in capsys.readouterr().err


def test_network_rejects_client_flags(capsys):
    assert main(["check", "--network", "ethereum", "--client", "geth", "--from", "1.17.7"]) == 3
    assert "--client" in capsys.readouterr().err


def test_network_needs_both_clients(capsys):
    assert main(["check", "--network", "ethereum", "--execution", "geth", "--execution-version", "1.17.7"]) == 3
    assert "--consensus" in capsys.readouterr().err


def test_consensus_client_cannot_be_execution(capsys):
    assert (
        main(
            _check(
                "--execution",
                "lighthouse",
                "--execution-version",
                "8.2.3",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            )
        )
        == 3
    )
    assert "consensus client" in capsys.readouterr().err


def test_below_announced_requirement_is_not_safe(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _write(tmp_path, _schedule(order="execution-first"))
    assert (
        main(
            _check(
                "--execution",
                "geth",
                "--execution-version",
                "1.17.7",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.3.0",
                "--json",
            )
        )
        == 2
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "unsafe"
    assert payload["execution"]["status"] == "below"
    assert payload["consensus"]["status"] == "exact"
    assert payload["order"] == "execution-first"
    assert any("before" in step and "Geth" in step for step in payload["steps"])


def test_exact_announced_versions_are_current(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _write(tmp_path, _schedule())
    assert (
        main(
            _check(
                "--execution",
                "geth",
                "--execution-version",
                "v1.18.0",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.3.0",
            )
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "ALREADY CURRENT" in output
    assert "is the announced requirement" in output


def test_newer_than_announced_stays_review(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _write(tmp_path, _schedule())
    assert (
        main(
            _check(
                "--execution",
                "geth",
                "--execution-version",
                "1.18.1",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.3.0",
            )
        )
        == 1
    )
    assert "newer than the announced requirement" in capsys.readouterr().out


def test_matching_versions_without_activation_stay_review(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _write(tmp_path, _schedule(activation=None))
    assert (
        main(
            _check(
                "--execution",
                "geth",
                "--execution-version",
                "1.18.0",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.3.0",
            )
        )
        == 1
    )
    assert "not scheduled" in capsys.readouterr().out


def test_schedule_rejects_a_short_requirement(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _write(tmp_path, _schedule(required_execution={"geth": "1.18"}))
    with pytest.raises(ValueError, match="major.minor.patch"):
        load_network("ethereum")


def test_schedule_rejects_a_testnet_client_in_the_wrong_role(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _write(tmp_path, _schedule(required_execution={"lighthouse": "8.3.0"}))
    with pytest.raises(ValueError, match="not an execution client"):
        load_network("ethereum")
