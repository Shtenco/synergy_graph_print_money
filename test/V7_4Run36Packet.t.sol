// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../contracts/V7_4GlobalPacketExecutor.sol";

interface VmV74 {
    function envString(string calldata name) external returns (string memory value);
    function createSelectFork(string calldata urlOrAlias,uint256 blockNumber) external returns (uint256 forkId);
}

interface IAggregatorV3V74 {
    function decimals() external view returns (uint8);
    function latestRoundData() external view returns (
        uint80 roundId,
        int256 answer,
        uint256 startedAt,
        uint256 updatedAt,
        uint80 answeredInRound
    );
}

/// @notice Exact same-block proof for the strict token-closed packet discovered
///         from Base run #36.  This test deliberately does NOT rely on a USD
///         netting shortcut: Balancer repayment is enforced in-kind by the
///         executor before any HardNAV aggregation occurs here.
contract V7_4Run36PacketTest {
    VmV74 constant vm=VmV74(address(uint160(uint256(keccak256("hevm cheat code")))));

    address constant BALANCER_V2_VAULT=0xBA12222222228d8Ba445958a75a0704d566BF2C8;
    address constant WETH=0x4200000000000000000000000000000000000006;
    address constant USDC=0x833589fCD6EDb6E08f4c7C32D4f71b54bDa02913;
    address constant VIRTUAL=0x0b3e328455c4059eEb9E3f84B5543F74E24e7E1b;
    address constant USDT=0xfDE4C96c8593536E31F229EA8f37b2ADa2699bb2;
    address constant EURC=0x60a3E35cC302bFa44CB288Bc5a4F316Fdb1ADB42;

    // Chainlink Standard ETH/USD proxy on Base.  Reading the proxy on the
    // pinned fork keeps the USD conversion in the same chain state as swaps.
    address constant ETH_USD_FEED=0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70;

    uint256 constant PINNED_BLOCK=51_148_993;
    uint256 constant STARTING_PERSONAL_HARDNAV_USD6=100_000_000; // $100
    uint256 constant KEEP_AFTER_COMPETITION_BPS=6_500;           // 35% reserve
    uint256 constant BPS=10_000;
    uint256 constant FIXED_L1_DATA_AND_MISC_BUFFER_USD6=1_000_000; // extra $1

    function _ethUsdE8() internal view returns(uint256) {
        (,int256 answer,,uint256 updatedAt,)=IAggregatorV3V74(ETH_USD_FEED).latestRoundData();
        require(answer>0 && updatedAt>0,"bad ETH/USD oracle");
        uint8 d=IAggregatorV3V74(ETH_USD_FEED).decimals();
        uint256 p=uint256(answer);
        if(d==8) return p;
        if(d<8) return p*(10**(8-d));
        return p/(10**(d-8));
    }

    function _wethUsd6(uint256 amountWei,uint256 ethUsdE8) internal pure returns(uint256) {
        // amountWei / 1e18 * ethUsdE8 / 1e8 * 1e6
        return amountWei*ethUsdE8/1e20;
    }

    function testRun36StrictTokenClosedPacket() public {
        vm.createSelectFork(vm.envString("BASE_RPC_URL"),PINNED_BLOCK);
        V7_4GlobalPacketExecutor ex=new V7_4GlobalPacketExecutor();

        address[] memory flashTokens=new address[](2);
        uint256[] memory flashAmounts=new uint256[](2);
        uint256[] memory minProfit=new uint256[](2);
        // Strictly sorted by address, as required by the executor.
        flashTokens[0]=WETH; flashTokens[1]=USDC;
        flashAmounts[0]=635250969890810496; // ~0.635251 WETH ~= $1,556.64 in the run-36 model
        flashAmounts[1]=613997129;          // 613.997129 USDC
        minProfit[0]=1; minProfit[1]=1;

        // Prove that the selected in-kind principals actually exist in the
        // Balancer Vault at the same pinned state used by the swap packet.
        require(IERC20V74(WETH).balanceOf(BALANCER_V2_VAULT)>=flashAmounts[0],"insufficient Balancer WETH");
        require(IERC20V74(USDC).balanceOf(BALANCER_V2_VAULT)>=flashAmounts[1],"insufficient Balancer USDC");

        V7_4GlobalPacketExecutor.Cycle[] memory cycles=new V7_4GlobalPacketExecutor.Cycle[](6);

        V7_4GlobalPacketExecutor.Step[] memory s0=new V7_4GlobalPacketExecutor.Step[](2);
        s0[0]=V7_4GlobalPacketExecutor.Step(0x9c087eb773291e50cf6c6a90ef0f4500e349b903,WETH,VIRTUAL,1);
        s0[1]=V7_4GlobalPacketExecutor.Step(0x21594b992f68495dd28d605834b58889d0a727c7,VIRTUAL,WETH,0);
        cycles[0]=V7_4GlobalPacketExecutor.Cycle(WETH,635250969890810496,s0);

        V7_4GlobalPacketExecutor.Step[] memory s1=new V7_4GlobalPacketExecutor.Step[](2);
        s1[0]=V7_4GlobalPacketExecutor.Step(0x3f0296bf652e19bca772ec3df08b32732f93014a,WETH,VIRTUAL,1);
        s1[1]=V7_4GlobalPacketExecutor.Step(0x21594b992f68495dd28d605834b58889d0a727c7,VIRTUAL,WETH,0);
        cycles[1]=V7_4GlobalPacketExecutor.Cycle(WETH,447286908083245184,s1);

        V7_4GlobalPacketExecutor.Step[] memory s2=new V7_4GlobalPacketExecutor.Step[](2);
        s2[0]=V7_4GlobalPacketExecutor.Step(0x9520e1a3bfd86da6c1e9e5ee4b9c2f11c413358f,WETH,VIRTUAL,1);
        s2[1]=V7_4GlobalPacketExecutor.Step(0x21594b992f68495dd28d605834b58889d0a727c7,VIRTUAL,WETH,0);
        cycles[2]=V7_4GlobalPacketExecutor.Cycle(WETH,207866817297214880,s2);

        V7_4GlobalPacketExecutor.Step[] memory s3=new V7_4GlobalPacketExecutor.Step[](2);
        s3[0]=V7_4GlobalPacketExecutor.Step(0xc200f21efe67c7f41b81a854c26f9cda80593065,WETH,VIRTUAL,1);
        s3[1]=V7_4GlobalPacketExecutor.Step(0x21594b992f68495dd28d605834b58889d0a727c7,VIRTUAL,WETH,0);
        cycles[3]=V7_4GlobalPacketExecutor.Cycle(WETH,211504149809868640,s3);

        V7_4GlobalPacketExecutor.Step[] memory s4=new V7_4GlobalPacketExecutor.Step[](3);
        s4[0]=V7_4GlobalPacketExecutor.Step(0xa41bc0affba7fd420d186b84899d7ab2ac57fcd1,USDC,USDT,1);
        s4[1]=V7_4GlobalPacketExecutor.Step(0x9785ef59e2b499fb741674ecf6faf912df7b3c1b,USDT,WETH,1);
        s4[2]=V7_4GlobalPacketExecutor.Step(0xd0b53d9277642d899df5c87a3966a349a798f224,WETH,USDC,1);
        cycles[4]=V7_4GlobalPacketExecutor.Cycle(USDC,613997129,s4);

        V7_4GlobalPacketExecutor.Step[] memory s5=new V7_4GlobalPacketExecutor.Step[](3);
        s5[0]=V7_4GlobalPacketExecutor.Step(0xe846373c1a92b167b4e9cd5d8e4d6b1db9e90ec7,USDC,EURC,1);
        s5[1]=V7_4GlobalPacketExecutor.Step(0xaa5fe7dcc07dcb8b7afcd1b93874e7cb1e0ab50b,EURC,WETH,1);
        s5[2]=V7_4GlobalPacketExecutor.Step(0xd0b53d9277642d899df5c87a3966a349a798f224,WETH,USDC,1);
        cycles[5]=V7_4GlobalPacketExecutor.Cycle(USDC,468677356,s5);

        uint256 beforeWeth=IERC20V74(WETH).balanceOf(address(ex));
        uint256 beforeUsdc=IERC20V74(USDC).balanceOf(address(ex));
        uint256 gasBefore=gasleft();

        // startPacket cannot return unless Balancer has already received every
        // flash principal plus the actual feeAmounts[] supplied by the Vault.
        ex.startPacket(flashTokens,flashAmounts,cycles,minProfit);

        uint256 executionGasUsed=gasBefore-gasleft();
        uint256 afterWeth=IERC20V74(WETH).balanceOf(address(ex));
        uint256 afterUsdc=IERC20V74(USDC).balanceOf(address(ex));
        require(afterWeth>beforeWeth,"no post-repayment WETH profit");
        require(afterUsdc>beforeUsdc,"no post-repayment USDC profit");

        uint256 wethProfit=afterWeth-beforeWeth;
        uint256 usdcProfit=afterUsdc-beforeUsdc;
        uint256 ethUsdE8=_ethUsdE8();

        // USDC is the HardNAV numeraire here (1 raw USDC = 1 USD6 unit).
        uint256 rawProfitUsd6=usdcProfit+_wethUsd6(wethProfit,ethUsdE8);
        uint256 riskAdjustedProfitUsd6=rawProfitUsd6*KEEP_AFTER_COMPETITION_BPS/BPS;
        uint256 executionGasUsd6=executionGasUsed*block.basefee*ethUsdE8/1e20;
        uint256 externalCostReserveUsd6=executionGasUsd6+FIXED_L1_DATA_AND_MISC_BUFFER_USD6;

        require(riskAdjustedProfitUsd6>externalCostReserveUsd6,"profit does not survive risk+gas reserve");
        uint256 netHardNavGainUsd6=riskAdjustedProfitUsd6-externalCostReserveUsd6;
        uint256 hardNavAfterUsd6=STARTING_PERSONAL_HARDNAV_USD6+netHardNavGainUsd6;

        require(hardNavAfterUsd6>STARTING_PERSONAL_HARDNAV_USD6,"V7.4 consolidated HardNAV did not increase");
    }
}
