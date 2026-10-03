import json
from pathlib import Path

import pytest

from chaindiff.catalog import load_flag_rules
from chaindiff.cli import main
from chaindiff.configparse import parse_cli, parse_config, parse_json, parse_toml, parse_yaml


def _rules() -> list[dict]:
    return [
        {
            "version": "1.17.4",
            "flag": "txlookuplimit",
            "effect": "removed",
            "action": "Drop the flag.",
            "source": "https://example.test/removed",
        },
        {
            "version": "1.17.4",
            "flag": "miner.etherbase",
            "effect": "renamed",
            "replacement": "miner.pending.feeRecipient",
            "action": "Use the new key.",
            "source": "https://example.test/renamed",
        },
        {
            "version": "1.17.2",
            "flag": "libp2p-addresses",
            "effect": "deprecated",
            "replacement": "boot-nodes",
            "action": "Use --boot-nodes.",
            "source": "https://example.test/deprecated",
        },
        {
            "version": "1.17.5",
            "flag": "gogc",
            "effect": "default",
            "action": "Pass --gogc=20 to keep the old behavior.",
            "source": "https://example.test/default",
        },
    ]


def _catalog(tmp_path: Path) -> None:
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
    flags = tmp_path / "flags"
    flags.mkdir()
    (flags / "geth.json").write_text(json.dumps({"schema_version": 1, "rules": _rules()}))


def test_cli_toml_json_and_yaml_parse_the_same_keys(tmp_path: Path):
    cli = tmp_path / "geth.flags"
    cli.write_text(
        "\n".join(
            [
                "# mainnet",
                "/usr/bin/geth \\",
                "  --http \\",
                "  --http.port 8545 \\",
                '  --authrpc.jwtsecret "/secrets/jwt file" \\',
                "  --txlookuplimit=2350000",
                "",
            ]
        )
    )
    toml = tmp_path / "geth.toml"
    toml.write_text('[Node]\nHTTPPort = 8545\nDataDir = "/data"\n')
    payload = {"JsonRpc": {"Enabled": True, "Port": 8545}}
    json_path = tmp_path / "nethermind.json"
    json_path.write_text(json.dumps(payload))
    yaml_path = tmp_path / "prysm.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "datadir: /var/lib/prysm",
                "http-web3provider: http://127.0.0.1:8551",
                "p2p:",
                "  max-peers: 50",
                "bootnodes:",
                "  - enode://a",
                "  - enode://b",
                "",
            ]
        )
    )

    flags = {item.flag: item.value for item in parse_cli(cli.read_text())}
    assert flags["http"] == ""
    assert flags["http.port"] == "8545"
    assert flags["authrpc.jwtsecret"] == "/secrets/jwt file"
    assert flags["txlookuplimit"] == "2350000"

    toml_flags = {item.flag: item.value for item in parse_toml(toml.read_text())}
    assert toml_flags == {"Node.HTTPPort": "8545", "Node.DataDir": "/data"}

    json_flags = {item.flag: item.value for item in parse_json(json_path.read_text())}
    assert json_flags == {"JsonRpc.Enabled": "true", "JsonRpc.Port": "8545"}

    yaml_flags = {item.flag: item.value for item in parse_yaml(yaml_path.read_text())}
    assert yaml_flags["datadir"] == "/var/lib/prysm"
    assert yaml_flags["http-web3provider"] == "http://127.0.0.1:8551"
    assert yaml_flags["p2p.max-peers"] == "50"
    assert yaml_flags["bootnodes"] == "enode://a, enode://b"

    detected, _ = parse_config(cli)
    assert detected == "cli"
    detected, _ = parse_config(toml)
    assert detected == "toml"
    detected, _ = parse_config(json_path)
    assert detected == "json"
    detected, _ = parse_config(yaml_path)
    assert detected == "yaml"


