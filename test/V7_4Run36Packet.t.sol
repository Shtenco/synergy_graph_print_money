// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../contracts/V7_4GlobalPacketExecutor.sol";

interface VmV74 {
    function envString(string calldata name) external returns (string memory value);
    function createSelectFork(string calldata urlOrAlias,uint256 blockNumber) external returns (uint256 forkId);
}

contract V7_4Run36PacketTest {
    VmV74 constant vm=VmV74(address(uint160(uint256(keccak256("hevm cheat code")))));
    address constant WETH=0x4200000000000000000000000000000000000006;
    address constant USDC=0x833589fCD6EDb6E08f4c7C32D4f71b54bDa02913;
    address constant VIRTUAL=0x0b3e328455c4059eEb9E3f84B5543F74E24e7E1b;
    address constant USDT=0xfDE4C96c8593536E31F229EA8f37b2ADa2699bb2;
    address constant EURC=0x60a3E35cC302bFa44CB288Bc5a4F316Fdb1ADB42;
    uint256 constant PINNED_BLOCK=51_148_993;
    uint256 constant WETH_USD_E6=2_450_430_000;

    function testRun36StrictTokenClosedPacket() public {
        vm.createSelectFork(vm.envString("BASE_RPC_URL"),PINNED_BLOCK);
        V7_4GlobalPacketExecutor ex=new V7_4GlobalPacketExecutor();

        address[] memory flashTokens=new address[](2);
        uint256[] memory flashAmounts=new uint256[](2);
        uint256[] memory minProfit=new uint256[](2);
        flashTokens[0]=WETH; flashTokens[1]=USDC;
        flashAmounts[0]=635250969890810496; // ~$1,556.64
        flashAmounts[1]=613997129;          // ~$615.29
        minProfit[0]=1; minProfit[1]=1;

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
        ex.startPacket(flashTokens,flashAmounts,cycles,minProfit);
        uint256 wethProfit=IERC20V74(WETH).balanceOf(address(ex))-beforeWeth;
        uint256 usdcProfit=IERC20V74(USDC).balanceOf(address(ex))-beforeUsdc;
        uint256 deltaHardNavUsd6=usdcProfit+wethProfit*WETH_USD_E6/1e18;
        require(deltaHardNavUsd6>0,"V7.4 consolidated HardNAV did not increase");
    }
}
