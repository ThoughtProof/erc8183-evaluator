"""
BNBAgent ThoughtProof Integration Module.

This module provides seamless integration of ThoughtProof reasoning verification
into the BNBAgent SDK and APEX (Agent Payment Exchange Protocol).

Components:
- ThoughtProofEvaluatorClient: Contract client for ThoughtProofEvaluator
- ThoughtProofHook: Automatic verification hook for job submissions  
- ThoughtProofConfig: Configuration for verification behavior
- Example agent with complete integration

Quick Start:
    from bnbagent_thoughtproof import (
        ThoughtProofEvaluatorClient, 
        ThoughtProofHook, 
        ThoughtProofConfig
    )
    
    # Create evaluator client
    evaluator = ThoughtProofEvaluatorClient(web3, contract_address, private_key)
    
    # Configure automatic verification
    config = ThoughtProofConfig(
        verification_speed="standard",
        auto_finalize=True,
        min_confidence_threshold=0.7
    )
    
    # Register hook for automatic verification
    hook = ThoughtProofHook(evaluator, config, storage_provider)

Features:
- Automatic ThoughtProof API integration on job submission
- Two-phase verification: store result + finalize settlement
- Configurable confidence thresholds and auto-finalization
- x402 payment handling for ThoughtProof API
- Error handling and retry logic
- Manual override capabilities
- Compatible with existing APEX evaluator interface

Contract Integration:
The ThoughtProofEvaluator contract implements the APEX evaluator interface
with these key functions:
- storeVerification(jobId, claim, speed, domain) - Phase 1: API call + store result
- finalize(jobId) - Phase 2: settle job based on stored result  
- getVerificationInfo(jobId) - Query stored verification data
- isSettleable(jobId) - Check if job can be finalized

API Integration:
Integrates with ThoughtProof API (https://api.thoughtproof.ai/v1/check):
- Handles x402 payment flow automatically
- Supports different verification speeds (standard, deep)
- Domain-specific verification contexts
- Confidence scoring and objection handling

See example_agent.py for a complete implementation example.
"""

from .thoughtproof_evaluator import (
    ThoughtProofEvaluatorClient,
    VerificationInfo,
    ThoughtProofResult,
    PaymentRequired,
)

from .thoughtproof_hook import (
    ThoughtProofHook,
    ThoughtProofConfig, 
    register_thoughtproof_hook,
)

__version__ = "1.0.0"
__author__ = "BNBAgent Team"
__email__ = "team@bnbagent.com"
__description__ = "ThoughtProof reasoning verification integration for BNBAgent SDK"

__all__ = [
    # Core client
    "ThoughtProofEvaluatorClient",
    "VerificationInfo", 
    "ThoughtProofResult",
    "PaymentRequired",
    
    # Hook integration
    "ThoughtProofHook",
    "ThoughtProofConfig",
    "register_thoughtproof_hook",
    
    # Version info
    "__version__",
]


def get_version() -> str:
    """Get the version of the ThoughtProof integration module."""
    return __version__


def get_contract_addresses() -> dict[str, str]:
    """
    Get known ThoughtProof contract addresses by network.
    
    Returns:
        Dict mapping network names to contract addresses
    """
    return {
        "base-mainnet": "0xf6aa6225fbff02455d51b287a33cc86c75897948",
        "bsc-testnet": "0x3464e64dD53bC093c53050cE5114062765e9F1b6",  # Example - replace with actual
        "ethereum-mainnet": "0x8004A818BFB912233c491871b3d84c89A494BD9e",  # Example - replace with actual
    }


def create_default_config(**overrides) -> ThoughtProofConfig:
    """
    Create a ThoughtProofConfig with sensible defaults.
    
    Args:
        **overrides: Override any config parameters
        
    Returns:
        ThoughtProofConfig instance
        
    Example:
        config = create_default_config(
            verification_speed="deep",
            min_confidence_threshold=0.8
        )
    """
    defaults = {
        "verification_speed": "standard",
        "verification_domain": "general", 
        "auto_finalize": True,
        "min_confidence_threshold": 0.7,
        "auto_finalize_delay": 30.0,
        "include_job_context": True,
        "max_retries": 3,
        "api_timeout": 120.0,
    }
    
    defaults.update(overrides)
    return ThoughtProofConfig(**defaults)


# Module-level convenience functions

def verify_claim_sync(
    claim: str,
    speed: str = "standard", 
    domain: str = "general",
    timeout: float = 120.0
) -> ThoughtProofResult:
    """
    Synchronous convenience function to verify a claim via ThoughtProof API.
    
    This is a lightweight wrapper around the API client for one-off verifications.
    For production use with contract integration, use ThoughtProofEvaluatorClient.
    
    Args:
        claim: The claim/content to verify
        speed: Verification speed (standard/deep)
        domain: Domain context (general/financial/medical/legal/code)
        timeout: API timeout in seconds
        
    Returns:
        ThoughtProofResult with verification outcome
        
    Raises:
        PaymentRequired: If x402 payment is needed
        httpx.HTTPError: On API errors
    """
    import httpx
    
    payload = {
        "claim": claim,
        "speed": speed,
        "domain": domain,
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            "https://api.thoughtproof.ai/v1/check",
            json=payload,
        )

        if response.status_code == 402:
            payment_info = response.json()
            raise PaymentRequired(payment_info)

        response.raise_for_status()
        data = response.json()

    return ThoughtProofResult.from_api_response(data)


async def verify_claim_async(
    claim: str,
    speed: str = "standard",
    domain: str = "general", 
    timeout: float = 120.0
) -> ThoughtProofResult:
    """
    Asynchronous convenience function to verify a claim via ThoughtProof API.
    
    Args:
        claim: The claim/content to verify
        speed: Verification speed (standard/deep)
        domain: Domain context (general/financial/medical/legal/code)
        timeout: API timeout in seconds
        
    Returns:
        ThoughtProofResult with verification outcome
        
    Raises:
        PaymentRequired: If x402 payment is needed
        httpx.HTTPError: On API errors
    """
    import httpx
    
    payload = {
        "claim": claim,
        "speed": speed,
        "domain": domain,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            "https://api.thoughtproof.ai/v1/check",
            json=payload,
        )

        if response.status_code == 402:
            payment_info = response.json()
            raise PaymentRequired(payment_info)

        response.raise_for_status()
        data = response.json()

    return ThoughtProofResult.from_api_response(data)