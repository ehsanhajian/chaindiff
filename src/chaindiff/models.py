"""Shared records for clients, releases, and advisories."""

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


@dataclass(frozen=True)
class Client:
    id: str
    name: str
    role: str
    github: str
    versioning: str


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
