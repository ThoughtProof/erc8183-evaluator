"""
ThoughtProof Hook Integration for BNBAgent SDK.

This module provides automatic ThoughtProof verification integration that triggers
when jobs are submitted via the APEX afterAction hook mechanism.

The hook monitors job submissions and automatically:
1. Extracts the deliverable content from IPFS/storage
2. Constructs a verification claim 
3. Calls ThoughtProof API for verification
4. Stores the result on-chain via ThoughtProofEvaluator contract
5. Optionally finalizes the job automatically

This enables seamless integration of ThoughtProof verification into the
APEX job lifecycle without requiring manual intervention.
"""

from __future__ import annotations

import asyncio
import logging
import json
from typing import Any, Dict, Optional
from dataclasses import dataclass

from .thoughtproof_evaluator import ThoughtProofEvaluatorClient, PaymentRequired

logger = logging.getLogger(__name__)


@dataclass  
class ThoughtProofConfig:
    """Configuration for ThoughtProof hook integration."""
    
    # ThoughtProof API settings
    verification_speed: str = "standard"  # standard, deep
    verification_domain: str = "general"  # general, financial, medical, legal, code
    api_timeout: float = 120.0
    
    # Automatic finalization settings
    auto_finalize: bool = True
    min_confidence_threshold: float = 0.7
    auto_finalize_delay: float = 30.0  # seconds to wait before auto-finalize
    
    # Claim construction settings
    include_job_context: bool = True
    include_negotiation_history: bool = False
    custom_claim_template: Optional[str] = None
    
    # Error handling
    max_retries: int = 3
    retry_delay: float = 5.0
    fallback_on_api_error: bool = False  # If True, allows job through on API errors


