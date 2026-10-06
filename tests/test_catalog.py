import json
from datetime import datetime, timezone

import pytest

from chaindiff.catalog import load_advisories, load_clients, load_releases, save_releases
from chaindiff.evaluate import latest_stable
from chaindiff.models import Client, Release
from chaindiff.versions import parse_version


def test_registry_lists_the_supported_clients():
    ids = [client.id for client in load_clients()]
    assert ids == [
        "geth",
        "nethermind",
        "erigon",
        "besu",
        "reth",
        "op-geth",
        "op-reth",
        "nitro",
        "lighthouse",
        "prysm",
        "teku",
        "nimbus",
        "op-node",
    ]
    by_id = {client.id: client for client in load_clients()}
    assert by_id["besu"].github == "besu-eth/besu"
    assert by_id["teku"].github == "Consensys-Incorporated/teku"
    assert by_id["besu"].versioning == "calver"
    assert by_id["geth"].versioning == "semver"
    assert by_id["op-geth"].github == "ethereum-optimism/op-geth"
    assert by_id["op-geth"].tag_prefix == ""
    assert by_id["op-reth"].github == "ethereum-optimism/optimism"
    assert by_id["op-reth"].tag_prefix == "op-reth/"
    assert by_id["op-node"].github == "ethereum-optimism/optimism"
    assert by_id["op-node"].tag_prefix == "op-node/"
    assert by_id["op-node"].role == "consensus"
    assert by_id["nitro"].github == "OffchainLabs/nitro"
    assert by_id["nitro"].role == "execution"
    assert by_id["nitro"].tag_prefix == ""


def test_shipped_catalog_has_a_stable_release_for_every_client():
    for client in load_clients():
        loaded = load_releases(client.id)
        assert loaded is not None, client.id
        _, releases = loaded
        assert latest_stable(releases) is not None, client.id
        assert all(
            parse_version(item.tag.removeprefix(client.tag_prefix)) is not None for item in releases
        )


def test_erigon_latest_is_on_the_semver_line():
    _, releases = load_releases("erigon")
    latest = latest_stable(releases)
    assert latest is not None
    assert latest.version.numbers[0] < 100
    assert not latest.tag.startswith("v202")


def test_shipped_catalog_drops_known_non_releases():
    _, nimbus = load_releases("nimbus")
    assert all(item.tag != "nightly" for item in nimbus)
    _, nethermind = load_releases("nethermind")
    assert all(not item.tag.startswith("zkvm-guests") for item in nethermind)
    _, op_node = load_releases("op-node")
    tags = {item.tag for item in op_node}
    assert "op-node/v1.19.8" in tags
    assert all(item.tag.startswith("op-node/") for item in op_node)
    assert all(not item.tag.startswith("op-batcher/") for item in op_node)
    assert all(not item.tag.startswith("op-proposer/") for item in op_node)
    _, op_reth = load_releases("op-reth")
    assert any(item.tag == "op-reth/v2.5.0" for item in op_reth)
    assert all(item.tag.startswith("op-reth/") for item in op_reth)
    _, nitro = load_releases("nitro")
    assert any(item.tag == "v3.12.1" for item in nitro)
    assert all(not item.tag.startswith("consensus-") for item in nitro)


def test_release_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
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
    client = Client("geth", "Geth", "execution", "ethereum/go-ethereum", "semver")
    version = parse_version("v1.2.3")
    assert version is not None
    save_releases(
        client,
        [
            Release(
                tag="v1.2.3",
                name="v1.2.3",
                published_at="2026-01-02T00:00:00Z",
                prerelease=False,
                url="https://example.test/v1.2.3",
                version=version,
            )
        ],
        ignored_tag_count=4,
        fetched_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    loaded = load_releases("geth")
    assert loaded is not None
    _, releases = loaded
    assert releases[0].tag == "v1.2.3"
    assert releases[0].url == "https://example.test/v1.2.3"


def test_advisory_requires_a_source_and_an_action(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    path = tmp_path / "advisories"
    path.mkdir()
    (path / "geth.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "advisories": [
                    {
                        "version": "1.2.3",
                        "severity": "breaking",
                        "summary": "Flag removed.",
                        "action": "",
                        "source": "https://example.test/notes",
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="action"):
        load_advisories("geth")
