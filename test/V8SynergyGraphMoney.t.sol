// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "../contracts/V8SynergyGraphMoney.sol";

contract MockERC20V8GM {
    string public name;
    string public symbol;
    uint8 public constant decimals = 18;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;

    constructor(string memory n, string memory s) {
        name = n;
        symbol = s;
    }

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        totalSupply += amount;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

contract MockFlashVaultV8GM {
    function flashLoan(
        address recipient,
        address[] calldata tokens,
        uint256[] calldata amounts,
        bytes calldata userData
    ) external {
        require(tokens.length == amounts.length, "shape");
        uint256[] memory beforeBal = new uint256[](tokens.length);
        uint256[] memory fees = new uint256[](tokens.length);

        for (uint256 i; i < tokens.length; ++i) {
            beforeBal[i] = MockERC20V8GM(tokens[i]).balanceOf(address(this));
            require(MockERC20V8GM(tokens[i]).transfer(recipient, amounts[i]), "loan transfer");
        }

        IFlashLoanRecipientV8GM(recipient).receiveFlashLoan(tokens, amounts, fees, userData);

        for (uint256 i; i < tokens.length; ++i) {
            require(MockERC20V8GM(tokens[i]).balanceOf(address(this)) >= beforeBal[i], "not repaid");
        }
    }
}

/// @notice Intentionally simple foreign pool used to test packet accounting.
///         token0->token1 and token1->token0 can have different fixed rates.
contract MockAeroPoolV8GM {
    address public immutable token0;
    address public immutable token1;
    uint256 public immutable rate01Num;
    uint256 public immutable rate01Den;
    uint256 public immutable rate10Num;
    uint256 public immutable rate10Den;

    constructor(
        address t0,
        address t1,
        uint256 r01n,
        uint256 r01d,
        uint256 r10n,
        uint256 r10d
    ) {
        token0 = t0;
        token1 = t1;
        rate01Num = r01n;
        rate01Den = r01d;
        rate10Num = r10n;
        rate10Den = r10d;
    }

    function getAmountOut(uint256 amountIn, address tokenIn) external view returns (uint256) {
        if (tokenIn == token0) return amountIn * rate01Num / rate01Den;
        if (tokenIn == token1) return amountIn * rate10Num / rate10Den;
        revert("token");
    }

    function swap(uint256 amount0Out, uint256 amount1Out, address to, bytes calldata) external {
        require(amount0Out == 0 || amount1Out == 0, "one side");
        if (amount0Out > 0) require(MockERC20V8GM(token0).transfer(to, amount0Out), "t0");
        if (amount1Out > 0) require(MockERC20V8GM(token1).transfer(to, amount1Out), "t1");
    }
}

contract V8SynergyGraphMoneyTest {
    uint256 private constant E18 = 1e18;
    uint256 private constant BPS = 10_000;

    function testSingleContractFlashSparseGraphQEAndStrictClosure() external {
        MockERC20V8GM a = new MockERC20V8GM("Hard A", "HA");
        MockERC20V8GM b = new MockERC20V8GM("Hard B", "HB");
        MockFlashVaultV8GM vault = new MockFlashVaultV8GM();
        V8SynergyGraphMoney engine = new V8SynergyGraphMoney(address(vault));

        // Two real foreign venues. Pool 1 values B 1% above A, pool 2 closes
        // denomination at 1:1. The external 1% spread is the only hard-value source.
        MockAeroPoolV8GM p1 = new MockAeroPoolV8GM(address(a), address(b), 100, 100, 101, 100);
        MockAeroPoolV8GM p2 = new MockAeroPoolV8GM(address(a), address(b), 100, 100, 100, 100);

        a.mint(address(vault), 10_000 * E18);
        b.mint(address(vault), 10_000 * E18);
        a.mint(address(p1), 10_000 * E18);
        b.mint(address(p1), 10_000 * E18);
        a.mint(address(p2), 10_000 * E18);
        b.mint(address(p2), 10_000 * E18);

        address[] memory flashTokens = new address[](2);
        uint256[] memory flashAmounts = new uint256[](2);
        uint256[] memory minProfit = new uint256[](2);

        // The production contract requires deterministic strictly-sorted denominations.
        if (uint160(address(a)) < uint160(address(b))) {
            flashTokens[0] = address(a);
            flashTokens[1] = address(b);
        } else {
            flashTokens[0] = address(b);
            flashTokens[1] = address(a);
        }
        flashAmounts[0] = 1_000 * E18;
        flashAmounts[1] = 1_000 * E18;

        V8SynergyGraphMoney.EdgeSeed[] memory edges = new V8SynergyGraphMoney.EdgeSeed[](2);
        edges[0] = V8SynergyGraphMoney.EdgeSeed({
            field: engine.FIELD_RUBC(),
            hardToken: address(a),
            hardReserve: 400 * E18,
            monetaryReserve: 400 * E18,
            feeBps: 30
        });
        edges[1] = V8SynergyGraphMoney.EdgeSeed({
            field: engine.FIELD_RUBC(),
            hardToken: address(b),
            hardReserve: 400 * E18,
            monetaryReserve: 400 * E18,
            feeBps: 30
        });

        // Before QE, A -> RUBC -> B -> external B/A is not a profitable graph cycle.
        uint256 baselineM = _q(400 * E18, 400 * E18, 50 * E18, 30);
        uint256 baselineB = _q(400 * E18, 400 * E18, baselineM, 30);
        uint256 baselineA = baselineB * 101 / 100;
        require(baselineA <= 50 * E18, "baseline already positive");

        // QE pulse on A/RUBC: internal mint -> buy hard A -> change node potential.
        uint256 pulse = 400 * E18;
        uint256 pulseHardA = _q(400 * E18, 400 * E18, pulse, 30);
        uint256 postPulseHardReserveA = 400 * E18 - pulseHardA;
        uint256 postPulseMonetaryReserveA = 400 * E18 + pulse;

        uint256 routeAIn = 50 * E18;
        uint256 routeM = _q(postPulseHardReserveA, postPulseMonetaryReserveA, routeAIn, 30);
        uint256 routeB = _q(400 * E18, 400 * E18, routeM, 30);
        uint256 routeAOut = routeB * 101 / 100;
        require(routeAOut > routeAIn, "QE did not create positive graph route");

        V8SynergyGraphMoney.Action[] memory actions = new V8SynergyGraphMoney.Action[](5);
        actions[0] = V8SynergyGraphMoney.Action({
            kind: engine.ACTION_QE_PULSE(), edgeIndex: 0, pool: address(0), tokenIn: address(0), tokenOut: address(0), amountIn: pulse, minOut: 0
        });
        actions[1] = V8SynergyGraphMoney.Action({
            kind: engine.ACTION_HARD_TO_MONETARY(), edgeIndex: 0, pool: address(0), tokenIn: address(0), tokenOut: address(0), amountIn: routeAIn, minOut: routeM
        });
        actions[2] = V8SynergyGraphMoney.Action({
            kind: engine.ACTION_MONETARY_TO_HARD(), edgeIndex: 1, pool: address(0), tokenIn: address(0), tokenOut: address(0), amountIn: routeM, minOut: routeB
        });
        actions[3] = V8SynergyGraphMoney.Action({
            kind: engine.ACTION_AERODROME_V2(), edgeIndex: 0, pool: address(p1), tokenIn: address(b), tokenOut: address(a), amountIn: routeB, minOut: routeAOut
        });
        // Denomination-closure leg: restore every B borrowed from flash. Any A
        // left after this step is real external hard profit.
        actions[4] = V8SynergyGraphMoney.Action({
            kind: engine.ACTION_AERODROME_V2(), edgeIndex: 0, pool: address(p2), tokenIn: address(a), tokenOut: address(b), amountIn: routeB, minOut: routeB
        });

        uint256 expectedProfitA = routeAOut - routeB;
        if (flashTokens[0] == address(a)) minProfit[0] = expectedProfitA;
        else minProfit[1] = expectedProfitA;

        engine.executePacket(flashTokens, flashAmounts, edges, actions, minProfit);

        require(a.balanceOf(address(engine)) == expectedProfitA, "wrong hard profit A");
        require(b.balanceOf(address(engine)) == 0, "B not denomination-closed");
        require(expectedProfitA > 0, "no external hard profit");
    }

    function testQEAloneCannotCreateHardProfit() external {
        MockERC20V8GM a = new MockERC20V8GM("Hard A", "HA");
        MockFlashVaultV8GM vault = new MockFlashVaultV8GM();
        V8SynergyGraphMoney engine = new V8SynergyGraphMoney(address(vault));
        a.mint(address(vault), 10_000 * E18);

        address[] memory tokens = new address[](1);
        tokens[0] = address(a);
        uint256[] memory amounts = new uint256[](1);
        amounts[0] = 1_000 * E18;
        uint256[] memory minProfit = new uint256[](1);

        V8SynergyGraphMoney.EdgeSeed[] memory edges = new V8SynergyGraphMoney.EdgeSeed[](1);
        edges[0] = V8SynergyGraphMoney.EdgeSeed({
            field: engine.FIELD_RUBX(),
            hardToken: address(a),
            hardReserve: 500 * E18,
            monetaryReserve: 500 * E18,
            feeBps: 30
        });

        V8SynergyGraphMoney.Action[] memory actions = new V8SynergyGraphMoney.Action[](1);
        actions[0] = V8SynergyGraphMoney.Action({
            kind: engine.ACTION_QE_PULSE(), edgeIndex: 0, pool: address(0), tokenIn: address(0), tokenOut: address(0), amountIn: 100 * E18, minOut: 0
        });

        engine.executePacket(tokens, amounts, edges, actions, minProfit);
        require(a.balanceOf(address(engine)) == 0, "QE manufactured hard NAV");
    }

    function _q(uint256 reserveIn, uint256 reserveOut, uint256 amountIn, uint16 feeBps)
        private pure returns (uint256)
    {
        uint256 effective = amountIn * (BPS - feeBps);
        return reserveOut * effective / (reserveIn * BPS + effective);
    }
}
