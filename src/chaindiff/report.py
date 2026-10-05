"""Text and JSON reports."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from chaindiff.catalog import format_time
from chaindiff.evaluate import latest_stable, newer_prerelease
from chaindiff.models import (
    VERDICT_LABELS,
    CheckResult,
    Client,
    FlagFinding,
    NetworkCheckResult,
    PairCheckResult,
    Release,
    ScanResult,
    Setting,
)


def _day(value: str) -> str:
    return value[:10] if len(value) >= 10 else "-"


def _shown_releases(releases: list[Release]) -> tuple[list[Release | None], int]:
    if len(releases) <= 12:
        return list(releases), 0
    hidden = releases[8:-3]
    shown: list[Release | None] = list(releases[:8]) + [None] + list(releases[-3:])
    return shown, len(hidden)


def format_check(result: CheckResult, *, plan_only: bool = False) -> str:
    lines = [
        f"{result.client.name}  {result.client.role}",
        result.client.github,
        f"Catalog: {format_time(result.fetched_at)}",
        "",
        f"{result.current.text}  →  {result.target.text}"
        + (f"  ({result.target_tag})" if result.target_tag else ""),
        "",
        f"Verdict: {VERDICT_LABELS[result.verdict]}",
        "",
    ]
    if result.reasons:
        lines.append("Why")
        lines.extend(f"  {reason}" for reason in result.reasons)
        lines.append("")
    if result.warnings:
        lines.append("Warnings")
        lines.extend(f"  {warning}" for warning in result.warnings)
        lines.append("")
    if not plan_only and result.releases:
        lines.append("Releases")
        shown, hidden = _shown_releases(result.releases)
        for item in shown:
            if item is None:
                lines.append(f"  ({hidden} older releases omitted)")
                continue
            lines.append(f"  {item.tag:<22} {_day(item.published_at)}  {item.url}")
        oldest = min(result.releases, key=lambda item: item.version)
        if len(result.releases) > 1:
            lines.append(
                f"  First release after {result.current.text}: {oldest.tag} on {_day(oldest.published_at)}"
            )
        lines.append("")
    if result.steps:
        lines.append("Before any upgrade")
        for index, step in enumerate(result.steps, start=1):
            lines.append(f"  {index}. {step}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_pair(result: PairCheckResult) -> str:
    lines = [
        "Execution and consensus",
        _pair_arrow(result.execution),
        _pair_arrow(result.consensus),
        "",
        f"Verdict: {VERDICT_LABELS[result.verdict]}",
        "",
        "Why",
    ]
    lines.extend(f"  {reason}" for reason in result.reasons)
    lines.append("")
    lines.append("Upgrade order")
    lines.append(f"  {result.schedule.order_summary}")
    lines.append(f"  {result.schedule.source}")
    lines.append("")
    if result.warnings:
        lines.append("Warnings")
        lines.extend(f"  {warning}" for warning in result.warnings)
        lines.append("")
    if result.steps:
        lines.append("Before any upgrade")
        for index, step in enumerate(result.steps, start=1):
            lines.append(f"  {index}. {step}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _pair_arrow(result: CheckResult) -> str:
    target = result.target.text
    if result.target_tag:
        target = f"{target}  ({result.target_tag})"
    return f"{result.client.id} {result.current.text}  →  {target}"


def pair_json(result: PairCheckResult) -> dict:
    return {
        "verdict": result.verdict,
        "order": result.schedule.order,
        "order_summary": result.schedule.order_summary,
        "order_source": result.schedule.source,
        "execution": _pair_side_json(result.execution),
        "consensus": _pair_side_json(result.consensus),
        "reasons": result.reasons,
        "warnings": result.warnings,
        "steps": result.steps,
    }


def _pair_side_json(result: CheckResult) -> dict:
    return {
        "client": result.client.id,
        "from": result.current.text,
        "to": result.target.text,
        "target_tag": result.target_tag,
        "verdict": result.verdict,
        "reasons": result.reasons,
    }


def format_network(result: NetworkCheckResult) -> str:
    activation = "not scheduled"
    if result.schedule.activation is not None:
        activation = format_time(result.schedule.activation)
    lines = [
        result.schedule.name,
        f"Next upgrade: {result.schedule.upgrade}",
        f"Mainnet activation: {activation}",
        f"Source: {result.schedule.source}",
        "",
        _network_side(result.execution),
        _network_side(result.consensus),
        "",
        f"Verdict: {VERDICT_LABELS[result.verdict]}",
        "",
    ]
    if result.reasons:
        lines.append("Why")
        lines.extend(f"  {reason}" for reason in result.reasons)
        lines.append("")
    if result.warnings:
        lines.append("Warnings")
        lines.extend(f"  {warning}" for warning in result.warnings)
        lines.append("")
    if result.steps:
        lines.append("What to do")
        for index, step in enumerate(result.steps, start=1):
            lines.append(f"  {index}. {step}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _network_side(side) -> str:
    if side.status == "unannounced":
        requirement = "requirement not announced"
    elif side.required is not None and side.status == "above":
        requirement = f"announced {side.required.text}, installed is newer"
    elif side.required is not None:
        requirement = f"required {side.required.text}"
    else:
        requirement = side.status
    return f"{side.client.id} {side.installed.text}  {side.client.role}  {requirement}"


def network_json(result: NetworkCheckResult) -> dict:
    activation = None
    if result.schedule.activation is not None:
        activation = format_time(result.schedule.activation)
    return {
        "network": result.schedule.id,
        "name": result.schedule.name,
        "upgrade": result.schedule.upgrade,
        "activation": activation,
        "source": result.schedule.source,
        "order": result.schedule.order,
        "execution": _network_side_json(result.execution),
        "consensus": _network_side_json(result.consensus),
        "verdict": result.verdict,
        "reasons": result.reasons,
        "warnings": result.warnings,
        "steps": result.steps,
    }


def _network_side_json(side) -> dict:
    return {
        "client": side.client.id,
        "version": side.installed.text,
        "required": None if side.required is None else side.required.text,
        "status": side.status,
    }


def check_json(result: CheckResult) -> dict:
    return {
        "client": result.client.id,
        "name": result.client.name,
        "role": result.client.role,
        "github": result.client.github,
        "from": result.current.text,
        "to": result.target.text,
        "target_tag": result.target_tag,
        "verdict": result.verdict,
        "reasons": result.reasons,
        "warnings": result.warnings,
        "releases": [
            {
                "tag": item.tag,
                "name": item.name,
                "published_at": item.published_at,
                "prerelease": item.prerelease,
                "url": item.url,
            }
            for item in result.releases
        ],
        "steps": result.steps,
        "catalog_fetched_at": format_time(result.fetched_at),
        "catalog_stale": result.stale,
    }


_EFFECT_LABELS = {
    "removed": "Removed",
    "renamed": "Renamed",
    "deprecated": "Deprecated",
    "default": "Default changed",
}


def _setting_label(flag: str, value: str, line: int | None) -> str:
    shown = flag if value == "" else f"{flag}={value}"
    if line:
        return f"{shown}  (line {line})"
    return shown


def format_scan(result: ScanResult) -> str:
    target = result.target.text
    if result.target_tag:
        target = f"{target}  ({result.target_tag})"
    lines = [
        f"{result.client.name}  {result.client.role}",
        result.client.github,
        "",
        f"{result.current.text}  →  {target}",
        f"Config: {result.config_path}  ({result.config_format})",
        "",
        f"Verdict: {VERDICT_LABELS[result.verdict]}",
        "",
    ]
    if result.reasons:
        lines.append("Why")
        lines.extend(f"  {reason}" for reason in result.reasons)
        lines.append("")
    if result.warnings:
        lines.append("Warnings")
        lines.extend(f"  {warning}" for warning in result.warnings)
        lines.append("")
    current_effect = None
    for finding in result.findings:
        if finding.effect != current_effect:
            current_effect = finding.effect
            lines.append(_EFFECT_LABELS[finding.effect])
        lines.append(f"  {_finding_line(finding)}")
        if finding.action:
            lines.append(f"  {finding.action}")
        lines.append(f"  {finding.source}")
        lines.append("")
    if result.uncovered:
        lines.append("Not covered")
        lines.append("  The flag catalog does not cover these settings.")
        for setting in result.uncovered:
            lines.append(f"  {_setting_label(setting.flag, setting.value, setting.line)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _finding_line(finding: FlagFinding) -> str:
    label = _setting_label(finding.flag, finding.value, finding.line)
    change = f"in {finding.version.text}"
    if finding.replacement:
        change = f"{change}  →  {finding.replacement}"
    return f"{label}  {change}"


def scan_json(result: ScanResult) -> dict:
    return {
        "client": result.client.id,
        "name": result.client.name,
        "role": result.client.role,
        "github": result.client.github,
        "from": result.current.text,
        "to": result.target.text,
        "target_tag": result.target_tag,
        "config": result.config_path,
        "format": result.config_format,
        "verdict": result.verdict,
        "reasons": result.reasons,
        "warnings": result.warnings,
        "findings": [_finding_json(item) for item in result.findings],
        "uncovered": [_setting_json(item) for item in result.uncovered],
    }


def _finding_json(finding: FlagFinding) -> dict:
    return {
        "effect": finding.effect,
        "flag": finding.flag,
        "value": finding.value,
        "line": finding.line,
        "version": finding.version.text,
        "replacement": finding.replacement,
        "action": finding.action,
        "source": finding.source,
    }


def _setting_json(setting: Setting) -> dict:
    return {"flag": setting.flag, "value": setting.value, "line": setting.line}


def format_versions(
    rows: list[tuple[Client, datetime | None, list[Release] | None]],
    now: datetime | None = None,
) -> str:
    moment = now or datetime.now(timezone.utc)
    lines = [f"{'Client':<12} {'Role':<10} {'Latest':<18} {'Published':<12} Notes"]
    stale = False
    for client, fetched_at, releases in rows:
        if releases is None or fetched_at is None:
            lines.append(f"{client.id:<12} {client.role:<10} {'-':<18} {'-':<12} no catalog")
            continue
        is_stale = moment - fetched_at > timedelta(days=5)
        stale = stale or is_stale
        stable = latest_stable(releases)
        ahead = newer_prerelease(releases, stable)
        if stable is None:
            latest = "-"
            published = "-"
        else:
            latest = stable.tag
            published = _day(stable.published_at)
        notes = f"prerelease {ahead.tag} is newer" if ahead else ""
        if is_stale:
            notes = (notes + "; " if notes else "") + "catalog is stale"
        lines.append(f"{client.id:<12} {client.role:<10} {latest:<18} {published:<12} {notes}".rstrip())
    if stale:
        lines.insert(0, "Release catalog is more than 5 days old. Run: chaindiff refresh")
        lines.insert(1, "")
    return "\n".join(lines) + "\n"


def versions_json(
    rows: list[tuple[Client, datetime | None, list[Release] | None]],
    now: datetime | None = None,
) -> dict:
    moment = now or datetime.now(timezone.utc)
    clients = []
    for client, fetched_at, releases in rows:
        if releases is None or fetched_at is None:
            clients.append(
                {
                    "id": client.id,
                    "name": client.name,
                    "role": client.role,
                    "github": client.github,
                    "catalog": None,
                }
            )
            continue
        stable = latest_stable(releases)
        ahead = newer_prerelease(releases, stable)
        clients.append(
            {
                "id": client.id,
                "name": client.name,
                "role": client.role,
                "github": client.github,
                "fetched_at": format_time(fetched_at),
                "stale": moment - fetched_at > timedelta(days=5),
                "latest_stable": None
                if stable is None
                else {
                    "tag": stable.tag,
                    "version": stable.version.text,
                    "published_at": stable.published_at,
                    "url": stable.url,
                },
                "prerelease_ahead": None
                if ahead is None
                else {"tag": ahead.tag, "published_at": ahead.published_at, "url": ahead.url},
            }
        )
    return {"clients": clients}
