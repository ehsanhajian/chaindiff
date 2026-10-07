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
        "bor",
        "bsc",
        "avalanchego",
        "linea-besu",
        "l2geth",
        "external-node",
        "pathfinder",
        "juno",
        "lighthouse",
        "prysm",
        "teku",
        "nimbus",
        "op-node",
        "heimdall",
        "maru",
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
    assert by_id["bor"].github == "0xPolygon/bor"
    assert by_id["bor"].role == "execution"
    assert by_id["bor"].tag_prefix == ""
    assert by_id["avalanchego"].github == "ava-labs/avalanchego"
    assert by_id["avalanchego"].role == "execution"
    assert by_id["avalanchego"].tag_prefix == ""
    assert by_id["linea-besu"].github == "LFDT-Lineth/lineth-monorepo"
    assert by_id["linea-besu"].role == "execution"
    assert by_id["linea-besu"].tag_prefix == "releases/linea-besu-package/"
    assert by_id["maru"].github == "LFDT-Lineth/lineth-monorepo"
    assert by_id["maru"].role == "consensus"
    assert by_id["maru"].tag_prefix == "releases/maru/"
    assert by_id["l2geth"].github == "scroll-tech/go-ethereum"
    assert by_id["l2geth"].role == "execution"
    assert by_id["l2geth"].tag_prefix == "scroll-"
    assert by_id["external-node"].github == "matter-labs/zksync-era"
    assert by_id["external-node"].role == "execution"
    assert by_id["external-node"].tag_prefix == "core-"
    assert by_id["pathfinder"].github == "software-mansion/pathfinder"
    assert by_id["pathfinder"].role == "execution"
    assert by_id["pathfinder"].tag_prefix == ""
    assert by_id["juno"].github == "NethermindEth/juno"
    assert by_id["juno"].role == "execution"
    assert by_id["juno"].tag_prefix == ""
    assert by_id["bsc"].github == "bnb-chain/bsc"
    assert by_id["bsc"].role == "execution"
    assert by_id["bsc"].tag_prefix == ""
    assert by_id["heimdall"].github == "0xPolygon/heimdall-v2"
    assert by_id["heimdall"].role == "consensus"
    assert by_id["heimdall"].tag_prefix == ""


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
    _, bor = load_releases("bor")
    assert any(item.tag == "v2.10.2" for item in bor)
    _, heimdall = load_releases("heimdall")
    assert any(item.tag == "v0.12.1" for item in heimdall)
    _, bsc = load_releases("bsc")
    assert any(item.tag == "v1.7.8" and not item.prerelease for item in bsc)
    assert any(item.tag == "v1.8.0-alpha" and item.prerelease for item in bsc)
    assert latest_stable(bsc).tag == "v1.7.8"
    _, avalanchego = load_releases("avalanchego")
    assert any(item.tag == "v1.15.1" and not item.prerelease for item in avalanchego)
    assert any(item.tag == "v1.15.0-fuji" and item.prerelease for item in avalanchego)
    assert latest_stable(avalanchego).tag == "v1.15.1"
    _, linea_besu = load_releases("linea-besu")
    assert any(item.tag == "releases/linea-besu-package/v2.3.0" and not item.prerelease for item in linea_besu)
    assert any(item.tag == "releases/linea-besu-package/v2.1.1" and item.prerelease for item in linea_besu)
    assert latest_stable(linea_besu).tag == "releases/linea-besu-package/v2.3.0"
    assert all(item.tag.startswith("releases/linea-besu-package/") for item in linea_besu)
    assert all(not item.tag.startswith("releases/maru/") for item in linea_besu)
    assert all(not item.tag.startswith("releases/coordinator/") for item in linea_besu)
    _, maru = load_releases("maru")
    assert any(item.tag == "releases/maru/v1.4.0" and not item.prerelease for item in maru)
    assert any(item.tag == "releases/maru/v1.3.0" and not item.prerelease for item in maru)
    assert latest_stable(maru).tag == "releases/maru/v1.4.0"
    assert all(item.tag.startswith("releases/maru/") for item in maru)
    assert all(not item.tag.startswith("releases/linea-besu-package/") for item in maru)
    assert all(not item.tag.startswith("releases/coordinator/") for item in maru)
    _, l2geth = load_releases("l2geth")
    assert any(item.tag == "scroll-v5.10.2" and not item.prerelease for item in l2geth)
    assert any(item.tag == "scroll-v5.8.52-fix" and item.prerelease for item in l2geth)
    assert latest_stable(l2geth).tag == "scroll-v5.10.2"
    assert all(item.tag.startswith("scroll-") for item in l2geth)
    assert all(not item.tag.startswith("v1.") for item in l2geth)
    _, external_node = load_releases("external-node")
    assert any(item.tag == "core-v31.5.0" and not item.prerelease for item in external_node)
    assert any(item.tag == "core-v29.4.0" and not item.prerelease for item in external_node)
    assert latest_stable(external_node).tag == "core-v31.5.0"
    assert all(item.tag.startswith("core-") for item in external_node)
    assert all(not item.tag.startswith("prover-") for item in external_node)
    assert all(not item.tag.startswith("contract_verifier-") for item in external_node)
    assert all(not item.tag.startswith("airbender_prover_server-") for item in external_node)
    _, pathfinder = load_releases("pathfinder")
    assert any(item.tag == "v0.24.0" and not item.prerelease for item in pathfinder)
    assert any(item.tag == "v0.22.8-beta.1" and item.prerelease for item in pathfinder)
    assert latest_stable(pathfinder).tag == "v0.24.1"
    _, juno = load_releases("juno")
    assert any(item.tag == "v0.16.6" and not item.prerelease for item in juno)
    assert any(item.tag == "v0.16.6-rc.4" and item.prerelease for item in juno)
    assert latest_stable(juno).tag == "v0.16.8"


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
