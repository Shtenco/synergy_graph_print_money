// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../contracts/V8_1SingleContractFlashGraph.sol";

interface VmV81Fork {
    function envString(string calldata name) external returns (string memory value);
    function createSelectFork(string calldata urlOrAlias, uint256 blockNumber) external returns (uint256 forkId);
}

interface IQuoterV2V81 {
    struct QuoteExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint256 amountIn;
        uint24 fee;
        uint160 sqrtPriceLimitX96;
    }
    function quoteExactInputSingle(QuoteExactInputSingleParams calldata params)
        external
        returns (uint256 amountOut, uint160 sqrtPriceX96After, uint32 initializedTicksCrossed, uint256 gasEstimate);
}

interface IUniPoolFeeV81 {
    function fee() external view returns (uint24);
}

interface IAggregatorV81 {
    function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80);
    function decimals() external view returns (uint8);
}

/// @notice Pinned Base proof for the one-contract V8.1 architecture.
/// The foreign cycle is one of the strict token-closed WETH cycles already
/// discovered in run #36.  A 5% RUBC pulse is used as a causal execution gate:
/// before QE, part of flash-WETH is locked in the virtual edge and the cycle
/// cannot be funded; after QE, the edge releases enough WETH to execute it.
contract V8SingleContractFlashForkTest {
    VmV81Fork constant vm = VmV81Fork(address(uint160(uint256(keccak256("hevm cheat code")))));

    address constant VAULT = 0xBA12222222228d8Ba445958a75a0704d566BF2C8;
    address constant WETH = 0x4200000000000000000000000000000000000006;
    address constant VIRTUAL = 0x0b3e328455c4059eEb9E3f84B5543F74E24e7E1b;
    address constant ETH_USD = 0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70;
    address constant UNI_QUOTER = 0x3d4e44eb1374240ce5f1b871ab261cd16335b76a;

    // Strict run-36 cycle 0.
    address constant UNI_VIRTUAL_WETH = 0x9c087eb773291e50cf6c6a90ef0f4500e349b903;
    address constant AERO_VIRTUAL_WETH = 0x21594b992f68495dd28d605834b58889d0a727c7;

    uint256 constant PINNED_BLOCK = 51_148_993;
    uint256 constant CYCLE_WETH_IN = 635250969890810496; // ~0.635251 WETH
    uint256 constant FLASH_WETH = 650000000000000000;    // 0.65 WETH, still below ~$2k at the pinned price
    uint256 constant EDGE_HARD = 15000000000000000;      // 0.015 WETH locked pre-QE
    uint256 constant EDGE_MONEY = 1 ether;
    uint256 constant QE_5PCT = 0.05 ether;
    uint256 constant BPS = 10_000;

    function testFivePercentQEGatesUnder2kFlashAndEndsHardPositive() public {
        vm.createSelectFork(vm.envString("BASE_RPC_URL"), PINNED_BLOCK);
        require(IERC20V81(WETH).balanceOf(VAULT) >= FLASH_WETH, "Balancer lacks WETH");

        uint256 ethUsdE8 = _ethUsdE8();
        uint256 flashUsd6 = FLASH_WETH * ethUsdE8 / 1e20;
        require(flashUsd6 < 2_000_000_000, "flash not below $2k");

        // Baseline sparse graph: edge reserve is locked, so there is not enough
        // free WETH to fund the already-discovered strict foreign cycle.
        uint256 baselineFree = FLASH_WETH - EDGE_HARD;
        require(baselineFree < CYCLE_WETH_IN, "baseline already executable");

        // Exact same 5% q/R QE pulse used by the V7.3 capped experiment.
        uint256 pulseHardOut = _q(EDGE_MONEY, EDGE_HARD, QE_5PCT, 30);
        uint256 postQeFree = baselineFree + pulseHardOut;
        require(postQeFree >= CYCLE_WETH_IN, "5% QE does not unlock cycle");

        // Quote the exact first foreign leg against the pinned Uniswap V3 pool,
        // then feed that exact output into the Aerodrome V2 closing leg.
        uint24 fee = IUniPoolFeeV81(UNI_VIRTUAL_WETH).fee();
        (uint256 virtualOut,,,) = IQuoterV2V81(UNI_QUOTER).quoteExactInputSingle(
            IQuoterV2V81.QuoteExactInputSingleParams({
                tokenIn: WETH,
                tokenOut: VIRTUAL,
                amountIn: CYCLE_WETH_IN,
                fee: fee,
                sqrtPriceLimitX96: 0
            })
        );
        require(virtualOut > 0, "zero VIRTUAL quote");
        uint256 wethOut = IAeroV2V81(AERO_VIRTUAL_WETH).getAmountOut(virtualOut, VIRTUAL);
        require(wethOut > CYCLE_WETH_IN, "foreign cycle not hard-positive");

        V8_1SingleContractFlashGraph engine = new V8_1SingleContractFlashGraph();

        address[] memory flashTokens = new address[](1);
        flashTokens[0] = WETH;
        uint256[] memory flashAmounts = new uint256[](1);
        flashAmounts[0] = FLASH_WETH;
        uint256[] memory minProfit = new uint256[](1);
        minProfit[0] = 1;

        V8_1SingleContractFlashGraph.EdgeSeed[] memory edges = new V8_1SingleContractFlashGraph.EdgeSeed[](1);
        edges[0] = V8_1SingleContractFlashGraph.EdgeSeed({
            field: engine.RUBC(),
            hardToken: WETH,
            hardReserve: EDGE_HARD,
            moneyReserve: EDGE_MONEY,
            feeBps: 30
        });

        V8_1SingleContractFlashGraph.Action[] memory actions = new V8_1SingleContractFlashGraph.Action[](3);
        actions[0] = V8_1SingleContractFlashGraph.Action({
            kind: engine.QE_PULSE(),
            edgeIndex: 0,
            pool: address(0),
            tokenIn: address(0),
            tokenOut: address(0),
            amountIn: QE_5PCT,
            minOut: pulseHardOut
        });
        actions[1] = V8_1SingleContractFlashGraph.Action({
            kind: engine.CL(),
            edgeIndex: 0,
            pool: UNI_VIRTUAL_WETH,
            tokenIn: WETH,
            tokenOut: VIRTUAL,
            amountIn: CYCLE_WETH_IN,
            minOut: virtualOut
        });
        actions[2] = V8_1SingleContractFlashGraph.Action({
            kind: engine.AERO_V2(),
            edgeIndex: 0,
            pool: AERO_VIRTUAL_WETH,
            tokenIn: VIRTUAL,
            tokenOut: WETH,
            amountIn: virtualOut,
            minOut: wethOut
        });

        uint256 beforeBal = IERC20V81(WETH).balanceOf(address(engine));
        uint256 gasBefore = gasleft();
        engine.execute(flashTokens, flashAmounts, edges, actions, minProfit);
        uint256 gasUsed = gasBefore - gasleft();
        uint256 afterBal = IERC20V81(WETH).balanceOf(address(engine));

        // execute() cannot return until principal + actual Balancer fee has been
        // repaid in WETH. Anything left in the engine is consolidated HardNAV.
        require(afterBal > beforeBal, "no post-repayment WETH HardNAV");
        uint256 rawProfitUsd6 = (afterBal - beforeBal) * ethUsdE8 / 1e20;
        uint256 riskAdjustedUsd6 = rawProfitUsd6 * 6500 / BPS;
        uint256 gasUsd6 = gasUsed * block.basefee * ethUsdE8 / 1e20;
        require(riskAdjustedUsd6 > gasUsd6, "profit fails 35% reserve + gas");
    }

    function _ethUsdE8() internal view returns (uint256) {
        (, int256 answer,, uint256 updatedAt,) = IAggregatorV81(ETH_USD).latestRoundData();
        require(answer > 0 && updatedAt > 0, "bad oracle");
        uint8 d = IAggregatorV81(ETH_USD).decimals();
        uint256 p = uint256(answer);
        if (d == 8) return p;
        if (d < 8) return p * 10 ** (8 - d);
        return p / 10 ** (d - 8);
    }

    function _q(uint256 rin, uint256 rout, uint256 amountIn, uint16 feeBps) internal pure returns (uint256) {
        uint256 effective = amountIn * (BPS - feeBps);
        return rout * effective / (rin * BPS + effective);
    }
}
