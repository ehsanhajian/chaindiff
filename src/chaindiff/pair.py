"""One verdict and one plan for an execution client and a consensus client.

Each side uses its own release reviews. Nothing here says that a version of
one client works with a version of the other. Upgrade order comes from the
network schedule, which is sourced from the announcement.
"""

from __future__ import annotations

from chaindiff.models import (
    CURRENT,
    DOWNGRADE,
    PRERELEASE,
    REVIEW,
    SAFE,
    UNSAFE,
    VERDICT_LABELS,
    CheckResult,
    NetworkSchedule,
    PairCheckResult,
)

# Higher wins. A breaking range outranks a prerelease target.
_RANK = {
    CURRENT: 0,
    SAFE: 1,
    REVIEW: 2,
    PRERELEASE: 3,
    DOWNGRADE: 4,
    UNSAFE: 5,
}

_GENERIC_STEPS = {
    "Read the release notes for every release in this range.",
    "Back up the data directory, or snapshot the disk, before changing the binary.",
    "Keep the current binary so you can roll back.",
    "Upgrade this client only. Confirm it is healthy before changing the client paired with it.",
    "If the release notes require an order for a network upgrade, follow that order.",
    "If the node fails to start or stops syncing, restore the previous binary.",
    "No upgrade to plan.",
    "Stay on the newer version you already run.",
    "Refresh the release catalog, then run this check again.",
}


def combine_pair(
    execution: CheckResult,
    consensus: CheckResult,
    schedule: NetworkSchedule,
) -> PairCheckResult:
    verdict = _verdict(execution, consensus)
    reasons = [_side_reason(execution), _side_reason(consensus), schedule.order_summary]
    if verdict == REVIEW:
        reasons.append("This pair stays review required until every release in both ranges has a review.")
    elif verdict == SAFE:
        reasons.append("Both ranges have been reviewed, and none is marked breaking.")
    warnings: list[str] = []
    for result in (execution, consensus):
        for warning in result.warnings:
            if warning not in warnings:
                warnings.append(warning)
    if schedule.warning and schedule.warning not in warnings:
        warnings.append(schedule.warning)
    return PairCheckResult(
        execution=execution,
        consensus=consensus,
        schedule=schedule,
        verdict=verdict,
        reasons=reasons,
        warnings=warnings,
        steps=_steps(execution, consensus, schedule),
    )


def _verdict(execution: CheckResult, consensus: CheckResult) -> str:
    if execution.verdict == CURRENT and consensus.verdict == CURRENT:
        return CURRENT
    return max((execution, consensus), key=lambda result: _RANK[result.verdict]).verdict


def _side_reason(result: CheckResult) -> str:
    detail = " ".join(result.reasons)
    return (
        f"{result.client.name} {result.current.text} → {result.target.text}: "
        f"{VERDICT_LABELS[result.verdict]}. {detail}"
    )


def _steps(
    execution: CheckResult,
    consensus: CheckResult,
    schedule: NetworkSchedule,
) -> list[str]:
    order = f"{schedule.order_summary} ({schedule.source})"
    if execution.verdict == CURRENT and consensus.verdict == CURRENT:
        return ["No upgrade to plan.", order]
    steps = [order]
    for result in (execution, consensus):
        if result.verdict == DOWNGRADE:
            steps.append(f"Stay on {result.client.name} {result.current.text}.")
        for step in result.steps:
            if step in _GENERIC_STEPS:
                continue
            steps.append(f"{result.client.name}: {step}")
    steps.extend(
        [
            "Read the release notes for every release in both ranges.",
            "Back up the data directory, or snapshot the disk, before changing a binary.",
            "Keep the current binaries so you can roll back.",
            "Upgrade one client at a time. Confirm it is healthy before changing the other.",
            "If a node fails to start or stops syncing, restore the previous binary.",
        ]
    )
    return steps
