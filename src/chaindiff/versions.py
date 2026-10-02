"""Parse and compare client release tags."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import total_ordering

_TAG = re.compile(r"^v?(?P<num>\d+(?:\.\d+)*)(?:-(?P<pre>[0-9A-Za-z.-]+))?$")
_TOKEN = re.compile(r"^([A-Za-z]+)(\d+)$")
_PRE_WORD = re.compile(
    r"(?i)(?:^|[^A-Za-z])(alpha|beta|rc|preview|dev|nightly|unstable)(?:[^A-Za-z]|$)"
)
_NAMED_RANK = {
    "a": 0,
    "alpha": 0,
    "b": 1,
    "beta": 1,
    "c": 2,
    "rc": 2,
    "preview": 3,
    "dev": 4,
    "nightly": 5,
    "unstable": 6,
}


def _rank(name: str) -> int:
    return _NAMED_RANK.get(name.lower(), 50)


def _pre_tuple(pre: str) -> tuple[tuple[int, int], ...]:
    parts: list[tuple[int, int]] = []
    for token in pre.split("."):
        if not token or token.lower() == "stable":
            continue
        matched = _TOKEN.fullmatch(token)
        if matched:
            parts.append((_rank(matched.group(1)), int(matched.group(2))))
        elif token.isdigit():
            parts.append((100, int(token)))
        else:
            parts.append((_rank(token), 0))
    return tuple(parts)


def _strip_trailing_zeros(numbers: tuple[int, ...]) -> tuple[int, ...]:
    trimmed = numbers
    while len(trimmed) > 1 and trimmed[-1] == 0:
        trimmed = trimmed[:-1]
    return trimmed


@total_ordering
@dataclass(frozen=True, eq=False)
class Version:
    numbers: tuple[int, ...]
    pre: tuple[tuple[int, int], ...] | None
    text: str = field(compare=False, hash=False)

    def _identity(self) -> tuple[tuple[int, ...], tuple[tuple[int, int], ...] | None]:
        return (_strip_trailing_zeros(self.numbers), self.pre)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._identity() == other._identity()

    def __hash__(self) -> int:
        return hash(self._identity())

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        left = _strip_trailing_zeros(self.numbers)
        right = _strip_trailing_zeros(other.numbers)
        size = max(len(left), len(right))
        left_nums = left + (0,) * (size - len(left))
        right_nums = right + (0,) * (size - len(right))
        if left_nums != right_nums:
            return left_nums < right_nums
        if self.pre is None:
            return False
        if other.pre is None:
            return True
        return self.pre < other.pre


def parse_version(tag: str) -> Version | None:
    text = tag.strip()
    if text.lower().endswith("-stable"):
        text = text[: -len("-stable")]
    matched = _TAG.fullmatch(text)
    if not matched:
        return None
    numbers = tuple(int(part) for part in matched.group("num").split("."))
    # Erigon used four-digit date tags (v2022.10.01). They are not semver and
    # must not sort above the 2.x/3.x line. Two-digit calver (26.9.0) stays valid.
    if numbers[0] >= 2000:
        return None
    if len(numbers) < 3:
        numbers = numbers + (0,) * (3 - len(numbers))
    pre_text = matched.group("pre")
    pre = None
    if pre_text and pre_text.lower() != "stable":
        pre = _pre_tuple(pre_text)
        if not pre:
            pre = None
    display_numbers = ".".join(str(part) for part in numbers)
    display = display_numbers if pre is None else f"{display_numbers}-{pre_text}"
    return Version(numbers=numbers, pre=pre, text=display)


def explain_unparsed(tag: str) -> str:
    text = tag.strip()
    if text.lower().endswith("-stable"):
        text = text[: -len("-stable")]
    matched = _TAG.fullmatch(text)
    if matched and int(matched.group("num").split(".")[0]) >= 2000:
        return (
            f"'{tag}' is a date-based release tag. "
            "ChainDiff does not compare those with the current release line."
        )
    return f"Cannot parse version '{tag}'."


def tag_is_prerelease(tag: str) -> bool:
    version = parse_version(tag)
    if version is not None and version.pre is not None:
        return True
    return _PRE_WORD.search(tag) is not None
