// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title ThoughtProofEvaluator
 * @notice ERC-8183 Evaluator that verifies agent work via multi-model consensus
 * @dev Off-chain service runs pot-sdk verification, then submits signed result here.
 *      This contract calls complete() or reject() on the ERC-8183 job contract.
 */

/// @notice Minimal ERC-8183 job contract interface (Evaluator perspective)
interface IERC8183Job {
    function complete(uint256 jobId, bytes32 reason) external;
    function reject(uint256 jobId, bytes32 reason) external;
}

contract ThoughtProofEvaluator {
    // ============ Config ============

    address public owner;
    address public verifierSigner; // EOA of the off-chain verification service
    uint256 public mdiThreshold;   // Minimum MDI * 1000 (e.g. 700 = 0.700)
    uint256 public minVerifiers;   // Minimum number of models that must agree
    uint256 public verificationFee; // Fee in wei (0 for MVP)

    // ============ State ============

    struct VerificationResult {
        address jobContract;
        uint256 jobId;
        uint256 mdi;              // MDI * 1000
        uint256 verifierCount;
        bytes32 epistemicBlockHash; // keccak256 of the full Epistemic Block (stored off-chain)
        bool passed;
        uint256 timestamp;
    }

    /// @notice jobContract => jobId => result
    mapping(address => mapping(uint256 => VerificationResult)) public results;

    uint256 public totalVerifications;
    uint256 public totalCompleted;
    uint256 public totalRejected;

    // ============ Events ============

    event VerificationSubmitted(
        address indexed jobContract,
        uint256 indexed jobId,
        uint256 mdi,
        uint256 verifierCount,
        bool passed,
        bytes32 epistemicBlockHash
    );

    event ConfigUpdated(uint256 mdiThreshold, uint256 minVerifiers, address verifierSigner);

    // ============ Errors ============

    error Unauthorized();
    error InvalidSignature();
    error AlreadyVerified();
    error InvalidParameters();
    error BelowMinVerifiers();

    // ============ Modifiers ============

    modifier onlyOwner() {
        if (msg.sender != owner) revert Unauthorized();
        _;
    }

    // ============ Constructor ============

    constructor(
        address _verifierSigner,
        uint256 _mdiThreshold,
        uint256 _minVerifiers
    ) {
        owner = msg.sender;
        verifierSigner = _verifierSigner;
        mdiThreshold = _mdiThreshold;
        minVerifiers = _minVerifiers;
    }

    // ============ Core: Submit Verification ============

    /**
     * @notice Submit a verification result from the off-chain service
     * @param jobContract Address of the ERC-8183 job contract
     * @param jobId The job ID being evaluated
     * @param mdi Model Diversity Index * 1000 (e.g. 850 = 0.850)
     * @param verifierCount Number of models that participated
     * @param epistemicBlockHash Hash of the full Epistemic Block (stored on IPFS/API)
     * @param signature EIP-191 signature from verifierSigner over the verification data
     */
    function submitVerification(
        address jobContract,
        uint256 jobId,
        uint256 mdi,
        uint256 verifierCount,
        bytes32 epistemicBlockHash,
        bytes calldata signature
    ) external {
        // 1. Prevent double-verification
        if (results[jobContract][jobId].timestamp != 0) revert AlreadyVerified();

        // 2. Validate parameters
        if (jobContract == address(0) || epistemicBlockHash == bytes32(0)) revert InvalidParameters();
        if (verifierCount < minVerifiers) revert BelowMinVerifiers();

        // 3. Verify signature from authorized signer
        bytes32 messageHash = keccak256(abi.encodePacked(
            "\x19Ethereum Signed Message:\n32",
            keccak256(abi.encodePacked(
                jobContract, jobId, mdi, verifierCount, epistemicBlockHash
            ))
        ));

        address recovered = _recoverSigner(messageHash, signature);
        if (recovered != verifierSigner) revert InvalidSignature();

        // 4. Determine pass/fail
        bool passed = mdi >= mdiThreshold;

        // 5. Store result
        results[jobContract][jobId] = VerificationResult({
            jobContract: jobContract,
            jobId: jobId,
            mdi: mdi,
            verifierCount: verifierCount,
            epistemicBlockHash: epistemicBlockHash,
            passed: passed,
            timestamp: block.timestamp
        });

        totalVerifications++;

        // 6. Call complete or reject on the job contract
        if (passed) {
            IERC8183Job(jobContract).complete(jobId, epistemicBlockHash);
            totalCompleted++;
        } else {
            IERC8183Job(jobContract).reject(jobId, epistemicBlockHash);
            totalRejected++;
        }

        emit VerificationSubmitted(
            jobContract, jobId, mdi, verifierCount, passed, epistemicBlockHash
        );
    }

    // ============ Views ============

    function getVerification(address jobContract, uint256 jobId)
        external
        view
        returns (VerificationResult memory)
    {
        return results[jobContract][jobId];
    }

    function isVerified(address jobContract, uint256 jobId) external view returns (bool) {
        return results[jobContract][jobId].timestamp != 0;
    }

    // ============ Admin ============

    function setConfig(
        uint256 _mdiThreshold,
        uint256 _minVerifiers,
        address _verifierSigner
    ) external onlyOwner {
        mdiThreshold = _mdiThreshold;
        minVerifiers = _minVerifiers;
        if (_verifierSigner != address(0)) {
            verifierSigner = _verifierSigner;
        }
        emit ConfigUpdated(_mdiThreshold, _minVerifiers, verifierSigner);
    }

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
