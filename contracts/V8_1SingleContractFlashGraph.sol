// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20V81 {
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
}

interface IBalancerVaultV81 {
    function flashLoan(address recipient, address[] calldata tokens, uint256[] calldata amounts, bytes calldata userData) external;
}

interface IAeroV2V81 {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function getAmountOut(uint256 amountIn, address tokenIn) external view returns (uint256);
    function swap(uint256 amount0Out, uint256 amount1Out, address to, bytes calldata data) external;
}

interface ICLV81 {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function swap(address recipient, bool zeroForOne, int256 amountSpecified, uint160 sqrtPriceLimitX96, bytes calldata data)
        external returns (int256 amount0, int256 amount1);
}

interface IFlashRecipientV81 {
    function receiveFlashLoan(address[] calldata tokens, uint256[] calldata amounts, uint256[] calldata feeAmounts, bytes calldata userData) external;
}

/// @title SYNERGY V8.1 Single Contract Flash Graph
/// @notice One atomic contract for sparse internal RUBC/RUBX graph fields plus
///         real external swaps and strict in-kind flash settlement.
/// @dev Internal monetary fields have no oracle value and never enter HardNAV.
///      External routes may traverse non-flash transient tokens (VIRTUAL, USDT,
///      EURC, etc.). Only the actual borrowed ERC20s must settle principal+fee.
///      Research code; not audited for production funds.
contract V8_1SingleContractFlashGraph is IFlashRecipientV81 {
    address public constant BALANCER_VAULT = 0xBA12222222228d8Ba445958a75a0704d566BF2C8;
    uint160 private constant MIN_SQRT_RATIO_PLUS_ONE = 4295128740;
    uint160 private constant MAX_SQRT_RATIO_MINUS_ONE = 1461446703485210103287273052203988822378723970341;
    uint256 private constant BPS = 10_000;

    uint8 public constant RUBC = 1;
    uint8 public constant RUBX = 2;
    uint8 public constant QE_PULSE = 0;
    uint8 public constant HARD_TO_MONEY = 1;
    uint8 public constant MONEY_TO_HARD = 2;
    uint8 public constant AERO_V2 = 3;
    uint8 public constant CL = 4;

    struct EdgeSeed {
        uint8 field;
        address hardToken;
        uint256 hardReserve;
        uint256 moneyReserve;
        uint16 feeBps;
    }

    struct Action {
        uint8 kind;
        uint16 edgeIndex;
        address pool;
        address tokenIn;
        address tokenOut;
        uint256 amountIn;
        uint256 minOut;
    }

    struct Edge {
        uint8 field;
        uint16 flashIndex;
        uint16 feeBps;
        uint256 hardReserve;
        uint256 moneyReserve;
    }

    address public immutable owner;
    bool private flashActive;
    address private activePool;
    address private activeTokenIn;
    uint256 private activeSpendable;

    error NotOwner();
    error NotVault();
    error BadShape();
    error BadEdge(uint256 index);
    error BadAction(uint256 index);
    error TokenNotBorrowed(address token);
    error FlashTokensNotSorted();
    error LockedOverflow(address token, uint256 locked, uint256 balance);
    error InsufficientHard(address token, uint256 need, uint256 have);
    error InsufficientMoney(uint8 field, uint256 need, uint256 have);
    error PoolMismatch(uint256 actionIndex);
    error Slippage(uint256 actionIndex, uint256 minOut, uint256 actualOut);
    error Repayment(address token, uint256 need, uint256 have);
    error ProfitFloor(address token, uint256 floor, uint256 actual);
    error NotActivePool();
    error TransferFailed(address token);

    event EdgeActivated(uint256 indexed edgeIndex, uint8 indexed field, address indexed hardToken, uint256 hardReserve, uint256 moneyReserve);
    event QEPulse(uint256 indexed actionIndex, uint8 indexed field, address indexed hardToken, uint256 minted, uint256 hardReleased);
    event ExternalSwap(uint256 indexed actionIndex, address indexed pool, address tokenIn, address tokenOut, uint256 amountIn, uint256 amountOut);
    event Settled(address indexed token, uint256 principal, uint256 fee, uint256 hardProfit);

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function execute(
        address[] calldata flashTokens,
        uint256[] calldata flashAmounts,
        EdgeSeed[] calldata seeds,
        Action[] calldata actions,
        uint256[] calldata minProfitRaw
    ) external onlyOwner {
        if (flashActive) revert BadShape();
        if (flashTokens.length == 0 || flashTokens.length != flashAmounts.length || flashTokens.length != minProfitRaw.length || actions.length == 0) {
            revert BadShape();
        }
        for (uint256 i; i < flashTokens.length; ++i) {
            if (flashTokens[i] == address(0) || flashAmounts[i] == 0) revert BadShape();
            if (i > 0 && uint160(flashTokens[i - 1]) >= uint160(flashTokens[i])) revert FlashTokensNotSorted();
        }
        for (uint256 e; e < seeds.length; ++e) {
            EdgeSeed calldata s = seeds[e];
            if ((s.field != RUBC && s.field != RUBX) || s.hardReserve == 0 || s.moneyReserve == 0 || s.feeBps >= BPS) revert BadEdge(e);
            _flashIndexCalldata(flashTokens, s.hardToken);
        }
        for (uint256 a; a < actions.length; ++a) {
            Action calldata x = actions[a];
            if (x.amountIn == 0) revert BadAction(a);
            if (x.kind <= MONEY_TO_HARD) {
                if (x.edgeIndex >= seeds.length) revert BadAction(a);
            } else if (x.kind == AERO_V2 || x.kind == CL) {
                if (x.pool == address(0) || x.tokenIn == address(0) || x.tokenOut == address(0) || x.tokenIn == x.tokenOut) revert BadAction(a);
            } else revert BadAction(a);
        }

        flashActive = true;
        IBalancerVaultV81(BALANCER_VAULT).flashLoan(address(this), flashTokens, flashAmounts, abi.encode(seeds, actions, minProfitRaw));
        flashActive = false;
    }

    function receiveFlashLoan(
        address[] calldata tokens,
        uint256[] calldata amounts,
        uint256[] calldata feeAmounts,
        bytes calldata userData
    ) external override {
        if (msg.sender != BALANCER_VAULT) revert NotVault();
        if (!flashActive) revert BadShape();
        if (tokens.length == 0 || tokens.length != amounts.length || tokens.length != feeAmounts.length) revert BadShape();

        (EdgeSeed[] memory seeds, Action[] memory actions, uint256[] memory floors) = abi.decode(userData, (EdgeSeed[], Action[], uint256[]));
        if (floors.length != tokens.length) revert BadShape();

        uint256[] memory pre = new uint256[](tokens.length);
        uint256[] memory locked = new uint256[](tokens.length);
        Edge[] memory edges = new Edge[](seeds.length);
        uint256[3] memory wallet;

        for (uint256 i; i < tokens.length; ++i) {
            uint256 bal = IERC20V81(tokens[i]).balanceOf(address(this));
            if (bal < amounts[i]) revert Repayment(tokens[i], amounts[i], bal);
            pre[i] = bal - amounts[i];
        }

        for (uint256 e; e < seeds.length; ++e) {
            EdgeSeed memory s = seeds[e];
            uint256 fi = _flashIndex(tokens, s.hardToken);
            locked[fi] += s.hardReserve;
            uint256 bal = IERC20V81(s.hardToken).balanceOf(address(this));
            if (locked[fi] > bal) revert LockedOverflow(s.hardToken, locked[fi], bal);
            edges[e] = Edge(s.field, uint16(fi), s.feeBps, s.hardReserve, s.moneyReserve);
            emit EdgeActivated(e, s.field, s.hardToken, s.hardReserve, s.moneyReserve);
        }

        for (uint256 a; a < actions.length; ++a) {
            Action memory x = actions[a];
            if (x.kind == QE_PULSE) {
                Edge memory e = edges[x.edgeIndex];
                uint256 hardOut = _q(e.moneyReserve, e.hardReserve, x.amountIn, e.feeBps);
                if (hardOut == 0 || hardOut >= e.hardReserve) revert BadAction(a);
                e.moneyReserve += x.amountIn;
                e.hardReserve -= hardOut;
                locked[e.flashIndex] -= hardOut;
                edges[x.edgeIndex] = e;
                if (hardOut < x.minOut) revert Slippage(a, x.minOut, hardOut);
                emit QEPulse(a, e.field, tokens[e.flashIndex], x.amountIn, hardOut);
            } else if (x.kind == HARD_TO_MONEY) {
                Edge memory e = edges[x.edgeIndex];
                address hard = tokens[e.flashIndex];
                uint256 free = _freeBorrowed(hard, locked[e.flashIndex]);
                if (free < x.amountIn) revert InsufficientHard(hard, x.amountIn, free);
                uint256 out = _q(e.hardReserve, e.moneyReserve, x.amountIn, e.feeBps);
                if (out == 0 || out >= e.moneyReserve) revert BadAction(a);
                if (out < x.minOut) revert Slippage(a, x.minOut, out);
                e.hardReserve += x.amountIn;
                e.moneyReserve -= out;
                locked[e.flashIndex] += x.amountIn;
                wallet[e.field] += out;
                edges[x.edgeIndex] = e;
            } else if (x.kind == MONEY_TO_HARD) {
                Edge memory e = edges[x.edgeIndex];
                if (wallet[e.field] < x.amountIn) revert InsufficientMoney(e.field, x.amountIn, wallet[e.field]);
                uint256 out = _q(e.moneyReserve, e.hardReserve, x.amountIn, e.feeBps);
                if (out == 0 || out >= e.hardReserve) revert BadAction(a);
                if (out < x.minOut) revert Slippage(a, x.minOut, out);
                wallet[e.field] -= x.amountIn;
                e.moneyReserve += x.amountIn;
                e.hardReserve -= out;
                locked[e.flashIndex] -= out;
                edges[x.edgeIndex] = e;
            } else if (x.kind == AERO_V2) {
                uint256 out = _swapAero(tokens, locked, x, a);
                if (out < x.minOut) revert Slippage(a, x.minOut, out);
                emit ExternalSwap(a, x.pool, x.tokenIn, x.tokenOut, x.amountIn, out);
            } else if (x.kind == CL) {
                uint256 out = _swapCL(tokens, locked, x, a);
                if (out < x.minOut) revert Slippage(a, x.minOut, out);
                emit ExternalSwap(a, x.pool, x.tokenIn, x.tokenOut, x.amountIn, out);
            } else revert BadAction(a);
        }

        // Internal RUBC/RUBX fields collapse here. They are not external assets.
        // Only actual ERC20 balances are allowed to service the flash liability.
        for (uint256 i; i < tokens.length; ++i) {
            uint256 have = IERC20V81(tokens[i]).balanceOf(address(this));
            uint256 need = pre[i] + amounts[i] + feeAmounts[i];
            if (have < need) revert Repayment(tokens[i], need, have);
            uint256 profit = have - need;
            if (profit < floors[i]) revert ProfitFloor(tokens[i], floors[i], profit);
            _safeTransfer(tokens[i], BALANCER_VAULT, amounts[i] + feeAmounts[i]);
            emit Settled(tokens[i], amounts[i], feeAmounts[i], profit);
        }
    }

    function quoteVirtual(uint256 rin, uint256 rout, uint256 amountIn, uint16 feeBps) external pure returns (uint256) {
        return _q(rin, rout, amountIn, feeBps);
    }

    function sweep(address token, address to, uint256 amount) external onlyOwner {
        _safeTransfer(token, to, amount);
    }

    function _swapAero(address[] calldata flashTokens, uint256[] memory locked, Action memory x, uint256 ai) internal returns (uint256 out) {
        uint256 free = _freeAny(flashTokens, locked, x.tokenIn);
        if (free < x.amountIn) revert InsufficientHard(x.tokenIn, x.amountIn, free);
        IAeroV2V81 p = IAeroV2V81(x.pool);
        address t0 = p.token0();
        address t1 = p.token1();
        bool z;
        if (x.tokenIn == t0 && x.tokenOut == t1) z = true;
        else if (x.tokenIn == t1 && x.tokenOut == t0) z = false;
        else revert PoolMismatch(ai);
        out = p.getAmountOut(x.amountIn, x.tokenIn);
        if (out == 0) revert BadAction(ai);
        _safeTransfer(x.tokenIn, x.pool, x.amountIn);
        if (z) p.swap(0, out, address(this), bytes(""));
        else p.swap(out, 0, address(this), bytes(""));
    }

    function _swapCL(address[] calldata flashTokens, uint256[] memory locked, Action memory x, uint256 ai) internal returns (uint256 out) {
        uint256 free = _freeAny(flashTokens, locked, x.tokenIn);
        if (free < x.amountIn) revert InsufficientHard(x.tokenIn, x.amountIn, free);
        ICLV81 p = ICLV81(x.pool);
        address t0 = p.token0();
        address t1 = p.token1();
        bool z;
        if (x.tokenIn == t0 && x.tokenOut == t1) z = true;
        else if (x.tokenIn == t1 && x.tokenOut == t0) z = false;
        else revert PoolMismatch(ai);

        activePool = x.pool;
        activeTokenIn = x.tokenIn;
        activeSpendable = free;
        (int256 a0, int256 a1) = p.swap(address(this), z, int256(x.amountIn), z ? MIN_SQRT_RATIO_PLUS_ONE : MAX_SQRT_RATIO_MINUS_ONE, bytes(""));
        activePool = address(0);
        activeTokenIn = address(0);
        activeSpendable = 0;
        int256 od = z ? a1 : a0;
        if (od >= 0) revert BadAction(ai);
        out = uint256(-od);
    }

    function uniswapV3SwapCallback(int256 amount0Delta, int256 amount1Delta, bytes calldata) external {
        _clCallback(amount0Delta, amount1Delta);
    }

    function aerodromeSlipstreamSwapCallback(int256 amount0Delta, int256 amount1Delta, bytes calldata) external {
        _clCallback(amount0Delta, amount1Delta);
    }

    function _clCallback(int256 a0, int256 a1) internal {
        if (msg.sender != activePool || activePool == address(0)) revert NotActivePool();
        uint256 owed = a0 > 0 ? uint256(a0) : (a1 > 0 ? uint256(a1) : 0);
        if (owed == 0 || owed > activeSpendable) revert NotActivePool();
        activeSpendable -= owed;
        _safeTransfer(activeTokenIn, msg.sender, owed);
    }

    function _freeBorrowed(address token, uint256 lockedAmount) internal view returns (uint256) {
        uint256 bal = IERC20V81(token).balanceOf(address(this));
        if (lockedAmount > bal) revert LockedOverflow(token, lockedAmount, bal);
        return bal - lockedAmount;
    }

    function _freeAny(address[] calldata flashTokens, uint256[] memory locked, address token) internal view returns (uint256) {
        uint256 bal = IERC20V81(token).balanceOf(address(this));
        for (uint256 i; i < flashTokens.length; ++i) {
            if (flashTokens[i] == token) {
                if (locked[i] > bal) revert LockedOverflow(token, locked[i], bal);
                return bal - locked[i];
            }
        }
        return bal;
    }

    function _flashIndex(address[] calldata tokens, address token) internal pure returns (uint256) {
        for (uint256 i; i < tokens.length; ++i) if (tokens[i] == token) return i;
        revert TokenNotBorrowed(token);
    }

    function _flashIndexCalldata(address[] calldata tokens, address token) internal pure returns (uint256) {
        for (uint256 i; i < tokens.length; ++i) if (tokens[i] == token) return i;
        revert TokenNotBorrowed(token);
    }

    function _q(uint256 rin, uint256 rout, uint256 amountIn, uint16 feeBps) internal pure returns (uint256) {
        if (rin == 0 || rout == 0 || amountIn == 0 || feeBps >= BPS) return 0;
        uint256 effective = amountIn * (BPS - feeBps);
        return rout * effective / (rin * BPS + effective);
    }

    function _safeTransfer(address token, address to, uint256 amount) internal {
        (bool ok, bytes memory ret) = token.call(abi.encodeWithSelector(IERC20V81.transfer.selector, to, amount));
        if (!ok || (ret.length != 0 && !abi.decode(ret, (bool)))) revert TransferFailed(token);
    }
}
