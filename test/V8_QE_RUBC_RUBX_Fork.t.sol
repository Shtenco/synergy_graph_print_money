// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20V8QE {
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
}

interface IVmV8QE {
    function envString(string calldata name) external returns (string memory);
    function createSelectFork(string calldata urlOrAlias, uint256 blockNumber) external returns (uint256 forkId);
    function prank(address msgSender) external;
}

interface IAggregatorV3V8QE {
    function decimals() external view returns (uint8);
    function latestRoundData() external view returns (
        uint80 roundId,
        int256 answer,
        uint256 startedAt,
        uint256 updatedAt,
        uint80 answeredInRound
    );
}

interface IUniV3FactoryV8QE {
    function getPool(address tokenA, address tokenB, uint24 fee) external view returns (address pool);
}

interface IUniV3PoolV8QE {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function swap(address recipient, bool zeroForOne, int256 amountSpecified, uint160 sqrtPriceLimitX96, bytes calldata data)
        external returns (int256 amount0, int256 amount1);
}

interface IUniV3QuoterV8QE {
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

contract V8MintableMonetaryToken {
    string public name;
    string public symbol;
    uint8 public constant decimals = 18;
    uint256 public totalSupply;
    address public immutable owner;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    constructor(string memory n, string memory s) {
        name = n;
        symbol = s;
        owner = msg.sender;
    }

    function mint(address to, uint256 amount) external {
        require(msg.sender == owner, "owner");
        totalSupply += amount;
        balanceOf[to] += amount;
    }

    function burn(uint256 amount) external {
        require(balanceOf[msg.sender] >= amount, "balance");
        balanceOf[msg.sender] -= amount;
        totalSupply -= amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 a = allowance[from][msg.sender];
        require(a >= amount, "allowance");
        if (a != type(uint256).max) allowance[from][msg.sender] = a - amount;
        _transfer(from, to, amount);
        return true;
    }

    function _transfer(address from, address to, uint256 amount) internal {
        require(balanceOf[from] >= amount, "balance");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
    }
}

/// @notice Small protocol-owned CPMM used only as the fork representation of a
///         RUBC/* or RUBX/* edge. All reserves remain protocol assets.
contract V8OwnedCPMM {
    address public immutable token0;
    address public immutable token1;
    address public immutable owner;
    uint256 public constant FEE_BPS = 30;
    uint256 private constant BPS = 10_000;

    constructor(address a, address b) {
        token0 = a;
        token1 = b;
        owner = msg.sender;
    }

    function reserves() public view returns (uint256 r0, uint256 r1) {
        r0 = IERC20V8QE(token0).balanceOf(address(this));
        r1 = IERC20V8QE(token1).balanceOf(address(this));
    }

    function seed(uint256 amount0, uint256 amount1) external {
        require(msg.sender == owner, "owner");
        _safeTransferFrom(token0, msg.sender, address(this), amount0);
        _safeTransferFrom(token1, msg.sender, address(this), amount1);
    }

    function quote(address tokenIn, uint256 amountIn) external view returns (uint256 amountOut) {
        (uint256 r0, uint256 r1) = reserves();
        if (tokenIn == token0) return _quote(r0, r1, amountIn);
        if (tokenIn == token1) return _quote(r1, r0, amountIn);
        revert("token");
    }

    function swapExactIn(address tokenIn, uint256 amountIn, address to) external returns (uint256 amountOut) {
        (uint256 r0, uint256 r1) = reserves();
        address tokenOut;
        uint256 rin;
        uint256 rout;
        if (tokenIn == token0) {
            tokenOut = token1;
            rin = r0;
            rout = r1;
        } else if (tokenIn == token1) {
            tokenOut = token0;
            rin = r1;
            rout = r0;
        } else {
            revert("token");
        }
        amountOut = _quote(rin, rout, amountIn);
        require(amountOut > 0 && amountOut < rout, "zero/out");
        _safeTransferFrom(tokenIn, msg.sender, address(this), amountIn);
        _safeTransfer(tokenOut, to, amountOut);
    }

    function drain(address to) external {
        require(msg.sender == owner, "owner");
        uint256 a = IERC20V8QE(token0).balanceOf(address(this));
        uint256 b = IERC20V8QE(token1).balanceOf(address(this));
        if (a > 0) _safeTransfer(token0, to, a);
        if (b > 0) _safeTransfer(token1, to, b);
    }

    function _quote(uint256 reserveIn, uint256 reserveOut, uint256 amountIn) internal pure returns (uint256) {
        if (reserveIn == 0 || reserveOut == 0 || amountIn == 0) return 0;
        uint256 effective = amountIn * (BPS - FEE_BPS);
        return reserveOut * effective / (reserveIn * BPS + effective);
    }

    function _safeTransfer(address token, address to, uint256 amount) private {
        (bool ok, bytes memory ret) = token.call(abi.encodeWithSelector(IERC20V8QE.transfer.selector, to, amount));
        require(ok && (ret.length == 0 || abi.decode(ret, (bool))), "transfer");
    }

    function _safeTransferFrom(address token, address from, address to, uint256 amount) private {
        (bool ok, bytes memory ret) = token.call(abi.encodeWithSelector(IERC20V8QE.transferFrom.selector, from, to, amount));
        require(ok && (ret.length == 0 || abi.decode(ret, (bool))), "transferFrom");
    }
}

/// @notice Fork laboratory for the original thesis:
/// mint RUBC/RUBX -> heterogeneous QE BUY pulses -> a newly-positive graph
/// cycle -> external hard-value capture -> remove own liquidity -> burn all
/// temporary monetary supply. RUBC/RUBX marks never enter HardNAV.
contract V8QERubcRubxForkHarness {
    address public constant WETH = 0x4200000000000000000000000000000000000006;
    address public constant USDC = 0x833589fCD6EDb6E08f4c7C32D4f71b54bDa02913;
    address public constant ETH_USD_FEED = 0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70;
    address public constant UNI_V3_FACTORY = 0x33128a8fc17869897dce68ed026d694621f6fdfd;
    address public constant UNI_V3_QUOTER = 0x3d4e44eb1374240ce5f1b871ab261cd16335b76a;

    uint160 private constant MIN_SQRT_RATIO_PLUS_ONE = 4295128740;
    uint160 private constant MAX_SQRT_RATIO_MINUS_ONE = 1461446703485210103287273052203988822378723970341;
    uint256 private constant BPS = 10_000;

    V8MintableMonetaryToken public immutable rubc;
    V8MintableMonetaryToken public immutable rubx;
    V8OwnedCPMM public immutable rubcWeth;
    V8OwnedCPMM public immutable rubcUsdc;
    V8OwnedCPMM public immutable rubxWeth;
    V8OwnedCPMM public immutable rubxUsdc;

    uint256 public hardNavBeforeUsd6;
    uint256 public hardNavAfterUsd6;
    int256 public hardNavGainUsd6;
    int256 public baselineApparentProfitUsd6;
    int256 public postQeApparentProfitUsd6;
    int256 public externalHardGainUsd6;
    uint256 public executionGas;
    uint256 public executionGasUsd6;
    int256 public riskAdjustedGainUsd6;
    bool public strictCycleCreated;
    uint8 public selectedField; // 1 RUBC, 2 RUBX
    bool public selectedStartIsWeth;
    address public selectedExternalPool;
    uint24 public selectedExternalFee;
    uint256 public selectedStartAmount;
    uint256 public selectedForeignInput;
    uint256 public selectedExternalOutput;

    address private activeExternalPool;
    address private activeExternalTokenIn;

    constructor() {
        rubc = new V8MintableMonetaryToken("Research RUBC", "RUBC");
        rubx = new V8MintableMonetaryToken("Research RUBX", "RUBX");
        rubcWeth = new V8OwnedCPMM(address(rubc), WETH);
        rubcUsdc = new V8OwnedCPMM(address(rubc), USDC);
        rubxWeth = new V8OwnedCPMM(address(rubx), WETH);
        rubxUsdc = new V8OwnedCPMM(address(rubx), USDC);
    }

    struct Choice {
        bool found;
        uint8 field;
        bool startIsWeth;
        address externalPool;
        uint24 fee;
        uint256 startAmount;
        uint256 foreignInput;
        uint256 externalOutput;
        int256 baselineProfitUsd6;
        int256 postProfitUsd6;
        int256 hardGainUsd6;
    }

    function runFullExperiment() external {
        uint256 ethUsdE8 = _ethUsdE8();
        uint256 wethBal = IERC20V8QE(WETH).balanceOf(address(this));
        uint256 usdcBal = IERC20V8QE(USDC).balanceOf(address(this));
        require(wethBal > 0 && usdcBal > 0, "funding");

        uint256 commonUsd6 = _min(_wethUsd6(wethBal, ethUsdE8), usdcBal);
        uint256 perFieldUsd6 = commonUsd6 / 3;
        require(perFieldUsd6 >= 25e6, "POL too small");
        uint256 wethSeed = _usd6ToWeth(perFieldUsd6, ethUsdE8);
        uint256 usdcSeed = perFieldUsd6;
        uint256 monetarySeed = perFieldUsd6 * 1e12; // $1 reference, 18 decimals.

        _seedField(rubc, rubcWeth, rubcUsdc, monetarySeed, wethSeed, usdcSeed);
        _seedField(rubx, rubxWeth, rubxUsdc, monetarySeed, wethSeed, usdcSeed);

        hardNavBeforeUsd6 = _hardNavUsd6(ethUsdE8);

        // Two independent graph-potential fields. RUBC pulses the WETH node,
        // RUBX pulses the USDC node. A 5% q/R cap matches the V7.3 risk-capped
        // experiment and creates opposite settlement directions simultaneously.
        uint256 qeGasStart = gasleft();
        _pulseInternal(rubc, rubcWeth, monetarySeed * 5 / 100);
        _pulseInternal(rubx, rubxUsdc, monetarySeed * 5 / 100);
        uint256 qeGas = qeGasStart - gasleft();

        Choice memory c = _findCreatedCycle(perFieldUsd6, monetarySeed, wethSeed, usdcSeed, ethUsdE8);
        require(c.found, "no QE-created hard-positive cycle");
        strictCycleCreated = c.baselineProfitUsd6 <= 0 && c.postProfitUsd6 > 0;
        selectedField = c.field;
        selectedStartIsWeth = c.startIsWeth;
        selectedExternalPool = c.externalPool;
        selectedExternalFee = c.fee;
        selectedStartAmount = c.startAmount;
        selectedForeignInput = c.foreignInput;
        selectedExternalOutput = c.externalOutput;
        baselineApparentProfitUsd6 = c.baselineProfitUsd6;
        postQeApparentProfitUsd6 = c.postProfitUsd6;
        externalHardGainUsd6 = c.hardGainUsd6;

        uint256 execGasStart = gasleft();
        _executeChoice(c);
        _drainAndBurn();
        uint256 execGas = execGasStart - gasleft();
        executionGas = qeGas + execGas;

        hardNavAfterUsd6 = _hardNavUsd6(ethUsdE8);
        hardNavGainUsd6 = int256(hardNavAfterUsd6) - int256(hardNavBeforeUsd6);
        executionGasUsd6 = executionGas * block.basefee * ethUsdE8 / 1e20;
        // Same 35% competition reserve used by the existing V7.3/V7.4 work,
        // plus measured Base execution gas. Search/quoter gas is deliberately
        // excluded because route search is off-chain in a production engine.
        riskAdjustedGainUsd6 = hardNavGainUsd6 * 6500 / 10_000 - int256(executionGasUsd6);

        require(strictCycleCreated, "QE improved but did not create cycle");
        require(externalHardGainUsd6 > 0, "foreign leg not hard-positive");
        require(hardNavGainUsd6 > 0, "consolidated HardNAV did not increase");
    }

    /// @notice Falsification control: mint/QE/BUY without crossing a foreign LP
    ///         cannot increase consolidated HardNAV.
    function runQeOnlyControl() external {
        uint256 ethUsdE8 = _ethUsdE8();
        uint256 commonUsd6 = _min(_wethUsd6(IERC20V8QE(WETH).balanceOf(address(this)), ethUsdE8), IERC20V8QE(USDC).balanceOf(address(this)));
        uint256 perFieldUsd6 = commonUsd6 / 3;
        require(perFieldUsd6 >= 25e6, "POL too small");
        uint256 wethSeed = _usd6ToWeth(perFieldUsd6, ethUsdE8);
        uint256 usdcSeed = perFieldUsd6;
        uint256 monetarySeed = perFieldUsd6 * 1e12;
        _seedField(rubc, rubcWeth, rubcUsdc, monetarySeed, wethSeed, usdcSeed);
        _seedField(rubx, rubxWeth, rubxUsdc, monetarySeed, wethSeed, usdcSeed);
        hardNavBeforeUsd6 = _hardNavUsd6(ethUsdE8);
        _pulseInternal(rubc, rubcWeth, monetarySeed * 5 / 100);
        _pulseInternal(rubx, rubxUsdc, monetarySeed * 5 / 100);
        _drainAndBurn();
        hardNavAfterUsd6 = _hardNavUsd6(ethUsdE8);
        hardNavGainUsd6 = int256(hardNavAfterUsd6) - int256(hardNavBeforeUsd6);
        require(hardNavGainUsd6 >= -2 && hardNavGainUsd6 <= 2, "QE alone created fake HardNAV");
    }

    function _seedField(
        V8MintableMonetaryToken m,
        V8OwnedCPMM pWeth,
        V8OwnedCPMM pUsdc,
        uint256 monetarySeed,
        uint256 wethSeed,
        uint256 usdcSeed
    ) internal {
        m.mint(address(this), monetarySeed * 2);
        m.approve(address(pWeth), type(uint256).max);
        m.approve(address(pUsdc), type(uint256).max);
        IERC20V8QE(WETH).approve(address(pWeth), type(uint256).max);
        IERC20V8QE(USDC).approve(address(pUsdc), type(uint256).max);
        pWeth.seed(monetarySeed, wethSeed);
        pUsdc.seed(monetarySeed, usdcSeed);
    }

    function _pulseInternal(V8MintableMonetaryToken m, V8OwnedCPMM pool, uint256 q) internal {
        m.mint(address(this), q);
        m.approve(address(pool), type(uint256).max);
        pool.swapExactIn(address(m), q, address(this));
    }

    function _findCreatedCycle(
        uint256 perFieldUsd6,
        uint256 monetarySeed,
        uint256 wethSeed,
        uint256 usdcSeed,
        uint256 ethUsdE8
    ) internal returns (Choice memory best) {
        uint24[4] memory fees = [uint24(100), uint24(500), uint24(3000), uint24(10000)];
        uint16[6] memory sizeBps = [uint16(100), uint16(250), uint16(500), uint16(1000), uint16(1500), uint16(2000)];
        for (uint256 fi; fi < fees.length; ++fi) {
            address pool = IUniV3FactoryV8QE(UNI_V3_FACTORY).getPool(WETH, USDC, fees[fi]);
            if (pool == address(0) || pool.code.length == 0) continue;
            for (uint256 si; si < sizeBps.length; ++si) {
                uint256 usd6 = perFieldUsd6 * sizeBps[si] / BPS;
                if (usd6 == 0) continue;
                uint256 wethAmount = _usd6ToWeth(usd6, ethUsdE8);
                Choice memory a = _candidate(1, true, pool, fees[fi], wethAmount, monetarySeed, wethSeed, usdcSeed, ethUsdE8);
                best = _pick(best, a);
                Choice memory b = _candidate(2, false, pool, fees[fi], usd6, monetarySeed, wethSeed, usdcSeed, ethUsdE8);
                best = _pick(best, b);
            }
        }
    }

    function _candidate(
        uint8 field,
        bool startIsWeth,
        address extPool,
        uint24 fee,
        uint256 startAmount,
        uint256 monetarySeed,
        uint256 wethSeed,
        uint256 usdcSeed,
        uint256 ethUsdE8
    ) internal returns (Choice memory c) {
        c.field = field;
        c.startIsWeth = startIsWeth;
        c.externalPool = extPool;
        c.fee = fee;
        c.startAmount = startAmount;

        V8OwnedCPMM pWeth = field == 1 ? rubcWeth : rubxWeth;
        V8OwnedCPMM pUsdc = field == 1 ? rubcUsdc : rubxUsdc;
        address internalToken = field == 1 ? address(rubc) : address(rubx);

        uint256 postForeignInput;
        if (startIsWeth) {
            uint256 m = pWeth.quote(WETH, startAmount);
            postForeignInput = pUsdc.quote(internalToken, m);
        } else {
            uint256 m = pUsdc.quote(USDC, startAmount);
            postForeignInput = pWeth.quote(internalToken, m);
        }
        if (postForeignInput == 0) return c;

        uint256 extOut;
        try IUniV3QuoterV8QE(UNI_V3_QUOTER).quoteExactInputSingle(
            IUniV3QuoterV8QE.QuoteExactInputSingleParams({
                tokenIn: startIsWeth ? USDC : WETH,
                tokenOut: startIsWeth ? WETH : USDC,
                amountIn: postForeignInput,
                fee: fee,
                sqrtPriceLimitX96: 0
            })
        ) returns (uint256 amountOut, uint160, uint32, uint256) {
            extOut = amountOut;
        } catch {
            return c;
        }
        if (extOut == 0) return c;

        (uint256 baselineForeignInput, uint256 baselineExtOut) = _baselineRouteQuote(
            startIsWeth, extPool, fee, startAmount, monetarySeed, wethSeed, usdcSeed
        );
        if (baselineForeignInput == 0 || baselineExtOut == 0) return c;

        int256 postProfit;
        int256 baseProfit;
        int256 hardGain;
        if (startIsWeth) {
            postProfit = int256(_wethUsd6(extOut, ethUsdE8)) - int256(_wethUsd6(startAmount, ethUsdE8));
            baseProfit = int256(_wethUsd6(baselineExtOut, ethUsdE8)) - int256(_wethUsd6(startAmount, ethUsdE8));
            hardGain = int256(_wethUsd6(extOut, ethUsdE8)) - int256(postForeignInput);
        } else {
            postProfit = int256(extOut) - int256(startAmount);
            baseProfit = int256(baselineExtOut) - int256(startAmount);
            hardGain = int256(extOut) - int256(_wethUsd6(postForeignInput, ethUsdE8));
        }

        c.foreignInput = postForeignInput;
        c.externalOutput = extOut;
        c.baselineProfitUsd6 = baseProfit;
        c.postProfitUsd6 = postProfit;
        c.hardGainUsd6 = hardGain;
        c.found = postProfit > 0 && hardGain > 0;
    }

    function _baselineRouteQuote(
        bool startIsWeth,
        address,
        uint24 fee,
        uint256 startAmount,
        uint256 monetarySeed,
        uint256 wethSeed,
        uint256 usdcSeed
    ) internal returns (uint256 foreignInput, uint256 extOut) {
        if (startIsWeth) {
            uint256 m = _cpmmQuote(wethSeed, monetarySeed, startAmount);
            foreignInput = _cpmmQuote(monetarySeed, usdcSeed, m);
        } else {
            uint256 m = _cpmmQuote(usdcSeed, monetarySeed, startAmount);
            foreignInput = _cpmmQuote(monetarySeed, wethSeed, m);
        }
        if (foreignInput == 0) return (0, 0);
        try IUniV3QuoterV8QE(UNI_V3_QUOTER).quoteExactInputSingle(
            IUniV3QuoterV8QE.QuoteExactInputSingleParams({
                tokenIn: startIsWeth ? USDC : WETH,
                tokenOut: startIsWeth ? WETH : USDC,
                amountIn: foreignInput,
                fee: fee,
                sqrtPriceLimitX96: 0
            })
        ) returns (uint256 amountOut, uint160, uint32, uint256) {
            extOut = amountOut;
        } catch {
            extOut = 0;
        }
    }

    function _pick(Choice memory best, Choice memory c) internal pure returns (Choice memory) {
        if (!c.found) return best;
        bool strict = c.baselineProfitUsd6 <= 0 && c.postProfitUsd6 > 0;
        bool bestStrict = best.found && best.baselineProfitUsd6 <= 0 && best.postProfitUsd6 > 0;
        if (!best.found) return c;
        if (strict && !bestStrict) return c;
        if (strict == bestStrict && c.hardGainUsd6 > best.hardGainUsd6) return c;
        return best;
    }

    function _executeChoice(Choice memory c) internal {
        V8OwnedCPMM pWeth = c.field == 1 ? rubcWeth : rubxWeth;
        V8OwnedCPMM pUsdc = c.field == 1 ? rubcUsdc : rubxUsdc;
        address internalToken = c.field == 1 ? address(rubc) : address(rubx);
        IERC20V8QE(WETH).approve(address(pWeth), type(uint256).max);
        IERC20V8QE(USDC).approve(address(pUsdc), type(uint256).max);
        IERC20V8QE(internalToken).approve(address(pWeth), type(uint256).max);
        IERC20V8QE(internalToken).approve(address(pUsdc), type(uint256).max);

        uint256 foreignInput;
        if (c.startIsWeth) {
            uint256 m = pWeth.swapExactIn(WETH, c.startAmount, address(this));
            foreignInput = pUsdc.swapExactIn(internalToken, m, address(this));
            _swapExternal(c.externalPool, USDC, WETH, foreignInput);
        } else {
            uint256 m = pUsdc.swapExactIn(USDC, c.startAmount, address(this));
            foreignInput = pWeth.swapExactIn(internalToken, m, address(this));
            _swapExternal(c.externalPool, WETH, USDC, foreignInput);
        }
    }

    function _swapExternal(address pool, address tokenIn, address tokenOut, uint256 amountIn) internal returns (uint256 amountOut) {
        address t0 = IUniV3PoolV8QE(pool).token0();
        address t1 = IUniV3PoolV8QE(pool).token1();
        bool zeroForOne;
        if (tokenIn == t0 && tokenOut == t1) zeroForOne = true;
        else if (tokenIn == t1 && tokenOut == t0) zeroForOne = false;
        else revert("external pair");
        activeExternalPool = pool;
        activeExternalTokenIn = tokenIn;
        (int256 a0, int256 a1) = IUniV3PoolV8QE(pool).swap(
            address(this),
            zeroForOne,
            int256(amountIn),
            zeroForOne ? MIN_SQRT_RATIO_PLUS_ONE : MAX_SQRT_RATIO_MINUS_ONE,
            bytes("")
        );
        activeExternalPool = address(0);
        activeExternalTokenIn = address(0);
        int256 d = zeroForOne ? a1 : a0;
        require(d < 0, "no output");
        amountOut = uint256(-d);
    }

    function uniswapV3SwapCallback(int256 amount0Delta, int256 amount1Delta, bytes calldata) external {
        require(msg.sender == activeExternalPool && activeExternalPool != address(0), "callback");
        uint256 owed = amount0Delta > 0 ? uint256(amount0Delta) : uint256(amount1Delta);
        require(owed > 0, "owed");
        _safeTransfer(activeExternalTokenIn, msg.sender, owed);
    }

    function _drainAndBurn() internal {
        rubcWeth.drain(address(this));
        rubcUsdc.drain(address(this));
        rubxWeth.drain(address(this));
        rubxUsdc.drain(address(this));
        uint256 c = rubc.balanceOf(address(this));
        uint256 x = rubx.balanceOf(address(this));
        if (c > 0) rubc.burn(c);
        if (x > 0) rubx.burn(x);
        require(rubc.totalSupply() == 0 && rubx.totalSupply() == 0, "temporary supply remains");
    }

    function _hardNavUsd6(uint256 ethUsdE8) internal view returns (uint256) {
        uint256 weth = IERC20V8QE(WETH).balanceOf(address(this));
        uint256 usdc = IERC20V8QE(USDC).balanceOf(address(this));
        weth += IERC20V8QE(WETH).balanceOf(address(rubcWeth));
        weth += IERC20V8QE(WETH).balanceOf(address(rubxWeth));
        usdc += IERC20V8QE(USDC).balanceOf(address(rubcUsdc));
        usdc += IERC20V8QE(USDC).balanceOf(address(rubxUsdc));
        return usdc + _wethUsd6(weth, ethUsdE8);
    }

    function _ethUsdE8() internal view returns (uint256) {
        (, int256 answer,, uint256 updatedAt,) = IAggregatorV3V8QE(ETH_USD_FEED).latestRoundData();
        require(answer > 0 && updatedAt > 0, "oracle");
        uint8 d = IAggregatorV3V8QE(ETH_USD_FEED).decimals();
        uint256 p = uint256(answer);
        if (d == 8) return p;
        if (d < 8) return p * (10 ** (8 - d));
        return p / (10 ** (d - 8));
    }

    function _wethUsd6(uint256 amountWei, uint256 ethUsdE8) internal pure returns (uint256) {
        return amountWei * ethUsdE8 / 1e20;
    }

    function _usd6ToWeth(uint256 usd6, uint256 ethUsdE8) internal pure returns (uint256) {
        return usd6 * 1e20 / ethUsdE8;
    }

    function _cpmmQuote(uint256 reserveIn, uint256 reserveOut, uint256 amountIn) internal pure returns (uint256) {
        if (reserveIn == 0 || reserveOut == 0 || amountIn == 0) return 0;
        uint256 effective = amountIn * 9970;
        return reserveOut * effective / (reserveIn * 10_000 + effective);
    }

    function _safeTransfer(address token, address to, uint256 amount) internal {
        (bool ok, bytes memory ret) = token.call(abi.encodeWithSelector(IERC20V8QE.transfer.selector, to, amount));
        require(ok && (ret.length == 0 || abi.decode(ret, (bool))), "transfer");
    }

    function _min(uint256 a, uint256 b) internal pure returns (uint256) { return a < b ? a : b; }
}

contract V8QERubcRubxForkTest {
    IVmV8QE constant vm = IVmV8QE(address(uint160(uint256(keccak256("hevm cheat code")))));
    address constant BALANCER_V2_VAULT = 0xBA12222222228d8Ba445958a75a0704d566BF2C8;
    address constant WETH = 0x4200000000000000000000000000000000000006;
    address constant USDC = 0x833589fCD6EDb6E08f4c7C32D4f71b54bDa02913;
    uint256 constant PINNED_BLOCK = 51_148_993;

    function testQEAloneDoesNotPrintHardNAV() public {
        vm.createSelectFork(vm.envString("BASE_RPC_URL"), PINNED_BLOCK);
        V8QERubcRubxForkHarness h = new V8QERubcRubxForkHarness();
        _fundForkLaboratory(address(h));
        h.runQeOnlyControl();
        require(h.hardNavGainUsd6() >= -2 && h.hardNavGainUsd6() <= 2, "internal accounting leak");
    }

    function testRubcRubxQECreatesCycleAndCapturesForeignHardValue() public {
        vm.createSelectFork(vm.envString("BASE_RPC_URL"), PINNED_BLOCK);
        V8QERubcRubxForkHarness h = new V8QERubcRubxForkHarness();
        _fundForkLaboratory(address(h));
        h.runFullExperiment();
        require(h.strictCycleCreated(), "no new positive graph cycle");
        require(h.baselineApparentProfitUsd6() <= 0, "cycle was already positive before QE");
        require(h.postQeApparentProfitUsd6() > 0, "cycle not positive after QE");
        require(h.externalHardGainUsd6() > 0, "foreign LP did not transfer hard value");
        require(h.hardNavGainUsd6() > 0, "consolidated HardNAV did not rise");
    }

    function _fundForkLaboratory(address to) internal {
        uint256 vw = IERC20V8QE(WETH).balanceOf(BALANCER_V2_VAULT);
        uint256 vu = IERC20V8QE(USDC).balanceOf(BALANCER_V2_VAULT);
        require(vw >= 0.10 ether && vu >= 250e6, "insufficient pinned hard inventory");
        uint256 takeWeth = _min(vw / 3, 20 ether);
        uint256 takeUsdc = _min(vu / 3, 50_000e6);
        vm.prank(BALANCER_V2_VAULT);
        require(IERC20V8QE(WETH).transfer(to, takeWeth), "fund WETH");
        vm.prank(BALANCER_V2_VAULT);
        require(IERC20V8QE(USDC).transfer(to, takeUsdc), "fund USDC");
    }

    function _min(uint256 a, uint256 b) internal pure returns (uint256) { return a < b ? a : b; }
}
