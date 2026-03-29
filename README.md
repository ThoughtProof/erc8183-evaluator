# BNBAgent ThoughtProof Integration

This module provides seamless integration of [ThoughtProof](https://thoughtproof.ai) reasoning verification into the BNBAgent SDK and APEX (Agent Payment Exchange Protocol).

## Features

- **Automatic Verification**: Integrates ThoughtProof API calls into the APEX job lifecycle
- **Two-Phase Settlement**: Store verification results on-chain, then finalize based on confidence
- **Smart Configuration**: Configurable confidence thresholds, auto-finalization, and retry logic
- **x402 Payment Support**: Handles ThoughtProof's x402 payment flow automatically
- **Error Resilience**: Comprehensive error handling with fallback options
- **Manual Override**: Manual verification and finalization controls
- **APEX Compatible**: Implements standard APEX evaluator interface

## Architecture

The integration consists of three main components:

### 1. ThoughtProofEvaluatorClient

Python client that wraps the ThoughtProofEvaluator smart contract. Provides methods to:
- Call ThoughtProof API and store results on-chain (`storeVerification`)
- Finalize jobs based on stored verification (`finalize`) 
- Query verification status (`getVerificationInfo`, `isSettleable`)

### 2. ThoughtProofHook

Hook integration that automatically triggers verification when jobs are submitted:
- Extracts deliverable content from IPFS/storage
- Constructs verification claims with job context
- Calls ThoughtProof API and stores results
- Schedules automatic finalization based on confidence thresholds

### 3. Example Agent

Complete example showing a BNBAgent with ThoughtProof verification:
- Processes APEX jobs normally
- Automatic verification on submission
- Custom endpoints for verification management
- Graceful error handling and monitoring

## Quick Start

### 1. Install Dependencies

```bash
pip install web3 httpx python-dotenv uvicorn fastapi
```

### 2. Set Environment Variables

Create a `.env` file:

```env
# Wallet configuration
WALLET_PASSWORD=your_secure_password
PRIVATE_KEY=0x1234...  # Optional - auto-generates if not provided

# Network configuration
NETWORK=bsc-testnet
RPC_URL=https://bsc-testnet.bnbchain.org  # Optional - uses network default
ERC8183_ADDRESS=0x3464e64dD53bC093c53050cE5114062765e9F1b6
THOUGHTPROOF_EVALUATOR=0xf6aa6225fbff02455d51b287a33cc86c75897948

# ThoughtProof configuration
THOUGHTPROOF_SPEED=standard  # or "deep"
THOUGHTPROOF_DOMAIN=general  # or "financial", "medical", "legal", "code"
MIN_CONFIDENCE=0.7
AUTO_FINALIZE=true
AUTO_FINALIZE_DELAY=30
```

### 3. Run the Example Agent

```bash
python example_agent.py
```

The agent will start an HTTP server with APEX endpoints plus ThoughtProof-specific routes:

- `POST /apex/submit` - Submit job results (triggers automatic verification)
- `GET /thoughtproof/status` - Get verification system status
- `GET /thoughtproof/job/{id}` - Get verification info for a job
- `POST /thoughtproof/job/{id}/finalize` - Manually finalize a job
- `DELETE /thoughtproof/job/{id}/auto-finalize` - Cancel auto-finalization

## Usage Examples

### Basic Integration

```python
from bnbagent_thoughtproof import (
    ThoughtProofEvaluatorClient,
    ThoughtProofHook, 
    ThoughtProofConfig
)

# Create evaluator client
evaluator = ThoughtProofEvaluatorClient(
    web3=web3,
    contract_address="0xf6aa6225fbff02455d51b287a33cc86c75897948",
    wallet_provider=wallet_provider
)

# Configure automatic verification
config = ThoughtProofConfig(
    verification_speed="standard",
    auto_finalize=True,
    min_confidence_threshold=0.7,
    auto_finalize_delay=30.0
)

# Set up hook for automatic verification
hook = ThoughtProofHook(evaluator, config, storage_provider)

# Register with APEX job operations
hook.on_job_submitted(job_id, job_data)  # Called automatically on submit
```

### Manual Verification

```python
# Manual verification and storage
result = evaluator.store_verification(
    job_id=123,
    claim="This is the deliverable to verify",
    speed="standard",
    domain="general"
)

print(f"Verification stored: {result['transactionHash']}")
print(f"ThoughtProof result: {result['thoughtproof_result']}")

# Check if ready to finalize
if evaluator.is_settleable(job_id):
    # Finalize the job
    finalize_result = evaluator.finalize(job_id)
    print(f"Job finalized: {finalize_result['transactionHash']}")
```

### Custom Claim Construction

```python
config = ThoughtProofConfig(
    custom_claim_template=\"\"\"
    Job #{job_id} Evaluation:
    
    Task: {description}
    Budget: {budget}
    Client: {client}
    
    Deliverable Content:
    {deliverable}
    
    Evaluation Criteria:
    - Does the deliverable fully address the task requirements?
    - Is the quality appropriate for the budget level?
    - Are there any factual errors or reasoning flaws?
    
    Question: Should this deliverable be approved for payment?
    \"\"\"
)
```

## Configuration Options

### ThoughtProofConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `verification_speed` | str | "standard" | API speed: "standard" ($0.008) or "deep" ($0.08) |
| `verification_domain` | str | "general" | Context: "general", "financial", "medical", "legal", "code" |
| `auto_finalize` | bool | True | Whether to automatically finalize jobs |
| `min_confidence_threshold` | float | 0.7 | Minimum confidence for auto-completion |
| `auto_finalize_delay` | float | 30.0 | Seconds to wait before auto-finalize |
| `include_job_context` | bool | True | Include job details in verification claim |
| `max_retries` | int | 3 | Number of retry attempts on API errors |
| `api_timeout` | float | 120.0 | API call timeout in seconds |
| `fallback_on_api_error` | bool | False | Allow jobs through if API fails |

## Contract Addresses

### Mainnet
- **Base**: `0xf6aa6225fbff02455d51b287a33cc86c75897948`

### Testnet  
- **BSC Testnet**: `0x3464e64dD53bC093c53050cE5114062765e9F1b6`

## API Reference

### ThoughtProof API

The integration calls the ThoughtProof API at `https://api.thoughtproof.ai/v1/check`:

**Request:**
```json
{
  "claim": "The deliverable content to verify",
  "speed": "standard",
  "domain": "general"
}
```

**Response:**
```json
{
  "status": "ALLOW",
  "confidence": 0.85,
  "mdi": 0.92,
  "passed": true,
  "blocked": false,
  "objections": [],
  "epistemicBlock": false
}
```

**x402 Payment (if required):**
```json
{
  "payment": {
    "amountUsdc": "0.008",
    "recipientWallet": "0x...",
    "chainId": 8453,
    "network": "base"
  }
}
```

### Contract Interface

The ThoughtProofEvaluator contract implements these key functions:

```solidity
// Phase 1: Store verification result
function storeVerification(
    uint256 jobId,
    string calldata claim,
    string calldata speed,
    string calldata domain
) external;

// Phase 2: Finalize job based on stored result  
function finalize(uint256 jobId) external;

// Query verification status
function getVerificationInfo(uint256 jobId) external view returns (
    bool stored,
    bool finalized,
    bool passed,
    uint256 confidence,
    uint256 timestamp
);

// Check if job can be finalized
function isSettleable(uint256 jobId) external view returns (bool);
```

## Error Handling

The integration handles several error scenarios:

### x402 Payment Required
```python
try:
    result = evaluator.store_verification(job_id, claim)
except PaymentRequired as e:
    print(f"Payment needed: {e.payment_info}")
    # Handle payment flow or manual intervention
```

### API Errors
```python
# Configure fallback behavior
config = ThoughtProofConfig(
    fallback_on_api_error=True,  # Allow jobs through on API failure
    max_retries=3,               # Retry attempts
    retry_delay=5.0              # Delay between retries
)
```

### Low Confidence
```python
# Jobs with low confidence are not auto-finalized
config = ThoughtProofConfig(
    min_confidence_threshold=0.8,  # Require 80% confidence
    auto_finalize=False            # Disable auto-finalize for manual review
)
```

## Monitoring and Management

### Health Checks

```bash
curl http://localhost:8000/thoughtproof/status
```

Returns:
```json
{
  "thoughtproof_enabled": true,
  "evaluator_address": "0xf6aa...",
  "config": {
    "speed": "standard",
    "domain": "general", 
    "auto_finalize": true,
    "min_confidence": 0.7
  },
  "pending_finalizations": 2
}
```

### Job Verification Status

```bash
curl http://localhost:8000/thoughtproof/job/123
```

Returns:
```json
{
  "job_id": 123,
  "verification_info": {
    "stored": true,
    "finalized": false,
    "passed": true,
    "confidence": 0.85,
    "timestamp": 1700000000
  },
  "settleable": true
}
```

### Manual Controls

```bash
# Manually finalize a job
curl -X POST http://localhost:8000/thoughtproof/job/123/finalize

# Cancel auto-finalization
curl -X DELETE http://localhost:8000/thoughtproof/job/123/auto-finalize
```

## Integration with Existing Agents

To add ThoughtProof verification to an existing BNBAgent:

1. **Add the evaluator client:**
```python
from bnbagent_thoughtproof import ThoughtProofEvaluatorClient

evaluator = ThoughtProofEvaluatorClient(web3, contract_address, wallet_provider)
```

2. **Set up the hook:**
```python
from bnbagent_thoughtproof import ThoughtProofHook, ThoughtProofConfig

config = ThoughtProofConfig()
hook = ThoughtProofHook(evaluator, config, agent.storage)
```

3. **Register with job lifecycle:**
```python
# Option 1: Automatic hook (if supported by APEXJobOps)
job_ops.add_submission_hook(hook.on_job_submitted)

# Option 2: Manual integration in your submit handler
async def on_submit(job_id, content, metadata):
    await hook.on_job_submitted(job_id, job_data)
```

4. **Update job creation to use ThoughtProof evaluator:**
```python
result = apex_client.create_job(
    provider=agent_address,
    evaluator=evaluator.address,  # Use ThoughtProof evaluator
    expired_at=expiry,
    description=description
)
```

## Security Considerations

- **Private Key Management**: Use WalletProvider for production deployments
- **x402 Payments**: Ensure sufficient USDC balance on Base for API calls
- **Confidence Thresholds**: Set appropriate confidence levels for your use case
- **Fallback Behavior**: Configure fallback options for API outages
- **Rate Limiting**: ThoughtProof API has rate limits - implement queuing for high volume

## Support

For issues related to:
- **BNBAgent SDK**: Contact BNBAgent support
- **ThoughtProof API**: Visit [thoughtproof.ai](https://thoughtproof.ai)
- **This Integration**: Create an issue in the repository

## License

MIT License - see LICENSE file for details.