// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../src/ThoughtProofEvaluator.sol";

contract DeployScript is Script {
    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address verifierSigner = vm.envAddress("VERIFIER_SIGNER");
        
        uint256 mdiThreshold = 700;  // 0.700
        uint256 minVerifiers = 3;

        vm.startBroadcast(deployerKey);
        
        ThoughtProofEvaluator evaluator = new ThoughtProofEvaluator(
            verifierSigner,
            mdiThreshold,
            minVerifiers
        );

        console.log("ThoughtProofEvaluator deployed at:", address(evaluator));
        console.log("  Owner:", msg.sender);
        console.log("  Verifier Signer:", verifierSigner);
        console.log("  MDI Threshold:", mdiThreshold);
        console.log("  Min Verifiers:", minVerifiers);

        vm.stopBroadcast();
    }
}
