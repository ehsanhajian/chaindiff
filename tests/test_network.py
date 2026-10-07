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
    assert main(["check", "--network", "not-a-chain", "--execution", "geth", "--execution-version", "1.17.7", "--consensus", "lighthouse", "--consensus-version", "8.2.3"]) == 3
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


def test_op_mainnet_requirement_is_not_announced(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "op-mainnet",
                "--execution",
                "op-geth",
                "--execution-version",
                "1.101702.2",
                "--consensus",
                "op-node",
                "--consensus-version",
                "1.19.8",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert "OP Mainnet" in output
    assert "Next upgrade: Lagoon" in output
    assert "Mainnet activation: not scheduled" in output
    assert "https://docs.optimism.io/op-stack/protocol/hardforks/lagoon" in output
    assert "op-geth 1.101702.2  execution  requirement not announced" in output
    assert "op-node 1.19.8  consensus  requirement not announced" in output
    assert "No upgrade order between the execution client and op-node is stated for OP Mainnet." in output
    assert "OP Sepolia and Unichain Sepolia" in output
    assert "late July 2026" in output
    assert "REVIEW REQUIRED" in output
    assert "Verdict: SAFE" not in output
    assert "NOT SAFE" not in output
    assert "required 1.19" not in output
    assert "required 1.101702" not in output
    assert "TBD" not in output


def test_op_mainnet_accepts_op_reth(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "op-mainnet",
                "--execution",
                "op-reth",
                "--execution-version",
                "2.5.0",
                "--consensus",
                "op-node",
                "--consensus-version",
                "op-node/v1.19.8",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert "op-reth 2.5.0  execution  requirement not announced" in output
    assert "op-node 1.19.8  consensus  requirement not announced" in output


def test_op_mainnet_refuses_a_prerelease(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "op-mainnet",
                "--execution",
                "op-reth",
                "--execution-version",
                "2.5.0",
                "--consensus",
                "op-node",
                "--consensus-version",
                "1.19.0-rc.1",
            ]
        )
        == 2
    )
    output = capsys.readouterr().out
    assert "PRERELEASE" in output
    assert "1.19.0-rc.1" in output


