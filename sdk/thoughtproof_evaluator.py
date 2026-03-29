"""
ThoughtProof Evaluator contract interaction client.

Python client for the ThoughtProofEvaluator contract that implements the
APEX evaluator interface with a two-phase verification process:
1. storeVerification - calls ThoughtProof API and stores result
2. finalize - settles the job based on stored verification

Follows the same pattern as APEXEvaluatorClient but adapted for ThoughtProof's
unique verification flow and API integration.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from web3 import Web3
from web3.contract import Contract
import httpx

if TYPE_CHECKING:
    try:
        from bnbagent.wallets.wallet_provider import WalletProvider
    except ImportError:
        # Fallback for standalone usage
        WalletProvider = None

logger = logging.getLogger(__name__)

THOUGHTPROOF_API = "https://api.thoughtproof.ai"

# ThoughtProof Evaluator ABI (simplified for key functions)
THOUGHTPROOF_EVALUATOR_ABI = [
    {
        "type": "function",
        "name": "storeVerification",
        "inputs": [
            {"name": "jobId", "type": "uint256"},
            {"name": "claim", "type": "string"},
            {"name": "speed", "type": "string"},
            {"name": "domain", "type": "string"}
        ],
        "outputs": [],
        "stateMutability": "nonpayable"
    },
    {
        "type": "function",
        "name": "finalize",
        "inputs": [{"name": "jobId", "type": "uint256"}],
        "outputs": [],
        "stateMutability": "nonpayable"
    },
    {
        "type": "function",
        "name": "getVerificationInfo",
        "inputs": [{"name": "jobId", "type": "uint256"}],
        "outputs": [
            {"name": "stored", "type": "bool"},
            {"name": "finalized", "type": "bool"},
            {"name": "passed", "type": "bool"},
            {"name": "confidence", "type": "uint256"},
            {"name": "timestamp", "type": "uint256"}
        ],
        "stateMutability": "view"
    },
    {
        "type": "function",
        "name": "isSettleable",
        "inputs": [{"name": "jobId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view"
    },
    {
        "type": "function",
        "name": "erc8183",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view"
    }
]


@dataclass
class VerificationInfo:
    """Verification information for a job."""
    stored: bool
    finalized: bool
    passed: bool
    confidence: float  # Converted from uint256 to 0-1 range
    timestamp: int


@dataclass
class ThoughtProofResult:
    """Result from ThoughtProof API verification."""
    verdict: str  # ALLOW, BLOCK, UNCERTAIN  
    confidence: float
    passed: bool
    blocked: bool
    objections: list[str]
    epistemic_block: bool
    raw: dict

    @classmethod
    def from_api_response(cls, data: dict) -> ThoughtProofResult:
        """Create from ThoughtProof API response."""
        return cls(
            verdict=data.get("status", "UNCERTAIN").upper(),
            confidence=data.get("confidence", 0.0),
            passed=data.get("passed", False),
            blocked=data.get("blocked", False),
            objections=data.get("objections", []),
            epistemic_block=data.get("epistemicBlock", False),
            raw=data
        )


class PaymentRequired(Exception):
    """Raised when x402 payment is needed for ThoughtProof API."""

    def __init__(self, payment_info: dict):
        self.payment_info = payment_info
        amount = payment_info.get("payment", {}).get("amountUsdc", "?")
        super().__init__(
            f"x402 payment required: {amount} USDC on Base. "
            f"Use an x402-compatible client or pay manually."
        )


class ThoughtProofEvaluatorClient:
    """
    Python client for the ThoughtProof Evaluator contract.
    
    Implements the APEX evaluator interface with ThoughtProof API integration.
    Supports two-phase verification:
    1. storeVerification() - calls API and stores result on-chain
    2. finalize() - settles job based on stored result
    """

    def __init__(
        self,
        web3: Web3,
        contract_address: str,
        private_key: str | None = None,
        abi: list | None = None,
        wallet_provider: WalletProvider | None = None,
        api_timeout: float = 120.0,
    ):
        self.w3 = web3
        self.address = Web3.to_checksum_address(contract_address)
        self.api_timeout = api_timeout

        if abi is None:
            abi = THOUGHTPROOF_EVALUATOR_ABI

        self.contract: Contract = self.w3.eth.contract(address=self.address, abi=abi)
        self._private_key = private_key
        self._wallet_provider = wallet_provider
        
        if wallet_provider is not None:
            self._account = wallet_provider.address
        else:
            self._account = (
                self.w3.eth.account.from_key(private_key).address if private_key else None
            )

    def _send_tx(self, fn, value: int = 0, gas: int = 500_000) -> dict[str, Any]:
        """Send transaction with retry logic (matches APEXEvaluatorClient pattern)."""
        # Import ContractClientMixin for transaction sending
        try:
            from bnbagent.core.contract_mixin import ContractClientMixin
        except ImportError:
            raise ImportError("BNBAgent SDK is required for transaction operations. Please install it or use in an environment where it's available.")
        
        # Create a temporary mixin instance to use _send_tx
        mixin = ContractClientMixin()
        mixin.w3 = self.w3
        mixin._private_key = self._private_key
        mixin._wallet_provider = self._wallet_provider
        mixin._account = self._account
        
        return mixin._send_tx(fn, value=value, gas=gas)

    def _call_with_retry(self, fn):
        """Call read function with retry logic."""
        try:
            from bnbagent.core.contract_mixin import ContractClientMixin
        except ImportError:
            raise ImportError("BNBAgent SDK is required for contract operations. Please install it or use in an environment where it's available.")
        
        mixin = ContractClientMixin()
        mixin.w3 = self.w3
        mixin._private_key = self._private_key
        mixin._wallet_provider = self._wallet_provider
        mixin._account = self._account
        
        return mixin._call_with_retry(fn)

    def _call_thoughtproof_api(
        self, 
        claim: str, 
        speed: str = "standard", 
        domain: str = "general"
    ) -> ThoughtProofResult:
        """
        Call ThoughtProof API for verification.
        
        Args:
            claim: The claim/deliverable to verify
            speed: standard ($0.008), deep ($0.08)
            domain: general, financial, medical, legal, code
            
        Returns:
            ThoughtProofResult with verification outcome
            
        Raises:
            PaymentRequired: If x402 payment is needed
            httpx.HTTPError: On network/server errors
        """
        payload = {
            "claim": claim,
            "speed": speed,
            "domain": domain,
        }

        with httpx.Client(timeout=self.api_timeout) as client:
            response = client.post(
                f"{THOUGHTPROOF_API}/v1/check",
                json=payload,
            )

            if response.status_code == 402:
                # x402 payment required
                payment_info = response.json()
                logger.warning(
                    "x402 payment required: %s USDC on Base to %s",
                    payment_info.get("payment", {}).get("amountUsdc", "?"),
                    payment_info.get("payment", {}).get("recipientWallet", "?"),
                )
                raise PaymentRequired(payment_info)

            response.raise_for_status()
            data = response.json()

        return ThoughtProofResult.from_api_response(data)

    # ── Query Functions ──

    def get_verification_info(self, job_id: int) -> VerificationInfo:
        """
        Get verification info for a job.
        
        Returns:
            VerificationInfo with stored, finalized, passed, confidence, timestamp
        """
        result = self._call_with_retry(self.contract.functions.getVerificationInfo(job_id))
        return VerificationInfo(
            stored=result[0],
            finalized=result[1],
            passed=result[2],
            confidence=result[3] / 10000,  # Convert from basis points to 0-1 range
            timestamp=result[4],
        )

    def is_settleable(self, job_id: int) -> bool:
        """Check if a job can be finalized/settled now."""
        return self._call_with_retry(self.contract.functions.isSettleable(job_id))

    def get_erc8183_address(self) -> str:
        """Get the ERC-8183 contract address."""
        return self._call_with_retry(self.contract.functions.erc8183())

    # ── Write Functions ──

    def store_verification(
        self, 
        job_id: int, 
        claim: str,
        speed: str = "standard",
        domain: str = "general"
    ) -> dict[str, Any]:
        """
        Phase 1: Call ThoughtProof API and store verification result on-chain.
        
        This function:
        1. Calls ThoughtProof API with the claim
        2. Stores the result on-chain via storeVerification()
        
        Args:
            job_id: The APEX job ID
            claim: The claim/deliverable to verify
            speed: API verification speed (standard/deep)
            domain: Domain for verification context
            
        Returns:
            Transaction receipt with API result included
            
        Raises:
            PaymentRequired: If x402 payment is needed
            Exception: On API or transaction errors
        """
        # Call ThoughtProof API first
        logger.info(f"Calling ThoughtProof API for job {job_id} (speed={speed}, domain={domain})")
        api_result = self._call_thoughtproof_api(claim, speed, domain)
        
        logger.info(
            f"ThoughtProof result: {api_result.verdict} | "
            f"Confidence: {api_result.confidence:.2f} | "
            f"Passed: {api_result.passed}"
        )
        
        if api_result.objections:
            logger.info(f"Objections: {api_result.objections}")

        # Store result on-chain
        fn = self.contract.functions.storeVerification(job_id, claim, speed, domain)
        result = self._send_tx(fn)
        
        # Include API result in return data for caller's reference
        result["thoughtproof_result"] = {
            "verdict": api_result.verdict,
            "confidence": api_result.confidence,
            "passed": api_result.passed,
            "blocked": api_result.blocked,
            "objections": api_result.objections,
            "epistemic_block": api_result.epistemic_block,
        }
        
        return result

    def finalize(self, job_id: int) -> dict[str, Any]:
        """
        Phase 2: Finalize/settle the job based on stored verification.
        
        This triggers the contract to complete or reject the job based on
        the previously stored ThoughtProof verification result.
        
        Args:
            job_id: The APEX job ID
            
        Returns:
            Transaction receipt
        """
        fn = self.contract.functions.finalize(job_id)
        return self._send_tx(fn)

    # ── Convenience Methods ──

    def verify_and_store(
        self,
        job_id: int,
        claim: str,
        speed: str = "standard",
        domain: str = "general"
    ) -> dict[str, Any]:
        """
        Convenience method: store verification for a job.
        
        This is the first phase - call ThoughtProof API and store result.
        Call finalize() separately to settle the job.
        """
        return self.store_verification(job_id, claim, speed, domain)

    def complete_evaluation(
        self,
        job_id: int,
        claim: str,
        speed: str = "standard", 
        domain: str = "general",
        auto_finalize: bool = True
    ) -> dict[str, Any]:
        """
        Complete two-phase evaluation: store verification + optionally finalize.
        
        Args:
            job_id: The APEX job ID
            claim: The claim/deliverable to verify
            speed: API verification speed
            domain: Domain for verification context
            auto_finalize: Whether to automatically call finalize() after storing
            
        Returns:
            Combined result from both phases (if auto_finalize=True)
        """
        # Phase 1: Store verification
        store_result = self.store_verification(job_id, claim, speed, domain)
        
        if not auto_finalize:
            return store_result
            
        # Phase 2: Finalize
        try:
            finalize_result = self.finalize(job_id)
            
            # Combine results
            combined_result = {
                "success": True,
                "store_tx": store_result.get("transactionHash"),
                "finalize_tx": finalize_result.get("transactionHash"),
                "thoughtproof_result": store_result.get("thoughtproof_result"),
                "store_receipt": store_result.get("receipt"),
                "finalize_receipt": finalize_result.get("receipt"),
            }
            
            return combined_result
            
        except Exception as e:
            logger.error(f"Failed to finalize job {job_id}: {e}")
            store_result["finalize_error"] = str(e)
            return store_result

    # ── Compatibility Methods (APEX Evaluator Interface) ──

    def initiate_assertion(self, job_id: int) -> dict[str, Any]:
        """
        APEX evaluator interface compatibility.
        
        For ThoughtProof, this does nothing as assertion is initiated
        during storeVerification. This method exists for interface compatibility.
        """
        logger.warning(
            f"initiate_assertion({job_id}) called on ThoughtProof evaluator. "
            f"Use store_verification() instead."
        )
        return {"success": False, "error": "Use store_verification() for ThoughtProof evaluator"}

    def settle_job(self, job_id: int) -> dict[str, Any]:
        """
        APEX evaluator interface compatibility.
        
        Maps to finalize() for ThoughtProof evaluator.
        """
        return self.finalize(job_id)

    def get_assertion_info(self, job_id: int) -> VerificationInfo:
        """
        APEX evaluator interface compatibility.
        
        Maps to get_verification_info() for ThoughtProof evaluator.
        """
        return self.get_verification_info(job_id)