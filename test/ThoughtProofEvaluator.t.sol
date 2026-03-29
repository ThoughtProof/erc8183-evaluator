// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {ThoughtProofEvaluator, IERC8183Job, IERC8004Reputation} from "../src/ThoughtProofEvaluator.sol";

/// @notice Mock ERC-8183 Job Contract
contract MockJobContract {
    enum Status { Open, Funded, Submitted, Completed, Rejected }
    
    mapping(uint256 => Status) public jobStatus;
    mapping(uint256 => bytes32) public jobReason;
    address public evaluator;

    constructor(address _evaluator) {
        evaluator = _evaluator;
    }

    function setJobStatus(uint256 jobId, Status status) external {
        jobStatus[jobId] = status;
    }

    function complete(uint256 jobId, bytes32 reason) external {
        require(msg.sender == evaluator, "Only evaluator");
        require(jobStatus[jobId] == Status.Submitted, "Not submitted");
        jobStatus[jobId] = Status.Completed;
        jobReason[jobId] = reason;
    }

    function reject(uint256 jobId, bytes32 reason) external {
        require(msg.sender == evaluator, "Only evaluator");
        require(jobStatus[jobId] == Status.Submitted, "Not submitted");
        jobStatus[jobId] = Status.Rejected;
        jobReason[jobId] = reason;
    }
}

/// @notice Mock that always reverts (for try/catch testing)
contract RevertingJobContract {
    function complete(uint256, bytes32) external pure {
        revert("Always reverts");
    }
    function reject(uint256, bytes32) external pure {
        revert("Always reverts");
    }
}

/// @notice Mock ERC-8004 Reputation Registry
contract MockReputationRegistry {
    struct Feedback {
        uint256 agentId;
        int128 value;
        uint8 valueDecimals;
        string tag1;
        string tag2;
        string endpoint;
        string feedbackURI;
        bytes32 feedbackHash;
    }

    Feedback[] public feedbacks;
    uint256 public feedbackCount;
    bool public shouldRevert;

    function giveFeedback(
        uint256 agentId,
        int128 value,
        uint8 valueDecimals,
        string calldata tag1,
        string calldata tag2,
        string calldata endpoint,
        string calldata feedbackURI,
        bytes32 feedbackHash
    ) external {
        if (shouldRevert) revert("Reputation reverts");
        feedbacks.push(Feedback(agentId, value, valueDecimals, tag1, tag2, endpoint, feedbackURI, feedbackHash));
        feedbackCount++;
    }

    function setShouldRevert(bool _shouldRevert) external {
        shouldRevert = _shouldRevert;
    }

    function getLastFeedback() external view returns (Feedback memory) {
        require(feedbackCount > 0, "No feedback");
        return feedbacks[feedbackCount - 1];
    }
}