def test_op_mainnet_rejects_an_ethereum_client(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "op-mainnet",
                "--execution",
                "geth",
                "--execution-version",
                "1.17.7",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "OP Mainnet does not include geth, lighthouse" in error
    assert "Lagoon" not in error


def test_base_requirement_is_not_announced(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "base",
                "--execution",
                "op-geth",
                "--execution-version",
                "1.101702.2",
                "--consensus",
                "op-node",
                "--consensus-version",
                "1.19.8",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert output.startswith("Base\n")
    assert "Next upgrade: Denim" in output
    assert "Next upgrade: Lagoon" not in output
    assert "Mainnet activation: not scheduled" in output
    assert "https://docs.base.org/upgrades/denim/overview" in output
    assert "op-geth 1.101702.2  execution  requirement not announced" in output
    assert "op-node 1.19.8  consensus  requirement not announced" in output
    assert "No upgrade order between op-geth and op-node is stated for Base." in output
    assert "November 2026" in output
    assert "October 2026" in output
    assert "2026-11" not in output
    assert "2026-10" not in output
    assert "REVIEW REQUIRED" in output
    assert "Verdict: SAFE" not in output
    assert "NOT SAFE" not in output
    assert "required 1.19" not in output
    assert "ghcr.io/base/node" in output


def test_base_rejects_op_reth_and_an_ethereum_client(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "base",
                "--execution",
                "op-reth",
                "--execution-version",
                "2.5.0",
                "--consensus",
                "op-node",
                "--consensus-version",
                "1.19.8",
            ]
        )
        == 3
    )
    assert "Base does not include op-reth" in capsys.readouterr().err
    assert (
        main(
            [
                "check",
                "--network",
                "base",
                "--execution",
                "geth",
                "--execution-version",
                "1.17.7",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "Base does not include geth, lighthouse" in error
    assert "Denim" not in error


def test_base_refuses_a_prerelease(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "base",
                "--execution",
                "op-geth",
                "--execution-version",
                "1.101702.3",
                "--consensus",
                "op-node",
                "--consensus-version",
                "1.19.0-rc.1",
            ]
        )
        == 2
    )
    assert "PRERELEASE" in capsys.readouterr().out


def test_arbitrum_one_requirement_is_not_announced(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "arbitrum-one",
                "--execution",
                "nitro",
                "--execution-version",
                "3.12.1",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert output.startswith("Arbitrum One\n")
    assert "Next upgrade: Unannounced" in output
    assert "Mainnet activation: not scheduled" in output
    assert "https://docs.arbitrum.io/run-arbitrum-node/arbos-releases/overview" in output
    assert "nitro 3.12.1  execution  requirement not announced" in output
    assert "consensus" not in output.split("Verdict:")[0]
    assert "Nitro is the node." in output
    assert "August 20, 2026" in output
    assert "v3.11.3 or higher" in output
    assert "Arbitrum Sepolia" in output
    assert "REVIEW REQUIRED" in output
    assert "Verdict: SAFE" not in output
    assert "NOT SAFE" not in output
    assert "required 3.11" not in output
    assert "not Arbitrum One" in output


def test_arbitrum_one_rejects_geth_and_a_consensus_flag(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "arbitrum-one",
                "--execution",
                "geth",
                "--execution-version",
                "1.17.7",
            ]
        )
        == 3
    )
    assert "Arbitrum One does not include geth" in capsys.readouterr().err
    assert (
        main(
            [
                "check",
                "--network",
                "arbitrum-one",
                "--execution",
                "nitro",
                "--execution-version",
                "3.12.1",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "does not use --consensus" in error
    assert "Glamsterdam" not in error


def test_arbitrum_one_refuses_a_prerelease(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "arbitrum-one",
                "--execution",
                "nitro",
                "--execution-version",
                "3.11.0-rc.3",
            ]
        )
        == 2
    )
    assert "PRERELEASE" in capsys.readouterr().out


def test_avalanche_requirement_is_not_announced(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "avalanche",
                "--execution",
                "avalanchego",
                "--execution-version",
                "1.15.1",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert output.startswith("Avalanche\n")
    assert "Next upgrade: Igloo" in output
    assert "Next upgrade: Helicon" not in output
    assert "Mainnet activation: not scheduled" in output
    assert "https://github.com/ava-labs/avalanchego/pull/6057" in output
    assert "avalanchego 1.15.1  execution  requirement not announced" in output
    assert "consensus" not in output.split("Verdict:")[0]
    assert "avalanchego is the node." in output
    assert "September 22, 2026 at 15:00 UTC" in output
    assert "July 28, 2026 at 15:00 UTC" in output
    assert "plugin version to 46" in output
    assert "v1.15.1 is backwards compatible" in output
    assert "REVIEW REQUIRED" in output
    assert "Verdict: SAFE" not in output
    assert "NOT SAFE" not in output
    assert "required 1.15" not in output
    assert "9999" not in output
    assert "2026-09-22" not in output


def test_avalanche_rejects_geth_and_a_consensus_flag(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "avalanche",
                "--execution",
                "geth",
                "--execution-version",
                "1.17.7",
            ]
        )
        == 3
    )
    assert "Avalanche does not include geth" in capsys.readouterr().err
    assert (
        main(
            [
                "check",
                "--network",
                "avalanche",
                "--execution",
                "avalanchego",
                "--execution-version",
                "1.15.1",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "does not use --consensus" in error
    assert "Igloo" not in error
    assert (
        main(
            [
                "check",
                "--execution",
                "avalanchego",
                "--execution-version",
                "1.15.1",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "does not include avalanchego" in error
    assert "--network avalanche" in error
    assert "Glamsterdam" not in error


def test_avalanche_refuses_a_prerelease(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "avalanche",
                "--execution",
                "avalanchego",
                "--execution-version",
                "1.15.0-fuji",
            ]
        )
        == 2
    )
    assert "PRERELEASE" in capsys.readouterr().out


def test_bsc_requirement_is_not_announced(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "bsc",
                "--execution",
                "bsc",
                "--execution-version",
                "1.7.8",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert output.startswith("BNB Smart Chain\n")
    assert "Next upgrade: Jenner" in output
    assert "Next upgrade: Pasteur" not in output
    assert "Mainnet activation: not scheduled" in output
    assert "https://docs.bnbchain.org/announce/jenner-bsc/" in output
    assert "bsc 1.7.8  execution  requirement not announced" in output
    assert "consensus" not in output.split("Verdict:")[0]
    assert "BSC is the node." in output
    assert "late October 2026" in output
    assert "late November 2026" in output
    assert "August 25, 2026" in output
    assert "v1.7.7" in output
    assert "--mev.grpc.disable" in output
    assert "opBNB is not this schedule." in output
    assert "REVIEW REQUIRED" in output
    assert "Verdict: SAFE" not in output
    assert "NOT SAFE" not in output
    assert "required 1.7" not in output
    assert "2026-10" not in output
    assert "2026-11" not in output


def test_bsc_rejects_geth_and_a_consensus_flag(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "bsc",
                "--execution",
                "geth",
                "--execution-version",
                "1.17.7",
            ]
        )
        == 3
    )
    assert "BNB Smart Chain does not include geth" in capsys.readouterr().err
    assert (
        main(
            [
                "check",
                "--network",
                "bsc",
                "--execution",
                "bsc",
                "--execution-version",
                "1.7.8",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "does not use --consensus" in error
    assert "Jenner" not in error
    assert (
        main(
            [
                "check",
                "--execution",
                "bsc",
                "--execution-version",
                "1.7.8",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "does not include bsc" in error
    assert "--network bsc" in error
    assert "Glamsterdam" not in error


def test_bsc_refuses_a_prerelease(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "bsc",
                "--execution",
                "bsc",
                "--execution-version",
                "1.8.0-alpha",
            ]
        )
        == 2
    )
    assert "PRERELEASE" in capsys.readouterr().out


def test_gnosis_requirement_is_not_announced(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "gnosis",
                "--execution",
                "nethermind",
                "--execution-version",
                "1.31.11",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert output.startswith("Gnosis Chain\n")
    assert "Next upgrade: Glamsterdam" in output
    assert "Next upgrade: Fusaka" not in output
    assert "Mainnet activation: not scheduled" in output
    assert "https://github.com/gnosischain/specs/blob/main/network-upgrades/glamsterdam.md" in output
    assert "blog.ethereum.org" not in output
    assert "nethermind 1.31.11  execution  requirement not announced" in output
    assert "lighthouse 8.2.3  consensus  requirement not announced" in output
    assert "No upgrade order between the execution client and the consensus client is stated for Gnosis." in output
    assert "April 14, 2026" in output
    assert "epoch 1714688" in output
    assert "March 16, 2026" in output
    assert "April 30, 2025" in output
    assert "Gnosis-only flag change" in output
    assert "REVIEW REQUIRED" in output
    assert "Verdict: SAFE" not in output
    assert "NOT SAFE" not in output
    assert "required 1." not in output
    assert "required 8." not in output
    assert "2026-04-14" not in output
    assert (
        main(
            [
                "check",
                "--network",
                "gnosis",
                "--execution",
                "erigon",
                "--execution-version",
                "3.0.2",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            ]
        )
        == 1
    )
    erigon = capsys.readouterr().out
    assert "erigon 3.0.2  execution  requirement not announced" in erigon
    assert "Next upgrade: Glamsterdam" in erigon


def test_gnosis_rejects_clients_it_does_not_document(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "gnosis",
                "--execution",
                "besu",
                "--execution-version",
                "26.9.0",
                "--consensus",
                "prysm",
                "--consensus-version",
                "7.2.0",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "Gnosis Chain does not include besu, prysm" in error
    assert "Glamsterdam" not in error
    assert "Fusaka" not in error


def test_gnosis_refuses_a_prerelease(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "gnosis",
                "--execution",
                "nethermind",
                "--execution-version",
                "1.31.11",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.3.0-rc.0",
            ]
        )
        == 2
    )
    assert "PRERELEASE" in capsys.readouterr().out


def test_polygon_requirement_is_not_announced(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "polygon",
                "--execution",
                "bor",
                "--execution-version",
                "2.10.2",
                "--consensus",
                "heimdall",
                "--consensus-version",
                "0.12.1",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert output.startswith("Polygon PoS\n")
    assert "Next upgrade: Unannounced" in output
    assert "Next upgrade: Lugano" not in output
    assert "Mainnet activation: not scheduled" in output
    assert "https://forum.polygon.technology/t/heimdall-v0-12-1/22300" in output
    assert "bor 2.10.2  execution  requirement not announced" in output
    assert "heimdall 0.12.1  consensus  requirement not announced" in output
    assert "No upgrade order between bor and heimdall is stated" in output
    assert "October 1, 2026" in output
    assert "v0.12.1" in output
    assert "v2.10.2" in output
    assert "https://github.com/0xPolygon/bor/releases/tag/v2.10.2" in output
    assert "Amoy is not this schedule." in output
    assert "REVIEW REQUIRED" in output
    assert "Verdict: SAFE" not in output
    assert "NOT SAFE" not in output
    assert "required 0.12" not in output
    assert "required 2.10" not in output
    assert "2026-10-01" not in output


def test_polygon_rejects_an_ethereum_pair(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "polygon",
                "--execution",
                "geth",
                "--execution-version",
                "1.17.7",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "Polygon PoS does not include geth, lighthouse" in error
    assert "Unannounced" not in error
    assert "Lugano" not in error
    assert (
        main(
            [
                "check",
                "--execution",
                "bor",
                "--execution-version",
                "2.10.2",
                "--consensus",
                "heimdall",
                "--consensus-version",
                "0.12.1",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "does not include bor, heimdall" in error
    assert "--network polygon" in error
    assert "Glamsterdam" not in error


def test_polygon_refuses_a_prerelease(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "polygon",
                "--execution",
                "bor",
                "--execution-version",
                "2.10.2-beta.1",
                "--consensus",
                "heimdall",
                "--consensus-version",
                "0.12.1",
            ]
        )
        == 2
    )
    assert "PRERELEASE" in capsys.readouterr().out


def test_linea_requirement_is_not_announced(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "linea",
                "--execution",
                "linea-besu",
                "--execution-version",
                "releases/linea-besu-package/v2.3.0",
                "--consensus",
                "maru",
                "--consensus-version",
                "1.4.0",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert output.startswith("Linea\n")
    assert "Next upgrade: Beta v5.3" in output
    assert "Next upgrade: Beta v5.2" not in output
    assert "Next upgrade: Fusaka" not in output
    assert "Mainnet activation: not scheduled" in output
    assert "https://docs.linea.build/changelog/release-notes" in output
    assert "linea-besu 2.3.0  execution  requirement not announced" in output
    assert "maru 1.4.0  consensus  requirement not announced" in output
    assert "No required Linea Besu or Maru version has been announced for Beta v5.3." in output
    assert "No upgrade order between Linea Besu and Maru is stated for Beta v5.3." in output
    assert "Q4 2026" in output
    assert "not activation times" in output
    assert "April 1, 2026" in output
    assert "December 3, 2025" in output
    assert "docker-compose" in output
    assert "Linea Sepolia" in output
    assert "Upstream Besu, Geth, and Erigon" in output
    assert "REVIEW REQUIRED" in output
    assert "Verdict: SAFE" not in output
    assert "NOT SAFE" not in output
    assert "Amsterdam" not in output
    assert "Glamsterdam" not in output
    assert "required 2.3" not in output
    assert "required 1.4" not in output
    assert "2026-04-01" not in output
    assert "2025-12-03" not in output


def test_linea_rejects_upstream_clients(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "linea",
                "--execution",
                "besu",
                "--execution-version",
                "26.8.1",
                "--consensus",
                "teku",
                "--consensus-version",
                "26.8.0",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "Linea does not include besu, teku" in error
    assert "Beta v5.3" not in error
    assert (
        main(
            [
                "check",
                "--network",
                "linea",
                "--execution",
                "geth",
                "--execution-version",
                "1.17.7",
                "--consensus",
                "maru",
                "--consensus-version",
                "1.4.0",
            ]
        )
        == 3
    )
    assert "Linea does not include geth" in capsys.readouterr().err
    assert (
        main(
            [
                "check",
                "--execution",
                "linea-besu",
                "--execution-version",
                "2.3.0",
                "--consensus",
                "maru",
                "--consensus-version",
                "1.4.0",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "does not include linea-besu, maru" in error
    assert "--network linea" in error
    assert "Glamsterdam" not in error


def test_linea_refuses_a_prerelease(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "linea",
                "--execution",
                "linea-besu",
                "--execution-version",
                "2.3.0",
                "--consensus",
                "maru",
                "--consensus-version",
                "1.4.0-rc.1",
            ]
        )
        == 2
    )
    assert "PRERELEASE" in capsys.readouterr().out


def test_scroll_requirement_is_not_announced(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "scroll",
                "--execution",
                "l2geth",
                "--execution-version",
                "scroll-v5.10.2",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert output.startswith("Scroll\n")
    assert "Next upgrade: Unannounced" in output
    assert "Next upgrade: OpenVM" not in output
    assert "Next upgrade: Galileo" not in output
    assert "Mainnet activation: not scheduled" in output
    assert "https://forum.scroll.io/t/announcement-openvm-v2-0-0-upgrade-on-scroll/1495" in output
    assert "l2geth 5.10.2  execution  requirement not announced" in output
    assert "l2geth is the node." in output
    assert "September 22, 2026" in output
    assert "02:00 UTC" in output
    assert "December 16, 2025" in output
    assert "December 18, 2025" in output
    assert "scroll-v5.8.38 or higher" in output
    assert "Early 2027 is not an activation time" in output
    assert "Scroll Sepolia" in output
    assert "Upstream Geth" in output
    assert "REVIEW REQUIRED" in output
    assert "Verdict: SAFE" not in output
    assert "NOT SAFE" not in output
    assert "required 5.8" not in output
    assert "required 5.10" not in output
    assert "2026-09-22" not in output
    assert "2025-12-16" not in output
    header, _, _ = output.partition("Verdict:")
    assert "consensus" not in header


def test_scroll_rejects_geth_and_a_consensus_flag(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "scroll",
                "--execution",
                "geth",
                "--execution-version",
                "1.17.7",
            ]
        )
        == 3
    )
    assert "Scroll does not include geth" in capsys.readouterr().err
    assert (
        main(
            [
                "check",
                "--network",
                "scroll",
                "--execution",
                "l2geth",
                "--execution-version",
                "5.10.2",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "does not use --consensus" in error
    assert "OpenVM" not in error
    assert (
        main(
            [
                "check",
                "--execution",
                "l2geth",
                "--execution-version",
                "5.10.2",
                "--consensus",
                "lighthouse",
                "--consensus-version",
                "8.2.3",
            ]
        )
        == 3
    )
    error = capsys.readouterr().err
    assert "does not include l2geth" in error
    assert "--network scroll" in error
    assert "Glamsterdam" not in error


def test_scroll_refuses_a_prerelease(capsys):
    assert (
        main(
            [
                "check",
                "--network",
                "scroll",
                "--execution",
                "l2geth",
                "--execution-version",
                "5.10.2-rc.1",
            ]
        )
        == 2
    )
    assert "PRERELEASE" in capsys.readouterr().out


def test_schedule_rejects_a_testnet_client_in_the_wrong_role(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAINDIFF_DATA", str(tmp_path))
    _write(tmp_path, _schedule(required_execution={"lighthouse": "8.3.0"}))
    with pytest.raises(ValueError, match="not an execution client"):
        load_network("ethereum")
