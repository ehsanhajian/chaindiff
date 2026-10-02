from datetime import datetime, timezone

from chaindiff.evaluate import evaluate, latest_stable, newer_prerelease
from chaindiff.models import (
    CURRENT,
    DOWNGRADE,
    PRERELEASE,
    REVIEW,
    SAFE,
    UNSAFE,
    Advisory,
    Client,
    Release,
)
from chaindiff.versions import parse_version

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)
FRESH = datetime(2026, 10, 1, tzinfo=timezone.utc)
STALE = datetime(2026, 9, 1, tzinfo=timezone.utc)


def version(tag: str):
    parsed = parse_version(tag)
    assert parsed is not None
    return parsed


def release(tag: str, *, name: str | None = None, published: str = "2026-01-01T00:00:00Z") -> Release:
    parsed = version(tag)
    return Release(
        tag=tag,
        name=name or tag,
        published_at=published,
        prerelease=parsed.pre is not None,
        url=f"https://example.test/{tag}",
        version=parsed,
    )


def geth(versioning: str = "semver") -> Client:
    return Client(
        id="geth",
        name="Geth",
        role="execution",
        github="ethereum/go-ethereum",
        versioning=versioning,
    )


def advisory(tag: str, severity: str, summary: str = "Reviewed.", action: str = "") -> Advisory:
    if severity in ("breaking", "deprecated") and not action:
        action = "Change the config."
    return Advisory(
        version=version(tag),
        severity=severity,
        summary=summary,
        action=action,
        source="https://example.test/notes",
    )


def check(current: str, target: str, releases: list[Release], **kwargs):
    fetched = kwargs.pop("fetched", FRESH)
    return evaluate(
        client=kwargs.pop("client", geth()),
        releases=releases,
        advisories=kwargs.pop("advisories", []),
        current=version(current),
        target=version(target),
        target_is_latest=kwargs.pop("latest", False),
        fetched_at=fetched,
        now=kwargs.pop("now", NOW),
    )


def test_latest_stable_skips_a_newer_prerelease():
    releases = [release("v1.2.0"), release("v1.3.0-rc.1")]
    stable = latest_stable(releases)
    assert stable is not None and stable.tag == "v1.2.0"
    ahead = newer_prerelease(releases, stable)
    assert ahead is not None and ahead.tag == "v1.3.0-rc.1"


def test_same_version_is_current():
    result = check("v1.2.0", "1.2.0", [release("v1.2.0")])
    assert result.verdict == CURRENT


def test_downgrade_is_not_an_upgrade():
    result = check("v1.3.0", "v1.2.0", [release("v1.2.0"), release("v1.3.0")])
    assert result.verdict == DOWNGRADE


def test_unreviewed_patch_requires_review():
    result = check("v1.2.0", "v1.2.1", [release("v1.2.0"), release("v1.2.1")])
    assert result.verdict == REVIEW
    assert result.releases[0].tag == "v1.2.1"


def test_reviewed_patch_is_safe():
    result = check(
        "v1.2.0",
        "v1.2.1",
        [release("v1.2.0"), release("v1.2.1", name="Security update")],
        advisories=[advisory("v1.2.1", "none")],
    )
    assert result.verdict == SAFE
    assert any("security" in warning.lower() for warning in result.warnings)


def test_breaking_advisory_is_unsafe():
    result = check(
        "v1.2.0",
        "v1.2.1",
        [release("v1.2.0"), release("v1.2.1")],
        advisories=[advisory("v1.2.1", "breaking", summary="Startup flag removed.", action="Delete --old.")],
    )
    assert result.verdict == UNSAFE
    assert any("Delete --old." in step for step in result.steps)


def test_deprecation_stays_review_required():
    result = check(
        "v1.2.0",
        "v1.2.1",
        [release("v1.2.0"), release("v1.2.1")],
        advisories=[advisory("v1.2.1", "deprecated", summary="--cache moved.", action="Use --state.cache.")],
    )
    assert result.verdict == REVIEW


def test_note_does_not_block_a_safe_verdict():
    result = check(
        "v1.2.0",
        "v1.2.1",
        [release("v1.2.0"), release("v1.2.1")],
        advisories=[advisory("v1.2.1", "note", action="Read the new metric name.")],
    )
    assert result.verdict == SAFE
    assert any("metric" in step for step in result.steps)


def test_unreviewed_semver_major_is_unsafe():
    result = check(
        "v1.9.0",
        "v2.0.1",
        [release("v1.9.0"), release("v2.0.0"), release("v2.0.1")],
    )
    assert result.verdict == UNSAFE
    assert any(reason.startswith("v2.0.0") for reason in result.reasons)
    assert not any(reason.startswith("v2.0.1 raises") for reason in result.reasons)


def test_reviewed_major_does_not_block_later_patches():
    result = check(
        "v1.9.0",
        "v2.0.1",
        [release("v1.9.0"), release("v2.0.0"), release("v2.0.1")],
        advisories=[advisory("v2.0.0", "none")],
    )
    assert result.verdict == REVIEW


def test_calver_year_bump_is_not_an_automatic_break():
    result = check(
        "25.9.0",
        "26.1.0",
        [release("25.9.0"), release("26.1.0")],
        client=Client("besu", "Besu", "execution", "besu-eth/besu", "calver"),
    )
    assert result.verdict == REVIEW
    assert not any("major" in reason for reason in result.reasons)


def test_prerelease_target_is_refused():
    result = check("v1.2.0", "v1.3.0-rc.1", [release("v1.2.0"), release("v1.3.0-rc.1")])
    assert result.verdict == PRERELEASE


def test_gap_in_the_catalog_is_not_safe():
    result = check("v1.0.0", "v1.2.0", [release("v1.0.0")])
    assert result.verdict == REVIEW
    assert any("No catalog releases" in reason for reason in result.reasons)


def test_stale_latest_cannot_be_safe():
    result = check(
        "v1.2.0",
        "v1.2.1",
        [release("v1.2.0"), release("v1.2.1")],
        advisories=[advisory("v1.2.1", "none")],
        latest=True,
        fetched=STALE,
    )
    assert result.verdict == REVIEW


def test_stale_explicit_target_can_still_be_safe():
    result = check(
        "v1.2.0",
        "v1.2.1",
        [release("v1.2.0"), release("v1.2.1")],
        advisories=[advisory("v1.2.1", "none")],
        latest=False,
        fetched=STALE,
    )
    assert result.verdict == SAFE
    assert any("5 days" in warning for warning in result.warnings)


def test_stale_catalog_does_not_treat_you_as_current():
    result = check("v1.2.1", "v1.2.1", [release("v1.2.1")], latest=True, fetched=STALE)
    assert result.verdict == REVIEW
    assert result.steps == ["Refresh the release catalog, then run this check again."]
