# ThoughtProofEvaluator v1.3.0 Gap Analysis

Based on the analysis of the current contract (`ThoughtProofEvaluator.sol`) and the test suite (`ThoughtProofEvaluator.t.sol`), here are the features that need to be added to bring the contract to v1.3.0 as expected by the tests:

## Critical Missing Features

### 1. Two-Phase Verification System
- **Missing Functions:**
  - `storeVerification()` - Store verification without calling job contract
  - `finalize()` - Permissionless finalization that calls job contract
  - `isFinalized()` - Check if verification has been finalized
- **Missing Errors:**
  - `NotStored` - For when finalize() is called on unverified job
  - `AlreadyFinalized` - For when finalize() is called twice

### 2. ERC-8004 Reputation Integration
- **Missing Interface:** `IERC8004Reputation` (imported but not defined)
- **Missing Functions:**
  - `setReputationRegistry(address registry, bool enabled)` - Configure reputation registry
  - `registerAgentId(address jobContract, uint256 agentId)` - Map job contracts to agent IDs
  - `removeAgentId(address jobContract)` - Remove agent ID mapping
  - `reputationEnabled()` - Check if reputation is enabled
  - `hasAgentId(address jobContract)` - Check if contract has agent ID
- **Missing State Variables:**
  - `reputationRegistry` - Address of ERC-8004 reputation registry
  - `agentIds` - Mapping of job contracts to agent IDs
  - `totalFeedbackSent` - Counter for successful feedback submissions
  - `totalFeedbackFailed` - Counter for failed feedback submissions

### 3. Per-Contract Threshold System (Failure Cost Tiers)
- **Missing Enum:** `FailureCost` with values: `NEGLIGIBLE(500)`, `LOW(600)`, `MODERATE(700)`, `HIGH(800)`, `CRITICAL(900)`
- **Missing Functions:**
  - `setContractTier(address jobContract, FailureCost tier)` - Set tier for contract
  - `setContractThreshold(address jobContract, uint256 threshold)` - Set custom threshold
  - `getEffectiveThreshold(address jobContract)` - Get threshold for contract (custom or tier-based)
  - `hasCustomThreshold(address jobContract)` - Check if contract has custom threshold
  - `removeContractThreshold(address jobContract)` - Remove custom threshold
- **Missing State Variables:**
  - `contractThresholds` - Mapping for custom per-contract thresholds
  - `defaultThreshold` - Rename `mdiThreshold` to this

### 4. Enhanced Verification Result Structure
- **Missing Fields in `VerificationResult`:**
  - `confidence` - Rename `mdi` to this
  - `threshold` - The threshold used for this verification
  - `jobCallSucceeded` - Whether the job contract call succeeded
- **Updated behavior:** Results should store the threshold that was actually used

### 5. Improved Signature Security
- **Missing Features:**
  - Include `block.chainid` in signature data to prevent cross-chain replay
  - Signature replay protection across different job contracts
- **Missing Errors:**
  - `SignatureAlreadyUsed` - For signature replay protection
- **Missing State Variables:**
  - `usedSignatures` - Mapping to track used signatures

### 6. Enhanced Error Handling
- **Missing Error:** `InvalidThreshold` - For threshold validation (100-1000 range)
- **Missing Features:**
  - Try/catch blocks around job contract calls
  - Track failed job contract calls with `totalCallFailed` counter
  - Graceful handling of reputation registry failures

### 7. Constructor Validation
- **Missing Validations:**
  - Threshold must be between 100-1000
  - Minimum verifiers must be >= 2

### 8. Admin Function Updates
- **Updated `setConfig()`:** Should use `defaultThreshold` instead of `mdiThreshold`
- **Enhanced validation:** Threshold range checking in setConfig

## Current Contract vs Expected Interface

### Current (v1.0):
- Basic verification with fixed threshold
- Simple signature verification
- Direct job contract calling
- Basic error handling

### Expected (v1.3.0):
- Two-phase verification system
- Per-contract thresholds with failure cost tiers
- ERC-8004 reputation integration
- Enhanced signature security with replay protection
- Comprehensive error handling with try/catch
- Extensive validation and admin controls

## Implementation Priority

1. **High Priority:** Two-phase system, signature security improvements
2. **Medium Priority:** Per-contract thresholds, enhanced error handling
3. **Low Priority:** ERC-8004 reputation integration

## Breaking Changes Required

1. Rename `mdi` to `confidence` in VerificationResult
2. Rename `mdiThreshold` to `defaultThreshold`
3. Add chainid to signature verification
4. Update constructor to include validation
5. Add new required state variables and mappings

The current contract is essentially v1.0 functionality while the tests expect a much more sophisticated v1.3.0 feature set.