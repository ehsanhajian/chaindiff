import json
import sys

import pytest

from chaindiff.cli import main
from chaindiff.detect import (
    read_binary_output,
    version_argv,
    version_from_image,
    version_from_output,
)

GETH = """\
Geth
Version: 1.17.7-stable
Git Commit: 88c3b0d1abcdef
Architecture: amd64
Go Version: go1.24.1
Operating System: linux
"""

NETHERMIND = """\
Version:     1.31.11+abcdef12
Commit:      abcdef12ffffffff
Source date: 2026-10-01 00:00:00Z
Runtime:     .NET 8.0.0
"""

ERIGON = "erigon version 3.7.1-a53e9545\n"

BESU = "besu/v26.9.0/linux-x86_64/openjdk-java-21\n"
BESU_DEV = "besu/v26.9.0-dev-ac23d311/linux-x86_64/graalvm-java-17\n"

RETH = """\
Version: 2.7.0
Commit SHA: abcdef1234567890abcdef1234567890abcdef12
Build Timestamp: 2026-09-28T00:00:00.000000000Z
Build Features: jemalloc
Build Profile: release
"""

LIGHTHOUSE = """\
v8.2.3-67da032
BLS library: blst
SHA256 hardware acceleration: true
Allocator: jemalloc
Profile: release
Specs: mainnet (true), minimal (false), gnosis (false)
"""

PRYSM = "beacon-chain version Prysm/v7.2.0/abcdef12. Built at: 2026-09-28T12:00:00Z\n"

TEKU = "teku/v26.9.1/linux-x86_64/openjdk-java-21\n"

NIMBUS = "v26.9.1-abcdef-stateofus\n"


@pytest.mark.parametrize(
    ("client", "text", "version"),
    [
        ("geth", GETH, "1.17.7"),
        ("nethermind", NETHERMIND, "1.31.11"),
        ("erigon", ERIGON, "3.7.1"),
        ("erigon", "erigon-node version 3.7.1-dev-a53e9545\n", "3.7.1-dev"),
        ("besu", BESU, "26.9.0"),
        ("besu", BESU_DEV, "26.9.0-dev"),
        ("reth", RETH, "2.7.0"),
        ("reth", "Version: 2.7.0-dev\n", "2.7.0-dev"),
        ("reth", "2.7.0 (abcdef12)\n", "2.7.0"),
        ("lighthouse", LIGHTHOUSE, "8.2.3"),
        ("lighthouse", "v8.3.0-rc.0-67da032\n", "8.3.0-rc.0"),
        ("lighthouse", "Lighthouse/v8.2.3-67da032\n", "8.2.3"),
        ("prysm", PRYSM, "7.2.0"),
        ("prysm", "validator version Prysm/v7.2.0-rc.0/abcdef12. Built at: 2026-09-28T12:00:00Z\n", "7.2.0-rc.0"),
        ("teku", TEKU, "26.9.1"),
        ("teku", "teku/26.9.1/linux-x86_64/21\n", "26.9.1"),
        ("nimbus", NIMBUS, "26.9.1"),
        ("nimbus", "26.9.1\n", "26.9.1"),
        ("nimbus", "Nimbus beacon node v26.9.1-abcdef-stateofus\n", "26.9.1"),
        ("bor", "Version: 2.10.2\nGitCommit: abcdef1234567890\n", "2.10.2"),
        ("heimdall", "0.12.1\n", "0.12.1"),
        ("bsc", "Geth\nVersion: 1.7.8\nGit Commit: abcdef\nGo Version: go1.24.1\n", "1.7.8"),
        (
            "avalanchego",
            "avalanchego/1.15.1 [database=v1.4.5, rpcchainvm=46, commit=abc, go=1.26.8]\n",
            "1.15.1",
        ),
    ],
)
def test_binary_output_reads_one_release(client, text, version):
    found = version_from_output(client, text)
    assert found is not None
    assert found.text == version


def test_geth_does_not_use_the_go_version():
    found = version_from_output("geth", GETH)
    assert found is not None
    assert found.text != "1.24.1"


def test_conflicting_versions_are_not_guessed():
    text = "Version: 1.17.7-stable\nVersion: 1.17.6-stable\n"
    assert version_from_output("geth", text) is None


def test_unparsed_binary_output_is_unsure():
    assert version_from_output("geth", "Geth\nGo Version: go1.24.1\n") is None
    assert version_from_output("nimbus", "Nim compiler version 2.2.4\nbuild failed\n") is None


@pytest.mark.parametrize(
    ("ref", "version"),
    [
        ("ethereum/client-go:v1.17.7", "1.17.7"),
        ("ethereum/client-go:v1.17.7-stable", "1.17.7"),
        ("localhost:5000/ethereum/client-go:v1.17.7", "1.17.7"),
        ("ethereum/client-go:v1.17.7@sha256:deadbeef", "1.17.7"),
        ("statusim/nimbus-eth2:amd64-v26.9.1", "26.9.1"),
        ("sigp/lighthouse:v8.3.0-rc.0", "8.3.0-rc.0"),
        ("client-go:v1.2.3-v1.2.3", "1.2.3"),
    ],
)
def test_image_tag_reads_one_release(ref, version):
    found = version_from_image(ref)
    assert found is not None
    assert found.text == version


@pytest.mark.parametrize(
    "ref",
    [
        "ethereum/client-go",
        "ethereum/client-go:latest",
        "ethereum/client-go:stable",
        "ethereum/client-go:nightly",
        "ethereum/client-go:master",
        "ethereum/client-go:main",
        "ethereum/client-go:develop",
        "ethereum/client-go:edge",
        "ethereum/client-go:unstable",
        "ethereum/client-go:dev",
        "ethereum/client-go:v1.17",
        "ethereum/client-go:v1.2.3-v1.2.4",
        "localhost:5000/ethereum/client-go",
        "ethereum/client-go@sha256:deadbeef",
        "erigontech/erigon:v2022.10.01",
        "",
    ],
)
def test_image_tag_without_one_release_is_unsure(ref):
    assert version_from_image(ref) is None


