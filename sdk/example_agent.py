#!/usr/bin/env python3
"""
Example BNBAgent with ThoughtProof Verification Integration.

This example demonstrates how to:
1. Set up a BNBAgent with ThoughtProof evaluator
2. Configure automatic verification on job submission
3. Handle jobs with ThoughtProof reasoning verification
4. Monitor and manage the verification process

Usage:
    python example_agent.py

Environment variables required:
    WALLET_PASSWORD         - Password for wallet encryption
    PRIVATE_KEY            - Agent wallet private key (optional)
    RPC_URL                - Blockchain RPC endpoint (optional)
    ERC8183_ADDRESS        - ERC-8183 contract address (optional)
    THOUGHTPROOF_EVALUATOR - ThoughtProof evaluator contract address

Optional environment variables:
    THOUGHTPROOF_SPEED     - standard (default) or deep
    THOUGHTPROOF_DOMAIN    - general (default), financial, medical, legal, code
    MIN_CONFIDENCE         - Minimum confidence for auto-completion (default: 0.7)
    AUTO_FINALIZE         - Whether to auto-finalize jobs (default: true)
    AUTO_FINALIZE_DELAY   - Seconds to wait before auto-finalize (default: 30)
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from web3 import Web3

# Import BNBAgent SDK components
try:
    from bnbagent import BNBAgent
    from bnbagent.apex.config import APEXConfig
    from bnbagent.apex.server import create_apex_app
    from bnbagent.storage import IPFSProvider, LocalStorageProvider
except ImportError as e:
    print(f"Failed to import BNBAgent SDK: {e}")
    print("Please install the BNBAgent SDK or ensure it's in your Python path")
    sys.exit(1)

# Import our ThoughtProof integration
from thoughtproof_evaluator import ThoughtProofEvaluatorClient
from thoughtproof_hook import ThoughtProofHook, ThoughtProofConfig, register_thoughtproof_hook

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ThoughtProofAgent:
    """
    Example agent that uses ThoughtProof for automatic verification.
    
    This agent:
    1. Processes APEX jobs normally
    2. Automatically triggers ThoughtProof verification on submission
    3. Provides endpoints for manual verification control
    4. Monitors verification status and handles edge cases
    """
    
    def __init__(self):
        self.config = self._load_config()
        self.agent = self._create_agent()
        self.evaluator = self._create_evaluator()
        self.hook = self._setup_thoughtproof_hook()
        self.app = None
        self._shutdown_event = asyncio.Event()
        
    def _load_config(self) -> APEXConfig:
        """Load configuration from environment variables."""
        logger.info("Loading agent configuration...")
        
        # Validate required environment variables
        required_vars = ["WALLET_PASSWORD"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {missing_vars}")
            
        # Load APEX configuration from environment
        config = APEXConfig.from_env()
        
        logger.info(f"Configuration loaded: {config}")
        return config
        
    def _create_agent(self) -> BNBAgent:
        """Create and configure the BNBAgent instance."""
        logger.info("Creating BNBAgent...")
        
        # Use storage provider from config or fallback to local
        storage = self.config.storage or LocalStorageProvider()
        
        # Create the agent
        agent = BNBAgent(
            apex_config=self.config,
            storage_provider=storage,
        )
        
        logger.info(f"Agent created with address: {agent.wallet_address}")
        return agent
        
    def _create_evaluator(self) -> ThoughtProofEvaluatorClient:
        """Create ThoughtProof evaluator client."""
        evaluator_address = os.getenv("THOUGHTPROOF_EVALUATOR")
        if not evaluator_address:
            raise ValueError("THOUGHTPROOF_EVALUATOR environment variable is required")
            
        logger.info(f"Creating ThoughtProof evaluator client for {evaluator_address}")
        
        # Create Web3 instance
        from bnbagent.core.abi_loader import create_web3
        web3 = create_web3(self.config.effective_rpc_url)
        
        # Create evaluator client
        evaluator = ThoughtProofEvaluatorClient(
            web3=web3,
            contract_address=evaluator_address,
            wallet_provider=self.config.wallet_provider,
            api_timeout=float(os.getenv("THOUGHTPROOF_TIMEOUT", "120")),
        )
        
        logger.info("ThoughtProof evaluator client created")
        return evaluator
        
    def _setup_thoughtproof_hook(self) -> ThoughtProofHook:
        """Set up the ThoughtProof hook for automatic verification."""
        logger.info("Setting up ThoughtProof hook...")
        
        # Create configuration from environment
        config = ThoughtProofConfig(
            verification_speed=os.getenv("THOUGHTPROOF_SPEED", "standard"),
            verification_domain=os.getenv("THOUGHTPROOF_DOMAIN", "general"),
            auto_finalize=os.getenv("AUTO_FINALIZE", "true").lower() == "true",
            min_confidence_threshold=float(os.getenv("MIN_CONFIDENCE", "0.7")),
            auto_finalize_delay=float(os.getenv("AUTO_FINALIZE_DELAY", "30")),
            include_job_context=os.getenv("INCLUDE_JOB_CONTEXT", "true").lower() == "true",
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            fallback_on_api_error=os.getenv("FALLBACK_ON_API_ERROR", "false").lower() == "true",
        )
        
        # Register the hook
        hook = register_thoughtproof_hook(
            job_ops=self.agent.apex.job_ops,
            evaluator_client=self.evaluator,
            config=config,
            storage_provider=self.agent.storage,
        )
        
        logger.info(f"ThoughtProof hook configured: {config}")
        return hook

    async def process_job(self, job: Dict[str, Any]) -> str:
        """
        Process a single APEX job.
        
        This is the main job processing function that gets called for each
        funded job. The ThoughtProof verification happens automatically
        via the hook when the result is submitted.
        """
        job_id = job["jobId"]
        description = job.get("description", "No description provided")
        
        logger.info(f"Processing job {job_id}: {description[:100]}...")
        
        try:
            # Simulate job processing (replace with your actual logic)
            response = await self._execute_job_logic(job)
            
            logger.info(f"Job {job_id} completed successfully")
            return response
            
        except Exception as e:
            logger.error(f"Job {job_id} processing failed: {e}")
            raise

    async def _execute_job_logic(self, job: Dict[str, Any]) -> str:
        """
        Execute the actual job logic.
        
        Replace this with your agent's specific functionality.
        """
        job_id = job["jobId"]
        description = job.get("description", "")
        
        # Example: Simple text processing
        if "summarize" in description.lower():
            return f"Summary of job {job_id}: {description[:200]}..."
        elif "analyze" in description.lower():
            return f"Analysis of job {job_id}: This task requires detailed analysis of the provided content."
        elif "translate" in description.lower():
            return f"Translation for job {job_id}: (Translation would be performed here)"
        else:
            return f"Completed job {job_id}: {description}"

    async def start_server(self):
        """Start the agent HTTP server with ThoughtProof endpoints."""
        logger.info("Starting agent server...")
        
        # Create FastAPI app with APEX endpoints
        self.app = create_apex_app(
            config=self.config,
            on_job=self.process_job,
            on_submit=self._on_job_submitted,
            job_timeout=float(os.getenv("JOB_TIMEOUT", "300")),
        )
        
        # Add custom ThoughtProof endpoints
        self._add_thoughtproof_endpoints()
        
        # Start the server
        import uvicorn
        config = uvicorn.Config(
            app=self.app,
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            log_level="info",
        )
        
        server = uvicorn.Server(config)
        
        # Set up graceful shutdown
        self._setup_signal_handlers()
        
        # Start server
        logger.info(f"Server starting on {config.host}:{config.port}")
        await server.serve()

    def _add_thoughtproof_endpoints(self):
        """Add custom endpoints for ThoughtProof management."""
        
        @self.app.get("/thoughtproof/status")
        async def thoughtproof_status():
            """Get ThoughtProof integration status."""
            return {
                "thoughtproof_enabled": True,
                "evaluator_address": self.evaluator.address,
                "config": {
                    "speed": self.hook.config.verification_speed,
                    "domain": self.hook.config.verification_domain,
                    "auto_finalize": self.hook.config.auto_finalize,
                    "min_confidence": self.hook.config.min_confidence_threshold,
                    "auto_finalize_delay": self.hook.config.auto_finalize_delay,
                },
                "pending_finalizations": len(self.hook._pending_finalizations),
            }

        @self.app.get("/thoughtproof/job/{job_id}")
        async def get_thoughtproof_info(job_id: int):
            """Get ThoughtProof verification info for a job."""
            try:
                info = await asyncio.to_thread(self.evaluator.get_verification_info, job_id)
                return {
                    "job_id": job_id,
                    "verification_info": {
                        "stored": info.stored,
                        "finalized": info.finalized,
                        "passed": info.passed,
                        "confidence": info.confidence,
                        "timestamp": info.timestamp,
                    },
                    "settleable": await asyncio.to_thread(self.evaluator.is_settleable, job_id),
                }
            except Exception as e:
                return {"error": str(e)}, 500

        @self.app.post("/thoughtproof/job/{job_id}/finalize")
        async def manual_finalize(job_id: int):
            """Manually finalize a job's ThoughtProof verification."""
            try:
                result = await self.hook.manual_finalize(job_id)
                return {
                    "job_id": job_id,
                    "finalized": True,
                    "transaction_hash": result.get("transactionHash"),
                }
            except Exception as e:
                return {"error": str(e)}, 500

        @self.app.delete("/thoughtproof/job/{job_id}/auto-finalize")
        async def cancel_auto_finalize(job_id: int):
            """Cancel pending auto-finalization for a job."""
            cancelled = self.hook.cancel_pending_finalization(job_id)
            return {
                "job_id": job_id,
                "auto_finalize_cancelled": cancelled,
            }

    async def _on_job_submitted(self, job_id: int, response_content: str, metadata: Dict[str, Any]):
        """
        Callback triggered after successful job submission.
        
        The ThoughtProof verification is triggered automatically via the hook,
        but this callback can be used for additional logging or processing.
        """
        logger.info(f"Job {job_id} submitted successfully")
        logger.info(f"ThoughtProof verification will be triggered automatically")

    def _setup_signal_handlers(self):
        """Set up graceful shutdown signal handlers."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self._shutdown_event.set()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    async def cleanup(self):
        """Perform cleanup on shutdown."""
        logger.info("Performing cleanup...")
        
        # Cancel any pending finalization tasks
        if self.hook:
            for job_id in list(self.hook._pending_finalizations.keys()):
                self.hook.cancel_pending_finalization(job_id)
                
        logger.info("Cleanup completed")


async def main():
    """Main application entry point."""
    logger.info("Starting ThoughtProof Agent...")
    
    try:
        # Create agent
        agent = ThoughtProofAgent()
        
        # Start server
        await agent.start_server()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if 'agent' in locals():
            await agent.cleanup()
        logger.info("ThoughtProof Agent stopped")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())