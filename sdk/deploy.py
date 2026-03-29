#!/usr/bin/env python3
"""
Deployment script for ThoughtProof integration.

This script helps deploy and configure the ThoughtProof integration:
1. Validates environment configuration
2. Tests connectivity to contracts and APIs
3. Sets up wallet if needed
4. Provides deployment checklist

Usage:
    python deploy.py --check-config
    python deploy.py --test-connectivity  
    python deploy.py --deploy
"""

import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()


def check_config():
    """Check configuration completeness and validity."""
    print("🔍 Checking configuration...")
    
    required_vars = {
        "WALLET_PASSWORD": "Password for wallet encryption",
        "THOUGHTPROOF_EVALUATOR": "ThoughtProof evaluator contract address",
    }
    
    optional_vars = {
        "PRIVATE_KEY": "Agent wallet private key (auto-generated if not provided)",
        "RPC_URL": "Blockchain RPC endpoint (uses network default if not set)",
        "ERC8183_ADDRESS": "ERC-8183 contract address (uses network default if not set)",
        "NETWORK": "Network name (default: bsc-testnet)",
        "THOUGHTPROOF_SPEED": "API verification speed (default: standard)",
        "THOUGHTPROOF_DOMAIN": "API domain context (default: general)",
    }
    
    print("\n📋 Required Configuration:")
    missing_required = []
    for var, desc in required_vars.items():
        value = os.getenv(var)
        if value:
            print(f"  ✅ {var}: {desc}")
        else:
            print(f"  ❌ {var}: {desc} - MISSING")
            missing_required.append(var)
    
    print("\n📋 Optional Configuration:")
    for var, desc in optional_vars.items():
        value = os.getenv(var)
        if value:
            if var == "PRIVATE_KEY":
                print(f"  ✅ {var}: {desc} - provided")
            else:
                print(f"  ✅ {var}: {desc} - {value}")
        else:
            print(f"  ⚠️  {var}: {desc} - using default")
    
    if missing_required:
        print(f"\n❌ Configuration incomplete! Missing: {missing_required}")
        print("Please set the required environment variables and try again.")
        return False
    else:
        print("\n✅ Configuration complete!")
        return True


def test_connectivity():
    """Test connectivity to blockchain and APIs."""
    print("🔌 Testing connectivity...")
    
    # Test blockchain connectivity
    network = os.getenv("NETWORK", "bsc-testnet")
    rpc_url = os.getenv("RPC_URL")
    
    if not rpc_url:
        # Get default RPC for network
        network_defaults = {
            "bsc-testnet": "https://bsc-testnet.bnbchain.org",
            "bsc-mainnet": "https://bsc-dataseed1.binance.org",
            "base-mainnet": "https://mainnet.base.org",
            "ethereum-mainnet": "https://eth-mainnet.g.alchemy.com/v2/demo",
        }
        rpc_url = network_defaults.get(network)
        
    if rpc_url:
        print(f"\n🌐 Testing blockchain connectivity ({network})...")
        try:
            from web3 import Web3
            web3 = Web3(Web3.HTTPProvider(rpc_url))
            
            if web3.is_connected():
                latest_block = web3.eth.block_number
                print(f"  ✅ Connected to {network} - Latest block: {latest_block}")
            else:
                print(f"  ❌ Failed to connect to {network}")
                return False
                
        except Exception as e:
            print(f"  ❌ Blockchain connection error: {e}")
            return False
    
    # Test ThoughtProof API connectivity
    print(f"\n🧠 Testing ThoughtProof API connectivity...")
    try:
        import httpx
        
        with httpx.Client(timeout=10) as client:
            # Test basic API availability
            response = client.get("https://api.thoughtproof.ai/health", follow_redirects=True)
            if response.status_code == 200:
                print(f"  ✅ ThoughtProof API accessible")
            else:
                print(f"  ⚠️  ThoughtProof API returned {response.status_code}")
                
    except Exception as e:
        print(f"  ❌ ThoughtProof API connection error: {e}")
        return False
    
    # Test contract accessibility
    evaluator_address = os.getenv("THOUGHTPROOF_EVALUATOR")
    if evaluator_address and rpc_url:
        print(f"\n📄 Testing contract accessibility...")
        try:
            from thoughtproof_evaluator import ThoughtProofEvaluatorClient
            from web3 import Web3
            
            web3 = Web3(Web3.HTTPProvider(rpc_url))
            evaluator = ThoughtProofEvaluatorClient(web3, evaluator_address)
            
            # Test read operation
            erc8183_address = evaluator.get_erc8183_address()
            print(f"  ✅ ThoughtProof evaluator contract accessible")
            print(f"  📍 ERC8183 address: {erc8183_address}")
            
        except Exception as e:
            print(f"  ❌ Contract access error: {e}")
            return False
    
    print("\n✅ All connectivity tests passed!")
    return True


