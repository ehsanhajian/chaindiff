"""Read an installed client version from a binary or an image tag.

The version command and the shape of its output come from each client's
source. A Docker reference is parsed only. Nothing is pulled or started.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable

from chaindiff.versions import Version, parse_version

# Geth, op-geth, bor, heimdall, and BSC use a version subcommand. The other
# confirmed clients print and exit on --version. A wrong flag can start the
# node, so there is no fallback.
_VERSION_ARGV = {
    "geth": ("version",),
    "op-geth": ("version",),
    "nethermind": ("--version",),
    "erigon": ("--version",),
    "besu": ("--version",),
    "reth": ("--version",),
    "lighthouse": ("--version",),
    "prysm": ("--version",),
    "teku": ("--version",),
    "nimbus": ("--version",),
    # Bor v2.10.2 registers `version` and prints "Version: <major.minor.patch>".
    # heimdalld v0.12.1 `version` prints that build version alone.
    "bor": ("version",),
    "heimdall": ("version",),
    # BSC v1.7.8 registers `version` and prints "Version: <major.minor.patch>".
    "bsc": ("version",),
    # avalanchego v1.15.1 --version prints and exits before the node starts.
    "avalanchego": ("--version",),
    # l2geth scroll-v5.10.2 registers `version` and prints "Version: 5.10.2-mainnet".
    "l2geth": ("version",),
}

# Tags that name a channel, not a release. Exact match only.
_UNVERSIONED_TAGS = frozenset(
    {"latest", "stable", "nightly", "master", "main", "develop", "edge", "unstable", "dev"}
)

# Three numeric components, plus a known prerelease. A shorter tag such as
# 1.17 is left unread: parse_version would otherwise pad it to 1.17.0.
_PRECISE_VERSION = re.compile(
    r"(?<![A-Za-z0-9.])"
    r"(v?\d+\.\d+\.\d+(?:-(?:alpha|beta|rc|preview|dev|nightly|unstable)(?:[.-]\d+)*)?)"
    r"(?![.\d])",
    re.IGNORECASE,
)
_VERSION_LINE = re.compile(r"(?m)^Version:[ \t]*(\S+)")
_RELEASE_TEXT = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")
_TRAILING_COMMIT = re.compile(r"-[0-9a-fA-F]{6,}$")


def version_argv(client_id: str) -> tuple[str, ...] | None:
    """Return the version command, or None when the binary format is unknown.

    An unknown client is left unread. Guessing ``--version`` can start the node.
    """
    return _VERSION_ARGV.get(client_id)


def check_command(client_id: str, version: Version | None) -> str:
    shown = version.text if version is not None else "<installed>"
    return f"chaindiff check --client {client_id} --from {shown}"


def normalize_release(raw: str) -> Version | None:
    """Return a release version, or None when the text is not one precise release.

    Commit suffixes and Nimbus's ``stateofus`` build word are not versions.
    """
    text = raw.strip().strip("'\"")
    if text[:1] in ("v", "V"):
        text = text[1:]
    text = text.split("+", 1)[0]
    if text.lower().endswith("-stateofus"):
        text = text[: -len("-stateofus")]
    text = _TRAILING_COMMIT.sub("", text)
    if _RELEASE_TEXT.fullmatch(text) is None:
        return None
    return parse_version(text)


def version_from_output(client_id: str, text: str) -> Version | None:
    extractor = _EXTRACTORS.get(client_id)
    if extractor is None:
        return None
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    return _one_version(extractor(cleaned))


def version_from_image(ref: str) -> Version | None:
    tag = image_tag(ref)
    if tag is None or tag.lower() in _UNVERSIONED_TAGS:
        return None
    found = [normalize_release(match) for match in _PRECISE_VERSION.findall(tag)]
    versions = [item for item in found if item is not None]
    unique: list[Version] = []
    for version in versions:
        if version not in unique:
            unique.append(version)
    if len(unique) != 1 or len(versions) != len(found):
        return None
    return unique[0]


def image_tag(ref: str) -> str | None:
    """Return the tag, ignoring a registry port and a digest.

    ``localhost:5000/client-go`` has no tag. The colon is a port because it
    sits before the last slash.
    """
    text = ref.strip().split("@", 1)[0].strip()
    if not text:
        return None
    name = text.rsplit("/", 1)[-1]
    if ":" not in name:
        return None
    tag = name.split(":", 1)[1]
    return tag or None


def read_binary_output(
    path: str,
    argv: tuple[str, ...],
    *,
    timeout: float = 10,
) -> str | None:
    """Run ``path`` with ``argv`` and return combined output. No shell."""
    try:
        completed = subprocess.run(
            [path, *argv],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    stdout = completed.stdout.decode("utf-8", "replace")
    stderr = completed.stderr.decode("utf-8", "replace")
    return stdout + stderr


def format_detect(
    *,
    client_id: str,
    client_name: str,
    version: Version | None,
    source: str,
) -> str:
    command = check_command(client_id, version)
    if version is None:
        if source == "binary":
            lead = f"Could not read a {client_name} version from that binary."
        else:
            lead = f"Could not read a {client_name} version from that image tag."
        return f"{lead}\n{command}\n"
    return f"{client_id} {version.text}\n{command}\n"


def detect_json(
    *,
    client_id: str,
    version: Version | None,
) -> dict[str, object]:
    return {
        "client": client_id,
        "detected": version is not None,
        "version": None if version is None else version.text,
        "check": check_command(client_id, version),
    }


def _one_version(raws: list[str]) -> Version | None:
    if not raws:
        return None
    found: list[Version] = []
    for raw in raws:
        version = normalize_release(raw)
        if version is None:
            return None
        if version not in found:
            found.append(version)
    if len(found) != 1:
        return None
    return found[0]


def _version_lines(text: str) -> list[str]:
    return _VERSION_LINE.findall(text)


def _slash_version(client: str, text: str) -> list[str]:
    pattern = re.compile(
        rf"(?m)^{client}/v?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)(?:/|$)",
        re.IGNORECASE,
    )
    return pattern.findall(text)


def _erigon(text: str) -> list[str]:
    # urfave prints "<basename> version <version>".
    return re.findall(r"(?m)^\S+ version (\S+)[ \t]*$", text)


def _reth(text: str) -> list[str]:
    found = _version_lines(text)
    found.extend(re.findall(r"(?m)^Reth[ \t]+(\S+)", text))
    found.extend(
        re.findall(r"(?m)^(\d+\.\d+\.\d+(?:-dev)?)[ \t]+\([0-9a-fA-F]+\)[ \t]*$", text)
    )
    return found


def _lighthouse(text: str) -> list[str]:
    return re.findall(r"(?m)^(?:Lighthouse/)?(v\d+\.\d+\.\d+\S*)", text)


def _prysm(text: str) -> list[str]:
    return re.findall(
        r"(?im)^(?:\S+[ \t]+)?version[ \t]+Prysm/v?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)",
        text,
    )


def _l2geth(text: str) -> list[str]:
    # VersionMeta is "mainnet". It is not a prerelease, and the Go version is a later line.
    return re.findall(r"(?m)^Version:[ \t]*(\d+\.\d+\.\d+)(?:-mainnet)?[ \t]*$", text)


def _avalanchego(text: str) -> list[str]:
    # The database version and the Go version are also in this line.
    return re.findall(
        r"(?m)^avalanchego/v?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)",
        text,
    )


def _plain_version(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) == 1:
        return lines
    return []


def _nimbus(text: str) -> list[str]:
    banner = re.findall(r"(?im)^Nimbus beacon node[ \t]+(\S+)[ \t]*$", text)
    if banner:
        return banner
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) == 1:
        return lines
    return []


_EXTRACTORS: dict[str, Callable[[str], list[str]]] = {
    "geth": _version_lines,
    "op-geth": _version_lines,
    "nethermind": _version_lines,
    "erigon": _erigon,
    "besu": lambda text: _slash_version("besu", text),
    "reth": _reth,
    "lighthouse": _lighthouse,
    "prysm": _prysm,
    "teku": lambda text: _slash_version("teku", text),
    "nimbus": _nimbus,
    "bor": _version_lines,
    "heimdall": _plain_version,
    "bsc": _version_lines,
    "avalanchego": _avalanchego,
    "l2geth": _l2geth,
}
