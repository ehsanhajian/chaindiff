"""Shared records for clients, releases, advisories, and flag rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from chaindiff.versions import Version

CURRENT = "current"
SAFE = "safe"
REVIEW = "review"
UNSAFE = "unsafe"
DOWNGRADE = "downgrade"
PRERELEASE = "prerelease"

VERDICT_LABELS = {
    CURRENT: "ALREADY CURRENT",
    SAFE: "SAFE",
    REVIEW: "REVIEW REQUIRED",
    UNSAFE: "NOT SAFE",
    DOWNGRADE: "DOWNGRADE",
    PRERELEASE: "PRERELEASE",
}

SEVERITIES = ("none", "note", "deprecated", "breaking")
FLAG_EFFECTS = ("removed", "renamed", "deprecated", "default")


@dataclass(frozen=True)
class Client:
    id: str
    name: str
    role: str
    github: str
    versioning: str
    tag_prefix: str = ""


@dataclass(frozen=True)
class Release:
    tag: str
    name: str
    published_at: str
    prerelease: bool
    url: str
    version: Version


@dataclass(frozen=True)
class Advisory:
    version: Version
    severity: str
    summary: str
    action: str
    source: str


@dataclass(frozen=True)
class FlagRule:
    version: Version
    flag: str
    effect: str
    action: str
    source: str
    replacement: str = ""
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class Setting:
    flag: str
    value: str
    line: int | None


@dataclass(frozen=True)
class FlagFinding:
    effect: str
    flag: str
    version: Version
    action: str
    source: str
    replacement: str
    value: str
    line: int | None


@dataclass
class ScanResult:
    client: Client
    current: Version
    target: Version
    target_tag: str | None
    config_path: str
    config_format: str
    verdict: str
    reasons: list[str]
    warnings: list[str]
    findings: list[FlagFinding]
    uncovered: list[Setting]


@dataclass(frozen=True)
class NetworkSchedule:
    id: str
    name: str
    upgrade: str
    activation: datetime | None
    source: str
    summary: str
    order: str | None
    order_summary: str
    warning: str
    required_execution: dict[str, Version]
    required_consensus: dict[str, Version]


@dataclass(frozen=True)
class NetworkSide:
    client: Client
    installed: Version
    required: Version | None
    status: str


@dataclass
class NetworkCheckResult:
    schedule: NetworkSchedule
    execution: NetworkSide
    consensus: NetworkSide | None
    verdict: str
    reasons: list[str]
    warnings: list[str]
    steps: list[str]


@dataclass
class PairCheckResult:
    execution: CheckResult
    consensus: CheckResult
    schedule: NetworkSchedule
    verdict: str
    reasons: list[str]
    warnings: list[str]
    steps: list[str]


@dataclass
class CheckResult:
    client: Client
    current: Version
    target: Version
    target_tag: str | None
    verdict: str
    reasons: list[str]
    warnings: list[str]
    releases: list[Release]
    steps: list[str]
    fetched_at: datetime
    stale: bool
