# Status (read this first)

**Last updated:** 2026-08-13  
**Repo status:** **historical / experimental** — not a production settlement product surface.

## What this repository is

Source and deploy artifacts for an **early ERC-8183 evaluator experiment** (March 2026): Solidity evaluator contract, Foundry tests, and a thin Python SDK sketch that can call ThoughtProof’s off-chain verification API and submit signed results on-chain.

## What this repository is not

- **Not** ThoughtProof’s current production gate (that is the live HTTP APIs: Sentinel / `/v1/check` and related products).
- **Not** a claim of ongoing mainnet settlement volume through these contracts.
- **Not** a claim that every feature named in older commit messages or badges was live on every deployed address at announce time.

## Honest deployment note

| Address | Chain | Notes (as of 2026-08-13) |
|---|---|---|
| `0x119299F33f918808edD5ef92bd79cefB8700C091` | Base mainnet | Early (v1.1-era) deploy. Contract code present. **No production settlement traffic claimed.** |
| `0xf6aa6225fbff02455d51b287a33cc86c75897948` | Base mainnet | Later deploy associated with the v1.3.0 source tree. Contract code present. **Treat as experimental; do not assume production usage.** |
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
| Current ThoughtProof verification | Live **HTTP APIs** (Sentinel / check), separate from these March evaluator deploys |

**Git trail:** PR [#1](https://github.com/ThoughtProof/erc8183-evaluator/pull/1) · merge `f488290` · pre-correction tip `18a25bd`.  
**Do not rewrite history.** Corrections clarify; they do not erase March artifacts.

