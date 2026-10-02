# ChainDiff

Decide whether an Ethereum node client upgrade is safe.

ChainDiff compares the client you run with the release you want. It answers **safe** only when every release in between has a sourced review and none of those reviews is breaking. Otherwise the answer is **review required** or **not safe**.

It does not restart a node, edit config, or apply an upgrade.

## Scope

Supported clients:

| Client | Role | Release source |
| --- | --- | --- |
| Geth | execution | ethereum/go-ethereum |
| Nethermind | execution | NethermindEth/nethermind |
| Erigon | execution | erigontech/erigon |
| Besu | execution | besu-eth/besu |
| Reth | execution | paradigmxyz/reth |
| Lighthouse | consensus | sigp/lighthouse |
| Prysm | consensus | OffchainLabs/prysm |
| Teku | consensus | Consensys-Incorporated/teku |
| Nimbus | consensus | status-im/nimbus-eth2 |

Reth and Nimbus are in the catalog because operators run them. Besu and Teku are read from their current GitHub repositories.

Not in this cut: Lodestar, Grandine, applying the upgrade, node metrics, peer or disk checks, and RPC benchmarks. Configuration scanning and execution/consensus pairing are tracked as later work. They need sourced rules, not guesses.

Calendar-versioned clients (Besu, Teku, Nimbus) do not treat a new year in the version as a breaking change by itself. Semver clients do: an unreviewed major bump is **not safe**.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Commands

```bash
chaindiff versions
chaindiff check --client geth --from <installed>
chaindiff check --client lighthouse --from <installed> --to v8.2.3
chaindiff plan --client nethermind --from <installed>
chaindiff refresh
```

`check` and `plan` use the local catalog. `refresh` is the only command that talks to GitHub. Set `GH_TOKEN` or `GITHUB_TOKEN` if you hit the unauthenticated rate limit.

### Verdicts

- **ALREADY CURRENT** (exit 0) — you are on the target release.
- **SAFE** (exit 0) — every release in the range has a sourced review, and none is breaking.
- **REVIEW REQUIRED** (exit 1) — ChainDiff will not call it safe. Releases are missing a review, something is deprecated, or the catalog is too old to trust "latest".
- **NOT SAFE** (exit 2) — a reviewed breaking change, or an unreviewed semver major bump.
- **PRERELEASE** (exit 2) — the target is a prerelease. Don't run it on a mainnet node.
- **DOWNGRADE** (exit 2) — the target is older than what you run.

A stale catalog (older than 5 days) cannot produce **safe** or **already current** for `latest`. Comparing two explicit versions still works; the report warns that the catalog is old.

The checklist always includes the operator steps that are worth doing on any upgrade: read the notes, back up, keep the old binary, upgrade one client at a time, and roll back if the node fails. Client-specific steps appear only when an advisory says what to change.

## Release catalog

GitHub Actions refreshes the catalog twice a week, Monday and Thursday at 06:15 UTC, and commits it when the run succeeds. Run `chaindiff refresh` yourself any time.

Erigon tags from the old date scheme, such as `v2022.10.01`, are left out. They are not comparable with the 2.x and 3.x line, and treating them as newer versions would hide the current release.

The stored catalog is tags, dates, titles, and URLs. It does not copy release-note bodies. A release title that mentions a security fix is reported as a warning. That warning does not by itself make the upgrade safe or unsafe.

## Advisories

Safe and not-safe both require a review. Put reviews in `src/chaindiff/data/advisories/<client>.json`:

```json
{
  "schema_version": 1,
  "advisories": [
    {
      "version": "2.0.0",
      "severity": "breaking",
      "summary": "What breaks.",
      "action": "What the operator changes.",
      "source": "https://github.com/org/repo/releases/tag/2.0.0"
    }
  ]
}
```

`severity` is `breaking`, `deprecated`, `note`, or `none`. `none` means the release was reviewed and there is nothing to do. `breaking` and `deprecated` need an `action`. Every advisory needs an `http` or `https` source. Do not mark a release reviewed without reading it.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests that need a private catalog can set `CHAINDIFF_DATA` to a directory with the same `clients.json`, `releases/`, and `advisories/` layout.
