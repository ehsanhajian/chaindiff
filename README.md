# ChainDiff

ChainDiff tells you whether a node-client upgrade is safe, and whether the release you run meets the next upgrade on your chain.

It answers from a local catalog of releases, sourced reviews, and network announcements. It does not restart a node, edit a config, or apply an upgrade.

## Install

```bash
pip install chaindiff
```

The package is published from a GitHub release. Python 3.11 or newer.

## Which command

| Question | Command |
| --- | --- |
| What version is installed? | `detect` |
| Is the move from this release to that release safe? | `check --client` |
| Do these two Ethereum clients upgrade together? | `check --execution` and `--consensus` |
| Does this install meet the next upgrade on this chain? | `check --network` |
| What should I do before I upgrade? | `plan` |
| Did a flag change between these releases? | `scan` |
| What is the latest stable tag? | `versions` |
| Is the local release catalog current? | `refresh` |

`check`, `plan`, and `scan` compare versions you pass in. They do not read a binary. Run `detect` first when you need the installed version, then pass that version to `check`.

`refresh` downloads release tags from GitHub into the local catalog. The other commands read that catalog and do not talk to GitHub. A catalog older than 5 days cannot call `latest` safe, so run `refresh` before you trust that answer. `refresh --client geth` updates one client.

`check --client` looks at the client, so the same command covers a mainnet node and a testnet node. A Sepolia Geth upgrade is the same check as a mainnet one. A release note that names a testnet deadline is included when that release is in the range.

`check --network` looks only at the **next** upgrade on that chain. A live fork, a planning month, and a testnet date stay out of the requirement.

## Examples

```bash
chaindiff detect --client geth --binary /usr/bin/geth
chaindiff detect --client lighthouse --image sigp/lighthouse:v8.2.3

chaindiff check --client geth --from 1.17.6
chaindiff check --client lighthouse --from 8.2.2 --to v8.2.3

chaindiff check --execution geth --execution-version 1.17.6 \
  --consensus lighthouse --consensus-version 8.2.2
chaindiff plan --execution geth --execution-version 1.17.6 \
  --consensus lighthouse --consensus-version 8.2.2

chaindiff check --network ethereum \
  --execution geth --execution-version 1.17.7 \
  --consensus lighthouse --consensus-version 8.2.3
chaindiff check --network starknet \
  --execution pathfinder --execution-version 0.24.0

chaindiff scan --client geth --from 1.17.3 --config /etc/geth/flags
chaindiff versions
chaindiff refresh
```

`--to` defaults to the latest stable release. `detect`, `versions`, `check`, `plan`, and `scan` accept `--json`.

## Verdicts

| Verdict | Exit | When |
| --- | --- | --- |
| ALREADY CURRENT | 0 | The installed release is the target. |
| SAFE | 0 | Every release in the range has a sourced review, and none is breaking. |
| REVIEW REQUIRED | 1 | A release has no review, a review is only a deprecation or a note, or the catalog is too old to trust `latest`. |
| NOT SAFE | 2 | A reviewed change is breaking, or a semver client has an unreviewed major bump. |
| PRERELEASE | 2 | The target is a prerelease. Leave it off a mainnet node. |
| DOWNGRADE | 2 | The target is older than the installed release. |

Exit 3 is a usage or catalog error.

A catalog older than 5 days cannot return **safe** or **already current** for `latest`. A check between two explicit versions still runs, and the report says the catalog is old.

Besu, Teku, and Nimbus use calendar versions. A new year is an ordinary release until a review says otherwise. Semver clients treat an unreviewed major bump as **not safe**.

A network check uses the same exits:

- **Already current** means every required client matches the announcement and the activation time is set.
- **Review required** means a required version or the activation time is still open, or the installed release is newer than the named requirement.
- **Not safe** means the installed release is older than an announced requirement.

The checklist always includes the steps worth doing on any upgrade: read the notes, back up, keep the old binary, upgrade one client at a time, and roll back if the node fails. Client-specific steps appear only when an advisory names them.

## Networks

Use the clients that chain runs. A release required on one chain stays on that chain's schedule.

