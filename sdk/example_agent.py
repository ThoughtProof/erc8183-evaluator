"""
Example: BNBAgent with ThoughtProof verification.

Demonstrates the full lifecycle:
  1. Agent registers on ERC-8004
  2. Client creates a job with ThoughtProof as evaluator
  3. Agent accepts and submits work
  4. ThoughtProof verifies the reasoning
  5. Job completes or rejects based on verification

Usage:
    # Set environment variables (see .env.example)
    export BSC_RPC_URL="https://bsc-testnet.bnbchain.org"
    export PRIVATE_KEY="0x..."
    export THOUGHTPROOF_EVALUATOR="0x..."

    python -m sdk.example_agent
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time

from web3 import Web3

from .thoughtproof_evaluator import (
    ThoughtProofEvaluatorClient,
    FailureCost,
    call_thoughtproof_api,
)
from .thoughtproof_hook import ThoughtProofVerificationHook, HookConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    """Run the example agent."""

    # ── Configuration ──
    rpc_url = os.environ.get("BSC_RPC_URL", "https://bsc-testnet.bnbchain.org")
    private_key = os.environ.get("PRIVATE_KEY")
    evaluator_address = os.environ.get("THOUGHTPROOF_EVALUATOR")
    verifier_key = os.environ.get("VERIFIER_SIGNER_KEY", private_key)

    if not private_key or not evaluator_address:
        print("Required environment variables:")
        print("  PRIVATE_KEY          — Wallet private key")
        print("  THOUGHTPROOF_EVALUATOR — ThoughtProofEvaluator contract address")
        print("")
        print("Optional:")
        print("  BSC_RPC_URL          — RPC endpoint (default: BSC testnet)")
        print("  VERIFIER_SIGNER_KEY  — Separate key for signing verifications")
        sys.exit(1)

    # ── Setup ──
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print(f"Failed to connect to {rpc_url}")
        sys.exit(1)

    chain_id = w3.eth.chain_id
    account = w3.eth.account.from_key(private_key)
    logger.info(f"Connected to chain {chain_id}, account {account.address}")

    # ── Initialize evaluator client ──
    evaluator = ThoughtProofEvaluatorClient(
        web3=w3,
        contract_address=evaluator_address,
        private_key=private_key,
        verifier_signer_key=verifier_key,
    )

    # ── Check evaluator status ──
    logger.info("Checking evaluator contract...")
    try:
        stats = evaluator.get_stats()
        threshold = evaluator.get_default_threshold()
        min_v = evaluator.get_min_verifiers()
        logger.info(
            f"Evaluator OK: threshold={threshold}, minVerifiers={min_v}, "
            f"totalVerifications={stats['total_verifications']}"
        )
    except Exception as e:
        logger.error(f"Cannot read evaluator contract: {e}")
        sys.exit(1)

    # ── Demo: Verify a claim ──
    logger.info("\n=== Demo: Off-chain verification only ===")
    demo_claim = (
        "The agent recommends buying ETH at $3,200 because the 200-day moving "
        "average has crossed above the 50-day MA, indicating a bullish trend reversal. "
        "Historical data shows this pattern has a 73% success rate over the past 5 years."
    )

    try:
        api_result = call_thoughtproof_api(
            claim=demo_claim,
            speed="fast",
            domain="financial",
        )
        logger.info(
            f"API Result: status={api_result.status} confidence={api_result.confidence:.3f} "
            f"mdi={api_result.mdi:.3f} verifiers={api_result.verifier_count}"
        )
        if api_result.objections:
            logger.info(f"Objections: {api_result.objections}")
    except Exception as e:
        logger.warning(f"API call failed (expected in demo): {e}")

    # ── Demo: Full on-chain flow ──
    logger.info("\n=== Demo: Full on-chain verification ===")

    # This would normally come from the APEX job lifecycle
    demo_job_contract = "0x3464e64dD53bC093c53050cE5114062765e9F1b6"  # BSC testnet ERC-8183
    demo_job_id = 1

    try:
        result = evaluator.verify_and_submit(
            job_contract=demo_job_contract,
            job_id=demo_job_id,
            claim=demo_claim,
            speed="fast",
            domain="financial",
            two_phase=True,
        )
        logger.info(f"Store TX: {result['tx_hash']}")
        logger.info(f"Confidence: {result['confidence']:.3f}, Passed: {result['passed']}")

        # Finalize
        fin = evaluator.finalize(demo_job_contract, demo_job_id)
        logger.info(f"Finalize TX: {fin.get('transactionHash')}")

    except Exception as e:
        logger.warning(f"On-chain flow failed (expected in demo without funded job): {e}")

    # ── Demo: Hook integration ──
    logger.info("\n=== Demo: Hook-based automatic verification ===")

    hook = ThoughtProofVerificationHook(
        evaluator=evaluator,
        config=HookConfig(
            speed="standard",
            domain="general",
            two_phase=True,
            auto_finalize=True,
        ),
    )

    event = hook.on_job_submitted(
        job_contract=demo_job_contract,
        job_id=2,
        description="Analyze the current BTC/USDT market and provide a trading recommendation",
        deliverable="Based on my analysis, I recommend a long position at $67,500...",
    )
    logger.info(
        f"Hook result: success={event.success} finalized={event.finalized} "
        f"error={event.error}"
    )

    logger.info("\nDone! See README.md for full integration guide.")


if __name__ == "__main__":
    main()
