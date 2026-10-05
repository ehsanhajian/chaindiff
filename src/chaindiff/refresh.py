"""Fetch client releases from GitHub."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from chaindiff.catalog import load_clients, save_releases
from chaindiff.models import Client, Release
from chaindiff.versions import tag_is_prerelease, version_from_tag

API_ROOT = "https://api.github.com"
_NEXT_LINK = re.compile(r'<([^>]+)>;\s*rel="next"')
Opener = Callable[[str, str | None], tuple[Any, str | None]]


class GitHubError(Exception):
    pass


def _default_opener(url: str, token: str | None) -> tuple[Any, str | None]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "chaindiff/0.1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
            return payload, response.headers.get("Link")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        message = ""
        try:
            message = json.loads(detail).get("message", "")
        except json.JSONDecodeError:
            message = detail.strip()
        if exc.code == 403 and "rate limit" in message.lower():
            raise GitHubError(
                "GitHub rate limit reached. Set GH_TOKEN or GITHUB_TOKEN and run refresh again."
            ) from exc
        raise GitHubError(f"GitHub returned {exc.code} for {url}: {message}") from exc
    except urllib.error.URLError as exc:
        raise GitHubError(f"Could not reach GitHub: {exc.reason}") from exc


def _next_url(link_header: str | None) -> str | None:
    if not link_header:
        return None
    matched = _NEXT_LINK.search(link_header)
    if not matched:
        return None
    return matched.group(1)


def releases_from_payload(
    items: list[dict[str, Any]],
    tag_prefix: str = "",
) -> tuple[list[Release], int]:
    releases: list[Release] = []
    ignored = 0
    seen: set[str] = set()
    for item in items:
        if item.get("draft"):
            ignored += 1
            continue
        tag = str(item.get("tag_name") or "")
        if not tag or tag in seen:
            ignored += 1
            continue
        version = version_from_tag(tag, tag_prefix)
        if version is None:
            ignored += 1
            continue
        seen.add(tag)
        published = str(item.get("published_at") or "")
        version_tag = tag[len(tag_prefix) :] if tag_prefix else tag
        prerelease = bool(item.get("prerelease")) or tag_is_prerelease(version_tag)
        releases.append(
            Release(
                tag=tag,
                name=str(item.get("name") or tag),
                published_at=published,
                prerelease=prerelease,
                url=str(item.get("html_url") or ""),
                version=version,
            )
        )
    return releases, ignored


def fetch_releases(
    client: Client,
    token: str | None = None,
    opener: Opener | None = None,
) -> tuple[list[Release], int]:
    fetch = opener or _default_opener
    url = f"{API_ROOT}/repos/{client.github}/releases?per_page=100"
    pages: list[dict[str, Any]] = []
    for _ in range(40):
        payload, link = fetch(url, token)
        if isinstance(payload, dict):
            message = payload.get("message", "unexpected GitHub response")
            raise GitHubError(f"{client.github}: {message}")
        if not isinstance(payload, list):
            raise GitHubError(f"{client.github}: unexpected GitHub response")
        pages.extend(payload)
        nxt = _next_url(link)
        if nxt is None:
            break
        url = nxt
    else:
        raise GitHubError(f"{client.github}: too many release pages")
    return releases_from_payload(pages, client.tag_prefix)


def github_token() -> str | None:
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or None


def refresh_catalog(client_ids: list[str] | None = None) -> int:
    clients = load_clients()
    if client_ids:
        wanted = {item.strip().lower() for item in client_ids}
        unknown = wanted - {client.id for client in clients}
        if unknown:
            names = ", ".join(sorted(unknown))
            print(f"Unknown client: {names}")
            return 3
        clients = [client for client in clients if client.id in wanted]

    token = github_token()
    failures: list[str] = []
    fetched_at = datetime.now(timezone.utc)
    for client in clients:
        try:
            releases, ignored = fetch_releases(client, token=token)
        except GitHubError as exc:
            failures.append(f"{client.id}: {exc}")
            print(f"{client.id}: failed — {exc}")
            continue
        save_releases(client, releases, ignored, fetched_at)
        stable = sum(1 for item in releases if not item.prerelease)
        print(
            f"{client.id}: {stable} stable releases, "
            f"{len(releases) - stable} prereleases, {ignored} ignored tags"
        )
    if failures:
        return 1
    return 0
