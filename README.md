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
| op-geth | execution | ethereum-optimism/op-geth |
| op-reth | execution | ethereum-optimism/optimism, tags `op-reth/` |
| Nitro | execution | OffchainLabs/nitro |
| Bor | execution | 0xPolygon/bor |
| Lighthouse | consensus | sigp/lighthouse |
| Prysm | consensus | OffchainLabs/prysm |
| Teku | consensus | Consensys-Incorporated/teku |
| Nimbus | consensus | status-im/nimbus-eth2 |
| op-node | consensus | ethereum-optimism/optimism, tags `op-node/` |
| Heimdall | consensus | 0xPolygon/heimdall-v2 |

Reth and Nimbus are in the catalog because operators run them. Besu and Teku are read from their current GitHub repositories. op-reth is the execution client Optimism documents for node operators, and op-node is the rollup node in the same repository. op-geth stays in the catalog because existing nodes may still be running it. op-batcher and op-proposer are not node clients.

The shipping network schedules are Ethereum mainnet, Gnosis Chain, OP Mainnet, Base, Arbitrum One, and Polygon PoS. op-geth, op-reth, and op-node are checked on their own with `--client`. `--network op-mainnet` and `--network base` each use that chain's next upgrade, so a release one chain requires is not assumed on the other. Arbitrum One is a Nitro node. Upstream Geth does not answer that check, and Arbitrum Nova and Orbit chains are not that schedule. Polygon PoS is bor with heimdall from the v2 repository. A bor release that does not name the matching heimdall is not a complete upgrade. Gnosis Chain reuses Nethermind, Erigon, Geth, or Reth with Lighthouse, Nimbus, or Teku. Lodestar stays out. The tool also covers these networks, one task each. A check has to use the clients that network actually runs, and that chain's upgrade, not only the latest tag of an upstream Ethereum client.

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

Not in this cut: Lodestar, Grandine, op-batcher, op-proposer, applying the upgrade, node metrics, peer or disk checks, and RPC benchmarks. `check` can take the execution client and the consensus client together and return one verdict and one plan. `check --network ethereum` compares that pair with the next Ethereum mainnet upgrade. `check --network op-mainnet` compares op-geth or op-reth and op-node with the next OP Mainnet upgrade. `check --network base` compares op-geth and op-node with the next Base upgrade. `check --network arbitrum-one` compares an installed Nitro release with the next Arbitrum One upgrade. `check --network polygon` compares installed bor and heimdall releases with the next Polygon PoS upgrade. `check --network gnosis` compares Nethermind or Erigon, or Geth or Reth, and Lighthouse, Nimbus, or Teku with the next Gnosis Chain upgrade. `scan` reads a config file you already have and compares it with sourced flag rules. A setting with no rule is reported as not covered. It is not called safe.

Calendar-versioned clients (Besu, Teku, Nimbus) do not treat a new year in the version as a breaking change by itself. Semver clients do: an unreviewed major bump is **not safe**.

## Install

```bash
pip install chaindiff
```

That package is published from a GitHub release.

## Commands

```bash
chaindiff versions
chaindiff detect --client geth --binary /usr/bin/geth
chaindiff detect --client lighthouse --image sigp/lighthouse:v8.2.3
chaindiff check --client geth --from <installed>
chaindiff check --client lighthouse --from <installed> --to v8.2.3
chaindiff check --execution geth --execution-version <installed> --consensus lighthouse --consensus-version <installed>
chaindiff plan --execution geth --execution-version <installed> --consensus lighthouse --consensus-version <installed>
chaindiff check --network ethereum --execution geth --execution-version <installed> --consensus lighthouse --consensus-version <installed>
chaindiff check --network polygon --execution bor --execution-version <installed> --consensus heimdall --consensus-version <installed>
chaindiff check --network gnosis --execution nethermind --execution-version <installed> --consensus lighthouse --consensus-version <installed>
chaindiff plan --client nethermind --from <installed>
chaindiff scan --client geth --from <installed> --to <target> --config <file>
chaindiff refresh
```

`check`, `plan`, `scan`, and `detect` read the client binary. Use them for a mainnet node or a testnet node. A Sepolia Geth upgrade is the same command as a mainnet one. A release note that names a testnet deadline is included when that release is in the range.

`detect` reads the version from a client binary, or from a Docker image tag. It does not pull or start an image, and it does not run `check`. Geth, op-geth, and bor are asked with `version` and read from a `Version:` line. `heimdalld version` prints the version alone. The other Ethereum clients are asked with `--version`. Prysm's binary is `beacon-chain` or `validator`. An op-node or op-reth version is read from the image tag. ChainDiff does not run those binaries, because their version output is not yet confirmed. Enter an OP Stack version as `1.19.8`. A full tag such as `op-node/v1.19.8` is also accepted.

