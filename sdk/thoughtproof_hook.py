"""
ThoughtProof verification hook for BNBAgent APEX protocol.

Automatically verifies agent work when jobs are submitted.
Plugs into the APEX job lifecycle as a post-submission hook.

Usage:
    from sdk.thoughtproof_evaluator import ThoughtProofEvaluatorClient
    from sdk.thoughtproof_hook import ThoughtProofVerificationHook

    evaluator = ThoughtProofEvaluatorClient(web3=w3, ...)
    hook = ThoughtProofVerificationHook(evaluator=evaluator)

    # Manual trigger
    result = hook.on_job_submitted(job_contract="0x...", job_id=42)

    # Or integrate with APEX server routes
    hook.register_routes(app)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from web3 import Web3

from .thoughtproof_evaluator import (
    ThoughtProofEvaluatorClient,
    ThoughtProofAPIResponse,
    call_thoughtproof_api,
)

logger = logging.getLogger(__name__)


@dataclass
class HookConfig:
    """Configuration for the verification hook."""

    # Verification settings
    speed: str = "standard"              # "fast", "standard", "deep"
    domain: str = "general"              # "general", "financial", "medical", "legal", "code"
    two_phase: bool = True               # Store first, finalize later (safer)
    auto_finalize: bool = True           # Auto-finalize after store (if two_phase=True)
    auto_finalize_delay: int = 0         # Seconds to wait before auto-finalize

    # Claim construction
    include_job_description: bool = True  # Include job description in claim
    include_deliverable: bool = True      # Include deliverable content in claim
    max_claim_length: int = 4000          # Truncate claims longer than this

    # Error handling
    fail_open: bool = False              # If True, don't block job on verification failure
    max_retries: int = 2                 # API call retries
    retry_delay: float = 2.0            # Base retry delay


@dataclass
class VerificationEvent:
    """Result of a hook verification."""

    job_contract: str
    job_id: int
    success: bool
    api_result: Optional[ThoughtProofAPIResponse] = None
    tx_hash: Optional[str] = None
    error: Optional[str] = None
    two_phase: bool = False
    finalized: bool = False


class ThoughtProofVerificationHook:
    """
    Verification hook that auto-evaluates APEX job submissions.

    Designed to be triggered when an agent submits work on an ERC-8183 job.
    The hook:
      1. Fetches job details (description + deliverable)
      2. Constructs a verification claim
      3. Calls ThoughtProof API for multi-model verification
      4. Signs and submits the result on-chain
      5. Optionally finalizes (calls complete/reject on job contract)
    """

    def __init__(
        self,
        evaluator: ThoughtProofEvaluatorClient,
        config: HookConfig | None = None,
    ):
        self.evaluator = evaluator
        self.config = config or HookConfig()
        self._pending_finalizations: list[tuple[str, int]] = []

    def on_job_submitted(
        self,
        job_contract: str,
        job_id: int,
        description: str = "",
        deliverable: str = "",
        metadata: dict | None = None,
    ) -> VerificationEvent:
        """
        Called when an agent submits work on a job.

        Args:
            job_contract: ERC-8183 job contract address
            job_id: The job ID
            description: Job task description
            deliverable: The agent's submitted work/response
            metadata: Optional additional context

        Returns:
            VerificationEvent with result details
        """
        job_contract = Web3.to_checksum_address(job_contract)

        logger.info(f"[ThoughtProof Hook] Verifying job {job_id} on {job_contract}")

        # 1. Construct verification claim
        claim = self._build_claim(job_id, description, deliverable, metadata)

        # 2. Call ThoughtProof API with retry
        api_result = None
        last_error = None

        for attempt in range(self.config.max_retries + 1):
            try:
                api_result = call_thoughtproof_api(
                    claim=claim,
                    speed=self.config.speed,
                    domain=self.config.domain,
                    api_url=self.evaluator._api_url,
                )
                break
            except Exception as e:
                last_error = e
                if attempt < self.config.max_retries:
                    import time
                    delay = self.config.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"[ThoughtProof Hook] API call failed (attempt {attempt + 1}), "
                        f"retrying in {delay:.1f}s: {e}"
                    )
                    time.sleep(delay)

        if api_result is None:
            error_msg = f"ThoughtProof API failed after {self.config.max_retries + 1} attempts: {last_error}"
            logger.error(f"[ThoughtProof Hook] {error_msg}")

            if self.config.fail_open:
                logger.warning("[ThoughtProof Hook] fail_open=True, skipping verification")
                return VerificationEvent(
                    job_contract=job_contract,
                    job_id=job_id,
                    success=False,
                    error=error_msg,
                )
            else:
                return VerificationEvent(
                    job_contract=job_contract,
                    job_id=job_id,
                    success=False,
                    error=error_msg,
                )

        # 3. Submit on-chain
        try:
            result = self.evaluator.verify_and_submit(
                job_contract=job_contract,
                job_id=job_id,
                claim=claim,
                speed=self.config.speed,
                domain=self.config.domain,
                two_phase=self.config.two_phase,
            )

            event = VerificationEvent(
                job_contract=job_contract,
                job_id=job_id,
                success=True,
                api_result=api_result,
                tx_hash=result.get("tx_hash"),
                two_phase=self.config.two_phase,
                finalized=not self.config.two_phase,
            )

            # 4. Auto-finalize if configured
            if self.config.two_phase and self.config.auto_finalize:
                if self.config.auto_finalize_delay > 0:
                    # Queue for later finalization
                    self._pending_finalizations.append((job_contract, job_id))
                    logger.info(
                        f"[ThoughtProof Hook] Queued finalization for job {job_id} "
                        f"(delay={self.config.auto_finalize_delay}s)"
                    )
                else:
                    try:
                        fin_result = self.evaluator.finalize(job_contract, job_id)
                        event.finalized = True
                        logger.info(
                            f"[ThoughtProof Hook] Finalized job {job_id}: "
                            f"tx={fin_result.get('transactionHash', 'N/A')}"
                        )
                    except Exception as e:
                        logger.error(f"[ThoughtProof Hook] Finalization failed: {e}")

            return event

        except Exception as e:
            error_msg = f"On-chain submission failed: {e}"
            logger.error(f"[ThoughtProof Hook] {error_msg}")
            return VerificationEvent(
                job_contract=job_contract,
                job_id=job_id,
                success=False,
                api_result=api_result,
                error=error_msg,
            )

    def finalize_pending(self) -> list[VerificationEvent]:
        """Finalize all pending two-phase verifications."""
        results = []
        remaining = []

        for job_contract, job_id in self._pending_finalizations:
            try:
                self.evaluator.finalize(job_contract, job_id)
                results.append(VerificationEvent(
                    job_contract=job_contract,
                    job_id=job_id,
                    success=True,
                    finalized=True,
                ))
            except Exception as e:
                logger.error(f"[ThoughtProof Hook] Failed to finalize {job_id}: {e}")
                remaining.append((job_contract, job_id))
                results.append(VerificationEvent(
                    job_contract=job_contract,
                    job_id=job_id,
                    success=False,
                    error=str(e),
                ))

        self._pending_finalizations = remaining
        return results

    def _build_claim(
        self,
        job_id: int,
        description: str,
        deliverable: str,
        metadata: dict | None,
    ) -> str:
        """Construct a verification claim from job data."""
        parts = [f"ERC-8183 Job #{job_id} — Agent Deliverable Verification"]

        if description and self.config.include_job_description:
            parts.append(f"\nTask Description:\n{description}")

        if deliverable and self.config.include_deliverable:
            parts.append(f"\nAgent Deliverable:\n{deliverable}")

        if metadata:
            parts.append(f"\nContext: {metadata}")

        parts.append(
            "\nQuestion: Does the agent's deliverable adequately and correctly "
            "fulfill the task requirements? Is the reasoning sound?"
        )

        claim = "\n".join(parts)

        # Truncate if needed
        if len(claim) > self.config.max_claim_length:
            claim = claim[: self.config.max_claim_length - 50] + "\n\n[TRUNCATED]"

        return claim

    # ── FastAPI Route Integration ──

    def register_routes(self, app: Any) -> None:
        """
        Register ThoughtProof verification routes on a FastAPI app.

        Adds:
          POST /thoughtproof/verify     — Manually trigger verification
          GET  /thoughtproof/status     — Get verification status for a job
          POST /thoughtproof/finalize   — Finalize a pending verification
          GET  /thoughtproof/stats      — Get evaluator statistics
        """
        try:
            from fastapi import FastAPI
            from fastapi.responses import JSONResponse
        except ImportError:
            logger.warning("[ThoughtProof Hook] FastAPI not installed, skipping route registration")
            return

        @app.post("/thoughtproof/verify")
        async def verify_job(payload: dict) -> JSONResponse:
            job_contract = payload.get("job_contract", "")
            job_id = int(payload.get("job_id", 0))
            description = payload.get("description", "")
            deliverable = payload.get("deliverable", "")

            if not job_contract or not job_id:
                return JSONResponse(
                    {"error": "job_contract and job_id required"}, status_code=400,
                )

            event = self.on_job_submitted(
                job_contract=job_contract,
                job_id=job_id,
                description=description,
                deliverable=deliverable,
            )

            return JSONResponse({
                "success": event.success,
                "passed": event.api_result.passed if event.api_result else None,
                "confidence": event.api_result.confidence if event.api_result else None,
                "tx_hash": event.tx_hash,
                "finalized": event.finalized,
                "error": event.error,
            }, status_code=200 if event.success else 500)

        @app.get("/thoughtproof/status")
        async def verification_status(job_contract: str, job_id: int) -> JSONResponse:
            try:
                result = self.evaluator.get_verification(job_contract, job_id)
                return JSONResponse({
                    "verified": result.timestamp > 0,
                    "confidence": result.confidence,
                    "passed": result.passed,
                    "threshold": result.threshold,
                    "finalized": result.finalized,
                    "job_call_succeeded": result.job_call_succeeded,
                    "timestamp": result.timestamp,
                })
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)

        @app.post("/thoughtproof/finalize")
        async def finalize_job(payload: dict) -> JSONResponse:
            job_contract = payload.get("job_contract", "")
            job_id = int(payload.get("job_id", 0))

            try:
                result = self.evaluator.finalize(job_contract, job_id)
                return JSONResponse({
                    "success": True,
                    "tx_hash": result.get("transactionHash"),
                })
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)

        @app.get("/thoughtproof/stats")
        async def evaluator_stats() -> JSONResponse:
            try:
                stats = self.evaluator.get_stats()
                stats["default_threshold"] = self.evaluator.get_default_threshold()
                stats["min_verifiers"] = self.evaluator.get_min_verifiers()
                stats["reputation_enabled"] = self.evaluator.reputation_enabled()
                return JSONResponse(stats)
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)

        logger.info("[ThoughtProof Hook] Registered routes: /thoughtproof/{verify,status,finalize,stats}")
