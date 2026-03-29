"""
ThoughtProof Evaluator SDK — Epistemic verification for ERC-8183 agentic commerce.

Quick start:
    from sdk import ThoughtProofEvaluatorClient, ThoughtProofVerificationHook

    client = ThoughtProofEvaluatorClient(web3=w3, contract_address="0x...", ...)
    result = client.verify_and_submit(job_contract="0x...", job_id=42, claim="...")
"""

from .thoughtproof_evaluator import (
    ThoughtProofEvaluatorClient,
    ThoughtProofAPIResponse,
    VerificationResult,
    FailureCost,
    call_thoughtproof_api,
    sign_verification,
    compute_epistemic_block_hash,
    THOUGHTPROOF_EVALUATOR_ABI,
    THOUGHTPROOF_API_URL,
    SPEED_TIERS,
)

from .thoughtproof_hook import (
    ThoughtProofVerificationHook,
    HookConfig,
    VerificationEvent,
)

__version__ = "1.3.0"
__all__ = [
    # Client
    "ThoughtProofEvaluatorClient",
    "ThoughtProofAPIResponse",
    "VerificationResult",
    "FailureCost",
    # API
    "call_thoughtproof_api",
    "sign_verification",
    "compute_epistemic_block_hash",
    # Hook
    "ThoughtProofVerificationHook",
    "HookConfig",
    "VerificationEvent",
    # Constants
    "THOUGHTPROOF_EVALUATOR_ABI",
    "THOUGHTPROOF_API_URL",
    "SPEED_TIERS",
]

# Contract addresses
CONTRACTS = {
    "base_mainnet": "0xf6aa6225fbff02455d51b287a33cc86c75897948",
    "base_sepolia": "0xed8628ca1d02d174b9b7ef1b98408712df0f1e22",
    "bsc_testnet": "0x3464e64dD53bC093c53050cE5114062765e9F1b6",  # ERC-8183
}
