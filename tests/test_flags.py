"""Shipped execution-client flag rules come from release notes."""

import json

from chaindiff.catalog import load_flag_rules
from chaindiff.cli import main


CLIENTS = ("geth", "nethermind", "erigon", "besu", "reth")


def test_execution_flag_files_load():
    for client_id in CLIENTS:
        rules = load_flag_rules(client_id)
        assert rules, client_id
        for rule in rules:
            assert rule.action
            assert rule.source.startswith("https://")
            assert rule.effect in ("removed", "renamed", "deprecated", "default")


def test_geth_removed_flag_is_not_safe(tmp_path, capsys):
    config = tmp_path / "geth.flags"
    config.write_text("--txlookuplimit 2350000\n--gogc 20\n")
    code = main(
        ["scan", "--client", "geth", "--from", "v1.17.0", "--to", "v1.17.7", "--config", str(config)]
    )
    output = capsys.readouterr().out
    assert code == 2
    assert "txlookuplimit" in output
    assert "Remove this flag" in output
    assert "gogc" not in output


def test_geth_unset_gogc_reports_the_default(tmp_path, capsys):
    config = tmp_path / "geth.flags"
    config.write_text("--http\n")
    code = main(
        ["scan", "--client", "geth", "--from", "v1.17.0", "--to", "v1.17.7", "--config", str(config)]
    )
    output = capsys.readouterr().out
    assert code == 1
    assert "gogc" in output
    assert "--gogc=20" in output
    assert "does not cover" in output


def test_nethermind_boolean_flush_fails_and_the_new_value_does_not(tmp_path, capsys):
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"Db": {"FlushOnExit": True}}))
    code = main(
        [
            "scan",
            "--client",
            "nethermind",
            "--from",
            "1.39.3",
            "--to",
            "2.0.0",
            "--config",
            str(broken),
        ]
    )
    assert code == 2
    assert "Full instead of true" in capsys.readouterr().out

    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps({"Db": {"FlushOnExit": "WalOnly"}}))
    code = main(
        [
            "scan",
            "--client",
            "nethermind",
            "--from",
            "1.39.3",
            "--to",
            "2.0.0",
            "--config",
            str(valid),
        ]
    )
    output = capsys.readouterr().out
    assert code == 1
    assert "Boolean values were removed" not in output
    assert "MaxBlockDepth" in output


def test_besu_noop_flag_is_deprecated(tmp_path, capsys):
    config = tmp_path / "besu.flags"
    config.write_text("--snapsync-synchronizer-pre-checkpoint-headers-only-enabled=true\n")
    code = main(["scan", "--client", "besu", "--from", "26.8.1", "--to", "26.9.0", "--config", str(config)])
    output = capsys.readouterr().out
    assert code == 1
    assert "silent no-op" in output


def test_erigon_removed_startup_flag(tmp_path, capsys):
    config = tmp_path / "erigon.flags"
    config.write_text("--fcu.background.commit\n")
    code = main(
        ["scan", "--client", "erigon", "--from", "v3.6.1", "--to", "v3.7.1", "--config", str(config)]
    )
    output = capsys.readouterr().out
    assert code == 2
    assert "prevents startup" in output


def test_reth_backpressure_default_is_reported_when_unset(tmp_path, capsys):
    config = tmp_path / "reth.flags"
    config.write_text("--datadir /data\n")
    code = main(["scan", "--client", "reth", "--from", "v1.9.0", "--to", "v2.0.0", "--config", str(config)])
    output = capsys.readouterr().out
    assert code == 1
    assert "engine.persistence-backpressure-threshold" in output
    assert "default is 16" in output
