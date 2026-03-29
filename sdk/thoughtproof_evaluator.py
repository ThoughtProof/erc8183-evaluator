"""
ThoughtProof Evaluator client for BNBAgent SDK.

Wraps the ThoughtProofEvaluator v1.3.0 Solidity contract following
the same patterns as APEXEvaluatorClient (ContractClientMixin inheritance,
_send_tx / _call_with_retry, nonce management, retry logic).

Flow:
  1. Call ThoughtProof API off-chain → get verification result
  2. Sign the result with verifierSigner private key
  3. Submit signed attestation on-chain via storeVerification() or submitVerification()
  4. Optionally finalize() later (two-phase) or do it atomically (one-phase)
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3
from web3.contract import Contract

# Import ContractClientMixin — works whether installed as package or via sys.path
try:
    from bnbagent.core.contract_mixin import ContractClientMixin
except ImportError:
    # Standalone mode: minimal mixin stub for development/testing
    class ContractClientMixin:  # type: ignore[no-redef]
        def _send_tx(self, fn, value=0, gas=500_000):
            raise NotImplementedError("Install bnbagent-sdk or provide a WalletProvider")
        def _call_with_retry(self, fn):
            return fn.call()

if TYPE_CHECKING:
    from bnbagent.wallets.wallet_provider import WalletProvider

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────
# Contract ABI — matches ThoughtProofEvaluator.sol v1.3.0 exactly
# ────────────────────────────────────────────

THOUGHTPROOF_EVALUATOR_ABI = [
    # ── Write Functions ──
    {
        "type": "function",
        "name": "submitVerification",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "jobContract", "type": "address"},
            {"name": "jobId", "type": "uint256"},
            {"name": "confidence", "type": "uint256"},
            {"name": "verifierCount", "type": "uint256"},
            {"name": "epistemicBlockHash", "type": "bytes32"},
            {"name": "signature", "type": "bytes"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "storeVerification",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "jobContract", "type": "address"},
            {"name": "jobId", "type": "uint256"},
            {"name": "confidence", "type": "uint256"},
            {"name": "verifierCount", "type": "uint256"},
            {"name": "epistemicBlockHash", "type": "bytes32"},
            {"name": "signature", "type": "bytes"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "finalize",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "jobContract", "type": "address"},
            {"name": "jobId", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "setConfig",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "_defaultThreshold", "type": "uint256"},
            {"name": "_minVerifiers", "type": "uint256"},
            {"name": "_verifierSigner", "type": "address"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "setContractTier",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "jobContract", "type": "address"},
            {"name": "tier", "type": "uint8"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "setContractThreshold",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "jobContract", "type": "address"},
            {"name": "threshold", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "removeContractThreshold",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "jobContract", "type": "address"}],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "setReputationRegistry",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "registry", "type": "address"},
            {"name": "enabled", "type": "bool"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "registerAgentId",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "jobContract", "type": "address"},
            {"name": "agentId", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "removeAgentId",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "jobContract", "type": "address"}],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "transferOwnership",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "newOwner", "type": "address"}],
        "outputs": [],
    },
    # ── Read Functions ──
    {
        "type": "function",
        "name": "getVerification",
        "stateMutability": "view",
        "inputs": [
            {"name": "jobContract", "type": "address"},
            {"name": "jobId", "type": "uint256"},
        ],
        "outputs": [
            {
                "name": "",
                "type": "tuple",
                "components": [
                    {"name": "jobContract", "type": "address"},
                    {"name": "jobId", "type": "uint256"},
                    {"name": "confidence", "type": "uint256"},
                    {"name": "verifierCount", "type": "uint256"},
                    {"name": "epistemicBlockHash", "type": "bytes32"},
                    {"name": "passed", "type": "bool"},
                    {"name": "threshold", "type": "uint256"},
                    {"name": "jobCallSucceeded", "type": "bool"},
                    {"name": "timestamp", "type": "uint256"},
                    {"name": "finalized", "type": "bool"},
                ],
            }
        ],
    },
    {
        "type": "function",
        "name": "isVerified",
        "stateMutability": "view",
        "inputs": [
            {"name": "jobContract", "type": "address"},
            {"name": "jobId", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function",
        "name": "isFinalized",
        "stateMutability": "view",
        "inputs": [
            {"name": "jobContract", "type": "address"},
            {"name": "jobId", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function",
        "name": "getEffectiveThreshold",
        "stateMutability": "view",
        "inputs": [{"name": "jobContract", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "hasCustomThreshold",
        "stateMutability": "view",
        "inputs": [{"name": "jobContract", "type": "address"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function",
        "name": "reputationEnabled",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function",
        "name": "hasAgentId",
        "stateMutability": "view",
        "inputs": [{"name": "jobContract", "type": "address"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function",
        "name": "owner",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "type": "function",
        "name": "verifierSigner",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "type": "function",
        "name": "defaultThreshold",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "minVerifiers",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "totalVerifications",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "totalCompleted",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "totalRejected",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "totalCallFailed",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    # ── Events ──
    {
        "type": "event",
        "name": "VerificationSubmitted",
        "inputs": [
            {"name": "jobContract", "type": "address", "indexed": True},
            {"name": "jobId", "type": "uint256", "indexed": True},
            {"name": "confidence", "type": "uint256", "indexed": False},
            {"name": "verifierCount", "type": "uint256", "indexed": False},
            {"name": "passed", "type": "bool", "indexed": False},
            {"name": "epistemicBlockHash", "type": "bytes32", "indexed": False},
        ],
    },
    {
        "type": "event",
        "name": "VerificationStored",
        "inputs": [
            {"name": "jobContract", "type": "address", "indexed": True},
            {"name": "jobId", "type": "uint256", "indexed": True},
            {"name": "confidence", "type": "uint256", "indexed": False},
            {"name": "passed", "type": "bool", "indexed": False},
        ],
    },
    {
        "type": "event",
        "name": "VerificationFinalized",
        "inputs": [
            {"name": "jobContract", "type": "address", "indexed": True},
            {"name": "jobId", "type": "uint256", "indexed": True},
            {"name": "jobCallSucceeded", "type": "bool", "indexed": False},
        ],
    },
    # ── Errors ──
    {"type": "error", "name": "Unauthorized", "inputs": []},
    {"type": "error", "name": "InvalidSignature", "inputs": []},
    {"type": "error", "name": "SignatureAlreadyUsed", "inputs": []},
    {"type": "error", "name": "AlreadyVerified", "inputs": []},
    {"type": "error", "name": "AlreadyFinalized", "inputs": []},
    {"type": "error", "name": "NotStored", "inputs": []},
    {"type": "error", "name": "InvalidParameters", "inputs": []},
    {"type": "error", "name": "InvalidThreshold", "inputs": []},
    {"type": "error", "name": "BelowMinVerifiers", "inputs": []},
]

# ────────────────────────────────────────────
# Data classes
# ────────────────────────────────────────────

@dataclass
class VerificationResult:
    """On-chain verification result."""
    job_contract: str
    job_id: int
    confidence: int          # basis points (e.g. 850 = 0.850)
    verifier_count: int
    epistemic_block_hash: bytes
    passed: bool
    threshold: int
    job_call_succeeded: bool
    timestamp: int
    finalized: bool


@dataclass
class ThoughtProofAPIResponse:
    """Parsed response from ThoughtProof API."""
    status: str              # "ALLOW", "BLOCK", "UNCERTAIN"
    confidence: float        # 0.0 - 1.0
    mdi: float               # Model Diversity Index 0.0 - 1.0
    passed: bool
    blocked: bool
    verifier_count: int
    objections: list[str] = field(default_factory=list)
    epistemic_block: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


# FailureCost enum values matching the Solidity contract
class FailureCost:
    NEGLIGIBLE = 0  # threshold 500
    LOW = 1         # threshold 600
    MODERATE = 2    # threshold 700
    HIGH = 3        # threshold 800
    CRITICAL = 4    # threshold 900


# ────────────────────────────────────────────
# ThoughtProof API Client
# ────────────────────────────────────────────

THOUGHTPROOF_API_URL = "https://api.thoughtproof.ai/v1/check"

SPEED_TIERS = {
    "fast": 0.008,       # $0.008 USDC
    "standard": 0.02,    # $0.02 USDC
    "deep": 0.08,        # $0.08 USDC
}


def call_thoughtproof_api(
    claim: str,
    speed: str = "standard",
    domain: str = "general",
    api_url: str = THOUGHTPROOF_API_URL,
    timeout: int = 60,
) -> ThoughtProofAPIResponse:
    """
    Call the ThoughtProof verification API.

    Args:
        claim: The claim/reasoning to verify
        speed: Verification tier — "fast", "standard", or "deep"
        domain: Domain context — "general", "financial", "medical", "legal", "code"
        api_url: API endpoint (default: https://api.thoughtproof.ai/v1/check)
        timeout: Request timeout in seconds

    Returns:
        ThoughtProofAPIResponse with verification result

    Raises:
        requests.HTTPError: On API errors (402 = payment required, 429 = rate limit)
    """
    if speed not in SPEED_TIERS:
        raise ValueError(f"Invalid speed '{speed}'. Must be one of: {list(SPEED_TIERS.keys())}")

    payload = {"claim": claim, "speed": speed, "domain": domain}

    resp = requests.post(api_url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    return ThoughtProofAPIResponse(
        status=data.get("status", "UNCERTAIN"),
        confidence=float(data.get("confidence", 0)),
        mdi=float(data.get("mdi", 0)),
        passed=data.get("status") == "ALLOW",
        blocked=data.get("status") == "BLOCK",
        verifier_count=int(data.get("verifierCount", data.get("verifier_count", 0))),
        objections=data.get("objections", []),
        epistemic_block=data.get("epistemicBlock", {}),
        raw=data,
    )


# ────────────────────────────────────────────
# Signature Generation
# ────────────────────────────────────────────

def sign_verification(
    signer_private_key: str,
    job_contract: str,
    job_id: int,
    confidence: int,
    verifier_count: int,
    epistemic_block_hash: bytes,
    chain_id: int,
) -> bytes:
    """
    Sign a verification result matching the contract's signature scheme.

    The contract verifies:
        dataHash = keccak256(abi.encodePacked(
            jobContract, jobId, confidence, verifierCount, epistemicBlockHash, block.chainid
        ))
        messageHash = keccak256("\\x19Ethereum Signed Message:\\n32" + dataHash)
        recovered = ecrecover(messageHash, v, r, s)

    Args:
        signer_private_key: Hex private key of the verifierSigner
        job_contract: ERC-8183 job contract address
        job_id: Job ID
        confidence: Confidence score * 1000 (basis points, e.g. 850)
        verifier_count: Number of models used
        epistemic_block_hash: keccak256 of the epistemic block data
        chain_id: Target chain ID (prevents cross-chain replay)

    Returns:
        65-byte signature (r + s + v)
    """
    # Replicate Solidity: keccak256(abi.encodePacked(...))
    data_hash = Web3.solidity_keccak(
        ["address", "uint256", "uint256", "uint256", "bytes32", "uint256"],
        [
            Web3.to_checksum_address(job_contract),
            job_id,
            confidence,
            verifier_count,
            epistemic_block_hash,
            chain_id,
        ],
    )

    # EIP-191 personal sign (matches contract's \x19Ethereum Signed Message:\n32)
    message = encode_defunct(primitive=data_hash)
    signed = Account.sign_message(message, private_key=signer_private_key)

    return signed.signature


def compute_epistemic_block_hash(epistemic_block: dict) -> bytes:
    """
    Compute keccak256 of the epistemic block JSON (deterministic).

    Args:
        epistemic_block: The full epistemic block dict from the API

    Returns:
        32-byte keccak256 hash
    """
    canonical = json.dumps(epistemic_block, sort_keys=True, separators=(",", ":"))
    return Web3.keccak(text=canonical)


# ────────────────────────────────────────────
# ThoughtProof Evaluator Client
# ────────────────────────────────────────────

class ThoughtProofEvaluatorClient(ContractClientMixin):
    """
    Python client for the ThoughtProofEvaluator v1.3.0 contract.

    Follows the same pattern as APEXEvaluatorClient:
    - Inherits ContractClientMixin for _send_tx / _call_with_retry
    - Uses Web3 contract instance for all interactions
    - Supports both private_key and WalletProvider

    Usage:
        client = ThoughtProofEvaluatorClient(
            web3=w3,
            contract_address="0x...",
            private_key="0x...",
            verifier_signer_key="0x...",  # Key for signing verifications
        )

        # Full pipeline: API call → sign → submit on-chain
        result = client.verify_and_submit(
            job_contract="0x...",
            job_id=42,
            claim="Agent claims the trade was profitable because...",
            speed="standard",
        )
    """

    def __init__(
        self,
        web3: Web3,
        contract_address: str,
        private_key: str | None = None,
        abi: list | None = None,
        wallet_provider: "WalletProvider | None" = None,
        verifier_signer_key: str | None = None,
        api_url: str = THOUGHTPROOF_API_URL,
    ):
        """
        Args:
            web3: Web3 instance connected to the target chain
            contract_address: ThoughtProofEvaluator contract address
            private_key: Private key for sending transactions
            abi: Contract ABI (uses built-in if not provided)
            wallet_provider: Alternative to private_key
            verifier_signer_key: Private key of the authorized verifierSigner
                                 (can be same as private_key or a separate signing key)
            api_url: ThoughtProof API endpoint
        """
        self.w3 = web3
        self.address = Web3.to_checksum_address(contract_address)

        if abi is None:
            abi = THOUGHTPROOF_EVALUATOR_ABI

        self.contract: Contract = self.w3.eth.contract(address=self.address, abi=abi)
        self._private_key = private_key
        self._wallet_provider = wallet_provider
        self._verifier_signer_key = verifier_signer_key or private_key
        self._api_url = api_url

        if wallet_provider is not None:
            self._account = wallet_provider.address
        else:
            self._account = (
                self.w3.eth.account.from_key(private_key).address if private_key else None
            )

    def _send_tx(self, fn, value: int = 0, gas: int = 500_000) -> dict[str, Any]:
        """Override default gas (500k is sufficient for evaluator ops)."""
        return super()._send_tx(fn, value=value, gas=gas)

    # ── High-Level Pipeline ──

    def verify_and_submit(
        self,
        job_contract: str,
        job_id: int,
        claim: str,
        speed: str = "standard",
        domain: str = "general",
        two_phase: bool = False,
    ) -> dict[str, Any]:
        """
        Full pipeline: Call ThoughtProof API → sign result → submit on-chain.

        Args:
            job_contract: ERC-8183 job contract address
            job_id: Job ID to evaluate
            claim: The claim/reasoning to verify
            speed: "fast", "standard", or "deep"
            domain: "general", "financial", "medical", "legal", "code"
            two_phase: If True, only store (don't finalize). Call finalize() later.

        Returns:
            Dict with api_result, confidence, passed, tx_hash, etc.
        """
        job_contract = Web3.to_checksum_address(job_contract)

        # 1. Call ThoughtProof API
        logger.info(f"[ThoughtProof] Verifying job {job_id} on {job_contract} (speed={speed})")
        api_result = call_thoughtproof_api(
            claim=claim, speed=speed, domain=domain, api_url=self._api_url
        )

        # 2. Convert confidence to basis points (contract uses * 1000)
        confidence_bps = int(api_result.confidence * 1000)

        # 3. Compute epistemic block hash
        eb_hash = compute_epistemic_block_hash(api_result.epistemic_block)

        # 4. Get chain ID
        chain_id = self.w3.eth.chain_id

        # 5. Sign the verification
        if not self._verifier_signer_key:
            raise RuntimeError("verifier_signer_key required for signing verifications")

        signature = sign_verification(
            signer_private_key=self._verifier_signer_key,
            job_contract=job_contract,
            job_id=job_id,
            confidence=confidence_bps,
            verifier_count=api_result.verifier_count,
            epistemic_block_hash=eb_hash,
            chain_id=chain_id,
        )

        # 6. Submit on-chain
        if two_phase:
            tx_result = self.store_verification(
                job_contract, job_id, confidence_bps,
                api_result.verifier_count, eb_hash, signature,
            )
        else:
            tx_result = self.submit_verification(
                job_contract, job_id, confidence_bps,
                api_result.verifier_count, eb_hash, signature,
            )

        logger.info(
            f"[ThoughtProof] Job {job_id}: confidence={api_result.confidence:.3f} "
            f"passed={api_result.passed} tx={tx_result.get('transactionHash', 'N/A')}"
        )

        return {
            "api_result": api_result,
            "confidence": api_result.confidence,
            "confidence_bps": confidence_bps,
            "passed": api_result.passed,
            "verifier_count": api_result.verifier_count,
            "epistemic_block_hash": eb_hash.hex(),
            "tx_hash": tx_result.get("transactionHash"),
            "tx_status": tx_result.get("status"),
            "two_phase": two_phase,
        }

    # ── Write Functions (match contract exactly) ──

    def submit_verification(
        self,
        job_contract: str,
        job_id: int,
        confidence: int,
        verifier_count: int,
        epistemic_block_hash: bytes,
        signature: bytes,
    ) -> dict[str, Any]:
        """One-phase: store + finalize atomically."""
        fn = self.contract.functions.submitVerification(
            Web3.to_checksum_address(job_contract),
            job_id, confidence, verifier_count,
            epistemic_block_hash, signature,
        )
        return self._send_tx(fn)

    def store_verification(
        self,
        job_contract: str,
        job_id: int,
        confidence: int,
        verifier_count: int,
        epistemic_block_hash: bytes,
        signature: bytes,
    ) -> dict[str, Any]:
        """Two-phase step 1: store verification without calling job contract."""
        fn = self.contract.functions.storeVerification(
            Web3.to_checksum_address(job_contract),
            job_id, confidence, verifier_count,
            epistemic_block_hash, signature,
        )
        return self._send_tx(fn)

    def finalize(self, job_contract: str, job_id: int) -> dict[str, Any]:
        """Two-phase step 2: finalize stored verification (permissionless)."""
        fn = self.contract.functions.finalize(
            Web3.to_checksum_address(job_contract), job_id,
        )
        return self._send_tx(fn)

    # ── Read Functions ──

    def get_verification(self, job_contract: str, job_id: int) -> VerificationResult:
        """Get the full verification result for a job."""
        r = self._call_with_retry(
            self.contract.functions.getVerification(
                Web3.to_checksum_address(job_contract), job_id,
            )
        )
        return VerificationResult(
            job_contract=r[0],
            job_id=r[1],
            confidence=r[2],
            verifier_count=r[3],
            epistemic_block_hash=r[4],
            passed=r[5],
            threshold=r[6],
            job_call_succeeded=r[7],
            timestamp=r[8],
            finalized=r[9],
        )

    def is_verified(self, job_contract: str, job_id: int) -> bool:
        """Check if a job has been verified (stored, may not be finalized)."""
        return self._call_with_retry(
            self.contract.functions.isVerified(
                Web3.to_checksum_address(job_contract), job_id,
            )
        )

    def is_finalized(self, job_contract: str, job_id: int) -> bool:
        """Check if a verification has been finalized (job contract called)."""
        return self._call_with_retry(
            self.contract.functions.isFinalized(
                Web3.to_checksum_address(job_contract), job_id,
            )
        )

    def get_effective_threshold(self, job_contract: str) -> int:
        """Get the effective threshold for a job contract (custom or default)."""
        return self._call_with_retry(
            self.contract.functions.getEffectiveThreshold(
                Web3.to_checksum_address(job_contract),
            )
        )

    def has_custom_threshold(self, job_contract: str) -> bool:
        """Check if a job contract has a custom threshold."""
        return self._call_with_retry(
            self.contract.functions.hasCustomThreshold(
                Web3.to_checksum_address(job_contract),
            )
        )

    def reputation_enabled(self) -> bool:
        """Check if ERC-8004 reputation feedback is enabled."""
        return self._call_with_retry(self.contract.functions.reputationEnabled())

    def get_owner(self) -> str:
        return self._call_with_retry(self.contract.functions.owner())

    def get_verifier_signer(self) -> str:
        return self._call_with_retry(self.contract.functions.verifierSigner())

    def get_default_threshold(self) -> int:
        return self._call_with_retry(self.contract.functions.defaultThreshold())

    def get_min_verifiers(self) -> int:
        return self._call_with_retry(self.contract.functions.minVerifiers())

    def get_total_verifications(self) -> int:
        return self._call_with_retry(self.contract.functions.totalVerifications())

    def get_total_completed(self) -> int:
        return self._call_with_retry(self.contract.functions.totalCompleted())

    def get_total_rejected(self) -> int:
        return self._call_with_retry(self.contract.functions.totalRejected())

    def get_total_call_failed(self) -> int:
        return self._call_with_retry(self.contract.functions.totalCallFailed())

    def get_stats(self) -> dict[str, int]:
        """Get all counter stats in one call."""
        return {
            "total_verifications": self.get_total_verifications(),
            "total_completed": self.get_total_completed(),
            "total_rejected": self.get_total_rejected(),
            "total_call_failed": self.get_total_call_failed(),
        }

    # ── Admin Functions (owner only) ──

    def set_config(
        self, default_threshold: int, min_verifiers: int, verifier_signer: str,
    ) -> dict[str, Any]:
        """Update evaluator configuration (owner only)."""
        fn = self.contract.functions.setConfig(
            default_threshold, min_verifiers,
            Web3.to_checksum_address(verifier_signer),
        )
        return self._send_tx(fn)

    def set_contract_tier(
        self, job_contract: str, tier: int,
    ) -> dict[str, Any]:
        """Set failure cost tier for a job contract (owner only)."""
        fn = self.contract.functions.setContractTier(
            Web3.to_checksum_address(job_contract), tier,
        )
        return self._send_tx(fn)

    def set_contract_threshold(
        self, job_contract: str, threshold: int,
    ) -> dict[str, Any]:
        """Set custom threshold for a job contract (owner only)."""
        fn = self.contract.functions.setContractThreshold(
            Web3.to_checksum_address(job_contract), threshold,
        )
        return self._send_tx(fn)

    def remove_contract_threshold(self, job_contract: str) -> dict[str, Any]:
        """Remove custom threshold, revert to default (owner only)."""
        fn = self.contract.functions.removeContractThreshold(
            Web3.to_checksum_address(job_contract),
        )
        return self._send_tx(fn)

    def set_reputation_registry(
        self, registry: str, enabled: bool,
    ) -> dict[str, Any]:
        """Set ERC-8004 reputation registry (owner only)."""
        fn = self.contract.functions.setReputationRegistry(
            Web3.to_checksum_address(registry), enabled,
        )
        return self._send_tx(fn)

    def register_agent_id(
        self, job_contract: str, agent_id: int,
    ) -> dict[str, Any]:
        """Register agent ID for a job contract (owner only)."""
        fn = self.contract.functions.registerAgentId(
            Web3.to_checksum_address(job_contract), agent_id,
        )
        return self._send_tx(fn)

    def remove_agent_id(self, job_contract: str) -> dict[str, Any]:
        """Remove agent ID mapping (owner only)."""
        fn = self.contract.functions.removeAgentId(
            Web3.to_checksum_address(job_contract),
        )
        return self._send_tx(fn)