def test_scan_reports_each_effect_and_leaves_the_file_unchanged(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _catalog(tmp_path)
    config = tmp_path / "node.flags"
    config.write_text(
        "\n".join(
            [
                "--txlookuplimit 2350000",
                "--miner.etherbase 0xabc",
                "--libp2p-addresses enode://a",
                "--datadir /data",
                "",
            ]
        )
    )
    before = config.read_bytes()
    code = main(
        ["scan", "--client", "geth", "--from", "v1.17.0", "--to", "v1.17.7", "--config", str(config)]
    )
    assert config.read_bytes() == before
    assert code == 2
    output = capsys.readouterr().out
    assert "NOT SAFE" in output
    assert "Drop the flag." in output
    assert "miner.pending.feeRecipient" in output
    assert "Use --boot-nodes." in output
    assert "gogc" in output
    assert "does not cover" in output
    assert "--datadir" not in output
    assert "datadir" in output


def test_explicit_value_hides_a_default_change(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _catalog(tmp_path)
    config = tmp_path / "node.flags"
    config.write_text("--gogc 20\n--boot-nodes enode://a\n")
    assert main(["scan", "--client", "geth", "--from", "1.17.0", "--to", "1.17.7", "--config", str(config)]) == 0
    output = capsys.readouterr().out
    assert "SAFE" in output
    assert "gogc" not in output


def test_a_change_before_the_installed_version_is_not_a_finding(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _catalog(tmp_path)
    config = tmp_path / "node.flags"
    config.write_text("--txlookuplimit 1\n")
    assert main(["scan", "--client", "geth", "--from", "1.17.4", "--to", "1.17.7", "--config", str(config)]) == 1
    output = capsys.readouterr().out
    assert "REVIEW REQUIRED" in output
    assert "Removed" not in output
    assert "gogc" in output
    assert "does not cover" not in output


def test_scan_json_and_rejects_a_downgrade(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _catalog(tmp_path)
    config = tmp_path / "node.json"
    config.write_text('{"txlookuplimit": 1, "datadir": "/data"}\n')
    assert (
        main(
            [
                "scan",
                "--client",
                "geth",
                "--from",
                "1.17.0",
                "--to",
                "1.17.4",
                "--config",
                str(config),
                "--json",
            ]
        )
        == 2
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["format"] == "json"
    assert payload["findings"][0]["effect"] == "removed"
    assert payload["uncovered"][0]["flag"] == "datadir"
    assert main(["scan", "--client", "geth", "--from", "1.17.7", "--to", "1.17.0", "--config", str(config)]) == 3


def test_bad_config_and_bad_rule_fail(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _catalog(tmp_path)
    config = tmp_path / "broken.json"
    config.write_text("{")
    assert main(["scan", "--client", "geth", "--from", "1.17.0", "--to", "1.17.1", "--config", str(config)]) == 3
    assert "JSON" in capsys.readouterr().err
    rules = json.loads((tmp_path / "flags" / "geth.json").read_text())
    rules["rules"] = [
        {
            "version": "1.17.4",
            "flag": "old",
            "effect": "renamed",
            "action": "Rename it.",
            "source": "https://example.test/rule",
        }
    ]
    (tmp_path / "flags" / "geth.json").write_text(json.dumps(rules))
    with pytest.raises(ValueError, match="replacement"):
        load_flag_rules("geth")


def test_stale_latest_cannot_be_safe(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _catalog(tmp_path)
    releases = tmp_path / "releases"
    releases.mkdir()
    (releases / "geth.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "client": "geth",
                "github": "ethereum/go-ethereum",
                "fetched_at": "2026-01-01T00:00:00Z",
                "ignored_tag_count": 0,
                "releases": [
                    {
                        "tag": "v1.17.7",
                        "name": "v1.17.7",
                        "published_at": "2026-01-01T00:00:00Z",
                        "prerelease": False,
                        "url": "https://example.test/v1.17.7",
                    }
                ],
            }
        )
    )
    config = tmp_path / "node.flags"
    config.write_text("--gogc 20\n")
    assert main(["scan", "--client", "geth", "--from", "1.17.0", "--config", str(config)]) == 1
    assert "more than 5 days old" in capsys.readouterr().out


def test_shipped_catalog_does_not_call_an_unknown_flag_safe(tmp_path, capsys):
    config = tmp_path / "geth.flags"
    config.write_text("--http.port 8545\n")
    code = main(
        ["scan", "--client", "geth", "--from", "v1.17.6", "--to", "v1.17.7", "--config", str(config)]
    )
    output = capsys.readouterr().out
    assert code == 1
    assert "REVIEW REQUIRED" in output
    assert "does not cover" in output
    assert "SAFE" not in output
