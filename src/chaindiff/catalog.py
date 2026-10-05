"""Load and store the client registry, release catalog, and advisories."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from chaindiff.configparse import normalize_flag
from chaindiff.models import FLAG_EFFECTS, SEVERITIES, Advisory, Client, FlagRule, NetworkSchedule, Release
from chaindiff.versions import Version, parse_version, version_from_tag

SCHEMA_VERSION = 1
_NETWORK_ORDERS = ("execution-first", "consensus-first")
_PRECISE_RELEASE = re.compile(r"v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def data_dir() -> Path:
    override = os.environ.get("CHAINDIFF_DATA")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data"


def format_time(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{path} has an unsupported schema_version")
    return payload


def load_clients() -> list[Client]:
    path = data_dir() / "clients.json"
    payload = _read_json(path)
    clients: list[Client] = []
    seen: set[str] = set()
    prefixes: set[str] = set()
    for raw in payload.get("clients", []):
        client_id = str(raw.get("id", "")).strip()
        role = raw.get("role")
        versioning = raw.get("versioning")
        github = str(raw.get("github", "")).strip()
        name = str(raw.get("name", "")).strip()
        tag_prefix = str(raw.get("tag_prefix", "")).strip()
        if not client_id or not name or not github:
            raise ValueError(f"{path} has a client missing id, name, or github")
        if role not in ("execution", "consensus"):
            raise ValueError(f"{client_id} has an unknown role")
        if versioning not in ("semver", "calver"):
            raise ValueError(f"{client_id} has an unknown versioning scheme")
        if tag_prefix and (any(char.isspace() for char in tag_prefix) or not tag_prefix.endswith("/")):
            raise ValueError(f"{client_id} tag_prefix must end with /")
        if client_id in seen:
            raise ValueError(f"{client_id} is listed twice")
        if tag_prefix and tag_prefix in prefixes:
            raise ValueError(f"{client_id} reuses tag_prefix {tag_prefix}")
        seen.add(client_id)
        if tag_prefix:
            prefixes.add(tag_prefix)
        clients.append(
            Client(
                id=client_id,
                name=name,
                role=role,
                github=github,
                versioning=versioning,
                tag_prefix=tag_prefix,
            )
        )
    if not clients:
        raise ValueError(f"{path} does not list any clients")
    return clients


def _tag_prefix(client_id: str) -> str:
    try:
        clients = load_clients()
    except ValueError:
        return ""
    client = client_by_id(clients, client_id)
    if client is None:
        return ""
    return client.tag_prefix


def client_by_id(clients: list[Client], client_id: str) -> Client | None:
    key = client_id.strip().lower()
    for client in clients:
        if client.id == key:
            return client
    return None


def releases_path(client_id: str) -> Path:
    return data_dir() / "releases" / f"{client_id}.json"


def load_releases(client_id: str) -> tuple[datetime, list[Release]] | None:
    path = releases_path(client_id)
    if not path.exists():
        return None
    payload = _read_json(path)
    fetched_at = parse_time(str(payload["fetched_at"]))
    tag_prefix = _tag_prefix(client_id)
    releases: list[Release] = []
    for raw in payload.get("releases", []):
        tag = str(raw.get("tag", ""))
        version = version_from_tag(tag, tag_prefix)
        if version is None:
            continue
        releases.append(
            Release(
                tag=tag,
                name=str(raw.get("name") or tag),
                published_at=str(raw.get("published_at") or ""),
                prerelease=bool(raw.get("prerelease")),
                url=str(raw.get("url") or ""),
                version=version,
            )
        )
    return fetched_at, releases


def save_releases(
    client: Client,
    releases: list[Release],
    ignored_tag_count: int,
    fetched_at: datetime,
) -> None:
    path = releases_path(client.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(releases, key=lambda item: (item.version, item.published_at, item.tag), reverse=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "client": client.id,
        "github": client.github,
        "fetched_at": format_time(fetched_at),
        "ignored_tag_count": ignored_tag_count,
        "releases": [
            {
                "tag": item.tag,
                "name": item.name,
                "published_at": item.published_at,
                "prerelease": item.prerelease,
                "url": item.url,
            }
            for item in ordered
        ],
    }
    text = json.dumps(payload, indent=2) + "\n"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(text)
    temporary.replace(path)


def load_advisories(client_id: str) -> list[Advisory]:
    path = data_dir() / "advisories" / f"{client_id}.json"
    if not path.exists():
        return []
    payload = _read_json(path)
    advisories: list[Advisory] = []
    for index, raw in enumerate(payload.get("advisories", []), start=1):
        version_text = str(raw.get("version", "")).strip()
        version = parse_version(version_text)
        severity = str(raw.get("severity", "")).strip()
        summary = str(raw.get("summary", "")).strip()
        action = str(raw.get("action", "")).strip()
        source = str(raw.get("source", "")).strip()
        where = f"{path} advisory {index} ({version_text or 'missing version'})"
        if version is None:
            raise ValueError(f"{where} has a version ChainDiff cannot parse")
        if severity not in SEVERITIES:
            raise ValueError(f"{where} has an unknown severity")
        if not summary:
            raise ValueError(f"{where} needs a summary")
        if severity in ("breaking", "deprecated") and not action:
            raise ValueError(f"{where} needs an action")
        if not source.startswith(("https://", "http://")):
            raise ValueError(f"{where} needs an http(s) source URL")
        advisories.append(
            Advisory(
                version=version,
                severity=severity,
                summary=summary,
                action=action,
                source=source,
            )
        )
    return advisories


def load_flag_rules(client_id: str) -> list[FlagRule]:
    path = data_dir() / "flags" / f"{client_id}.json"
    if not path.exists():
        return []
    payload = _read_json(path)
    rules: list[FlagRule] = []
    for index, raw in enumerate(payload.get("rules", []), start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"{path} rule {index} must be an object")
        version_text = str(raw.get("version", "")).strip()
        version = parse_version(version_text)
        flag = str(raw.get("flag", "")).strip().removeprefix("--")
        effect = str(raw.get("effect", "")).strip()
        action = str(raw.get("action", "")).strip()
        source = str(raw.get("source", "")).strip()
        replacement = str(raw.get("replacement", "")).strip().removeprefix("--")
        raw_values = raw.get("values", [])
        where = f"{path} rule {index} ({flag or version_text or 'missing flag'})"
        if version is None:
            raise ValueError(f"{where} has a version ChainDiff cannot parse")
        if effect not in FLAG_EFFECTS:
            raise ValueError(f"{where} has an unknown effect")
        if normalize_flag(flag) == "":
            raise ValueError(f"{where} needs a flag")
        if not action:
            raise ValueError(f"{where} needs an action")
        if effect == "renamed" and normalize_flag(replacement) == "":
            raise ValueError(f"{where} needs a replacement")
        if not source.startswith(("https://", "http://")):
            raise ValueError(f"{where} needs an http(s) source URL")
        if not isinstance(raw_values, list) or any(not isinstance(item, str) or not item.strip() for item in raw_values):
            raise ValueError(f"{where} values must be a list of strings")
        values = tuple(item.strip() for item in raw_values)
        if effect == "default" and values:
            raise ValueError(f"{where} matches a missing key, so it cannot list values")
        rules.append(
            FlagRule(
                version=version,
                flag=flag,
                effect=effect,
                action=action,
                source=source,
                replacement=replacement,
                values=values,
            )
        )
    return rules


def network_ids() -> list[str]:
    directory = data_dir() / "networks"
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.json"))


def load_network(network_id: str) -> NetworkSchedule:
    key = network_id.strip().lower()
    path = data_dir() / "networks" / f"{key}.json"
    if not path.exists():
        known = ", ".join(network_ids()) or "none"
        raise ValueError(f"Unknown network '{network_id}'. Known networks: {known}")
    payload = _read_json(path)
    if str(payload.get("id", "")).strip() != key:
        raise ValueError(f"{path} id does not match the file name")
    name = str(payload.get("name", "")).strip()
    upgrade = payload.get("upgrade")
    if not name or not isinstance(upgrade, dict):
        raise ValueError(f"{path} needs a name and an upgrade object")
    upgrade_name = str(upgrade.get("name", "")).strip()
    source = str(upgrade.get("source", "")).strip()
    summary = str(upgrade.get("summary", "")).strip()
    order_summary = str(upgrade.get("order_summary", "")).strip()
    order = upgrade.get("order")
    warning = str(upgrade.get("warning", "")).strip()
    if not upgrade_name or not summary or not order_summary:
        raise ValueError(f"{path} needs an upgrade name, summary, and order summary")
    if not source.startswith(("https://", "http://")):
        raise ValueError(f"{path} needs an http(s) source URL")
    if order is not None and order not in _NETWORK_ORDERS:
        raise ValueError(f"{path} has an unknown upgrade order")
    activation = _optional_time(path, upgrade.get("activation"), "activation")
    clients = load_clients()
    required = upgrade.get("required")
    if not isinstance(required, dict):
        raise ValueError(f"{path} needs a required object")
    return NetworkSchedule(
        id=key,
        name=name,
        upgrade=upgrade_name,
        activation=activation,
        source=source,
        summary=summary,
        order=order,
        order_summary=order_summary,
        warning=warning,
        required_execution=_required_versions(path, required, "execution", clients),
        required_consensus=_required_versions(path, required, "consensus", clients),
    )


def _optional_time(path: Path, value: object, label: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} has an unreadable {label}")
    try:
        return parse_time(value.strip())
    except ValueError as exc:
        raise ValueError(f"{path} has an unreadable {label}") from exc


def _required_versions(
    path: Path,
    required: dict,
    role: str,
    clients: list[Client],
) -> dict[str, Version]:
    raw = required.get(role)
    if not isinstance(raw, dict):
        raise ValueError(f"{path} needs required.{role}")
    versions: dict[str, Version] = {}
    for client_id, version_text in raw.items():
        client = client_by_id(clients, str(client_id))
        where = f"{path} required {role} {client_id}"
        if client is None or client.role != role:
            article = "an" if role[:1] in "aeiou" else "a"
            raise ValueError(f"{where} is not {article} {role} client")
        text = str(version_text).strip()
        if _PRECISE_RELEASE.fullmatch(text) is None:
            raise ValueError(f"{where} needs a major.minor.patch version")
        version = parse_version(text)
        if version is None:
            raise ValueError(f"{where} has a version ChainDiff cannot parse")
        versions[client.id] = version
    return versions
