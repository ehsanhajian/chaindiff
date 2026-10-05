"""Shipped advisories load and change the upgrade verdict."""

from datetime import datetime, timezone

from chaindiff.catalog import client_by_id, load_advisories, load_clients, load_releases
from chaindiff.cli import main
from chaindiff.evaluate import evaluate
from chaindiff.models import SAFE, UNSAFE
from chaindiff.versions import parse_version


def test_every_client_advisory_file_loads_against_known_releases():
    for client in load_clients():
        advisories = load_advisories(client.id)
        assert advisories, client.id
        loaded = load_releases(client.id)
        assert loaded is not None
        _, releases = loaded
        known = {item.version for item in releases}
        for advisory in advisories:
            assert advisory.version in known, f"{client.id} {advisory.version}"
            assert advisory.source.startswith("https://")


def test_nethermind_2_0_config_break_is_not_safe():
    client = client_by_id(load_clients(), "nethermind")
    assert client is not None
    loaded = load_releases("nethermind")
    assert loaded is not None
    fetched_at, releases = loaded
    result = evaluate(
        client=client,
        releases=releases,
        advisories=load_advisories("nethermind"),
        current=parse_version("1.39.3"),
        target=parse_version("2.0.0"),
        target_is_latest=False,
        fetched_at=fetched_at,
        now=datetime(2026, 10, 2, tzinfo=timezone.utc),
    )
    assert result.verdict == UNSAFE
    assert any("FlushOnExit" in step for step in result.steps)


def test_geth_1_17_7_patch_is_safe_once_reviewed():
    client = client_by_id(load_clients(), "geth")
    assert client is not None
    loaded = load_releases("geth")
    assert loaded is not None
    fetched_at, releases = loaded
    result = evaluate(
        client=client,
        releases=releases,
        advisories=load_advisories("geth"),
        current=parse_version("v1.17.6"),
        target=parse_version("v1.17.7"),
        target_is_latest=False,
        fetched_at=fetched_at,
        now=datetime(2026, 10, 2, tzinfo=timezone.utc),
    )
    assert result.verdict == SAFE


def test_op_geth_library_release_is_not_a_node_upgrade(capsys):
    code = main(
        ["check", "--client", "op-geth", "--from", "1.101702.2", "--to", "1.101702.3"]
    )
    output = capsys.readouterr().out
    assert code == 2
    assert "NOT SAFE" in output
    assert "Do not run this release as a node." in output


def test_op_node_prefixed_tag_is_the_same_version(capsys):
    code = main(
        [
            "check",
            "--client",
            "op-node",
            "--from",
            "op-node/v1.19.7",
            "--to",
            "1.19.8",
        ]
    )
    output = capsys.readouterr().out
    assert code == 0
    assert "Verdict: SAFE" in output
    assert "custom rollup config" in output


def test_op_node_unreviewed_release_stays_review(capsys):
    code = main(["check", "--client", "op-node", "--from", "1.19.3", "--to", "1.19.5"])
    output = capsys.readouterr().out
    assert code == 1
    assert "REVIEW REQUIRED" in output


def test_op_node_removed_sync_field_is_not_safe(capsys):
    code = main(["check", "--client", "op-node", "--from", "1.19.5", "--to", "1.19.8"])
    output = capsys.readouterr().out
    assert code == 2
    assert "unsafe_l2" in output


def test_op_reth_removed_import_commands_are_not_safe(capsys):
    code = main(["check", "--client", "op-reth", "--from", "2.4.4", "--to", "2.5.0"])
    output = capsys.readouterr().out
    assert code == 2
    assert "import-op" in output
    assert "init-state --without-ovm" in output


def test_op_stack_versions_are_comparable():
    assert parse_version("1.101702.2") < parse_version("1.101702.3")
    assert parse_version("1.19.7") < parse_version("1.19.8")
    # The jump stays inside major 1, so it is not an automatic semver break.
    assert parse_version("1.101603.5").numbers[0] == parse_version("1.101702.3").numbers[0]
