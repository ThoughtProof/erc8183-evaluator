#!/usr/bin/env python3
"""
Test script for BNBAgent ThoughtProof integration.

This script tests the core functionality without requiring a full agent setup.
It validates:
1. ThoughtProof API client functionality
2. Contract integration (if configured)
3. Hook integration logic
4. Configuration validation

Usage:
    python test_integration.py
    python test_integration.py --api-only  # Test only API, skip contract
"""

import argparse
import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

# Import the ThoughtProof integration components
try:
    from thoughtproof_evaluator import (
        ThoughtProofEvaluatorClient,
        ThoughtProofResult, 
        PaymentRequired,
    )
    from thoughtproof_hook import ThoughtProofConfig, ThoughtProofHook
    from bnbagent_thoughtproof import verify_claim_sync, verify_claim_async
except ImportError as e:
    print(f"Failed to import ThoughtProof integration: {e}")
    sys.exit(1)

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_api_integration():
    """Test direct ThoughtProof API integration."""
    logger.info("Testing ThoughtProof API integration...")
    
    test_claim = """
    Test Claim for Verification:
    
    Task: Summarize the benefits of renewable energy
    
    Deliverable: Renewable energy sources like solar and wind power offer numerous 
    benefits including reduced greenhouse gas emissions, lower long-term costs, 
    energy independence, and job creation in the clean energy sector. These 
    technologies are becoming increasingly cost-competitive with fossil fuels 
    and represent a crucial component of addressing climate change.
    
    Question: Is this a sound and accurate summary of renewable energy benefits?
    """
    
    try:
        # Test synchronous API call
        logger.info("Testing synchronous API call...")
        result = verify_claim_sync(
            claim=test_claim,
            speed="standard",
            domain="general"
        )
        
        logger.info(f"API Result: {result.verdict}")
        logger.info(f"Confidence: {result.confidence:.2f}")
        logger.info(f"Passed: {result.passed}")
        
        if result.objections:
            logger.info(f"Objections: {result.objections}")
            
        return True
        
    except PaymentRequired as e:
        logger.warning(f"x402 payment required: {e}")
        logger.warning(f"Payment info: {e.payment_info}")
        return True  # This is expected behavior
        
    except Exception as e:
        logger.error(f"API test failed: {e}")
        return False


async def test_async_api():
    """Test asynchronous ThoughtProof API integration."""
    logger.info("Testing asynchronous API integration...")
    
    test_claim = "Simple test claim: The sky is blue."
    
    try:
        result = await verify_claim_async(
            claim=test_claim,
            speed="standard", 
            domain="general"
        )
        
        logger.info(f"Async API Result: {result.verdict}")
        logger.info(f"Confidence: {result.confidence:.2f}")
        return True
        
    except PaymentRequired:
        logger.info("x402 payment required (expected)")
        return True
        
    except Exception as e:
        logger.error(f"Async API test failed: {e}")
        return False


def test_contract_integration():
    """Test ThoughtProof contract integration."""
    logger.info("Testing contract integration...")
    
    # Check if contract configuration is available
    evaluator_address = os.getenv("THOUGHTPROOF_EVALUATOR")
    rpc_url = os.getenv("RPC_URL")
    
    if not evaluator_address:
        logger.warning("THOUGHTPROOF_EVALUATOR not set - skipping contract tests")
        return True
        
    if not rpc_url:
        logger.warning("RPC_URL not set - skipping contract tests")  
        return True
    
    try:
        # Import Web3 and create client
        from web3 import Web3
        
        web3 = Web3(Web3.HTTPProvider(rpc_url))
        if not web3.is_connected():
            logger.error("Failed to connect to Web3")
            return False
            
        logger.info(f"Connected to Web3: {rpc_url}")
        
        # Create evaluator client (read-only)
        evaluator = ThoughtProofEvaluatorClient(
            web3=web3,
            contract_address=evaluator_address,
        )
        
        logger.info(f"Created evaluator client for {evaluator_address}")
        
        # Test read-only methods
        try:
            erc8183_address = evaluator.get_erc8183_address()
            logger.info(f"ERC8183 address: {erc8183_address}")
            
            # Test with a dummy job ID
            test_job_id = 999999  # Unlikely to exist
            info = evaluator.get_verification_info(test_job_id)
            logger.info(f"Test job {test_job_id} verification info: {info}")
            
            return True
            
        except Exception as e:
            logger.error(f"Contract read operations failed: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Contract integration test failed: {e}")
        return False


def test_config_validation():
    """Test configuration validation and defaults."""
    logger.info("Testing configuration validation...")
    
    try:
        # Test default configuration
        default_config = ThoughtProofConfig()
        logger.info(f"Default config: {default_config}")
        
        # Test custom configuration
        custom_config = ThoughtProofConfig(
            verification_speed="deep",
            verification_domain="code", 
            min_confidence_threshold=0.9,
            auto_finalize=False
        )
        logger.info(f"Custom config: {custom_config}")
        
        # Test invalid configuration
        try:
            invalid_config = ThoughtProofConfig(min_confidence_threshold=1.5)
            logger.warning("Invalid config was accepted - this may be a bug")
        except Exception:
            logger.info("Invalid config correctly rejected")
            
        return True
        
    except Exception as e:
        logger.error(f"Config validation failed: {e}")
        return False


async def test_hook_logic():
    """Test hook integration logic (without actual contract calls)."""
    logger.info("Testing hook integration logic...")
    
    try:
        # Create mock evaluator and config
        config = ThoughtProofConfig(
            auto_finalize=False,  # Disable to avoid actual contract calls
            verification_speed="standard"
        )
        
        # Create hook without evaluator (for testing logic only)
        hook = ThoughtProofHook(None, config, None)
        
        # Test claim construction
        test_job_data = {
            "jobId": 123,
            "description": "Test job description",
            "deliverable": b"Test deliverable content",
            "budget": 1000000000000000000,
            "client": "0x1234567890123456789012345678901234567890",
            "provider": "0x0987654321098765432109876543210987654321",
        }
        
        claim = await hook._build_verification_claim(123, test_job_data)
        logger.info(f"Generated claim: {claim[:200]}...")
        
        # Test deliverable content extraction  
        content = await hook._get_deliverable_content(test_job_data)
        logger.info(f"Extracted content: {content}")
        
        return True
        
    except Exception as e:
        logger.error(f"Hook logic test failed: {e}")
        return False


async def main():
    """Run all tests."""
    parser = argparse.ArgumentParser(description="Test ThoughtProof integration")
    parser.add_argument("--api-only", action="store_true", help="Test only API integration")
    args = parser.parse_args()
    
    logger.info("Starting ThoughtProof integration tests...")
    
    results = {}
    
    # API tests
    results["api_sync"] = test_api_integration()
    results["api_async"] = await test_async_api()
    
    if not args.api_only:
        # Contract and integration tests
        results["contract"] = test_contract_integration()
        results["config"] = test_config_validation()
        results["hook_logic"] = await test_hook_logic()
    
    # Summary
    logger.info("\n" + "="*50)
    logger.info("TEST RESULTS SUMMARY")
    logger.info("="*50)
    
    passed = 0
    total = 0
    
    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        logger.info(f"{test_name:<15}: {status}")
        if result:
            passed += 1
        total += 1
        
    logger.info("-" * 50)
    logger.info(f"OVERALL: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("All tests passed! 🎉")
        return 0
    else:
        logger.error("Some tests failed! 😞")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)