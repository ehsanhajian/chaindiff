"""Load and store the client registry, release catalog, and advisories."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from chaindiff.models import SEVERITIES, Advisory, Client, Release
from chaindiff.versions import parse_version

SCHEMA_VERSION = 1


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
    for raw in payload.get("clients", []):
        client_id = str(raw.get("id", "")).strip()
        role = raw.get("role")
        versioning = raw.get("versioning")
        github = str(raw.get("github", "")).strip()
        name = str(raw.get("name", "")).strip()
        if not client_id or not name or not github:
            raise ValueError(f"{path} has a client missing id, name, or github")
        if role not in ("execution", "consensus"):
            raise ValueError(f"{client_id} has an unknown role")
        if versioning not in ("semver", "calver"):
            raise ValueError(f"{client_id} has an unknown versioning scheme")
        if client_id in seen:
            raise ValueError(f"{client_id} is listed twice")
        seen.add(client_id)
        clients.append(
            Client(
                id=client_id,
                name=name,
                role=role,
                github=github,
                versioning=versioning,
            )
        )
    if not clients:
        raise ValueError(f"{path} does not list any clients")
    return clients


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
    releases: list[Release] = []
    for raw in payload.get("releases", []):
        tag = str(raw.get("tag", ""))
        version = parse_version(tag)
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