| Chain | `--network` | Clients | Next upgrade | Named requirement |
| --- | --- | --- | --- | --- |
| Ethereum mainnet | `ethereum` | Geth, Nethermind, Erigon, Besu, or Reth, with Lighthouse, Prysm, Teku, or Nimbus | Glamsterdam | None yet |
| Gnosis Chain | `gnosis` | Nethermind, Erigon, Geth, or Reth, with Lighthouse, Nimbus, or Teku | Glamsterdam | None yet |
| BNB Smart Chain | `bsc` | BSC | Jenner | None yet |
| Avalanche | `avalanche` | avalanchego | Igloo | None yet |
| OP Mainnet | `op-mainnet` | op-geth or op-reth, with op-node | Lagoon | None yet |
| Base | `base` | op-geth with op-node | Denim | None yet |
| Arbitrum One | `arbitrum-one` | Nitro | Unannounced | None yet |
| Polygon PoS | `polygon` | bor with heimdall | Unannounced | None yet |
| Linea | `linea` | Linea Besu with Maru | Beta v5.3 | None yet |
| Scroll | `scroll` | l2geth | Unannounced | None yet |
| zkSync Era | `zksync-era` | external node | v31 | None yet |
| Starknet | `starknet` | Pathfinder or Juno | v0.14.4 | Pathfinder 0.24.0 or Juno 0.16.6 |

A chain with one client takes `--execution` and `--execution-version`. Leave `--consensus` off. For Starknet, pass either Pathfinder or Juno.

Schedules live in `src/chaindiff/data/networks/`.

### Ethereum mainnet

Glamsterdam has no mainnet activation time and no required client release. Sepolia activates at 2026-10-06 13:53:36 UTC. That date is a testnet time. The announcement publishes no mainnet client releases. No upgrade order is stated.

### Gnosis Chain

Glamsterdam leaves the Chiado and mainnet timestamps blank and names no client release. Fusaka activated on Gnosis mainnet on April 14, 2026. Chiado is a separate schedule. Lodestar stays out. No Gnosis-only flag change is recorded for Glamsterdam.

### BNB Smart Chain

Jenner leaves the fork time and the hard-fork release unannounced. Late October 2026 and late November 2026 are planning windows. Pasteur activated on August 25, 2026 and used BSC v1.7.7. That live fork stays out of the next requirement. opBNB is a separate schedule. Pass `--execution bsc`.

### Avalanche

Igloo is unscheduled and names no avalanchego release. Helicon activated on Avalanche Mainnet on September 22, 2026 at 15:00 UTC. v1.15.0 is that live upgrade. v1.15.1 is a later optional release. Fuji is a separate schedule. Pass `--execution avalanchego`.

### OP Mainnet

Lagoon is in development, with no activation time and no required op-geth, op-reth, or op-node release. The OP Sepolia interop notice names neither those releases nor an OP Mainnet time. A late July 2026 line in that notice stays out of the schedule. A release named for Base stays on the Base schedule.

### Base

Denim is in planning. November 2026 is the mainnet planning target and October 2026 is the Sepolia planning target. Denim names no op-geth or op-node release. The operator image published from base/base is left out of the requirement. Pass `--execution op-geth` and `--consensus op-node`.

### Arbitrum One

No ArbOS upgrade after Elara is listed. ArbOS 61 Elara activated on August 20, 2026 and required Nitro v3.11.3 or higher. That live minimum stays out of the next requirement. Nitro v3.11.4 before October 6, 2026 is the Arbitrum Sepolia notice. Nova and Orbit are separate schedules. Pass `--execution nitro`.

### Polygon PoS

No upgrade after Lugano names both a bor release and a heimdall release. Lugano activated on October 1, 2026 and names Heimdall v0.12.1. Bor v2.10.2 says it has no hardfork and names no heimdall release. A bor release without the matching heimdall is an incomplete upgrade. Amoy is a separate schedule. Pass `--execution bor` and `--consensus heimdall`.

### Linea

Beta v5.3 has a mainnet timing the changelog describes as a target that can move. Q4 2026 is that target. The changelog names no Linea Besu or Maru release. Beta v5.2 activated on April 1, 2026. The Fusaka guide from December 3, 2025 points at the current docker-compose files. Linea Sepolia is a separate schedule. Pass `--execution linea-besu` and `--consensus maru`. Upstream Besu, Geth, and Erigon are outside this check.