def setup_wallet():
    """Set up wallet if needed."""
    print("👛 Setting up wallet...")
    
    try:
        from bnbagent.wallets import EVMWalletProvider
        
        wallet_password = os.getenv("WALLET_PASSWORD")
        private_key = os.getenv("PRIVATE_KEY")
        
        if private_key:
            print("  🔑 Using provided private key...")
            wallet = EVMWalletProvider(
                password=wallet_password,
                private_key=private_key
            )
        else:
            print("  🎲 No private key provided - checking for existing wallet...")
            if EVMWalletProvider.keystore_exists():
                print("  📂 Loading existing wallet from keystore...")
                wallet = EVMWalletProvider(password=wallet_password)
            else:
                print("  ✨ Generating new wallet...")
                wallet = EVMWalletProvider(password=wallet_password)
        
        print(f"  ✅ Wallet ready: {wallet.address}")
        return True
        
    except Exception as e:
        print(f"  ❌ Wallet setup failed: {e}")
        return False


def deploy():
    """Deploy the ThoughtProof integration."""
    print("🚀 Deploying ThoughtProof integration...")
    
    # Run all checks first
    if not check_config():
        return False
        
    if not test_connectivity():
        return False
        
    if not setup_wallet():
        return False
    
    print("\n📝 Deployment checklist:")
    print("  ✅ Configuration validated")
    print("  ✅ Connectivity tested")  
    print("  ✅ Wallet configured")
    
    # Create example systemd service file
    create_systemd_service()
    
    # Create example docker-compose file
    create_docker_compose()
    
    print("\n🎉 Deployment preparation complete!")
    print("\nNext steps:")
    print("1. Review the generated configuration files")
    print("2. Fund your wallet with the payment token")  
    print("3. Fund your Base wallet with USDC for ThoughtProof payments")
    print("4. Start the agent: python example_agent.py")
    print("5. Register your agent with the APEX protocol")
    print("6. Monitor logs and agent endpoints")
    
    return True


def create_systemd_service():
    """Create an example systemd service file."""
    service_content = """[Unit]
Description=BNBAgent with ThoughtProof Integration
After=network.target

[Service]
Type=simple
User=bnbagent
WorkingDirectory=/opt/bnbagent-thoughtproof
Environment=PATH=/opt/bnbagent-thoughtproof/venv/bin
ExecStart=/opt/bnbagent-thoughtproof/venv/bin/python example_agent.py
Restart=always
RestartSec=10

# Environment file
EnvironmentFile=/opt/bnbagent-thoughtproof/.env

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/bnbagent-thoughtproof/storage

[Install]
WantedBy=multi-user.target
"""
    
    try:
        with open("bnbagent-thoughtproof.service", "w") as f:
            f.write(service_content)
        print("  📄 Created systemd service file: bnbagent-thoughtproof.service")
    except Exception as e:
        print(f"  ⚠️  Failed to create systemd service file: {e}")


def create_docker_compose():
    """Create an example docker-compose.yml file."""
    compose_content = """version: '3.8'

services:
  bnbagent-thoughtproof:
    build: .
    container_name: bnbagent-thoughtproof
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./storage:/app/storage
      - ./wallets:/app/wallets
    environment:
      - HOST=0.0.0.0
      - PORT=8000
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/apex/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - bnbagent

  # Optional: IPFS node for decentralized storage
  ipfs:
    image: ipfs/kubo:latest
    container_name: bnbagent-ipfs
    ports:
      - "5001:5001"
      - "8080:8080"
    volumes:
      - ./ipfs-data:/data/ipfs
    networks:
      - bnbagent

networks:
  bnbagent:
    driver: bridge
"""
    
    dockerfile_content = """FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories
RUN mkdir -p storage wallets

# Create non-root user
RUN useradd -m -u 1001 bnbagent && \\
    chown -R bnbagent:bnbagent /app
USER bnbagent

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:8000/apex/health || exit 1

# Default command
CMD ["python", "example_agent.py"]
"""
    
    try:
        with open("docker-compose.yml", "w") as f:
            f.write(compose_content)
        print("  🐳 Created Docker Compose file: docker-compose.yml")
        
        with open("Dockerfile", "w") as f:
            f.write(dockerfile_content)
        print("  🐳 Created Dockerfile: Dockerfile")
        
    except Exception as e:
        print(f"  ⚠️  Failed to create Docker files: {e}")


def main():
    parser = argparse.ArgumentParser(description="Deploy ThoughtProof integration")
    parser.add_argument("--check-config", action="store_true", help="Check configuration")
    parser.add_argument("--test-connectivity", action="store_true", help="Test connectivity")
    parser.add_argument("--deploy", action="store_true", help="Full deployment")
    
    args = parser.parse_args()
    
    if args.check_config:
        success = check_config()
    elif args.test_connectivity:
        success = test_connectivity()
    elif args.deploy:
        success = deploy()
    else:
        print("Please specify an action: --check-config, --test-connectivity, or --deploy")
        parser.print_help()
        return 1
        
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())