When the output or the tag is one precise release, `detect` prints that version and the `check` command. A tag such as `1.17` is not treated as `1.17.0`. `latest`, `stable`, `nightly`, and the other channel names are not versions. If the binary fails, the tag is not a release, or more than one version appears, it prints:

```bash
chaindiff check --client geth --from <installed>
```

Exit 0 means a version was read. Exit 1 means it was not. Exit 3 means the client is unknown.

A pair check takes an Ethereum mainnet execution client and consensus client and returns one verdict and one plan. The pair is **safe** only when every release in both ranges has a sourced review and none is breaking. Otherwise it stays **review required** or **not safe**. The plan states the upgrade order from the mainnet schedule. It does not invent a compatibility matrix between the two clients. op-geth, op-reth, op-node, bor, and heimdall are not part of that pair.

`check --network ethereum` asks whether the execution client and the consensus client you run are the versions the next mainnet upgrade requires, and whether an upgrade order is stated. The schedule is `src/chaindiff/data/networks/ethereum.json`, taken from the network announcement. A Sepolia date in that announcement is not a mainnet deadline. No required mainnet version is invented from a testnet table. For this network check, **already current** means both clients are the announced requirement and the activation time is set. **Review required** means a required version or the activation time has not been announced, or the installed version is newer than the announcement. **Not safe** means an installed version is older than an announced requirement. A prerelease is still refused.

`check --network op-mainnet` asks the same question for op-geth or op-reth and op-node. The schedule is `src/chaindiff/data/networks/op-mainnet.json`. The next upgrade is Lagoon. OP Mainnet's activation time and client releases are not scheduled. The OP Sepolia interop notice does not name those releases, and a late July 2026 line in that notice is not an activation time. No required version is taken from that notice or from Base.

`check --network base` asks the same question for op-geth and op-node. The schedule is `src/chaindiff/data/networks/base.json`. The next upgrade is Denim. Base Mainnet's activation time is not scheduled. November 2026 is a planning target on the upgrades index, and October 2026 is the Sepolia planning target. Denim does not name an op-geth or op-node release. The operator node is published from base/base, and that image tag is not recorded here as the requirement.

`check --network arbitrum-one` asks the same question for Nitro alone. The schedule is `src/chaindiff/data/networks/arbitrum-one.json`. No ArbOS upgrade after Elara is listed, so no Nitro release is recorded as the next requirement. ArbOS 61 Elara is already active and required Nitro v3.11.3 or higher; that live minimum is not stored as the next upgrade. Nitro v3.11.4 before October 6, 2026 is the Arbitrum Sepolia notice, not an Arbitrum One requirement. Pass `--execution nitro` and `--execution-version`. Do not pass `--consensus`.

`check --network gnosis` asks the same question for Nethermind, Erigon, Geth, or Reth, with Lighthouse, Nimbus, or Teku. The schedule is `src/chaindiff/data/networks/gnosis.json`. The next upgrade is Glamsterdam. Its spec leaves the Chiado and mainnet timestamps blank and names no client release, so no required version is recorded. Fusaka activated on Gnosis mainnet on April 14, 2026 and is not the next upgrade. No Gnosis-only flag change is stated for Glamsterdam. Chiado is not this schedule.

`check --network polygon` asks the same question for bor and heimdall. The schedule is `src/chaindiff/data/networks/polygon.json`. No upgrade after Lugano names both releases, so no required pair is recorded. Lugano activated on Polygon PoS mainnet on October 1, 2026 and the announcement names only Heimdall v0.12.1. Bor v2.10.2 says it has no hardfork and names no heimdall release. That live fork is not stored as the next upgrade. Pass `--execution bor` and `--consensus heimdall`. Amoy is not this schedule.

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

## Networks

`check --network` reads `src/chaindiff/data/networks/<network>.json`:

```json
{
  "schema_version": 1,
  "id": "ethereum",
  "name": "Ethereum mainnet",
  "upgrade": {
    "name": "Glamsterdam",
    "activation": null,
    "source": "https://blog.ethereum.org/2026/09/17/glamsterdam-testnet-announcement",
    "summary": "What the announcement says about mainnet.",
    "order": null,
    "order_summary": "What the announcement says about upgrade order.",
    "warning": "A date or table the operator must not treat as the mainnet requirement.",
    "required": {
      "execution": {},
      "consensus": {}
    }
  }
}
```

`activation` is an ISO time, or `null` when mainnet is not scheduled. `order` is `execution-first`, `consensus-first`, or `null`. `required` maps a client id to a `major.minor.patch` version from the announcement. An empty map means that role has no announced requirement. Do not fill it from a testnet table.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Tests that need a private catalog can set `CHAINDIFF_DATA` to a directory with the same `clients.json`, `releases/`, `advisories/`, and `flags/` layout.
