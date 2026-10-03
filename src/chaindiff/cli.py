"""Command line for ChainDiff."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from chaindiff import __version__
from chaindiff.catalog import client_by_id, load_advisories, load_clients, load_flag_rules, load_releases
from chaindiff.configparse import parse_config
from chaindiff.evaluate import evaluate, latest_stable
from chaindiff.models import CURRENT, DOWNGRADE, PRERELEASE, REVIEW, SAFE, UNSAFE
from chaindiff.refresh import refresh_catalog
from chaindiff.report import check_json, format_check, format_scan, format_versions, scan_json, versions_json
from chaindiff.scan import scan_settings
from chaindiff.versions import explain_unparsed, parse_version

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
        command.add_argument("--client", required=True, help="Client id, for example geth")
        command.add_argument("--from", dest="current", required=True, help="Installed version")
        command.add_argument("--to", dest="target", default="latest", help="Target version, or latest")
        command.add_argument("--json", action="store_true")

    scan = commands.add_parser("scan", help="Compare a config file with sourced flag changes")
    scan.add_argument("--client", required=True, help="Client id, for example geth")
    scan.add_argument("--from", dest="current", required=True, help="Installed version")
    scan.add_argument("--to", dest="target", default="latest", help="Target version, or latest")
    scan.add_argument("--config", required=True, help="CLI flags, TOML, JSON, or YAML file")
    scan.add_argument("--format", choices=("cli", "toml", "json", "yaml"), help="Config format")
    scan.add_argument("--json", action="store_true")

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
    clients = _selected_clients([args.client])
    if clients is None:
        return 3
    client = clients[0]
    current = parse_version(args.current)
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
        target = parse_version(args.target)
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
    current = parse_version(args.current)
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
        target = parse_version(args.target)
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


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "versions":
        return _versions(args)
    if args.command == "refresh":
        return refresh_catalog(args.clients)
    if args.command == "scan":
        return _scan(args)
    if args.command == "plan":
        return _check(args, plan_only=True)
    return _check(args, plan_only=False)
