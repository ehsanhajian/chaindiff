"""Shipped advisories load and change the upgrade verdict."""

from datetime import datetime, timezone

from chaindiff.catalog import client_by_id, load_advisories, load_clients, load_releases
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
