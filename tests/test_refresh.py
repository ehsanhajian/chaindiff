from chaindiff.models import Client
from chaindiff.refresh import fetch_releases, releases_from_payload


def _item(tag: str, **extra):
    payload = {
        "tag_name": tag,
        "name": extra.get("name", tag),
        "published_at": extra.get("published_at", "2026-01-01T00:00:00Z"),
        "prerelease": extra.get("prerelease", False),
        "draft": extra.get("draft", False),
        "html_url": f"https://example.test/{tag}",
    }
    return payload


def test_payload_keeps_releases_and_drops_junk():
    releases, ignored = releases_from_payload(
        [
            _item("v1.2.3"),
            _item("v1.2.4-rc.1", prerelease=True),
            _item("v1.10.17-stable"),
            _item("nightly", prerelease=True),
            _item("zkvm-guests-2.1.0-unstable-abc", prerelease=True),
            _item("v1.0.0", draft=True),
        ]
    )
    tags = {item.tag for item in releases}
    assert tags == {"v1.2.3", "v1.2.4-rc.1", "v1.10.17-stable"}
    assert ignored == 3
    stable = next(item for item in releases if item.tag == "v1.10.17-stable")
    assert not stable.prerelease
    candidate = next(item for item in releases if item.tag == "v1.2.4-rc.1")
    assert candidate.prerelease


def test_fetch_follows_the_next_link():
    first = "https://api.github.com/repos/ethereum/go-ethereum/releases?per_page=100"
    second = "https://example.test/page-2"
    pages = {
        first: (
            [_item("v1.2.0"), _item("nightly")],
            f'<{second}>; rel="next"',
        ),
        second: ([_item("v1.1.0", name="Security fix")], None),
    }

    def opener(url, token):
        assert token is None
        return pages[url]

    client = Client("geth", "Geth", "execution", "ethereum/go-ethereum", "semver")
    releases, ignored = fetch_releases(client, opener=opener)
    assert {item.tag for item in releases} == {"v1.2.0", "v1.1.0"}
    assert ignored == 1
    security = next(item for item in releases if item.tag == "v1.1.0")
    assert security.name == "Security fix"
