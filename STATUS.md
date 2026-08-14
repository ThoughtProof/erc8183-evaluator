# Status (read this first)

**Last updated:** 2026-08-14  
**Repo status:** **historical / experimental** — not a production settlement product surface.

## What this repository is

Source and deploy artifacts for an **early ERC-8183 evaluator experiment** (March 2026): Solidity evaluator contract, Foundry tests, and a thin Python SDK sketch that can call ThoughtProof’s off-chain verification API and submit signed results on-chain.

## What this repository is not

- **Not** ThoughtProof’s current production gate (that is the live HTTP APIs: Sentinel / `/v1/check` and related products).
- **Not** a claim of ongoing mainnet settlement volume through these contracts.
- **Not** a claim that every feature named in older commit messages or badges was live on every deployed address at announce time.

## Honest deployment note

| Address | Chain | Notes (as of 2026-08-14) |
|---|---|---|
| `0x119299F33f918808edD5ef92bd79cefB8700C091` | Base mainnet | Early (v1.1-era) deploy. Contract code present. **No production settlement traffic claimed.** Independent full-range log scan (deploy→head, 2026-08-13): **0 logs**. Bytecode is **pre-two-phase** (has single-phase `submitVerification`; lacks `storeVerification`/`finalize` and ERC-8004 reputation selectors). Do **not** read forum “v1.3.0 reputation integration” language as a description of *this* bytecode. |
| `0xf6aa6225fbff02455d51b287a33cc86c75897948` | Base mainnet | Later deploy (block 43,441,448 · 2026-03-16) associated with the v1.3.0 source tree. Contract code present (~13,817 B). **Code shape:** independent selector scan finds the v1.3.0-distinguishing two-phase + reputation family present — “associated with the v1.3.0 source tree” is accurate for *this* address. **Usage:** experimental only; **no production settlement traffic.** Explorer history is deploy-only; balance 0; independent recon (2026-08-13/14): **0 operational logs / never called** after deploy. Right code, deployed, unused. |
| `0xed8628ca1d02d174b9b7ef1b98408712df0f1e22` | Base Sepolia | Testnet deploy. |
| `0x3464e64dD53bC093c53050cE5114062765e9F1b6` | BSC testnet | Testnet / APEX experiments. |

**Verification policy for external readers:** trust **RPC + explorer history + bytecode**, not badges or version strings. If `eth_getLogs` / tx history shows no operational calls, the deploy is not “production traffic.”

## Source vs deploy gaps

See [`GAP_ANALYSIS.md`](./GAP_ANALYSIS.md). That document records places where tests/docs expected a richer v1.3.0 surface than an earlier contract revision provided. Treat it as an internal honesty artifact, not as marketing.

Contract headers and SDK constants may still say `v1.3.0` as a **source-tree label**. That label is **not** a warranty that every listed mainnet address continuously ran every documented feature in production.

## Where ThoughtProof verification actually runs today

| Surface | Role |
|---|---|
| https://sentinel.thoughtproof.ai | Live agentic verification API |
| https://api.thoughtproof.ai | PoT / check API |
| https://www.thoughtproof.ai | Product site |

ERC-8183 contribution work (forum, hooks, evaluator composition discussion) continues separately from these experimental mainnet deploys.

## Correction posture

If you are doing independent on-chain diligence: thank you. Prefer this file + on-chain evidence over archived social/forum posts from March 2026. Forum posts are historical and may overstate operational maturity relative to later product focus.

## Explorer links (Base)

| Address | Basescan | Blockscout |
|---|---|---|
| `0x119299F33f918808edD5ef92bd79cefB8700C091` | [basescan](https://basescan.org/address/0x119299F33f918808edD5ef92bd79cefB8700C091) | [blockscout](https://base.blockscout.com/address/0x119299F33f918808edD5ef92bd79cefB8700C091) |
| `0xf6aa6225fbff02455d51b287a33cc86c75897948` | [basescan](https://basescan.org/address/0xf6aa6225fbff02455d51b287a33cc86c75897948) | [blockscout](https://base.blockscout.com/address/0xf6aa6225fbff02455d51b287a33cc86c75897948) |

## Claim correction log

### 2026-08-13 — public claim hygiene

| Previously easy to misread | Correct reading |
|---|---|
| README “production-ready” evaluator | **Historical / experimental** source + deploys; not a current production settlement product |
| Mainnet addresses listed without usage caveat | **Deploy references only** — verify bytecode and tx/log history yourself; no ongoing production settlement volume claimed through these contracts |
| Source-tree label `v1.3.0` | Label for the **repository source tree**, not a warranty that every address always ran every documented feature |
| Forum “v1.3.0 + ERC-8004 reputation” on `0x1192…` | **Inaccurate for that bytecode** — pre-two-phase / no reputation selectors (see deploy table + GAP_ANALYSIS) |
| Current ThoughtProof verification | Live **HTTP APIs** (Sentinel / check), separate from these March evaluator deploys |

### 2026-08-14 — `0xf6aa…` usage honesty

| Previously easy to misread | Correct reading |
|---|---|
| `0xf6aa…` listed with v1.3 association but without an explicit silence note | **Code shape OK for v1.3.0 association** (two-phase + reputation selectors present). **Usage still experimental / unused** — deploy-only history, balance 0, **0 operational logs / never called** (independent recon 2026-08-13/14). Same outcome as `0x1192…` on traffic; different reason on bytecode. |

**Git trail:** PR [#1](https://github.com/ThoughtProof/erc8183-evaluator/pull/1) · merge `f488290` · pre-correction tip `18a25bd` · PR [#3](https://github.com/ThoughtProof/erc8183-evaluator/pull/3) (`0x1192…` bytecode) · this file’s `0xf6aa…` silence note.  
**Do not rewrite history.** Corrections clarify; they do not erase March artifacts.

