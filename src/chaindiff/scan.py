"""Compare an operator's config with sourced flag rules.

A rule counts only when its version is after the installed release and at or
before the target. Removed, renamed, and deprecated rules apply when the file
sets that key. If the rule lists values, the setting must be one of them.
A default change applies when the file does not set it.
A key with no rule is uncovered: the scan does not call it safe.
"""

from __future__ import annotations

from chaindiff.configparse import normalize_flag
from chaindiff.models import (
    FLAG_EFFECTS,
    REVIEW,
    SAFE,
    UNSAFE,
    Client,
    FlagFinding,
    FlagRule,
    ScanResult,
    Setting,
)
from chaindiff.versions import Version

_EFFECT_ORDER = {effect: index for index, effect in enumerate(FLAG_EFFECTS)}


def scan_settings(
    *,
    client: Client,
    rules: list[FlagRule],
    settings: list[Setting],
    current: Version,
    target: Version,
    target_tag: str | None,
    config_path: str,
    config_format: str,
) -> ScanResult:
    present = {normalize_flag(setting.flag): setting for setting in settings}
    known = {normalize_flag(rule.flag) for rule in rules}
    known.update(normalize_flag(rule.replacement) for rule in rules if rule.replacement)

    findings: list[FlagFinding] = []
    for rule in rules:
        if not current < rule.version <= target:
            continue
        setting = present.get(normalize_flag(rule.flag))
        if rule.effect == "default":
            if setting is not None:
                continue
            findings.append(
                FlagFinding(
                    effect=rule.effect,
                    flag=rule.flag,
                    version=rule.version,
                    action=rule.action,
                    source=rule.source,
                    replacement=rule.replacement,
                    value="",
                    line=None,
                )
            )
            continue
        if setting is None or not _value_matches(rule, setting):
            continue
        findings.append(
            FlagFinding(
                effect=rule.effect,
                flag=setting.flag,
                version=rule.version,
                action=rule.action,
                source=rule.source,
                replacement=rule.replacement,
                value=setting.value,
                line=setting.line,
            )
        )

    findings.sort(key=lambda item: (_EFFECT_ORDER[item.effect], item.version, item.flag.lower()))
    uncovered = [setting for setting in settings if normalize_flag(setting.flag) not in known]
    verdict, reasons = _verdict(findings, uncovered)
    return ScanResult(
        client=client,
        current=current,
        target=target,
        target_tag=target_tag,
        config_path=config_path,
        config_format=config_format,
        verdict=verdict,
        reasons=reasons,
        warnings=[],
        findings=findings,
        uncovered=uncovered,
    )


def _value_matches(rule: FlagRule, setting: Setting) -> bool:
    if not rule.values:
        return True
    actual = setting.value.strip().casefold()
    return actual in {item.casefold() for item in rule.values}


def _verdict(findings: list[FlagFinding], uncovered: list[Setting]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if any(item.effect in ("removed", "renamed") for item in findings):
        reasons.append("A setting in this file was removed or renamed in this range.")
    if any(item.effect == "deprecated" for item in findings):
        reasons.append("A setting in this file is deprecated in this range.")
    if any(item.effect == "default" for item in findings):
        reasons.append("A default changed in this range, and this file does not set that key.")
    if uncovered:
        reasons.append("The flag catalog does not cover every setting in this file.")
    if any(item.effect in ("removed", "renamed") for item in findings):
        return UNSAFE, reasons
    if findings or uncovered:
        return REVIEW, reasons
    reasons.append("No setting in this file has a sourced flag change in this range.")
    return SAFE, reasons
