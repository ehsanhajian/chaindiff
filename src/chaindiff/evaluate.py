"""Decide whether a client upgrade is safe."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from chaindiff.models import (
    CURRENT,
    DOWNGRADE,
    PRERELEASE,
    REVIEW,
    SAFE,
    UNSAFE,
    Advisory,
    CheckResult,
    Client,
    Release,
)
from chaindiff.versions import Version

STALE_AFTER = timedelta(days=5)
_SECURITY = re.compile(r"(?i)\b(security|cve-\d+|vulnerability)\b")
_SEVERITY_RANK = {"none": 0, "note": 1, "deprecated": 2, "breaking": 3}


def latest_stable(releases: list[Release]) -> Release | None:
    stable = [item for item in releases if not item.prerelease]
    if not stable:
        return None
    return max(stable, key=lambda item: (item.version, item.published_at))


def newer_prerelease(releases: list[Release], stable: Release | None) -> Release | None:
    if stable is None:
        return None
    newer = [item for item in releases if item.prerelease and item.version > stable.version]
    if not newer:
        return None
    return max(newer, key=lambda item: (item.version, item.published_at))


def advisories_for(advisories: list[Advisory], version: Version) -> list[Advisory]:
    return [item for item in advisories if item.version == version]


def _worst(advisories: list[Advisory]) -> Advisory | None:
    if not advisories:
        return None
    return max(advisories, key=lambda item: _SEVERITY_RANK[item.severity])


def _backup_steps() -> list[str]:
    return [
        "Read the release notes for every release in this range.",
        "Back up the data directory, or snapshot the disk, before changing the binary.",
        "Keep the current binary so you can roll back.",
        "Upgrade this client only. Confirm it is healthy before changing the client paired with it.",
        "If the release notes require an order for a network upgrade, follow that order.",
        "If the node fails to start or stops syncing, restore the previous binary.",
    ]


def _plan_steps(verdict: str, hops: list[Release], advisories: list[Advisory]) -> list[str]:
    if verdict == CURRENT:
        return ["No upgrade to plan."]
    if verdict == DOWNGRADE:
        return ["Stay on the newer version you already run."]
    steps: list[str] = []
    for hop in sorted(hops, key=lambda item: item.version):
        for advisory in advisories_for(advisories, hop.version):
            if advisory.severity in ("breaking", "deprecated") or (
                advisory.severity == "note" and advisory.action
            ):
                steps.append(f"{hop.tag}: {advisory.action} ({advisory.source})")
    steps.extend(_backup_steps())
    return steps


def _choose_target(releases: list[Release], target: Version) -> Release | None:
    matches = [item for item in releases if item.version == target]
    if not matches:
        return None
    if target.pre is None:
        stable = [item for item in matches if not item.prerelease]
        if stable:
            matches = stable
    return max(matches, key=lambda item: item.published_at)


def _major_crossings(client: Client, current: Version, hops: list[Release]) -> list[Release]:
    """First release in range that enters each new semver major."""
    if client.versioning != "semver":
        return []
    crossings: list[Release] = []
    seen: set[int] = set()
    for hop in sorted(hops, key=lambda item: item.version):
        major = hop.version.numbers[0]
        if major <= current.numbers[0] or major in seen:
            continue
        seen.add(major)
        crossings.append(hop)
    return crossings


def evaluate(
    *,
    client: Client,
    releases: list[Release],
    advisories: list[Advisory],
    current: Version,
    target: Version,
    target_is_latest: bool,
    fetched_at: datetime,
    now: datetime,
) -> CheckResult:
    warnings: list[str] = []
    reasons: list[str] = []
    stale = now - fetched_at > STALE_AFTER
    chosen = _choose_target(releases, target)
    target_tag = chosen.tag if chosen else None

    if not any(item.version == current and not item.prerelease for item in releases):
        warnings.append(
            "The current version is not a known stable tag. Comparison uses the version number only."
        )
    if chosen is None:
        warnings.append("The target version is not in the catalog. The hop list may be incomplete.")

    def finish(verdict: str, hops: list[Release]) -> CheckResult:
        if stale and not (target_is_latest and verdict == REVIEW):
            warnings.append("The release catalog is more than 5 days old.")
        return CheckResult(
            client=client,
            current=current,
            target=target,
            target_tag=target_tag,
            verdict=verdict,
            reasons=reasons,
            warnings=warnings,
            releases=hops,
            steps=_plan_steps(verdict, hops, advisories),
            fetched_at=fetched_at,
            stale=stale,
        )

    if current == target:
        reasons.append("The target is the version you already run.")
        if stale and target_is_latest:
            reasons.append(
                "The release catalog is more than 5 days old, so a newer stable release may exist."
            )
            result = finish(REVIEW, [])
            result.steps = ["Refresh the release catalog, then run this check again."]
            return result
        return finish(CURRENT, [])

    if target < current:
        reasons.append("The target is older than the version you already run.")
        return finish(DOWNGRADE, [])

    include_prereleases = target.pre is not None or (chosen is not None and chosen.prerelease)
    hops = [
        item
        for item in releases
        if current < item.version <= target and (include_prereleases or not item.prerelease)
    ]
    hops.sort(key=lambda item: item.version, reverse=True)

    breaking: list[tuple[Release, Advisory]] = []
    deprecated: list[tuple[Release, Advisory]] = []
    unreviewed: list[Release] = []
    for hop in hops:
        matched = advisories_for(advisories, hop.version)
        if not matched:
            unreviewed.append(hop)
            continue
        worst = _worst(matched)
        if worst is not None and worst.severity == "breaking":
            breaking.append((hop, worst))
        elif worst is not None and worst.severity == "deprecated":
            deprecated.append((hop, worst))

    unreviewed_versions = {hop.version for hop in unreviewed}
    unreviewed_majors = [
        hop
        for hop in _major_crossings(client, current, hops)
        if hop.version in unreviewed_versions
    ]

    for hop, advisory in sorted(breaking, key=lambda item: item[0].version):
        reasons.append(f"{hop.tag} is breaking: {advisory.summary}")
    for hop in unreviewed_majors:
        reasons.append(f"{hop.tag} raises the major version and has no review. Treat it as breaking.")
    if len(unreviewed) == 1 and len(hops) == 1:
        reasons.append("The release in this range has no advisory yet.")
    elif len(unreviewed) == 1:
        reasons.append(f"1 of {len(hops)} releases in this range has no advisory yet.")
    elif unreviewed and len(unreviewed) == len(hops):
        reasons.append(f"None of the {len(hops)} releases in this range has an advisory yet.")
    elif unreviewed:
        reasons.append(f"{len(unreviewed)} of {len(hops)} releases in this range have no advisory yet.")
    for hop, advisory in sorted(deprecated, key=lambda item: item[0].version):
        reasons.append(f"{hop.tag} deprecates something you may still be using: {advisory.summary}")
    if not hops:
        reasons.append("No catalog releases sit strictly between these versions.")

    for hop in hops:
        if _SECURITY.search(hop.name):
            warnings.append(f"{hop.tag}: the release title mentions a security fix.")

    target_is_pre = target.pre is not None or (chosen is not None and chosen.prerelease)
    if target_is_pre:
        reasons.append("The target is a prerelease. Do not run it on a mainnet node.")
    if breaking or unreviewed_majors:
        verdict = UNSAFE
    elif target_is_pre:
        verdict = PRERELEASE
    elif not hops or unreviewed or deprecated or (stale and target_is_latest):
        verdict = REVIEW
        if stale and target_is_latest:
            reasons.append(
                "The release catalog is more than 5 days old, so this latest-stable result may be behind."
            )
    else:
        verdict = SAFE
        reasons.append("Every release in this range has been reviewed, and none is marked breaking.")

    return finish(verdict, hops)
