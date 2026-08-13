# ERC-8183 ThoughtProof Evaluator

> **Status: historical / experimental (updated 2026-08-13).**  
> Read **[STATUS.md](./STATUS.md) first.** This repo is **not** ThoughtProof’s production verification product and does **not** claim ongoing mainnet settlement volume through the listed contracts.  
> Live product surfaces: [sentinel.thoughtproof.ai](https://sentinel.thoughtproof.ai) · [api.thoughtproof.ai](https://api.thoughtproof.ai) · [thoughtproof.ai](https://www.thoughtproof.ai)

**Early ERC-8183 evaluator experiment** — Solidity contract, Foundry tests, and a thin Python SDK sketch that can call ThoughtProof’s off-chain multi-model verification API and submit signed results on-chain.

[![Status](https://img.shields.io/badge/Status-historical%20%2F%20experimental-orange)](./STATUS.md)
[![Source label](https://img.shields.io/badge/Source_label-v1.3.0-lightgrey)](./ThoughtProofEvaluator.sol)
[![License](https://img.shields.io/badge/License-MIT-green)](./LICENSE)

**Source-tree design goals** (see Solidity + tests; verify on-chain before assuming a given deploy has every feature): two-phase settlement helpers, optional ERC-8004 reputation hooks, EIP-191 signatures with replay protection, per-contract thresholds.  
**Do not treat badges, commit titles, or older forum posts as proof of production traffic.** Prefer RPC/explorer history. See also [`GAP_ANALYSIS.md`](./GAP_ANALYSIS.md).

## Architecture

```
     ┌─────────────┐      ┌──────────────────┐      ┌─────────────────┐
     │ Agent/User  │────► │ ThoughtProof API │────► │ Multi-Model AI  │
     │ (Submit)    │      │ /v1/check        │      │ Grok+Gemini+... │
     └─────────────┘      └──────────────────┘      └─────────────────┘
              │                        │                        │
              ▼                        ▼                        ▼
     ┌─────────────┐               ┌────────┐              ┌──────────┐
     │ Job Contract│               │ Result │              │Epistemic │
     │ (ERC-8183)  │               │+ Conf. │              │  Block   │
     └─────────────┘               └────────┘              └──────────┘
              │                        │                        │
              │                        ▼                        ▼
              │              ┌──────────────────┐      ┌─────────────┐
              │              │ EIP-191 Signature│      │   SHA-256   │
              │              │ (verifierSigner) │      │    Hash     │
              │              └──────────────────┘      └─────────────┘
              │                        │                        │
              ▼                        ▼                        ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │           ThoughtProofEvaluator (source-tree design)           │
    │                                                                 │
    │  Phase 1: storeVerification()     Phase 2: finalize()          │
    │  ├─ Verify signature              ├─ Check stored result        │
    │  ├─ Store result on-chain         ├─ Call job.complete()        │
    │  ├─ Send ERC-8004 feedback        └─ Or job.reject()            │
    │  └─ Emit VerificationStored                                     │
    │                                                                 │
    │  OR: submitVerification() (atomic store + finalize)            │
    └─────────────────────────────────────────────────────────────────┘
              │                                              │
              ▼                                              ▼
    ┌─────────────────┐                            ┌─────────────────┐
    │ ERC-8004        │                            │ Job Contract    │
    │ Reputation      │                            │ complete() or   │
    │ Registry        │                            │ reject()        │
    └─────────────────┘                            └─────────────────┘
```

## Design features (source / tests)

These describe the **intended contract/SDK design** in this tree — not a warranty that every deployed address ran them in production:

- **Two-phase settlement helpers**: store verification results, then finalize
- **Off-chain multi-model verification**: API-side consensus pipeline (models configurable over time)
- **EIP-191 signatures**: cryptographic verification with replay protection and chain id binding
- **Per-contract thresholds**: configure confidence thresholds by contract tier
- **Optional ERC-8004 reputation hooks**: when a registry is configured and enabled
- **Permissionless finalization path**: where implemented in source
- **BNBAgent / APEX sketches**: experimental integration examples (testnet-oriented)

For known source/test gaps during the v1.3.0 push, see [`GAP_ANALYSIS.md`](./GAP_ANALYSIS.md).

## Quick Start

### 1. Install Dependencies

```bash
pip install web3 requests eth-account
```

### 2. Initialize Client

```python
from web3 import Web3
from sdk.thoughtproof_evaluator import ThoughtProofEvaluatorClient

# Connect to BNB Chain
w3 = Web3(Web3.HTTPProvider("https://bsc-dataseed1.binance.org"))

# Initialize evaluator
evaluator = ThoughtProofEvaluatorClient(
    web3=w3,
    contract_address="0x3464e64dD53bC093c53050cE5114062765e9F1b6",  # BSC Testnet
    private_key="0x...",  # Your transaction key
    verifier_signer_key="0x..."  # ThoughtProof verifier key (Agent #28388)
)
```

### 3. Verify Agent Work

```python
# Option A: Full pipeline (API + on-chain)
result = evaluator.verify_and_submit(
    job_contract="0xJobContractAddress",
    job_id=42,
    claim="Agent delivered a profitable trading strategy with 15% returns...",
    speed="standard",  # $0.02 USDC
    domain="financial",
    two_phase=True  # Store first, finalize separately
)

print(f"Confidence: {result['api_result'].confidence}")
print(f"Passed: {result['api_result'].passed}")
print(f"TX: {result['tx_hash']}")

# Option B: Two-phase manual control
api_result = evaluator.call_thoughtproof_api(
    claim="The deliverable meets all requirements...",
    speed="deep",  # $0.08 USDC for complex verification
    domain="code"
)

signature = evaluator.sign_verification(
    job_contract="0x...",
    job_id=42,
    confidence=int(api_result.confidence * 1000),
    verifier_count=api_result.verifier_count,
    epistemic_block_hash=api_result.epistemic_block_hash
)

# Store on-chain
store_tx = evaluator.store_verification(
    job_contract="0x...",
    job_id=42,
    confidence=int(api_result.confidence * 1000),
    verifier_count=api_result.verifier_count,
    epistemic_block_hash=api_result.epistemic_block_hash,
    signature=signature
)

# Finalize later (permissionless)
finalize_tx = evaluator.finalize("0x...", 42)
```

### 4. Set Up Auto-Verification Hook

```python
from sdk.thoughtproof_hook import ThoughtProofVerificationHook, HookConfig

# Configure hook
config = HookConfig(
    speed="standard",
    domain="general", 
    two_phase=True,
    auto_finalize=True,
    auto_finalize_delay=30,  # Wait 30s before finalizing
    fail_open=False  # Strict mode: block job if verification fails
)

hook = ThoughtProofVerificationHook(evaluator, config)

# Integrate with APEX job lifecycle
async def on_job_submitted(job_contract: str, job_id: int, deliverable: str):
    result = hook.on_job_submitted(job_contract, job_id, deliverable=deliverable)
    if result.success:
        logger.info(f"Job {job_id} verified: {result.api_result.confidence:.1%}")
    else:
        logger.error(f"Verification failed: {result.error}")
```

## Contract Interface

### Core Functions

```solidity
// Submit verification (atomic: store + finalize)
function submitVerification(
    address jobContract,
    uint256 jobId,
    uint256 confidence,      // * 1000 (e.g., 850 = 85.0%)
    uint256 verifierCount,   // Number of AI models
    bytes32 epistemicBlockHash,
    bytes signature          // EIP-191 signature
) external;

// Two-phase: store verification result
function storeVerification(
    address jobContract,
    uint256 jobId,
    uint256 confidence,
    uint256 verifierCount,
    bytes32 epistemicBlockHash,
    bytes signature
) external;

// Two-phase: finalize stored verification (permissionless)
function finalize(
    address jobContract,
    uint256 jobId
) external;
```

### Configuration

```solidity
// Update global config (owner only)
function setConfig(
    uint256 defaultThreshold,  // 100-1000
    uint256 minVerifiers,      // >= 2
    address verifierSigner
) external onlyOwner;

// Set contract-specific threshold
function setContractThreshold(
    address jobContract,
    uint256 threshold  // 100-1000
) external onlyOwner;

// Set contract failure tier (auto-maps to threshold)
function setContractTier(
    address jobContract,
    FailureCost tier
) external onlyOwner;

// Enum FailureCost { NEGLIGIBLE(500), LOW(600), MODERATE(700), HIGH(800), CRITICAL(900) }
```

### ERC-8004 Reputation

```solidity
// Enable reputation feedback
function setReputationRegistry(
    address registry,
    bool enabled
) external onlyOwner;

// Register agent ID for a job contract
function registerAgentId(
    address jobContract,
    uint256 agentId
) external onlyOwner;
```

### Read Functions

```solidity
// Get verification result
function results(
    address jobContract,
    uint256 jobId
) external view returns (
    address jobContract,
    uint256 jobId,
    uint256 confidence,
    uint256 verifierCount,
    bytes32 epistemicBlockHash,
    bool passed,
    uint256 threshold,
    bool jobCallSucceeded,
    uint256 timestamp,
    bool finalized
);

// Check effective threshold for a contract
function getEffectiveThreshold(
    address jobContract
) external view returns (uint256);

// Check if verification exists and is finalized
function isVerified(
    address jobContract,
    uint256 jobId
) external view returns (bool);

function isFinalized(
    address jobContract,
    uint256 jobId
) external view returns (bool);
```

## Python SDK Reference

### ThoughtProofEvaluatorClient

```python
class ThoughtProofEvaluatorClient(ContractClientMixin):
    def __init__(
        self,
        web3: Web3,
        contract_address: str,
        private_key: str | None = None,
        wallet_provider: WalletProvider | None = None,
        verifier_signer_key: str | None = None,
        api_url: str = "https://api.thoughtproof.ai/v1/check"
    )
    
    # High-level pipeline
    def verify_and_submit(
        self,
        job_contract: str,
        job_id: int,
        claim: str,
        speed: str = "standard",
        domain: str = "general",
        two_phase: bool = False
    ) -> dict[str, Any]
    
    # API integration
    def call_thoughtproof_api(
        self, claim: str, speed: str, domain: str
    ) -> ThoughtProofAPIResponse
    
    # Signature generation
    def sign_verification(
        self,
        job_contract: str,
        job_id: int,
        confidence: int,
        verifier_count: int,
        epistemic_block_hash: bytes
    ) -> bytes
    
    # Contract interactions
    def submit_verification(self, ...) -> dict[str, Any]
    def store_verification(self, ...) -> dict[str, Any]
    def finalize(self, job_contract: str, job_id: int) -> dict[str, Any]
    
    # Read functions
    def get_verification(self, job_contract: str, job_id: int) -> dict
    def is_verified(self, job_contract: str, job_id: int) -> bool
    def is_finalized(self, job_contract: str, job_id: int) -> bool
    def get_effective_threshold(self, job_contract: str) -> int
    def get_stats(self) -> dict[str, int]
    
    # Admin functions
    def set_config(self, threshold: int, min_verifiers: int, signer: str) -> dict
    def set_contract_tier(self, job_contract: str, tier: int) -> dict
    def set_contract_threshold(self, job_contract: str, threshold: int) -> dict
    def set_reputation_registry(self, registry: str, enabled: bool) -> dict
    def register_agent_id(self, job_contract: str, agent_id: int) -> dict
```

### ThoughtProofVerificationHook

```python
@dataclass
class HookConfig:
    speed: str = "standard"              # "fast", "standard", "deep"
    domain: str = "general"              # Verification domain
    two_phase: bool = True               # Store first, finalize later
    auto_finalize: bool = True           # Auto-finalize after store
    auto_finalize_delay: int = 0         # Seconds to wait
    include_job_description: bool = True  # Include job context
    fail_open: bool = False              # Block on verification failure
    max_retries: int = 2                 # API retry attempts

class ThoughtProofVerificationHook:
    def __init__(self, evaluator: ThoughtProofEvaluatorClient, config: HookConfig)
    
    def on_job_submitted(
        self,
        job_contract: str,
        job_id: int,
        description: str = "",
        deliverable: str = "",
        metadata: dict | None = None
    ) -> VerificationEvent
    
    # FastAPI route registration
    def register_routes(self, app) -> None
    # Routes: /thoughtproof/{verify,status,finalize,stats}
```

## Security Model

### Signature Verification

```python
# EIP-191 signature with chain ID for replay protection
data_hash = keccak256(
    jobContract + jobId + confidence + verifierCount + epistemicBlockHash + chainId
)
message_hash = keccak256("\\x19Ethereum Signed Message:\\n32" + data_hash)
recovered = ecrecover(message_hash, signature)
assert recovered == verifierSigner
```

### Threshold Tiers

| Tier | Threshold | Use Case |
|------|-----------|----------|
| NEGLIGIBLE | 50.0% | Simple tasks, low impact |
| LOW | 60.0% | Standard verification |
| MODERATE | 70.0% | Important decisions |
| HIGH | 80.0% | Financial operations |
| CRITICAL | 90.0% | High-stakes verification |

### Anti-Replay Protection

- Each signature includes `block.chainid` for cross-chain safety
- Used signatures are tracked in `usedSignatures` mapping
- Prevents double-spending of verification results

## Deployment addresses (experimental — verify on-chain)

> **Full honesty notes:** [`STATUS.md`](./STATUS.md). Addresses below are **deploy references**, not proof of production settlement traffic.

| Network | Address | Role |
|---|---|---|
| Base mainnet (early) | `0x119299F33f918808edD5ef92bd79cefB8700C091` | Early evaluator deploy (v1.1-era). Historical Magicians reference. |
| Base mainnet (later) | `0xf6aa6225fbff02455d51b287a33cc86c75897948` | Deploy associated with this source tree’s v1.3.0 label. **Experimental.** |
| Base Sepolia | `0xed8628ca1d02d174b9b7ef1b98408712df0f1e22` | Testnet |
| BSC testnet | `0x3464e64dD53bC093c53050cE5114062765e9F1b6` | Testnet / APEX experiments |

### Related identifiers (not “TP owns this registry”)
- Example ERC-8004 registry address referenced in older docs: `0x8004A818BFB912233c491871b3d84c89A494BD9e` — **confirm canonicity and holdings yourself**; this repo does not claim exclusive or production reputation writes there.
- ThoughtProof ERC-8004 agent id (historical reference): `#28388`

**External diligence rule:** if logs/tx history are empty beyond deploy, do **not** describe the address as a live production evaluator.

## ThoughtProof Integration

### API Endpoints

```bash
POST https://api.thoughtproof.ai/v1/check
Content-Type: application/json

{
  "claim": "The agent's trading algorithm achieved 15% returns...",
  "speed": "standard",  # fast($0.008) | standard($0.02) | deep($0.08)
  "domain": "financial" # general | financial | medical | legal | code
}
```

### Response Format

```json
{
  "status": "ALLOW",
  "confidence": 0.85,
  "passed": true,
  "blocked": false,
  "objections": [],
  "verifierCount": 4,
  "epistemicBlock": {
    "models": ["grok", "gemini", "deepseek", "sonnet"],
    "consensus": 0.85,
    "reasoning": "...",
    "metadata": {...}
  },
  "epistemicBlockHash": "0x1234..."
}
```

### Payment (x402 Protocol)

When payment is required:

```json
{
  "payment": {
    "amountUsdc": "0.02",
    "recipientWallet": "0x...",
    "chainId": 8453,
    "network": "base"
  }
}
```

## BNBAgent SDK Integration

Compatible with the [bnb-chain/bnbagent-sdk](https://github.com/bnb-chain/bnbagent-sdk) APEX protocol:

```python
# Create job with ThoughtProof evaluator
result = apex_client.create_job(
    provider=agent_address,
    evaluator="0x3464e64dD53bC093c53050cE5114062765e9F1b6",  # ThoughtProof
    expired_at=int(time.time()) + 3600,
    description="Analyze trading opportunities",
    expected_result_schema=schema
)

# Hook will automatically verify on submission
hook.on_job_submitted(
    job_contract=result["contractAddress"],
    job_id=result["jobId"],
    description="Analyze trading opportunities",
    deliverable=agent_output
)
```

## Related surfaces

- **[STATUS.md](./STATUS.md)** — claim hygiene / what is and is not production
- **[GAP_ANALYSIS.md](./GAP_ANALYSIS.md)** — source/test gap notes from the v1.3.0 push
- Live verification today: [sentinel.thoughtproof.ai](https://sentinel.thoughtproof.ai), [api.thoughtproof.ai](https://api.thoughtproof.ai)
- [bnb-chain/bnbagent-sdk](https://github.com/bnb-chain/bnbagent-sdk) — APEX protocol (external)

## License

MIT License - see [LICENSE](./LICENSE) for details.
