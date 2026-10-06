"""Command line for ChainDiff."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from chaindiff import __version__
from chaindiff.catalog import (
    client_by_id,
    load_advisories,
    load_clients,
    load_flag_rules,
    load_network,
    load_releases,
)
from chaindiff.configparse import parse_config
from chaindiff.evaluate import evaluate, latest_stable
from chaindiff.models import CURRENT, DOWNGRADE, PRERELEASE, REVIEW, SAFE, UNSAFE
from chaindiff.detect import (
    detect_json,
    format_detect,
    read_binary_output,
    version_argv,
    version_from_image,
    version_from_output,
)
from chaindiff.network import evaluate_network
from chaindiff.pair import combine_pair
from chaindiff.refresh import refresh_catalog
from chaindiff.report import (
    check_json,
    format_check,
    format_network,
    format_pair,
    format_scan,
    format_versions,
    network_json,
    pair_json,
    scan_json,
    versions_json,
)
from chaindiff.scan import scan_settings
from chaindiff.versions import Version, explain_unparsed, parse_version

_EXIT = {
    CURRENT: 0,
    SAFE: 0,
    REVIEW: 1,
    UNSAFE: 2,
    DOWNGRADE: 2,
    PRERELEASE: 2,
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chaindiff",
        description="Decide whether an Ethereum node client upgrade is safe.",
    )
    parser.add_argument("--version", action="version", version=f"chaindiff {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    versions = commands.add_parser("versions", help="Show the latest stable release of each client")
    versions.add_argument("--client", action="append", dest="clients", help="Limit to one client id")
    versions.add_argument("--json", action="store_true")

    check = commands.add_parser("check", help="Compare an installed version with a target release")
    plan = commands.add_parser("plan", help="Checklist for the same comparison as check")
    for command in (check, plan):
        command.add_argument("--client", help="Client id, for example geth")
        command.add_argument("--from", dest="current", help="Installed version")
        command.add_argument("--to", dest="target", default="latest", help="Target version, or latest")
        command.add_argument("--network", help="Network id, for example ethereum, op-mainnet, or base")
        command.add_argument("--execution", help="Execution client id")
        command.add_argument("--execution-version", help="Installed execution client version")
        command.add_argument("--execution-to", help="Execution target version, or latest")
        command.add_argument("--consensus", help="Consensus client id")
        command.add_argument("--consensus-version", help="Installed consensus client version")
        command.add_argument("--consensus-to", help="Consensus target version, or latest")
        command.add_argument("--json", action="store_true")

    scan = commands.add_parser("scan", help="Compare a config file with sourced flag changes")
    scan.add_argument("--client", required=True, help="Client id, for example geth")
    scan.add_argument("--from", dest="current", required=True, help="Installed version")
    scan.add_argument("--to", dest="target", default="latest", help="Target version, or latest")
    scan.add_argument("--config", required=True, help="CLI flags, TOML, JSON, or YAML file")
    scan.add_argument("--format", choices=("cli", "toml", "json", "yaml"), help="Config format")
    scan.add_argument("--json", action="store_true")

    detect = commands.add_parser("detect", help="Read the installed client version")
    detect.add_argument("--client", required=True, help="Client id, for example geth")
    source = detect.add_mutually_exclusive_group(required=True)
    source.add_argument("--binary", help="Path to the client binary")
    source.add_argument("--image", help="Docker image reference; only the tag is read")
    detect.add_argument("--json", action="store_true")

    refresh = commands.add_parser("refresh", help="Download the release catalog from GitHub")
    refresh.add_argument("--client", action="append", dest="clients", help="Refresh one client id")
    return parser


def _selected_clients(raw_ids: list[str] | None):
    try:
        clients = load_clients()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return None
    if not raw_ids:
        return clients
    selected = []
    for raw in raw_ids:
        client = client_by_id(clients, raw)
        if client is None:
            known = ", ".join(item.id for item in clients)
            print(f"Unknown client '{raw}'. Known clients: {known}", file=sys.stderr)
            return None
        selected.append(client)
    return selected


def _versions(args: argparse.Namespace) -> int:
    clients = _selected_clients(args.clients)
    if clients is None:
        return 3
    rows = []
    missing = False
    for client in clients:
        try:
            loaded = load_releases(client.id)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 3
        if loaded is None:
            missing = True
            rows.append((client, None, None))
            continue
        fetched_at, releases = loaded
        rows.append((client, fetched_at, releases))
    now = datetime.now(timezone.utc)
    if args.json:
        print(json.dumps(versions_json(rows, now=now), indent=2))
    else:
        print(format_versions(rows, now=now), end="")
    if missing:
        print("Run `chaindiff refresh` to fill a missing catalog.", file=sys.stderr)
    return 0


def _check(args: argparse.Namespace, *, plan_only: bool) -> int:
    if args.network:
        return _network_check(args)
    if any(
        (
            args.execution,
            args.execution_version,
            args.execution_to,
            args.consensus,
            args.consensus_version,
            args.consensus_to,
        )
    ):
        return _pair_check(args)
    if not args.client or not args.current:
        print("A client check needs --client and --from.", file=sys.stderr)
        return 3
    clients = _selected_clients([args.client])
    if clients is None:
        return 3
    client = clients[0]
    current = _parse_client_version(client, args.current)
    if current is None:
        print(explain_unparsed(args.current), file=sys.stderr)
        return 3
    try:
        loaded = load_releases(client.id)
        advisories = load_advisories(client.id)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    if loaded is None:
        print(f"No release catalog for {client.id}. Run: chaindiff refresh", file=sys.stderr)
        return 3
    fetched_at, releases = loaded
    target_is_latest = args.target.lower() in ("latest", "stable")
    if target_is_latest:
        stable = latest_stable(releases)
        if stable is None:
            print(f"{client.id} has no stable release in the catalog.", file=sys.stderr)
            return 3
        target = stable.version
    else:
        target = _parse_client_version(client, args.target)
        if target is None:
            print(explain_unparsed(args.target), file=sys.stderr)
            return 3
    result = evaluate(
        client=client,
        releases=releases,
        advisories=advisories,
        current=current,
        target=target,
        target_is_latest=target_is_latest,
        fetched_at=fetched_at,
        now=datetime.now(timezone.utc),
    )
    if args.json:
        print(json.dumps(check_json(result), indent=2))
    else:
        print(format_check(result, plan_only=plan_only), end="")
    return _EXIT[result.verdict]


def _scan(args: argparse.Namespace) -> int:
    clients = _selected_clients([args.client])
    if clients is None:
        return 3
    client = clients[0]
    current = _parse_client_version(client, args.current)
    if current is None:
        print(explain_unparsed(args.current), file=sys.stderr)
        return 3
    path = Path(args.config)
    if not path.is_file():
        print(f"Config file not found: {args.config}", file=sys.stderr)
        return 3
    try:
        rules = load_flag_rules(client.id)
        config_format, settings = parse_config(path, args.format)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    target_tag = None
    stale_warning = None
    target_is_latest = args.target.lower() in ("latest", "stable")
    if target_is_latest:
        try:
            loaded = load_releases(client.id)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 3
        if loaded is None:
            print(f"No release catalog for {client.id}. Run: chaindiff refresh", file=sys.stderr)
            return 3
        fetched_at, releases = loaded
        stable = latest_stable(releases)
        if stable is None:
            print(f"{client.id} has no stable release in the catalog.", file=sys.stderr)
            return 3
        target = stable.version
        target_tag = stable.tag
        if datetime.now(timezone.utc) - fetched_at > timedelta(days=5):
            stale_warning = "The release catalog is more than 5 days old, so latest may be behind."
    else:
        target = _parse_client_version(client, args.target)
        if target is None:
            print(explain_unparsed(args.target), file=sys.stderr)
            return 3
    if target < current:
        print("The target is older than the version you already run.", file=sys.stderr)
        return 3
    result = scan_settings(
        client=client,
        rules=rules,
        settings=settings,
        current=current,
        target=target,
        target_tag=target_tag,
        config_path=str(path),
        config_format=config_format,
    )
    if stale_warning:
        if result.verdict == SAFE:
            result.verdict = REVIEW
            result.reasons.append(stale_warning)
        else:
            result.warnings.append(stale_warning)
    if args.json:
        print(json.dumps(scan_json(result), indent=2))
    else:
        print(format_scan(result), end="")
    return _EXIT[result.verdict]


_MAINNET_EXECUTION = frozenset({"geth", "nethermind", "erigon", "besu", "reth"})
_MAINNET_CONSENSUS = frozenset({"lighthouse", "prysm", "teku", "nimbus"})
_OP_MAINNET_EXECUTION = frozenset({"op-geth", "op-reth"})
_OP_MAINNET_CONSENSUS = frozenset({"op-node"})
_BASE_EXECUTION = frozenset({"op-geth"})
_BASE_CONSENSUS = frozenset({"op-node"})


def _parse_client_version(client, text: str) -> Version | None:
    raw = text.strip()
    if client.tag_prefix and raw.startswith(client.tag_prefix):
        raw = raw[len(client.tag_prefix) :]
    return parse_version(raw)


def _outside_mainnet_pair(execution, consensus) -> str | None:
    outside = [
        client.id
        for client, allowed in (
            (execution, _MAINNET_EXECUTION),
            (consensus, _MAINNET_CONSENSUS),
        )
        if client.id not in allowed
    ]
    if not outside:
        return None
    listed = ", ".join(outside)
    return (
        f"The Ethereum mainnet pair does not include {listed}. "
        "Use --client for one OP Stack client, or --network op-mainnet or --network base for that chain's schedule."
    )


def _outside_op_mainnet(execution, consensus) -> str | None:
    outside = [
        client.id
        for client, allowed in (
            (execution, _OP_MAINNET_EXECUTION),
            (consensus, _OP_MAINNET_CONSENSUS),
        )
        if client.id not in allowed
    ]
    if not outside:
        return None
    listed = ", ".join(outside)
    return (
        f"OP Mainnet does not include {listed}. "
        "This check uses op-geth or op-reth with op-node."
    )


def _outside_base(execution, consensus) -> str | None:
    outside = [
        client.id
        for client, allowed in (
            (execution, _BASE_EXECUTION),
            (consensus, _BASE_CONSENSUS),
        )
        if client.id not in allowed
    ]
    if not outside:
        return None
    listed = ", ".join(outside)
    return f"Base does not include {listed}. This check uses op-geth with op-node."


def _client_result(client, current_text: str, target_text: str):
    current = _parse_client_version(client, current_text)
    if current is None:
        raise ValueError(explain_unparsed(current_text))
    loaded = load_releases(client.id)
    advisories = load_advisories(client.id)
    if loaded is None:
        raise ValueError(f"No release catalog for {client.id}. Run: chaindiff refresh")
    fetched_at, releases = loaded
    target_is_latest = target_text.lower() in ("latest", "stable")
    if target_is_latest:
        stable = latest_stable(releases)
        if stable is None:
            raise ValueError(f"{client.id} has no stable release in the catalog.")
        target = stable.version
    else:
        target = _parse_client_version(client, target_text)
        if target is None:
            raise ValueError(explain_unparsed(target_text))
    return evaluate(
        client=client,
        releases=releases,
        advisories=advisories,
        current=current,
        target=target,
        target_is_latest=target_is_latest,
        fetched_at=fetched_at,
        now=datetime.now(timezone.utc),
    )


def _pair_check(args: argparse.Namespace) -> int:
    if args.client or args.current:
        print("A pair check does not use --client or --from.", file=sys.stderr)
        return 3
    if args.target != "latest":
        print("A pair check does not use --to. Use --execution-to and --consensus-to.", file=sys.stderr)
        return 3
    if not all((args.execution, args.execution_version, args.consensus, args.consensus_version)):
        print(
            "A pair check needs --execution, --execution-version, --consensus, and --consensus-version.",
            file=sys.stderr,
        )
        return 3
    try:
        clients = load_clients()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    execution = client_by_id(clients, args.execution)
    consensus = client_by_id(clients, args.consensus)
    if execution is None or consensus is None:
        known = ", ".join(item.id for item in clients)
        missing = args.execution if execution is None else args.consensus
        print(f"Unknown client '{missing}'. Known clients: {known}", file=sys.stderr)
        return 3
    if execution.role != "execution":
        print(f"{execution.id} is a consensus client.", file=sys.stderr)
        return 3
    if consensus.role != "consensus":
        print(f"{consensus.id} is an execution client.", file=sys.stderr)
        return 3
    outside = _outside_mainnet_pair(execution, consensus)
    if outside is not None:
        print(outside, file=sys.stderr)
        return 3
    try:
        schedule = load_network("ethereum")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    try:
        execution_result = _client_result(
            execution,
            args.execution_version,
            args.execution_to or "latest",
        )
        consensus_result = _client_result(
            consensus,
            args.consensus_version,
            args.consensus_to or "latest",
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    result = combine_pair(execution_result, consensus_result, schedule)
    if args.json:
        print(json.dumps(pair_json(result), indent=2))
    else:
        print(format_pair(result), end="")
    return _EXIT[result.verdict]


def _network_check(args: argparse.Namespace) -> int:
    if args.client or args.current:
        print("--network does not use --client or --from.", file=sys.stderr)
        return 3
    if args.target != "latest":
        print("--network does not use --to.", file=sys.stderr)
        return 3
    if args.execution_to or args.consensus_to:
        print("--network does not use --execution-to or --consensus-to.", file=sys.stderr)
        return 3
    if not all((args.execution, args.execution_version, args.consensus, args.consensus_version)):
        print(
            "A network check needs --execution, --execution-version, --consensus, and --consensus-version.",
            file=sys.stderr,
        )
        return 3
    try:
        schedule = load_network(args.network)
        clients = load_clients()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    execution = client_by_id(clients, args.execution)
    consensus = client_by_id(clients, args.consensus)
    if execution is None or consensus is None:
        known = ", ".join(item.id for item in clients)
        missing = args.execution if execution is None else args.consensus
        print(f"Unknown client '{missing}'. Known clients: {known}", file=sys.stderr)
        return 3
    if execution.role != "execution":
        print(f"{execution.id} is a consensus client.", file=sys.stderr)
        return 3
    if consensus.role != "consensus":
        print(f"{consensus.id} is an execution client.", file=sys.stderr)
        return 3
    if schedule.id == "ethereum":
        outside = _outside_mainnet_pair(execution, consensus)
    elif schedule.id == "op-mainnet":
        outside = _outside_op_mainnet(execution, consensus)
    elif schedule.id == "base":
        outside = _outside_base(execution, consensus)
    else:
        outside = None
    if outside is not None:
        print(outside, file=sys.stderr)
        return 3
    execution_version = _parse_client_version(execution, args.execution_version)
    if execution_version is None:
        print(explain_unparsed(args.execution_version), file=sys.stderr)
        return 3
    consensus_version = _parse_client_version(consensus, args.consensus_version)
    if consensus_version is None:
        print(explain_unparsed(args.consensus_version), file=sys.stderr)
        return 3
    result = evaluate_network(
        schedule,
        execution=execution,
        execution_version=execution_version,
        consensus=consensus,
        consensus_version=consensus_version,
    )
    if args.json:
        print(json.dumps(network_json(result), indent=2))
    else:
        print(format_network(result), end="")
    return _EXIT[result.verdict]


def _detect(args: argparse.Namespace) -> int:
    clients = _selected_clients([args.client])
    if clients is None:
        return 3
    client = clients[0]
    if args.binary is not None:
        argv = version_argv(client.id)
        output = None if argv is None else read_binary_output(args.binary, argv)
        version = None if output is None else version_from_output(client.id, output)
        source = "binary"
    else:
        version = version_from_image(args.image)
        source = "image"
    if args.json:
        print(json.dumps(detect_json(client_id=client.id, version=version), indent=2))
    else:
        print(
            format_detect(
                client_id=client.id,
                client_name=client.name,
                version=version,
                source=source,
            ),
            end="",
        )
    return 0 if version is not None else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "versions":
        return _versions(args)
    if args.command == "refresh":
        return refresh_catalog(args.clients)
    if args.command == "scan":
        return _scan(args)
    if args.command == "detect":
        return _detect(args)
    if args.command == "plan":
        return _check(args, plan_only=True)
    return _check(args, plan_only=False)