### Scroll

No upgrade after OpenVM v2.0.0 is announced. OpenVM v2.0.0 executed on September 22, 2026 at 02:00 UTC and names no l2geth release. Galileo activated on December 16, 2025 and December 18, 2025. The current node guide names scroll-v5.8.38 or higher. That live minimum stays out of the next requirement. Early 2027 is a planning window. Scroll Sepolia is a separate schedule. Pass `--execution l2geth`. The current node guide still pins l2geth.

### zkSync Era

v31 is the next Era upgrade and is not scheduled. The announcement asks for a v31-compatible zksync-era release and does not name the tag. August 4, 2026 and August 24, 2026 were estimates. On August 24, 2026 Matter Labs said v31 is delayed and under review. Protocol version 30 was not deployed to Era mainnet. The current mainnet compose file pins `matterlabs/external-node:v29.4.0`. ZIP-17 increases the execution delay to 24 hours on October 7, 2026 at 13:00 UTC and names no node release. Other ZK Chains are separate schedules. Pass `--execution external-node`.

### Starknet

v0.14.4 names Pathfinder 0.24.0 and Juno 0.16.6. An operator runs one of them. Mainnet is listed as October 5, 2026, pending governance approval, so activation stays unset. An exact match is review required until an activation time is announced. September 15, 2026 is the testnet date. A newer Pathfinder or Juno tag stays review required. SNIP-36 prover operators are outside this check.

## Clients

| Client | id | Role | Release source |
| --- | --- | --- | --- |
| Geth | `geth` | execution | ethereum/go-ethereum |
| Nethermind | `nethermind` | execution | NethermindEth/nethermind |
| Erigon | `erigon` | execution | erigontech/erigon |
| Besu | `besu` | execution | besu-eth/besu |
| Reth | `reth` | execution | paradigmxyz/reth |
| op-geth | `op-geth` | execution | ethereum-optimism/op-geth |
| op-reth | `op-reth` | execution | ethereum-optimism/optimism, tags `op-reth/` |
| Nitro | `nitro` | execution | OffchainLabs/nitro |
| Bor | `bor` | execution | 0xPolygon/bor |
| BSC | `bsc` | execution | bnb-chain/bsc |
| avalanchego | `avalanchego` | execution | ava-labs/avalanchego |
| Linea Besu | `linea-besu` | execution | LFDT-Lineth/lineth-monorepo, tags `releases/linea-besu-package/` |
| l2geth | `l2geth` | execution | scroll-tech/go-ethereum, tags `scroll-` |
| external node | `external-node` | execution | matter-labs/zksync-era, tags `core-` |
| Pathfinder | `pathfinder` | execution | software-mansion/pathfinder |
| Juno | `juno` | execution | NethermindEth/juno |
| Lighthouse | `lighthouse` | consensus | sigp/lighthouse |
| Prysm | `prysm` | consensus | OffchainLabs/prysm |
| Teku | `teku` | consensus | Consensys-Incorporated/teku |
| Nimbus | `nimbus` | consensus | status-im/nimbus-eth2 |
| op-node | `op-node` | consensus | ethereum-optimism/optimism, tags `op-node/` |
| Heimdall | `heimdall` | consensus | 0xPolygon/heimdall-v2 |
| Maru | `maru` | consensus | LFDT-Lineth/lineth-monorepo, tags `releases/maru/` |

Reth and Nimbus are included because operators run them. Besu and Teku are read from their current GitHub repositories. op-reth is the execution client Optimism documents for node operators. op-geth stays because existing nodes may still run it. op-batcher and op-proposer are left out.

A pair check without `--network` accepts only the Ethereum mainnet clients: Geth, Nethermind, Erigon, Besu, or Reth, with Lighthouse, Prysm, Teku, or Nimbus. The pair is **safe** only when every release in both ranges has a sourced review and none is breaking. The plan states the upgrade order from the mainnet schedule. Any other client is rejected, with a hint toward that chain's `--network` command.

Outside this catalog: Lodestar, Grandine, applying the upgrade, node metrics, peer or disk checks, and RPC benchmarks.

## Reading a version

`detect` reads a binary or a Docker image tag. It does not pull or start an image, and it does not run `check`. When the output or the tag is one precise release, it prints that version and the matching `check` command.

