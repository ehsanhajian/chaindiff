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

The shipping catalog is Ethereum mainnet. The tool also covers these networks, one task each. A check has to use the clients that network actually runs, and that chain's upgrade, not only the latest tag of an upstream Ethereum client.

- Ethereum mainnet
- Gnosis
- BNB Smart Chain
- Avalanche
- OP Mainnet
- Base
- Arbitrum One
- Polygon PoS
- Linea
- Scroll
- zkSync Era
- Starknet

Not in this cut: Lodestar, Grandine, applying the upgrade, node metrics, peer or disk checks, and RPC benchmarks. Execution and consensus pairing is later work. `scan` reads a config file you already have and compares it with sourced flag rules. A setting with no rule is reported as not covered. It is not called safe.

Calendar-versioned clients (Besu, Teku, Nimbus) do not treat a new year in the version as a breaking change by itself. Semver clients do: an unreviewed major bump is **not safe**.

## Install

```bash
pip install chaindiff
```

That package is published from a GitHub release. Until the first release is on PyPI:

```bash
pip install git+https://github.com/ehsanhajian/chaindiff.git
```

## Commands

```bash
chaindiff versions
chaindiff detect --client geth --binary /usr/bin/geth
chaindiff detect --client lighthouse --image sigp/lighthouse:v8.2.3
chaindiff check --client geth --from <installed>
chaindiff check --client lighthouse --from <installed> --to v8.2.3
chaindiff plan --client nethermind --from <installed>
chaindiff scan --client geth --from <installed> --to <target> --config <file>
chaindiff refresh
```

`detect` reads the version from a client binary, or from a Docker image tag. It does not pull or start an image, and it does not run `check`. Geth is asked with `version`. The other clients are asked with `--version`. Prysm's binary is `beacon-chain` or `validator`.

When the output or the tag is one precise release, `detect` prints that version and the `check` command. A tag such as `1.17` is not treated as `1.17.0`. `latest`, `stable`, `nightly`, and the other channel names are not versions. If the binary fails, the tag is not a release, or more than one version appears, it prints:

```bash
chaindiff check --client geth --from <installed>
```

Exit 0 means a version was read. Exit 1 means it was not. Exit 3 means the client is unknown.

`scan` accepts CLI flags, TOML, JSON, or YAML. The format follows the file extension (`.toml`, `.json`, `.yaml`, `.yml`). A file of command-line flags has no extension requirement. `--format cli|toml|json|yaml` overrides that. `--to` defaults to the latest stable release. The command prints what to change. It does not edit the file.

Exit 2 means a setting in the file was removed or renamed. Exit 1 means a default changed, a setting is deprecated, or the catalog does not cover a setting. Exit 0 means every setting is covered and none of those changes apply. A stale catalog cannot return exit 0 for `latest`.

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

## Flag rules

`scan` uses `src/chaindiff/data/flags/<client>.json`. A missing file means the catalog covers nothing for that client.

```json
{
  "schema_version": 1,
  "rules": [
    {
      "version": "1.17.4",
      "flag": "txlookuplimit",
      "effect": "removed",
      "action": "Drop the flag.",
      "source": "https://github.com/ethereum/go-ethereum/releases/tag/v1.17.4"
    }
  ]
}
```

`effect` is `removed`, `renamed`, `deprecated`, or `default`. `renamed` also needs `replacement`. Every rule needs an action and an `http` or `https` source. `flag` is the key the operator set: a CLI name without the leading dashes, or a dotted path such as `JsonRpc.Enabled`. Dashes and underscores match dots. A rule may list `values`. It then matches only when the file sets the key to one of those values, so a new valid value is left alone.

A rule applies when its version is after `--from` and at or before `--to`. Removed, renamed, and deprecated rules are reported when the file sets that key. A `default` rule is reported when the file does not set it. The same key outside that range is covered, and it is not listed as a change.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Tests that need a private catalog can set `CHAINDIFF_DATA` to a directory with the same `clients.json`, `releases/`, `advisories/`, and `flags/` layout.