def test_read_binary_output_captures_both_streams():
    code = "import sys; print('from-out'); print('from-err', file=sys.stderr)"
    text = read_binary_output(sys.executable, ("-c", code))
    assert text is not None
    assert "from-out" in text
    assert "from-err" in text


def test_read_binary_output_timeout_and_missing_file():
    assert read_binary_output(sys.executable, ("-c", "import time; time.sleep(5)"), timeout=0.2) is None
    assert read_binary_output("/no/such/chaindiff-binary", ("--version",)) is None


def test_detect_binary_prints_check_command(monkeypatch, capsys):
    def fake(path, argv, timeout=10):
        assert path == "/usr/bin/geth"
        assert argv == ("version",)
        return GETH

    monkeypatch.setattr("chaindiff.cli.read_binary_output", fake)
    assert main(["detect", "--client", "geth", "--binary", "/usr/bin/geth"]) == 0
    output = capsys.readouterr().out
    assert "geth 1.17.7" in output
    assert "chaindiff check --client geth --from 1.17.7" in output
    assert "go1.24.1" not in output


def test_detect_other_clients_use_version_flag(monkeypatch, capsys):
    def fake(path, argv, timeout=10):
        assert argv == ("--version",)
        return PRYSM

    monkeypatch.setattr("chaindiff.cli.read_binary_output", fake)
    assert main(["detect", "--client", "prysm", "--binary", "/usr/bin/beacon-chain"]) == 0
    assert "prysm 7.2.0" in capsys.readouterr().out


def test_detect_unsure_binary_prints_placeholder(monkeypatch, capsys):
    monkeypatch.setattr("chaindiff.cli.read_binary_output", lambda path, argv, timeout=10: None)
    assert main(["detect", "--client", "geth", "--binary", "/usr/bin/geth"]) == 1
    output = capsys.readouterr().out
    assert "Could not read a Geth version from that binary." in output
    assert "chaindiff check --client geth --from <installed>" in output
    assert "1.17" not in output


def test_detect_image_does_not_run_a_binary(monkeypatch, capsys):
    def fail(path, argv, timeout=10):
        raise AssertionError("image detection must not run a binary")

    monkeypatch.setattr("chaindiff.cli.read_binary_output", fail)
    assert main(["detect", "--client", "geth", "--image", "ethereum/client-go:v1.17.7", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "client": "geth",
        "detected": True,
        "version": "1.17.7",
        "check": "chaindiff check --client geth --from 1.17.7",
    }


def test_detect_unsure_image_json(capsys):
    assert main(["detect", "--client", "nimbus", "--image", "statusim/nimbus-eth2:latest", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["detected"] is False
    assert payload["version"] is None
    assert payload["check"] == "chaindiff check --client nimbus --from <installed>"


def test_op_geth_uses_the_geth_version_command(monkeypatch, capsys):
    text = "Op-Geth\nVersion: 1.101702.2-stable\nUpstream Version: 1.17.2-stable\nGo Version: go1.24.1\n"

    def fake(path, argv, timeout=10):
        assert argv == ("version",)
        return text

    monkeypatch.setattr("chaindiff.cli.read_binary_output", fake)
    assert main(["detect", "--client", "op-geth", "--binary", "/usr/bin/op-geth"]) == 0
    output = capsys.readouterr().out
    assert "op-geth 1.101702.2" in output
    assert "1.17.2" not in output
    assert "go1.24.1" not in output


def test_bor_and_heimdall_use_the_version_subcommand(monkeypatch, capsys):
    def fake(path, argv, timeout=10):
        assert argv == ("version",)
        if path.endswith("bor"):
            return "Version: 2.10.2\nGitCommit: abcdef1234567890\n"
        return "0.12.1\n"

    monkeypatch.setattr("chaindiff.cli.read_binary_output", fake)
    assert main(["detect", "--client", "bor", "--binary", "/usr/bin/bor"]) == 0
    assert "bor 2.10.2" in capsys.readouterr().out
    assert main(["detect", "--client", "heimdall", "--binary", "/usr/bin/heimdalld"]) == 0
    output = capsys.readouterr().out
    assert "heimdall 0.12.1" in output
    assert version_from_output("heimdall", "name: heimdall\nversion: 0.12.1\n") is None


def test_op_node_binary_is_not_run(monkeypatch, capsys):
    def fail(path, argv, timeout=10):
        raise AssertionError("op-node version output is not confirmed")

    monkeypatch.setattr("chaindiff.cli.read_binary_output", fail)
    assert version_argv("op-node") is None
    assert version_argv("op-reth") is None
    assert main(["detect", "--client", "op-node", "--binary", "/usr/bin/op-node"]) == 1
    output = capsys.readouterr().out
    assert "Could not read a op-node version from that binary." in output
    assert "chaindiff check --client op-node --from <installed>" in output


def test_op_node_image_tag_is_read(capsys):
    assert (
        main(
            [
                "detect",
                "--client",
                "op-node",
                "--image",
                "us-docker.pkg.dev/oplabs-tools-artifacts/images/op-node:v1.19.8",
            ]
        )
        == 0
    )
    assert "op-node 1.19.8" in capsys.readouterr().out


def test_detect_unknown_client(capsys):
    assert main(["detect", "--client", "lodestar", "--image", "lodestar:v1.2.3"]) == 3
    assert "Unknown client" in capsys.readouterr().err