| Clients | How the version is read |
| --- | --- |
| Geth, op-geth, bor, BSC, l2geth | `version`, from the `Version:` line |
| Heimdall | `version`. The line is the version alone |
| Nethermind, Erigon, Besu, Reth, Lighthouse, Prysm, Teku, Nimbus, avalanchego, external node, Pathfinder, Juno | `--version` |
| op-node, op-reth, Linea Besu, Maru | Image tag only. The binary is left unrun |

A wrong flag can start a node, so an unknown client is left unread. There is no fallback flag.

Details that change the parsed version:

- l2geth prints `5.10.2-mainnet`. The `mainnet` suffix is metadata, and the Go version on the following lines is ignored.
- avalanchego's version is the `avalanchego/` prefix. The database version and the Go version on that line are ignored.
- The external node prints `zksync_external_node 31.5.0-non-semver-compat`. That suffix is the crate version.
- Pathfinder prints `Pathfinder v0.24.1`. Juno prints `juno version v0.16.8`. A git describe with extra commits is left unread.
- Prysm's binary is `beacon-chain` or `validator`.
- Enter an OP Stack version as `1.19.8`. A full tag such as `op-node/v1.19.8` is also accepted.
- Enter a Linea version as `1.4.0` or `2.3.0`. A full tag such as `releases/maru/v1.4.0` is also accepted. Maru's CLI annotation is `0.0.1`, which is the annotation rather than the release, and its documented run command uses `--network`.

A short tag such as `1.17` is left unread, as are channel names such as `latest`, `stable`, and `nightly`. If the binary fails, the tag is not a release, or more than one version appears, `detect` prints the `check` command with `<installed>` still in place.

Exit 0 means a version was read. Exit 1 means it was not. Exit 3 means the client is unknown.

## Config scan

`scan` reads a config you already have and compares it with sourced flag rules. It prints what to change. It does not edit the file.

The format follows the extension: `.toml`, `.json`, `.yaml`, or `.yml`. A file of command-line flags has no extension requirement. `--format cli|toml|json|yaml` overrides that.

| Exit | Meaning |
| --- | --- |
| 0 | Every setting is covered, and no rule reports a change. |
| 1 | A default changed, a setting is deprecated, or the catalog does not cover a setting. |
| 2 | A setting was removed or renamed. |

A stale catalog cannot return exit 0 for `latest`. A setting with no rule is reported as not covered. It is not called safe.

## Release catalog

`check`, `plan`, and `scan` use the catalog shipped with the package. `refresh` is the only command that talks to GitHub. Set `GH_TOKEN` or `GITHUB_TOKEN` if you hit the unauthenticated rate limit.

GitHub Actions refreshes the catalog twice a week, Monday and Thursday at 06:15 UTC, and merges the update when the release lists change. Run `chaindiff refresh` any time. `chaindiff refresh --client geth` limits the fetch to one client.

The stored catalog is tags, dates, titles, and URLs. Release-note bodies stay on GitHub. A release title that mentions a security fix is reported as a warning. That warning does not by itself make the upgrade safe or unsafe.

Erigon tags from the old date scheme, such as `v2022.10.01`, are left out. They are not comparable with the 2.x and 3.x line.

## Reviews

Safe and not-safe both require a review. Reviews live in `src/chaindiff/data/advisories/<client>.json`:

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

`severity` is `breaking`, `deprecated`, `note`, or `none`. `none` means the release was reviewed and there is nothing to do. `breaking` and `deprecated` need an `action`. Every advisory needs an `http` or `https` source. Leave a release unreviewed until the notes have been read.

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

## Network files

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
    "warning": "A date or table the operator must keep separate from the mainnet requirement.",
    "required": {
      "execution": {},
      "consensus": {}
    }
  }
}
```

`activation` is an ISO time, or `null` when mainnet is unscheduled. `order` is `execution-first`, `consensus-first`, or `null`. `required` maps a client id to a `major.minor.patch` version taken from the announcement. An empty map means that role has no announced requirement. A testnet table stays out of `required`.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Tests that need a private catalog can set `CHAINDIFF_DATA` to a directory with the same `clients.json`, `releases/`, `advisories/`, and `flags/` layout.
