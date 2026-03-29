# ERC-8183 ThoughtProof Evaluator

**Advanced multi-model reasoning verification for BNB Chain agents**

[![Contract](https://img.shields.io/badge/Contract-v1.3.0-blue)](./ThoughtProofEvaluator.sol)
[![License](https://img.shields.io/badge/License-MIT-green)](./LICENSE)
[![BNB Chain](https://img.shields.io/badge/BNB_Chain-Compatible-yellow)](https://github.com/bnb-chain/bnbagent-sdk)

A production-ready ERC-8183 evaluator that leverages ThoughtProof's multi-model verification pipeline for autonomous agent work validation. Features two-phase settlement, ERC-8004 reputation integration, signature-based security, and per-contract threshold configuration.

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
    │                ThoughtProofEvaluator v1.3.0                    │
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

## Key Features

- **Two-Phase Settlement**: Store verification results first, finalize later for safer execution
- **Multi-Model Verification**: Grok + Gemini + DeepSeek + Sonnet consensus pipeline
- **EIP-191 Signatures**: Cryptographic verification with replay protection and cross-chain safety
- **Per-Contract Thresholds**: Configure confidence thresholds by contract tier (NEGLIGIBLE to CRITICAL)
- **ERC-8004 Integration**: Automatic reputation feedback for verified agents
- **Permissionless Finalization**: Anyone can finalize stored verifications
- **APEX Protocol Compatible**: Works seamlessly with BNBAgent SDK

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

## Deployment Addresses

### Mainnet
- **Base**: `0xf6aa6225fbff02455d51b287a33cc86c75897948`
- **Base Sepolia**: `0xed8628ca1d02d174b9b7ef1b98408712df0f1e22`

### Testnet
- **BSC Testnet**: `0x3464e64dD53bC093c53050cE5114062765e9F1b6`

### Related Contracts
- **ERC-8004 Registry**: `0x8004A818BFB912233c491871b3d84c89A494BD9e`
- **ThoughtProof Agent**: #28388

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

## Trust Stack Integration

Part of a comprehensive trust infrastructure:

1. **Intuition** (Identity): Know who the agent is
2. **AgentProof** (Reputation): Track agent performance history  
3. **ANP** (Negotiation): Agree on work terms
4. **ThoughtProof** (Verification): Validate work quality ← *This repo*
5. **ar.io** (Archive): Permanent storage of proofs

## Related Repositories

- [ThoughtProof/erc8183-evaluator](https://github.com/ThoughtProof/erc8183-evaluator) - This contract
- [ThoughtProof/pot-sdk](https://github.com/ThoughtProof/pot-sdk) - Python SDK
- [ThoughtProof/pot-api](https://github.com/ThoughtProof/pot-api) - Multi-model API
- [bnb-chain/bnbagent-sdk](https://github.com/bnb-chain/bnbagent-sdk) - APEX protocol

## License

MIT License - see [LICENSE](./LICENSE) for details.
