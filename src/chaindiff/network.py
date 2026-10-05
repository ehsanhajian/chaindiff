"""Compare an installed execution and consensus pair with a network upgrade."""

from __future__ import annotations

from chaindiff.catalog import format_time
from chaindiff.models import (
    CURRENT,
    PRERELEASE,
    REVIEW,
    UNSAFE,
    Client,
    NetworkCheckResult,
    NetworkSchedule,
    NetworkSide,
)
from chaindiff.versions import Version

_UNANNOUNCED = "unannounced"
_BELOW = "below"
_EXACT = "exact"
_ABOVE = "above"


def evaluate_network(
    schedule: NetworkSchedule,
    *,
    execution: Client,
    execution_version: Version,
    consensus: Client,
    consensus_version: Version,
) -> NetworkCheckResult:
    execution_side = _side(execution, execution_version, schedule.required_execution)
    consensus_side = _side(consensus, consensus_version, schedule.required_consensus)
    reasons = [schedule.summary]
    reasons.extend(_version_reasons(schedule.upgrade, execution_side, consensus_side))
    reasons.append(schedule.order_summary)
    warnings = [schedule.warning] if schedule.warning else []
    prereleases = [
        side
        for side in (execution_side, consensus_side)
        if side.installed.pre is not None
    ]
    if prereleases:
        verdict = PRERELEASE
        reasons[0:0] = [
            f"{side.client.name} {side.installed.text} is a prerelease. Don't run it on a mainnet node."
            for side in prereleases
        ]
    elif execution_side.status == _BELOW or consensus_side.status == _BELOW:
        verdict = UNSAFE
    elif (
        schedule.activation is not None
        and execution_side.status == _EXACT
        and consensus_side.status == _EXACT
    ):
        verdict = CURRENT
    else:
        verdict = REVIEW
    return NetworkCheckResult(
        schedule=schedule,
        execution=execution_side,
        consensus=consensus_side,
        verdict=verdict,
        reasons=reasons,
        warnings=warnings,
        steps=_steps(schedule, execution_side, consensus_side),
    )


def _side(client: Client, installed: Version, required_versions: dict[str, Version]) -> NetworkSide:
    required = required_versions.get(client.id)
    if required is None:
        status = _UNANNOUNCED
    elif installed < required:
        status = _BELOW
    elif installed == required:
        status = _EXACT
    else:
        status = _ABOVE
    return NetworkSide(client=client, installed=installed, required=required, status=status)


def _version_reasons(upgrade: str, execution: NetworkSide, consensus: NetworkSide) -> list[str]:
    if execution.status == _UNANNOUNCED and consensus.status == _UNANNOUNCED:
        return [
            f"No required {execution.client.name} or {consensus.client.name} version has been announced for {upgrade}."
        ]
    return [_one_reason(upgrade, execution), _one_reason(upgrade, consensus)]


def _one_reason(upgrade: str, side: NetworkSide) -> str:
    installed = f"{side.client.name} {side.installed.text}"
    if side.status == _UNANNOUNCED:
        return f"No required {side.client.name} version has been announced for {upgrade}."
    assert side.required is not None
    required = side.required.text
    if side.status == _BELOW:
        return f"{installed} is older than the announced requirement {required}."
    if side.status == _EXACT:
        return f"{installed} is the announced requirement."
    return f"{installed} is newer than the announced requirement {required}. A newer tag is not treated as that requirement."


def _steps(
    schedule: NetworkSchedule,
    execution: NetworkSide,
    consensus: NetworkSide,
) -> list[str]:
    steps = [f"Read {schedule.source}."]
    for side in (execution, consensus):
        if side.installed.pre is not None:
            steps.append(
                f"Do not run {side.client.name} {side.installed.text} on mainnet. It is a prerelease."
            )
    if schedule.activation is None:
        steps.append(
            "Mainnet activation is not scheduled. Wait for an announcement that names the time and the client releases."
        )
    else:
        steps.append(f"The announced mainnet activation is {format_time(schedule.activation)}.")
    if schedule.order == "execution-first":
        steps.append(f"Upgrade {execution.client.name} before {consensus.client.name}.")
    elif schedule.order == "consensus-first":
        steps.append(f"Upgrade {consensus.client.name} before {execution.client.name}.")
    else:
        steps.append(schedule.order_summary)
    for side in (execution, consensus):
        if side.status == _BELOW and side.required is not None:
            steps.append(
                f"Upgrade {side.client.name} to {side.required.text} before activation. "
                "A newer tag is not automatically the same requirement."
            )
    return steps