contract ThoughtProofEvaluatorTest is Test {
    ThoughtProofEvaluator evaluator;
    MockJobContract jobContract;
    MockJobContract jobContract2;
    RevertingJobContract revertingJob;
    MockReputationRegistry repRegistry;
    
    uint256 signerPrivateKey = 0xA11CE;
    address signer;
    
    uint256 constant DEFAULT_THRESHOLD = 700;
    uint256 constant MIN_VERIFIERS = 3;

    function setUp() public {
        signer = vm.addr(signerPrivateKey);
        evaluator = new ThoughtProofEvaluator(signer, DEFAULT_THRESHOLD, MIN_VERIFIERS);
        jobContract = new MockJobContract(address(evaluator));
        jobContract2 = new MockJobContract(address(evaluator));
        revertingJob = new RevertingJobContract();
        repRegistry = new MockReputationRegistry();
    }

    // ============ Helpers ============

    function _signVerification(
        address _jobContract,
        uint256 _jobId,
        uint256 _confidence,
        uint256 _verifierCount,
        bytes32 _blockHash
    ) internal view returns (bytes memory) {
        bytes32 dataHash = keccak256(abi.encodePacked(
            _jobContract, _jobId, _confidence, _verifierCount, _blockHash, block.chainid
        ));
        bytes32 messageHash = keccak256(abi.encodePacked(
            "\x19Ethereum Signed Message:\n32", dataHash
        ));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerPrivateKey, messageHash);
        return abi.encodePacked(r, s, v);
    }

    function _setupReputation(address _jobContract, uint256 agentId) internal {
        evaluator.setReputationRegistry(address(repRegistry), true);
        evaluator.registerAgentId(_jobContract, agentId);
    }

    // ============ Deployment ============

    function test_DeploymentConfig() public view {
        assertEq(evaluator.owner(), address(this));
        assertEq(evaluator.verifierSigner(), signer);
        assertEq(evaluator.defaultThreshold(), DEFAULT_THRESHOLD);
        assertEq(evaluator.minVerifiers(), MIN_VERIFIERS);
        assertEq(evaluator.totalVerifications(), 0);
        assertFalse(evaluator.reputationEnabled());
    }

    function test_DeploymentRevertOnThresholdTooHigh() public {
        vm.expectRevert(ThoughtProofEvaluator.InvalidThreshold.selector);
        new ThoughtProofEvaluator(signer, 1001, MIN_VERIFIERS);
    }

    function test_DeploymentRevertOnThresholdTooLow() public {
        vm.expectRevert(ThoughtProofEvaluator.InvalidThreshold.selector);
        new ThoughtProofEvaluator(signer, 99, MIN_VERIFIERS);
    }

    function test_DeploymentRevertOnMinVerifiersTooLow() public {
        vm.expectRevert(ThoughtProofEvaluator.InvalidParameters.selector);
        new ThoughtProofEvaluator(signer, DEFAULT_THRESHOLD, 1);
    }

    // ============ Happy Path: submitVerification (backward compat) ============

    function test_SubmitVerification_Passed() public {
        uint256 jobId = 1;
        uint256 confidence = 850;
        uint256 verifierCount = 3;
        bytes32 blockHash = keccak256("epistemic-block-001");

        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, confidence, verifierCount, blockHash);
        evaluator.submitVerification(address(jobContract), jobId, confidence, verifierCount, blockHash, sig);

        assertTrue(evaluator.isVerified(address(jobContract), jobId));
        assertTrue(evaluator.isFinalized(address(jobContract), jobId));
        
        ThoughtProofEvaluator.VerificationResult memory result = evaluator.getVerification(address(jobContract), jobId);
        assertEq(result.confidence, 850);
        assertEq(result.verifierCount, 3);
        assertTrue(result.passed);
        assertTrue(result.jobCallSucceeded);
        assertEq(result.epistemicBlockHash, blockHash);
        assertEq(result.threshold, DEFAULT_THRESHOLD);

        assertEq(uint(jobContract.jobStatus(jobId)), uint(MockJobContract.Status.Completed));
        assertEq(evaluator.totalVerifications(), 1);
        assertEq(evaluator.totalCompleted(), 1);
    }

    function test_SubmitVerification_Rejected() public {
        uint256 jobId = 2;
        uint256 confidence = 400;
        uint256 verifierCount = 3;
        bytes32 blockHash = keccak256("epistemic-block-002");

        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, confidence, verifierCount, blockHash);
        evaluator.submitVerification(address(jobContract), jobId, confidence, verifierCount, blockHash, sig);

        ThoughtProofEvaluator.VerificationResult memory result = evaluator.getVerification(address(jobContract), jobId);
        assertFalse(result.passed);
        assertTrue(result.jobCallSucceeded);
        assertEq(uint(jobContract.jobStatus(jobId)), uint(MockJobContract.Status.Rejected));
        assertEq(evaluator.totalRejected(), 1);
    }

    function test_SubmitVerification_ExactThreshold() public {
        uint256 jobId = 3;
        uint256 confidence = 700;
        uint256 verifierCount = 3;
        bytes32 blockHash = keccak256("epistemic-block-003");

        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, confidence, verifierCount, blockHash);
        evaluator.submitVerification(address(jobContract), jobId, confidence, verifierCount, blockHash, sig);

        assertTrue(evaluator.getVerification(address(jobContract), jobId).passed);
    }

    // ============ Two-Phase: store + finalize ============

    function test_StoreVerification_DoesNotCallJob() public {
        uint256 jobId = 100;
        uint256 confidence = 850;
        uint256 verifierCount = 3;
        bytes32 blockHash = keccak256("two-phase-001");

        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, confidence, verifierCount, blockHash);
        evaluator.storeVerification(address(jobContract), jobId, confidence, verifierCount, blockHash, sig);

        // Stored but NOT finalized
        assertTrue(evaluator.isVerified(address(jobContract), jobId));
        assertFalse(evaluator.isFinalized(address(jobContract), jobId));

        // Job contract NOT called yet
        assertEq(uint(jobContract.jobStatus(jobId)), uint(MockJobContract.Status.Submitted));

        ThoughtProofEvaluator.VerificationResult memory result = evaluator.getVerification(address(jobContract), jobId);
        assertTrue(result.passed);
        assertFalse(result.jobCallSucceeded);
    }

    function test_Finalize_PermissionlessAfterStore() public {
        uint256 jobId = 101;
        uint256 confidence = 850;
        uint256 verifierCount = 3;
        bytes32 blockHash = keccak256("two-phase-002");

        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, confidence, verifierCount, blockHash);
        evaluator.storeVerification(address(jobContract), jobId, confidence, verifierCount, blockHash, sig);

        // Anyone can finalize
        address randomUser = address(0xCAFE);
        vm.prank(randomUser);
        evaluator.finalize(address(jobContract), jobId);

        assertTrue(evaluator.isFinalized(address(jobContract), jobId));
        assertEq(uint(jobContract.jobStatus(jobId)), uint(MockJobContract.Status.Completed));

        ThoughtProofEvaluator.VerificationResult memory result = evaluator.getVerification(address(jobContract), jobId);
        assertTrue(result.jobCallSucceeded);
    }

    function test_Finalize_RevertIfNotStored() public {
        vm.expectRevert(ThoughtProofEvaluator.NotStored.selector);
        evaluator.finalize(address(jobContract), 999);
    }

    function test_Finalize_RevertIfAlreadyFinalized() public {
        uint256 jobId = 102;
        uint256 confidence = 850;
        uint256 verifierCount = 3;
        bytes32 blockHash = keccak256("two-phase-003");

        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, confidence, verifierCount, blockHash);
        evaluator.submitVerification(address(jobContract), jobId, confidence, verifierCount, blockHash, sig);

        // Already finalized by submitVerification
        vm.expectRevert(ThoughtProofEvaluator.AlreadyFinalized.selector);
        evaluator.finalize(address(jobContract), jobId);
    }

    function test_StoreAndFinalize_Rejection() public {
        uint256 jobId = 103;
        uint256 confidence = 400;
        uint256 verifierCount = 3;
        bytes32 blockHash = keccak256("two-phase-reject");

        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, confidence, verifierCount, blockHash);
        evaluator.storeVerification(address(jobContract), jobId, confidence, verifierCount, blockHash, sig);
        evaluator.finalize(address(jobContract), jobId);

        assertEq(uint(jobContract.jobStatus(jobId)), uint(MockJobContract.Status.Rejected));
        assertTrue(evaluator.isFinalized(address(jobContract), jobId));
    }

    // ============ ERC-8004 Reputation Feedback ============

    function test_ReputationFeedback_OnPass() public {
        uint256 agentId = 28388;
        _setupReputation(address(jobContract), agentId);

        uint256 jobId = 200;
        uint256 confidence = 850;
        bytes32 blockHash = keccak256("rep-pass");

        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, confidence, 3, blockHash);
        evaluator.submitVerification(address(jobContract), jobId, confidence, 3, blockHash, sig);

        assertEq(repRegistry.feedbackCount(), 1);
        assertEq(evaluator.totalFeedbackSent(), 1);

        MockReputationRegistry.Feedback memory fb = repRegistry.getLastFeedback();
        assertEq(fb.agentId, agentId);
        assertEq(fb.value, int128(int256(confidence))); // positive for pass
        assertEq(fb.valueDecimals, 3);
        assertEq(fb.tag1, "thoughtproof");
        assertEq(fb.tag2, "verification");
    }

    function test_ReputationFeedback_OnReject() public {
        uint256 agentId = 28388;
        _setupReputation(address(jobContract), agentId);

        uint256 jobId = 201;
        uint256 confidence = 400;
        bytes32 blockHash = keccak256("rep-reject");

        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, confidence, 3, blockHash);
        evaluator.submitVerification(address(jobContract), jobId, confidence, 3, blockHash, sig);

        MockReputationRegistry.Feedback memory fb = repRegistry.getLastFeedback();
        assertEq(fb.value, -int128(int256(confidence))); // negative for reject
    }

    function test_ReputationFeedback_SkippedWhenDisabled() public {
        // Don't enable reputation
        uint256 jobId = 202;
        bytes32 blockHash = keccak256("rep-disabled");
        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, 850, 3, blockHash);
        evaluator.submitVerification(address(jobContract), jobId, 850, 3, blockHash, sig);

        assertEq(repRegistry.feedbackCount(), 0);
        assertEq(evaluator.totalFeedbackSent(), 0);
    }

    function test_ReputationFeedback_SkippedWhenNoAgentId() public {
        evaluator.setReputationRegistry(address(repRegistry), true);
        // Don't register agent ID

        uint256 jobId = 203;
        bytes32 blockHash = keccak256("rep-no-agent");
        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, 850, 3, blockHash);
        evaluator.submitVerification(address(jobContract), jobId, 850, 3, blockHash, sig);

        assertEq(repRegistry.feedbackCount(), 0);
    }

    function test_ReputationFeedback_DoesNotRevertOnFailure() public {
        _setupReputation(address(jobContract), 28388);
        repRegistry.setShouldRevert(true);

        uint256 jobId = 204;
        bytes32 blockHash = keccak256("rep-reverts");
        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, 850, 3, blockHash);
        // Should NOT revert even though reputation call fails
        evaluator.submitVerification(address(jobContract), jobId, 850, 3, blockHash, sig);

        assertTrue(evaluator.isVerified(address(jobContract), jobId));
        assertEq(evaluator.totalFeedbackSent(), 0); // Failed, so not counted
        assertEq(evaluator.totalFeedbackFailed(), 1); // But failure IS counted
    }

    function test_ReputationFeedback_SentDuringStore() public {
        _setupReputation(address(jobContract), 28388);

        uint256 jobId = 205;
        bytes32 blockHash = keccak256("rep-store-phase");
        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, 850, 3, blockHash);
        evaluator.storeVerification(address(jobContract), jobId, 850, 3, blockHash, sig);

        // Feedback sent during store (not finalize)
        assertEq(repRegistry.feedbackCount(), 1);
    }

    // ============ Reputation Config ============

    function test_SetReputationRegistry() public {
        evaluator.setReputationRegistry(address(repRegistry), true);
        assertTrue(evaluator.reputationEnabled());
        assertEq(address(evaluator.reputationRegistry()), address(repRegistry));
    }

    function test_RegisterAgentId() public {
        evaluator.registerAgentId(address(jobContract), 28388);
        assertTrue(evaluator.hasAgentId(address(jobContract)));
        assertEq(evaluator.agentIds(address(jobContract)), 28388);
    }

    function test_RemoveAgentId() public {
        evaluator.registerAgentId(address(jobContract), 28388);
        evaluator.removeAgentId(address(jobContract));
        assertFalse(evaluator.hasAgentId(address(jobContract)));
    }

    function test_RegisterAgentId_RevertOnZeroAddress() public {
        vm.expectRevert(ThoughtProofEvaluator.InvalidParameters.selector);
        evaluator.registerAgentId(address(0), 28388);
    }

    function test_ReputationConfig_OnlyOwner() public {
        vm.prank(address(0xDEAD));
        vm.expectRevert(ThoughtProofEvaluator.Unauthorized.selector);
        evaluator.setReputationRegistry(address(repRegistry), true);

        vm.prank(address(0xDEAD));
        vm.expectRevert(ThoughtProofEvaluator.Unauthorized.selector);
        evaluator.registerAgentId(address(jobContract), 28388);
    }

    // ============ Per-Contract Threshold (Failure Cost Tiers) ============

    function test_SetContractTier_Critical() public {
        evaluator.setContractTier(address(jobContract), ThoughtProofEvaluator.FailureCost.CRITICAL);
        assertEq(evaluator.getEffectiveThreshold(address(jobContract)), 900);
    }

    function test_SetContractTier_AllTiers() public {
        evaluator.setContractTier(address(jobContract), ThoughtProofEvaluator.FailureCost.NEGLIGIBLE);
        assertEq(evaluator.getEffectiveThreshold(address(jobContract)), 500);

        evaluator.setContractTier(address(jobContract), ThoughtProofEvaluator.FailureCost.LOW);
        assertEq(evaluator.getEffectiveThreshold(address(jobContract)), 600);

        evaluator.setContractTier(address(jobContract), ThoughtProofEvaluator.FailureCost.MODERATE);
        assertEq(evaluator.getEffectiveThreshold(address(jobContract)), 700);

        evaluator.setContractTier(address(jobContract), ThoughtProofEvaluator.FailureCost.HIGH);
        assertEq(evaluator.getEffectiveThreshold(address(jobContract)), 800);

        evaluator.setContractTier(address(jobContract), ThoughtProofEvaluator.FailureCost.CRITICAL);
        assertEq(evaluator.getEffectiveThreshold(address(jobContract)), 900);
    }

    function test_SetContractThreshold_Custom() public {
        evaluator.setContractThreshold(address(jobContract), 750);
        assertEq(evaluator.getEffectiveThreshold(address(jobContract)), 750);
    }

    function test_SetContractThreshold_RevertOnTooHigh() public {
        vm.expectRevert(ThoughtProofEvaluator.InvalidThreshold.selector);
        evaluator.setContractThreshold(address(jobContract), 1001);
    }

    function test_SetContractThreshold_RevertOnTooLow() public {
        vm.expectRevert(ThoughtProofEvaluator.InvalidThreshold.selector);
        evaluator.setContractThreshold(address(jobContract), 99);
    }

    function test_SetContractTier_RevertOnZeroAddress() public {
        vm.expectRevert(ThoughtProofEvaluator.InvalidParameters.selector);
        evaluator.setContractTier(address(0), ThoughtProofEvaluator.FailureCost.HIGH);
    }

    function test_SetContractTier_OnlyOwner() public {
        vm.prank(address(0xDEAD));
        vm.expectRevert(ThoughtProofEvaluator.Unauthorized.selector);
        evaluator.setContractTier(address(jobContract), ThoughtProofEvaluator.FailureCost.HIGH);
    }

    function test_RemoveContractThreshold() public {
        evaluator.setContractTier(address(jobContract), ThoughtProofEvaluator.FailureCost.CRITICAL);
        evaluator.removeContractThreshold(address(jobContract));
        assertEq(evaluator.getEffectiveThreshold(address(jobContract)), DEFAULT_THRESHOLD);
        assertFalse(evaluator.hasCustomThreshold(address(jobContract)));
    }

    function test_SubmitVerification_UsesPerContractThreshold() public {
        evaluator.setContractTier(address(jobContract), ThoughtProofEvaluator.FailureCost.CRITICAL);

        uint256 jobId = 10;
        uint256 confidence = 800;
        bytes32 blockHash = keccak256("epistemic-block-010");

        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, confidence, 3, blockHash);
        evaluator.submitVerification(address(jobContract), jobId, confidence, 3, blockHash, sig);

        ThoughtProofEvaluator.VerificationResult memory result = evaluator.getVerification(address(jobContract), jobId);
        assertFalse(result.passed); // 800 < 900
        assertEq(result.threshold, 900);
    }

    function test_SubmitVerification_DifferentContractsDifferentThresholds() public {
        evaluator.setContractTier(address(jobContract), ThoughtProofEvaluator.FailureCost.CRITICAL);
        evaluator.setContractTier(address(jobContract2), ThoughtProofEvaluator.FailureCost.NEGLIGIBLE);

        uint256 confidence = 600;

        bytes32 blockHash1 = keccak256("block-critical");
        jobContract.setJobStatus(1, MockJobContract.Status.Submitted);
        bytes memory sig1 = _signVerification(address(jobContract), 1, confidence, 3, blockHash1);
        evaluator.submitVerification(address(jobContract), 1, confidence, 3, blockHash1, sig1);
        assertFalse(evaluator.getVerification(address(jobContract), 1).passed); // 600 < 900

        bytes32 blockHash2 = keccak256("block-negligible");
        jobContract2.setJobStatus(1, MockJobContract.Status.Submitted);
        bytes memory sig2 = _signVerification(address(jobContract2), 1, confidence, 3, blockHash2);
        evaluator.submitVerification(address(jobContract2), 1, confidence, 3, blockHash2, sig2);
        assertTrue(evaluator.getVerification(address(jobContract2), 1).passed); // 600 > 500
    }

    // ============ Try/Catch: Graceful External Call Failure ============

    function test_SubmitVerification_ExternalCallReverts_StillRecords() public {
        uint256 jobId = 1;
        uint256 confidence = 850;
        bytes32 blockHash = keccak256("epistemic-block-revert");

        bytes memory sig = _signVerification(address(revertingJob), jobId, confidence, 3, blockHash);
        evaluator.submitVerification(address(revertingJob), jobId, confidence, 3, blockHash, sig);

        assertTrue(evaluator.isVerified(address(revertingJob), jobId));
        ThoughtProofEvaluator.VerificationResult memory result = evaluator.getVerification(address(revertingJob), jobId);
        assertTrue(result.passed);
        assertFalse(result.jobCallSucceeded);
        assertEq(evaluator.totalCallFailed(), 1);
    }

    // ============ Security: Signature Validation ============

    function test_RevertOnInvalidSignature() public {
        uint256 jobId = 4;
        bytes32 blockHash = keccak256("epistemic-block-004");

        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        uint256 wrongKey = 0xBAD;
        bytes32 dataHash = keccak256(abi.encodePacked(
            address(jobContract), jobId, uint256(800), uint256(3), blockHash, block.chainid
        ));
        bytes32 messageHash = keccak256(abi.encodePacked(
            "\x19Ethereum Signed Message:\n32", dataHash
        ));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(wrongKey, messageHash);
        bytes memory badSig = abi.encodePacked(r, s, v);

        vm.expectRevert(ThoughtProofEvaluator.InvalidSignature.selector);
        evaluator.submitVerification(address(jobContract), jobId, 800, 3, blockHash, badSig);
    }

    function test_RevertOnSignatureReplay() public {
        uint256 jobId = 5;
        bytes32 blockHash = keccak256("epistemic-block-005");

        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, 850, 3, blockHash);
        evaluator.submitVerification(address(jobContract), jobId, 850, 3, blockHash, sig);

        vm.expectRevert(ThoughtProofEvaluator.SignatureAlreadyUsed.selector);
        evaluator.submitVerification(address(revertingJob), jobId, 850, 3, blockHash, sig);
    }

    // ============ Security: Input Validation ============

    function test_RevertOnDoubleVerification() public {
        uint256 jobId = 6;
        bytes32 blockHash = keccak256("epistemic-block-006");

        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, 850, 3, blockHash);
        evaluator.submitVerification(address(jobContract), jobId, 850, 3, blockHash, sig);

        bytes32 blockHash2 = keccak256("epistemic-block-006b");
        bytes memory sig2 = _signVerification(address(jobContract), jobId, 850, 3, blockHash2);
        vm.expectRevert(ThoughtProofEvaluator.AlreadyVerified.selector);
        evaluator.submitVerification(address(jobContract), jobId, 850, 3, blockHash2, sig2);
    }

    function test_RevertOnBelowMinVerifiers() public {
        uint256 jobId = 7;
        bytes32 blockHash = keccak256("epistemic-block-007");

        jobContract.setJobStatus(jobId, MockJobContract.Status.Submitted);

        bytes memory sig = _signVerification(address(jobContract), jobId, 900, 2, blockHash);
        vm.expectRevert(ThoughtProofEvaluator.BelowMinVerifiers.selector);
        evaluator.submitVerification(address(jobContract), jobId, 900, 2, blockHash, sig);
    }

    function test_RevertOnZeroAddress() public {
        bytes32 blockHash = keccak256("test");
        bytes memory sig = _signVerification(address(0), 1, 800, 3, blockHash);
        vm.expectRevert(ThoughtProofEvaluator.InvalidParameters.selector);
        evaluator.submitVerification(address(0), 1, 800, 3, blockHash, sig);
    }

    function test_RevertOnZeroBlockHash() public {
        jobContract.setJobStatus(1, MockJobContract.Status.Submitted);
        bytes memory sig = _signVerification(address(jobContract), 1, 800, 3, bytes32(0));
        vm.expectRevert(ThoughtProofEvaluator.InvalidParameters.selector);
        evaluator.submitVerification(address(jobContract), 1, 800, 3, bytes32(0), sig);
    }

    // ============ Admin ============

    function test_SetConfig() public {
        evaluator.setConfig(800, 5, address(0xBEEF));
        assertEq(evaluator.defaultThreshold(), 800);
        assertEq(evaluator.minVerifiers(), 5);
        assertEq(evaluator.verifierSigner(), address(0xBEEF));
    }

    function test_SetConfig_RevertOnThresholdTooHigh() public {
        vm.expectRevert(ThoughtProofEvaluator.InvalidThreshold.selector);
        evaluator.setConfig(1001, 5, address(0xBEEF));
    }

    function test_SetConfig_OnlyOwner() public {
        vm.prank(address(0xDEAD));
        vm.expectRevert(ThoughtProofEvaluator.Unauthorized.selector);
        evaluator.setConfig(800, 5, address(0xBEEF));
    }

    function test_TransferOwnership() public {
        address newOwner = address(0xCAFE);
        evaluator.transferOwnership(newOwner);
        assertEq(evaluator.owner(), newOwner);
    }

    function test_TransferOwnership_RevertZero() public {
        vm.expectRevert(ThoughtProofEvaluator.InvalidParameters.selector);
        evaluator.transferOwnership(address(0));
    }
}