class ThoughtProofHook:
    """
    Hook integration for automatic ThoughtProof verification on job submission.
    
    This class integrates with the APEX job lifecycle to provide automatic
    verification of submitted deliverables using the ThoughtProof API.
    
    Usage:
        hook = ThoughtProofHook(evaluator_client, config)
        
        # Register with APEX job operations
        job_ops.add_submission_hook(hook.on_job_submitted)
        
    Or use the convenience function:
        register_thoughtproof_hook(job_ops, evaluator_client, config)
    """
    
    def __init__(
        self, 
        evaluator_client: ThoughtProofEvaluatorClient,
        config: ThoughtProofConfig,
        storage_provider=None
    ):
        self.evaluator = evaluator_client
        self.config = config
        self.storage = storage_provider
        self._pending_finalizations: dict[int, asyncio.Task] = {}
        
    async def on_job_submitted(self, job_id: int, job_data: dict) -> Dict[str, Any]:
        """
        Hook callback triggered when a job is submitted.
        
        This method:
        1. Extracts deliverable content from the job
        2. Constructs a verification claim
        3. Calls ThoughtProof API and stores result
        4. Schedules automatic finalization if configured
        
        Args:
            job_id: The APEX job ID that was submitted
            job_data: Job details from the APEX contract
            
        Returns:
            Dict with verification results and status
        """
        logger.info(f"ThoughtProof hook triggered for job {job_id}")
        
        try:
            # Extract deliverable content
            claim = await self._build_verification_claim(job_id, job_data)
            
            # Perform verification and store result
            verification_result = await self._verify_and_store(job_id, claim)
            
            # Schedule automatic finalization if configured
            if self.config.auto_finalize:
                await self._schedule_auto_finalization(job_id, verification_result)
                
            return {
                "success": True,
                "job_id": job_id,
                "verification_stored": True,
                "auto_finalize_scheduled": self.config.auto_finalize,
                "thoughtproof_result": verification_result.get("thoughtproof_result"),
                "transaction_hash": verification_result.get("transactionHash"),
            }
            
        except PaymentRequired as e:
            logger.error(f"ThoughtProof payment required for job {job_id}: {e}")
            return await self._handle_payment_required(job_id, e)
            
        except Exception as e:
            logger.error(f"ThoughtProof verification failed for job {job_id}: {e}")
            return await self._handle_verification_error(job_id, e)

    async def _build_verification_claim(self, job_id: int, job_data: dict) -> str:
        """
        Build the claim text for ThoughtProof verification.
        
        Args:
            job_id: The job ID
            job_data: Job details from contract
            
        Returns:
            Formatted claim string for verification
        """
        if self.config.custom_claim_template:
            # Use custom template
            return self.config.custom_claim_template.format(
                job_id=job_id,
                job=job_data,
                description=job_data.get("description", ""),
                deliverable=await self._get_deliverable_content(job_data),
                **job_data
            )
        
        # Get deliverable content
        deliverable_content = await self._get_deliverable_content(job_data)
        
        # Build standard claim format
        claim_parts = [
            f"Job #{job_id} deliverable evaluation:",
            f"Task: {job_data.get('description', 'Unknown task')}",
            f"Deliverable: {deliverable_content}",
            "Question: Is this deliverable a sound, complete, and appropriate response to the task?"
        ]
        
        # Add job context if configured
        if self.config.include_job_context:
            claim_parts.extend([
                f"Budget: {job_data.get('budget', 'Unknown')}",
                f"Client: {job_data.get('client', 'Unknown')}",
                f"Provider: {job_data.get('provider', 'Unknown')}",
            ])
            
        return "\n".join(claim_parts)

    async def _get_deliverable_content(self, job_data: dict) -> str:
        """
        Extract the actual deliverable content from storage.
        
        Args:
            job_data: Job details including deliverable hash
            
        Returns:
            String content of the deliverable
        """
        deliverable_hash = job_data.get("deliverable", b"")
        
        if not deliverable_hash or deliverable_hash == b"\x00" * 32:
            return "No deliverable provided"
            
        # Try to get content from storage if storage provider available
        if self.storage:
            try:
                # Convert hash to storage key/URL
                if isinstance(deliverable_hash, bytes):
                    storage_key = deliverable_hash.hex()
                else:
                    storage_key = str(deliverable_hash)
                    
                content = await self.storage.download(storage_key)
                
                # If content is JSON, extract the response field
                try:
                    if isinstance(content, str):
                        data = json.loads(content)
                        if isinstance(data, dict) and "response" in data:
                            return data["response"]
                        elif isinstance(data, dict) and "deliverable" in data:
                            return data["deliverable"]
                        else:
                            return content
                    return str(content)
                except json.JSONDecodeError:
                    return content
                    
            except Exception as e:
                logger.warning(f"Failed to fetch deliverable content from storage: {e}")
                
        # Fallback: use hash as identifier
        if isinstance(deliverable_hash, bytes):
            return f"Deliverable hash: 0x{deliverable_hash.hex()}"
        else:
            return f"Deliverable: {deliverable_hash}"

    async def _verify_and_store(self, job_id: int, claim: str) -> dict[str, Any]:
        """
        Call ThoughtProof API and store verification result.
        
        Args:
            job_id: The job ID
            claim: The claim to verify
            
        Returns:
            Transaction result from storing verification
        """
        for attempt in range(self.config.max_retries):
            try:
                # Call evaluator to verify and store
                result = await asyncio.to_thread(
                    self.evaluator.store_verification,
                    job_id,
                    claim,
                    self.config.verification_speed,
                    self.config.verification_domain
                )
                
                logger.info(f"ThoughtProof verification stored for job {job_id}")
                return result
                
            except PaymentRequired:
                # Don't retry payment errors
                raise
                
            except Exception as e:
                logger.warning(f"Verification attempt {attempt + 1} failed for job {job_id}: {e}")
                
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay)
                else:
                    raise

    async def _schedule_auto_finalization(self, job_id: int, verification_result: dict) -> None:
        """
        Schedule automatic finalization of the job after delay.
        
        Args:
            job_id: The job ID
            verification_result: Result from verification storage
        """
        # Cancel any existing finalization task for this job
        if job_id in self._pending_finalizations:
            self._pending_finalizations[job_id].cancel()
            
        # Create finalization task
        task = asyncio.create_task(self._auto_finalize_job(job_id, verification_result))
        self._pending_finalizations[job_id] = task
        
        logger.info(f"Scheduled auto-finalization for job {job_id} in {self.config.auto_finalize_delay}s")

    async def _auto_finalize_job(self, job_id: int, verification_result: dict) -> None:
        """
        Automatically finalize a job after the configured delay.
        
        Args:
            job_id: The job ID  
            verification_result: Result from verification storage
        """
        try:
            # Wait for the configured delay
            await asyncio.sleep(self.config.auto_finalize_delay)
            
            # Check if job should be finalized based on confidence threshold
            thoughtproof_result = verification_result.get("thoughtproof_result", {})
            confidence = thoughtproof_result.get("confidence", 0.0)
            passed = thoughtproof_result.get("passed", False)
            
            if passed and confidence >= self.config.min_confidence_threshold:
                # Finalize the job
                finalize_result = await asyncio.to_thread(self.evaluator.finalize, job_id)
                logger.info(f"Auto-finalized job {job_id}: {finalize_result.get('transactionHash')}")
            else:
                logger.warning(
                    f"Job {job_id} not auto-finalized: passed={passed}, "
                    f"confidence={confidence:.2f}, threshold={self.config.min_confidence_threshold}"
                )
                
        except Exception as e:
            logger.error(f"Auto-finalization failed for job {job_id}: {e}")
        finally:
            # Clean up the task
            self._pending_finalizations.pop(job_id, None)

    async def _handle_payment_required(self, job_id: int, payment_error: PaymentRequired) -> dict[str, Any]:
        """
        Handle x402 payment required error.
        
        Args:
            job_id: The job ID
            payment_error: The payment required exception
            
        Returns:
            Error response dict
        """
        payment_info = payment_error.payment_info
        
        return {
            "success": False,
            "job_id": job_id,
            "error": "payment_required",
            "error_message": str(payment_error),
            "payment_info": payment_info,
            "requires_manual_intervention": True,
        }

    async def _handle_verification_error(self, job_id: int, error: Exception) -> dict[str, Any]:
        """
        Handle verification API errors.
        
        Args:
            job_id: The job ID
            error: The error that occurred
            
        Returns:
            Error response dict
        """
        if self.config.fallback_on_api_error:
            logger.warning(f"Allowing job {job_id} through due to API error (fallback enabled): {error}")
            return {
                "success": True,
                "job_id": job_id,
                "verification_stored": False,
                "fallback_used": True,
                "error_message": str(error),
                "requires_manual_intervention": True,
            }
        else:
            return {
                "success": False,
                "job_id": job_id,
                "error": "verification_failed",
                "error_message": str(error),
                "requires_manual_intervention": True,
            }

    def cancel_pending_finalization(self, job_id: int) -> bool:
        """
        Cancel pending auto-finalization for a job.
        
        Args:
            job_id: The job ID
            
        Returns:
            True if cancellation was successful, False if no pending finalization
        """
        if job_id in self._pending_finalizations:
            self._pending_finalizations[job_id].cancel()
            del self._pending_finalizations[job_id]
            logger.info(f"Cancelled pending finalization for job {job_id}")
            return True
        return False

    async def manual_finalize(self, job_id: int) -> dict[str, Any]:
        """
        Manually finalize a job (bypasses auto-finalization logic).
        
        Args:
            job_id: The job ID
            
        Returns:
            Finalization result
        """
        # Cancel any pending auto-finalization
        self.cancel_pending_finalization(job_id)
        
        # Finalize immediately
        result = await asyncio.to_thread(self.evaluator.finalize, job_id)
        logger.info(f"Manually finalized job {job_id}: {result.get('transactionHash')}")
        return result


def register_thoughtproof_hook(
    job_ops,
    evaluator_client: ThoughtProofEvaluatorClient,
    config: Optional[ThoughtProofConfig] = None,
    storage_provider=None
) -> ThoughtProofHook:
    """
    Convenience function to register ThoughtProof hook with APEX job operations.
    
    Args:
        job_ops: APEXJobOps instance
        evaluator_client: ThoughtProofEvaluatorClient instance
        config: Optional configuration (uses defaults if not provided)
        storage_provider: Optional storage provider for deliverable content
        
    Returns:
        ThoughtProofHook instance
    """
    if config is None:
        config = ThoughtProofConfig()
        
    hook = ThoughtProofHook(evaluator_client, config, storage_provider)
    
    # Register the hook with job operations
    # Note: This assumes APEXJobOps has a method to register submission hooks
    # The actual integration point may vary depending on the SDK implementation
    if hasattr(job_ops, 'add_submission_hook'):
        job_ops.add_submission_hook(hook.on_job_submitted)
    else:
        logger.warning("APEXJobOps does not support submission hooks - manual integration required")
    
    logger.info("ThoughtProof hook registered with APEX job operations")
    return hook