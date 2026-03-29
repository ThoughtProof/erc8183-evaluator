// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title ThoughtProofEvaluator v1.3.0
 * @notice Advanced ERC-8183 Evaluator with two-phase verification, reputation integration, and per-contract thresholds
 * @dev Supports ERC-8004 reputation feedback and flexible failure cost tiers
 */

/// @notice Minimal ERC-8183 job contract interface
interface IERC8183Job {
    function complete(uint256 jobId, bytes32 reason) external;
    function reject(uint256 jobId, bytes32 reason) external;
}

/// @notice ERC-8004 reputation registry interface
interface IERC8004Reputation {
    function giveFeedback(
        uint256 agentId,
        int128 value,
        uint8 valueDecimals,
        string calldata tag1,
        string calldata tag2,
        string calldata endpoint,
        string calldata feedbackURI,
        bytes32 feedbackHash
    ) external;
}

contract ThoughtProofEvaluator {
    // ============ Enums ============

    /// @notice Failure cost tiers for per-contract threshold configuration
    enum FailureCost {
        NEGLIGIBLE, // 500
        LOW,        // 600
        MODERATE,   // 700
        HIGH,       // 800
        CRITICAL    // 900
    }

    // ============ Config ============

    address public owner;
    address public verifierSigner;     // EOA of the off-chain verification service
    uint256 public defaultThreshold;   // Default confidence threshold * 1000
    uint256 public minVerifiers;       // Minimum number of models that must agree
    uint256 public verificationFee;    // Fee in wei (0 for MVP)

    // ============ ERC-8004 Reputation ============

    IERC8004Reputation public reputationRegistry;
    mapping(address => uint256) public agentIds;       // jobContract => agentId
    uint256 public totalFeedbackSent;
    uint256 public totalFeedbackFailed;

    // ============ Per-Contract Thresholds ============

    mapping(address => uint256) public contractThresholds; // Custom thresholds
    mapping(address => bool) private _hasCustomThreshold;

    // ============ State ============

    struct VerificationResult {
        address jobContract;
        uint256 jobId;
        uint256 confidence;         // Renamed from mdi
        uint256 verifierCount;
        bytes32 epistemicBlockHash;
        bool passed;
        uint256 threshold;          // Threshold used for this verification
        bool jobCallSucceeded;      // Whether the job contract call succeeded
        uint256 timestamp;
        bool finalized;             // Whether finalize() has been called
    }

    /// @notice jobContract => jobId => result
    mapping(address => mapping(uint256 => VerificationResult)) public results;

    /// @notice Track used signatures to prevent replay attacks
    mapping(bytes32 => bool) public usedSignatures;

    // ============ Counters ============

    uint256 public totalVerifications;
    uint256 public totalCompleted;
    uint256 public totalRejected;
    uint256 public totalCallFailed;

    // ============ Events ============

    event VerificationSubmitted(
        address indexed jobContract,
        uint256 indexed jobId,
        uint256 confidence,
        uint256 verifierCount,
        bool passed,
        bytes32 epistemicBlockHash
    );

    event VerificationStored(
        address indexed jobContract,
        uint256 indexed jobId,
        uint256 confidence,
        bool passed
    );

    event VerificationFinalized(
        address indexed jobContract,
        uint256 indexed jobId,
        bool jobCallSucceeded
    );

    event ConfigUpdated(uint256 defaultThreshold, uint256 minVerifiers, address verifierSigner);
    
    event ReputationRegistrySet(address indexed registry, bool enabled);
    
    event AgentIdRegistered(address indexed jobContract, uint256 agentId);
    
    event AgentIdRemoved(address indexed jobContract);

    event ContractTierSet(address indexed jobContract, FailureCost tier);
    
    event ContractThresholdSet(address indexed jobContract, uint256 threshold);
    
    event ContractThresholdRemoved(address indexed jobContract);

    // ============ Errors ============

    error Unauthorized();
    error InvalidSignature();
    error SignatureAlreadyUsed();
    error AlreadyVerified();
    error AlreadyFinalized();
    error NotStored();
    error InvalidParameters();
    error InvalidThreshold();
    error BelowMinVerifiers();

    // ============ Modifiers ============

    modifier onlyOwner() {
        if (msg.sender != owner) revert Unauthorized();
        _;
    }

    // ============ Constructor ============

    /**
     * @notice Deploy the evaluator with initial configuration
     * @param _verifierSigner Address authorized to sign verification results
     * @param _defaultThreshold Default confidence threshold (100-1000)
     * @param _minVerifiers Minimum verifiers required (>= 2)
     */
    constructor(
        address _verifierSigner,
        uint256 _defaultThreshold,
        uint256 _minVerifiers
    ) {
        if (_defaultThreshold < 100 || _defaultThreshold > 1000) revert InvalidThreshold();
        if (_minVerifiers < 2) revert InvalidParameters();
        
        owner = msg.sender;
        verifierSigner = _verifierSigner;
        defaultThreshold = _defaultThreshold;
        minVerifiers = _minVerifiers;
    }

    // ============ Core: Verification Functions ============

    /**
     * @notice Submit verification and immediately call job contract (backward compatible)
     * @param jobContract Address of the ERC-8183 job contract
     * @param jobId The job ID being evaluated
     * @param confidence Confidence score * 1000 (e.g. 850 = 0.850)
     * @param verifierCount Number of models that participated
     * @param epistemicBlockHash Hash of the full Epistemic Block
     * @param signature EIP-191 signature from verifierSigner
     */
    function submitVerification(
        address jobContract,
        uint256 jobId,
        uint256 confidence,
        uint256 verifierCount,
        bytes32 epistemicBlockHash,
        bytes calldata signature
    ) external {
        _storeVerification(jobContract, jobId, confidence, verifierCount, epistemicBlockHash, signature);
        _finalizeVerification(jobContract, jobId);
    }

    /**
     * @notice Store verification result without calling job contract
     * @param jobContract Address of the ERC-8183 job contract
     * @param jobId The job ID being evaluated
     * @param confidence Confidence score * 1000
     * @param verifierCount Number of models that participated
     * @param epistemicBlockHash Hash of the full Epistemic Block
     * @param signature EIP-191 signature from verifierSigner
     */
    function storeVerification(
        address jobContract,
        uint256 jobId,
        uint256 confidence,
        uint256 verifierCount,
        bytes32 epistemicBlockHash,
        bytes calldata signature
    ) external {
        _storeVerification(jobContract, jobId, confidence, verifierCount, epistemicBlockHash, signature);
    }

    /**
     * @notice Finalize a stored verification by calling the job contract (permissionless)
     * @param jobContract Address of the ERC-8183 job contract
     * @param jobId The job ID to finalize
     */
    function finalize(address jobContract, uint256 jobId) external {
        if (results[jobContract][jobId].timestamp == 0) revert NotStored();
        if (results[jobContract][jobId].finalized) revert AlreadyFinalized();
        
        _finalizeVerification(jobContract, jobId);
    }

    // ============ Internal Implementation ============

    function _storeVerification(
        address jobContract,
        uint256 jobId,
        uint256 confidence,
        uint256 verifierCount,
        bytes32 epistemicBlockHash,
        bytes calldata signature
    ) internal {
        // 1. Prevent double-verification
        if (results[jobContract][jobId].timestamp != 0) revert AlreadyVerified();

        // 2. Validate parameters
        if (jobContract == address(0) || epistemicBlockHash == bytes32(0)) revert InvalidParameters();
        if (verifierCount < minVerifiers) revert BelowMinVerifiers();

        // 3. Replay protection: each signature can only be used once
        bytes32 sigHash = keccak256(signature);
        if (usedSignatures[sigHash]) revert SignatureAlreadyUsed();
        usedSignatures[sigHash] = true;

        // 4. Verify signature with chainid
        bytes32 dataHash = keccak256(abi.encodePacked(
            jobContract, jobId, confidence, verifierCount, epistemicBlockHash, block.chainid
        ));

        bytes32 messageHash = keccak256(abi.encodePacked(
            "\x19Ethereum Signed Message:\n32", dataHash
        ));

        address recovered = _recoverSigner(messageHash, signature);
        if (recovered != verifierSigner) revert InvalidSignature();

        // 4. Get effective threshold for this contract
        uint256 threshold = getEffectiveThreshold(jobContract);
        bool passed = confidence >= threshold;

        // 5. Store result
        results[jobContract][jobId] = VerificationResult({
            jobContract: jobContract,
            jobId: jobId,
            confidence: confidence,
            verifierCount: verifierCount,
            epistemicBlockHash: epistemicBlockHash,
            passed: passed,
            threshold: threshold,
            jobCallSucceeded: false,
            timestamp: block.timestamp,
            finalized: false
        });

        totalVerifications++;

        // 6. Send ERC-8004 reputation feedback if enabled
        _sendReputationFeedback(jobContract, confidence, passed);

        emit VerificationStored(jobContract, jobId, confidence, passed);
        emit VerificationSubmitted(jobContract, jobId, confidence, verifierCount, passed, epistemicBlockHash);
    }

    function _finalizeVerification(address jobContract, uint256 jobId) internal {
        VerificationResult storage result = results[jobContract][jobId];
        result.finalized = true;

        bool callSucceeded = false;

        if (result.passed) {
            // Verification passed → complete the job
            try IERC8183Job(jobContract).complete(jobId, result.epistemicBlockHash) {
                callSucceeded = true;
                totalCompleted++;
            } catch {
                totalCallFailed++;
            }
        } else {
            // Verification failed → reject the job
            try IERC8183Job(jobContract).reject(jobId, result.epistemicBlockHash) {
                callSucceeded = true;
                totalRejected++;
            } catch {
                totalCallFailed++;
            }
        }

        result.jobCallSucceeded = callSucceeded;
        
        emit VerificationFinalized(jobContract, jobId, callSucceeded);
    }

    function _sendReputationFeedback(address jobContract, uint256 confidence, bool passed) internal {
        if (!reputationEnabled() || !hasAgentId(jobContract)) {
            return;
        }

        uint256 agentId = agentIds[jobContract];
        int128 value = passed ? int128(int256(confidence)) : -int128(int256(confidence));

        try reputationRegistry.giveFeedback(
            agentId,
            value,
            3, // valueDecimals
            "thoughtproof",
            "verification",
            "",
            "",
            bytes32(0)
        ) {
            totalFeedbackSent++;
        } catch {
            totalFeedbackFailed++;
        }
    }

    // ============ Per-Contract Thresholds ============

    /**
     * @notice Set failure cost tier for a job contract
     * @param jobContract Address of the job contract
     * @param tier Failure cost tier
     */
    function setContractTier(address jobContract, FailureCost tier) external onlyOwner {
        if (jobContract == address(0)) revert InvalidParameters();
        
        uint256 threshold;
        if (tier == FailureCost.NEGLIGIBLE) threshold = 500;
        else if (tier == FailureCost.LOW) threshold = 600;
        else if (tier == FailureCost.MODERATE) threshold = 700;
        else if (tier == FailureCost.HIGH) threshold = 800;
        else if (tier == FailureCost.CRITICAL) threshold = 900;

        contractThresholds[jobContract] = threshold;
        _hasCustomThreshold[jobContract] = true;

        emit ContractTierSet(jobContract, tier);
    }

    /**
     * @notice Set custom threshold for a job contract
     * @param jobContract Address of the job contract
     * @param threshold Custom threshold (100-1000)
     */
    function setContractThreshold(address jobContract, uint256 threshold) external onlyOwner {
        if (threshold < 100 || threshold > 1000) revert InvalidThreshold();
        
        contractThresholds[jobContract] = threshold;
        _hasCustomThreshold[jobContract] = true;

        emit ContractThresholdSet(jobContract, threshold);
    }

    /**
     * @notice Remove custom threshold for a job contract
     * @param jobContract Address of the job contract
     */
    function removeContractThreshold(address jobContract) external onlyOwner {
        delete contractThresholds[jobContract];
        _hasCustomThreshold[jobContract] = false;

        emit ContractThresholdRemoved(jobContract);
    }

    /**
     * @notice Get effective threshold for a job contract
     * @param jobContract Address of the job contract
     * @return threshold The threshold to use (custom or default)
     */
    function getEffectiveThreshold(address jobContract) public view returns (uint256) {
        return _hasCustomThreshold[jobContract] ? contractThresholds[jobContract] : defaultThreshold;
    }

    /**
     * @notice Check if a contract has a custom threshold
     * @param jobContract Address of the job contract
     * @return hasCustom True if contract has custom threshold
     */
    function hasCustomThreshold(address jobContract) external view returns (bool) {
        return _hasCustomThreshold[jobContract];
    }

    // ============ ERC-8004 Reputation Management ============

    /**
     * @notice Set the reputation registry and enable/disable reputation feedback
     * @param registry Address of the ERC-8004 reputation registry
     * @param enabled Whether reputation feedback is enabled
     */
    function setReputationRegistry(address registry, bool enabled) external onlyOwner {
        reputationRegistry = enabled ? IERC8004Reputation(registry) : IERC8004Reputation(address(0));
        emit ReputationRegistrySet(registry, enabled);
    }

    /**
     * @notice Register an agent ID for a job contract
     * @param jobContract Address of the job contract
     * @param agentId Agent ID to associate with the contract
     */
    function registerAgentId(address jobContract, uint256 agentId) external onlyOwner {
        if (jobContract == address(0)) revert InvalidParameters();
        agentIds[jobContract] = agentId;
        emit AgentIdRegistered(jobContract, agentId);
    }

    /**
     * @notice Remove agent ID mapping for a job contract
     * @param jobContract Address of the job contract
     */
    function removeAgentId(address jobContract) external onlyOwner {
        delete agentIds[jobContract];
        emit AgentIdRemoved(jobContract);
    }

    /**
     * @notice Check if reputation feedback is enabled
     * @return enabled True if reputation is enabled
     */
    function reputationEnabled() public view returns (bool) {
        return address(reputationRegistry) != address(0);
    }

    /**
     * @notice Check if a job contract has an agent ID registered
     * @param jobContract Address of the job contract
     * @return hasAgent True if contract has agent ID
     */
    function hasAgentId(address jobContract) public view returns (bool) {
        return agentIds[jobContract] != 0;
    }

    // ============ Views ============

    /**
     * @notice Get verification result for a job
     * @param jobContract Address of the job contract
     * @param jobId Job ID
     * @return result The verification result
     */
    function getVerification(address jobContract, uint256 jobId)
        external
        view
        returns (VerificationResult memory)
    {
        return results[jobContract][jobId];
    }

    /**
     * @notice Check if a job has been verified
     * @param jobContract Address of the job contract
     * @param jobId Job ID
     * @return verified True if job has been verified
     */
    function isVerified(address jobContract, uint256 jobId) external view returns (bool) {
        return results[jobContract][jobId].timestamp != 0;
    }

    /**
     * @notice Check if a verification has been finalized
     * @param jobContract Address of the job contract
     * @param jobId Job ID
     * @return finalized True if verification has been finalized
     */
    function isFinalized(address jobContract, uint256 jobId) external view returns (bool) {
        return results[jobContract][jobId].finalized;
    }

    // ============ Admin ============

    /**
     * @notice Update configuration parameters
     * @param _defaultThreshold New default threshold (100-1000)
     * @param _minVerifiers New minimum verifiers
     * @param _verifierSigner New verifier signer address
     */
    function setConfig(
        uint256 _defaultThreshold,
        uint256 _minVerifiers,
        address _verifierSigner
    ) external onlyOwner {
        if (_defaultThreshold < 100 || _defaultThreshold > 1000) revert InvalidThreshold();
        if (_minVerifiers < 2) revert InvalidParameters();
        
        defaultThreshold = _defaultThreshold;
        minVerifiers = _minVerifiers;
        if (_verifierSigner != address(0)) {
            verifierSigner = _verifierSigner;
        }
        emit ConfigUpdated(_defaultThreshold, _minVerifiers, verifierSigner);
    }

    /**
     * @notice Transfer ownership to a new address
     * @param newOwner Address of the new owner
     */
    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert InvalidParameters();
        owner = newOwner;
    }

    // ============ Internal ============

    function _recoverSigner(bytes32 hash, bytes calldata sig)
        internal
        pure
        returns (address)
    {
        if (sig.length != 65) revert InvalidSignature();

        bytes32 r;
        bytes32 s;
        uint8 v;

        assembly {
            r := calldataload(sig.offset)
            s := calldataload(add(sig.offset, 32))
            v := byte(0, calldataload(add(sig.offset, 64)))
        }

        if (v < 27) v += 27;

        return ecrecover(hash, v, r, s);
    }
}