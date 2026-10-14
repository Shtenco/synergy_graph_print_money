// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20V8GM {
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
}

interface IBalancerV2VaultV8GM {
    function flashLoan(address recipient, address[] calldata tokens, uint256[] calldata amounts, bytes calldata userData) external;
}

interface IAeroV2PoolV8GM {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function getAmountOut(uint256 amountIn, address tokenIn) external view returns (uint256);
    function swap(uint256 amount0Out, uint256 amount1Out, address to, bytes calldata data) external;
}

interface ICLPoolV8GM {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function swap(address recipient, bool zeroForOne, int256 amountSpecified, uint160 sqrtPriceLimitX96, bytes calldata data)
        external returns (int256 amount0, int256 amount1);
}

interface IFlashLoanRecipientV8GM {
    function receiveFlashLoan(address[] calldata tokens, uint256[] calldata amounts, uint256[] calldata feeAmounts, bytes calldata userData) external;
}

/// @title SYNERGY Graph Money V8
/// @notice Single-contract research executor for the original RUBC/RUBX thesis:
///         flash hard assets -> instantiate only the needed virtual protocol-owned
///         monetary edges -> QE/BUY pulses -> execute real foreign swaps -> collapse
///         the virtual graph -> repay every flash token in-kind -> retain only hard profit.
///
/// @dev RUBC and RUBX are deliberately INTERNAL accounting fields, not ERC-20s.
///      This removes thousands of unnecessary pool/token deployments and prevents
///      protocol-owned transfers from being mistaken for HardNAV profit.
///
///      This contract is research software. It is not audited for production funds.
contract V8SynergyGraphMoney is IFlashLoanRecipientV8GM {
    address public constant DEFAULT_BALANCER_V2_VAULT = 0xBA12222222228d8Ba445958a75a0704d566BF2C8;

    uint160 private constant MIN_SQRT_RATIO_PLUS_ONE = 4295128740;
    uint160 private constant MAX_SQRT_RATIO_MINUS_ONE =
        1461446703485210103287273052203988822378723970341;

    uint256 private constant BPS = 10_000;
    uint8 public constant FIELD_RUBC = 1;
    uint8 public constant FIELD_RUBX = 2;

    // Action kinds.
    uint8 public constant ACTION_QE_PULSE = 0;          // mint internal monetary units, swap monetary -> hard
    uint8 public constant ACTION_HARD_TO_MONETARY = 1; // free hard -> virtual edge -> monetary wallet
    uint8 public constant ACTION_MONETARY_TO_HARD = 2; // monetary wallet -> virtual edge -> free hard
    uint8 public constant ACTION_AERODROME_V2 = 3;      // real external swap
    uint8 public constant ACTION_CL = 4;                // real UniV3/Slipstream-compatible swap

    struct EdgeSeed {
        uint8 field;             // 1 RUBC, 2 RUBX
        address hardToken;       // must be one of the flash token denominations
        uint256 hardReserve;     // raw token units temporarily locked into this virtual edge
        uint256 monetaryReserve; // 18-decimal internal monetary units
        uint16 feeBps;           // virtual CPMM fee, e.g. 30 = 0.30%
    }

    struct Action {
        uint8 kind;
        uint16 edgeIndex; // used by virtual actions
        address pool;     // used by external actions
        address tokenIn;  // used by external actions
        address tokenOut; // used by external actions
        uint256 amountIn;
        uint256 minOut;
    }

    struct Packet {
        EdgeSeed[] edges;
        Action[] actions;
        uint256[] minProfitRaw; // per flash token after principal + fee, same ordering as flashTokens
    }

    struct RuntimeEdge {
        uint8 field;
        uint16 tokenIndex;
        uint16 feeBps;
        uint256 hardReserve;
        uint256 monetaryReserve;
    }

    address public immutable owner;
    address public immutable flashVault;
    bool private flashActive;

    // CL callback authorization.
    address private activeCLPool;
    address private activeCLTokenIn;
    uint256 private activeCLSpendable;

    error NotOwner();
    error NotVault();
    error ReentrantFlash();
    error BadFlashShape();
    error FlashTokensNotStrictlySorted();
    error BadPacket();
    error BadEdge(uint256 edgeIndex);
    error BadAction(uint256 actionIndex);
    error UnsupportedAction(uint8 kind);
    error TokenNotInFlashSet(address token);
    error LockedReserveOverflow(address token, uint256 locked, uint256 balance);
    error InsufficientFreeHard(address token, uint256 need, uint256 freeBalance);
    error InsufficientMonetary(uint8 field, uint256 need, uint256 have);
    error VirtualLiquidity(uint256 edgeIndex);
    error PoolTokenMismatch(uint256 actionIndex);
    error ZeroOutput(uint256 actionIndex);
    error Slippage(uint256 actionIndex, uint256 minOut, uint256 actualOut);
    error NotActivePool();
    error FlashNotRepayable(address token, uint256 need, uint256 have);
    error ProfitFloorNotMet(address token, uint256 floor, uint256 actual);
    error TransferFailed(address token);

    event PacketStarted(bytes32 indexed packetId, uint256 flashTokenCount, uint256 edgeCount, uint256 actionCount);
    event EdgeActivated(
        bytes32 indexed packetId,
        uint256 indexed edgeIndex,
        uint8 indexed field,
        address hardToken,
        uint256 hardReserve,
        uint256 monetaryReserve,
        uint16 feeBps
    );
    event QEPulse(
        bytes32 indexed packetId,
        uint256 indexed actionIndex,
        uint8 indexed field,
        address hardToken,
        uint256 monetaryMinted,
        uint256 hardReleased
    );
    event VirtualSwap(
        bytes32 indexed packetId,
        uint256 indexed actionIndex,
        uint8 indexed field,
        address hardToken,
        bool hardToMonetary,
        uint256 amountIn,
        uint256 amountOut
    );
    event ExternalSwap(
        bytes32 indexed packetId,
        uint256 indexed actionIndex,
        address indexed pool,
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 amountOut
    );
    event MonetaryCollapsed(bytes32 indexed packetId, uint256 rubcBurned, uint256 rubxBurned);
    event PacketSettled(bytes32 indexed packetId, address indexed token, uint256 principal, uint256 fee, uint256 profit);

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address vault_) {
        owner = msg.sender;
        flashVault = vault_ == address(0) ? DEFAULT_BALANCER_V2_VAULT : vault_;
    }

    /// @notice Starts one atomic graph-money packet.
    /// @dev The optimizer is expected to run off-chain. The contract is deliberately
    ///      a deterministic execution/risk gate, not an on-chain brute-force searcher.
    function executePacket(
        address[] calldata flashTokens,
        uint256[] calldata flashAmounts,
        EdgeSeed[] calldata edges,
        Action[] calldata actions,
        uint256[] calldata minProfitRaw
    ) external onlyOwner {
        if (flashActive) revert ReentrantFlash();
        if (
            flashTokens.length == 0 ||
            flashTokens.length != flashAmounts.length ||
            flashTokens.length != minProfitRaw.length ||
            actions.length == 0
        ) revert BadFlashShape();

        for (uint256 i; i < flashTokens.length; ++i) {
            if (flashTokens[i] == address(0) || flashAmounts[i] == 0) revert BadFlashShape();
            if (i > 0 && uint160(flashTokens[i - 1]) >= uint160(flashTokens[i])) {
                revert FlashTokensNotStrictlySorted();
            }
        }

        _validateSeedsAndActions(flashTokens, edges, actions);

        flashActive = true;
        IBalancerV2VaultV8GM(flashVault).flashLoan(
            address(this),
            flashTokens,
            flashAmounts,
            abi.encode(edges, actions, minProfitRaw)
        );
        flashActive = false;
    }

    function receiveFlashLoan(
        address[] calldata tokens,
        uint256[] calldata amounts,
        uint256[] calldata feeAmounts,
        bytes calldata userData
    ) external override {
        if (msg.sender != flashVault) revert NotVault();
        if (!flashActive) revert ReentrantFlash();
        if (tokens.length == 0 || tokens.length != amounts.length || tokens.length != feeAmounts.length) {
            revert BadFlashShape();
        }

        (EdgeSeed[] memory decodedEdges, Action[] memory decodedActions, uint256[] memory decodedMinProfitRaw) =
            abi.decode(userData, (EdgeSeed[], Action[], uint256[]));
        Packet memory packet = Packet({edges: decodedEdges, actions: decodedActions, minProfitRaw: decodedMinProfitRaw});
        if (packet.minProfitRaw.length != tokens.length || packet.actions.length == 0) revert BadPacket();

        bytes32 packetId = keccak256(abi.encode(block.number, address(this), tokens, amounts, packet.edges, packet.actions));
        emit PacketStarted(packetId, tokens.length, packet.edges.length, packet.actions.length);

        uint256[] memory preExisting = new uint256[](tokens.length);
        uint256[] memory locked = new uint256[](tokens.length);
        RuntimeEdge[] memory edges = new RuntimeEdge[](packet.edges.length);

        for (uint256 i; i < tokens.length; ++i) {
            uint256 bal = IERC20V8GM(tokens[i]).balanceOf(address(this));
            if (bal < amounts[i]) revert FlashNotRepayable(tokens[i], amounts[i], bal);
            preExisting[i] = bal - amounts[i];
        }

        // Activate only the sparse set of protocol-owned edges requested for this packet.
        for (uint256 e; e < packet.edges.length; ++e) {
            EdgeSeed memory seed = packet.edges[e];
            uint256 tokenIndex = _tokenIndex(tokens, seed.hardToken);
            if (seed.field != FIELD_RUBC && seed.field != FIELD_RUBX) revert BadEdge(e);
            if (seed.hardReserve == 0 || seed.monetaryReserve == 0 || seed.feeBps >= BPS) revert BadEdge(e);

            locked[tokenIndex] += seed.hardReserve;
            uint256 bal = IERC20V8GM(seed.hardToken).balanceOf(address(this));
            if (locked[tokenIndex] > bal) {
                revert LockedReserveOverflow(seed.hardToken, locked[tokenIndex], bal);
            }

            edges[e] = RuntimeEdge({
                field: seed.field,
                tokenIndex: uint16(tokenIndex),
                feeBps: seed.feeBps,
                hardReserve: seed.hardReserve,
                monetaryReserve: seed.monetaryReserve
            });

            emit EdgeActivated(
                packetId,
                e,
                seed.field,
                seed.hardToken,
                seed.hardReserve,
                seed.monetaryReserve,
                seed.feeBps
            );
        }

        uint256[3] memory monetaryWallet;
        uint256[3] memory monetaryMinted;
        uint256[3] memory monetarySeeded;
        for (uint256 e; e < edges.length; ++e) {
            monetarySeeded[edges[e].field] += edges[e].monetaryReserve;
        }

        for (uint256 a; a < packet.actions.length; ++a) {
            Action memory action = packet.actions[a];

            if (action.kind == ACTION_QE_PULSE) {
                if (action.edgeIndex >= edges.length || action.amountIn == 0) revert BadAction(a);
                RuntimeEdge memory edge = edges[action.edgeIndex];
                uint256 hardOut = _quoteMonetaryToHard(edge, action.amountIn);
                if (hardOut == 0 || hardOut >= edge.hardReserve) revert VirtualLiquidity(action.edgeIndex);

                monetaryMinted[edge.field] += action.amountIn;
                edge.monetaryReserve += action.amountIn;
                edge.hardReserve -= hardOut;
                locked[edge.tokenIndex] -= hardOut;
                edges[action.edgeIndex] = edge;

                if (action.minOut != 0 && hardOut < action.minOut) revert Slippage(a, action.minOut, hardOut);
                emit QEPulse(packetId, a, edge.field, tokens[edge.tokenIndex], action.amountIn, hardOut);
            } else if (action.kind == ACTION_HARD_TO_MONETARY) {
                if (action.edgeIndex >= edges.length || action.amountIn == 0) revert BadAction(a);
                RuntimeEdge memory edge = edges[action.edgeIndex];
                address hardToken = tokens[edge.tokenIndex];
                uint256 freeHard = _freeHard(hardToken, locked[edge.tokenIndex]);
                if (freeHard < action.amountIn) revert InsufficientFreeHard(hardToken, action.amountIn, freeHard);

                uint256 monetaryOut = _quoteHardToMonetary(edge, action.amountIn);
                if (monetaryOut == 0 || monetaryOut >= edge.monetaryReserve) revert VirtualLiquidity(action.edgeIndex);
                if (action.minOut != 0 && monetaryOut < action.minOut) revert Slippage(a, action.minOut, monetaryOut);

                edge.hardReserve += action.amountIn;
                edge.monetaryReserve -= monetaryOut;
                locked[edge.tokenIndex] += action.amountIn;
                monetaryWallet[edge.field] += monetaryOut;
                edges[action.edgeIndex] = edge;

                emit VirtualSwap(packetId, a, edge.field, hardToken, true, action.amountIn, monetaryOut);
            } else if (action.kind == ACTION_MONETARY_TO_HARD) {
                if (action.edgeIndex >= edges.length || action.amountIn == 0) revert BadAction(a);
                RuntimeEdge memory edge = edges[action.edgeIndex];
                uint256 haveMonetary = monetaryWallet[edge.field];
                if (haveMonetary < action.amountIn) {
                    revert InsufficientMonetary(edge.field, action.amountIn, haveMonetary);
                }

                uint256 hardOut = _quoteMonetaryToHard(edge, action.amountIn);
                if (hardOut == 0 || hardOut >= edge.hardReserve) revert VirtualLiquidity(action.edgeIndex);
                if (action.minOut != 0 && hardOut < action.minOut) revert Slippage(a, action.minOut, hardOut);

                monetaryWallet[edge.field] -= action.amountIn;
                edge.monetaryReserve += action.amountIn;
                edge.hardReserve -= hardOut;
                locked[edge.tokenIndex] -= hardOut;
                edges[action.edgeIndex] = edge;

                emit VirtualSwap(packetId, a, edge.field, tokens[edge.tokenIndex], false, action.amountIn, hardOut);
            } else if (action.kind == ACTION_AERODROME_V2) {
                uint256 out = _swapAeroV2(tokens, locked, action, a);
                if (out < action.minOut) revert Slippage(a, action.minOut, out);
                emit ExternalSwap(packetId, a, action.pool, action.tokenIn, action.tokenOut, action.amountIn, out);
            } else if (action.kind == ACTION_CL) {
                uint256 out = _swapCL(tokens, locked, action, a);
                if (out < action.minOut) revert Slippage(a, action.minOut, out);
                emit ExternalSwap(packetId, a, action.pool, action.tokenIn, action.tokenOut, action.amountIn, out);
            } else {
                revert UnsupportedAction(action.kind);
            }
        }

        // Collapse every protocol-owned virtual edge back into the same contract.
        // The raw hard-token balances never move during internal operations; only
        // foreign swaps changed them. All internal monetary units are now burned.
        uint256 rubcBurned = monetarySeeded[FIELD_RUBC] + monetaryMinted[FIELD_RUBC];
        uint256 rubxBurned = monetarySeeded[FIELD_RUBX] + monetaryMinted[FIELD_RUBX];
        emit MonetaryCollapsed(packetId, rubcBurned, rubxBurned);

        // Strict denomination closure: every flash token must be repayable in-kind.
        for (uint256 i; i < tokens.length; ++i) {
            uint256 have = IERC20V8GM(tokens[i]).balanceOf(address(this));
            uint256 need = preExisting[i] + amounts[i] + feeAmounts[i];
            if (have < need) revert FlashNotRepayable(tokens[i], need, have);

            uint256 profit = have - need;
            if (profit < packet.minProfitRaw[i]) {
                revert ProfitFloorNotMet(tokens[i], packet.minProfitRaw[i], profit);
            }

            _safeTransfer(tokens[i], flashVault, amounts[i] + feeAmounts[i]);
            emit PacketSettled(packetId, tokens[i], amounts[i], feeAmounts[i], profit);
        }
    }

    /// @notice Public pure quote helper used by the off-chain optimizer and tests.
    function quoteVirtual(
        uint256 reserveIn,
        uint256 reserveOut,
        uint256 amountIn,
        uint16 feeBps
    ) external pure returns (uint256) {
        return _cpmmQuote(reserveIn, reserveOut, amountIn, feeBps);
    }

    function sweep(address token, address to, uint256 amount) external onlyOwner {
        _safeTransfer(token, to, amount);
    }

    function _validateSeedsAndActions(
        address[] calldata flashTokens,
        EdgeSeed[] calldata edges,
        Action[] calldata actions
    ) internal pure {
        for (uint256 e; e < edges.length; ++e) {
            EdgeSeed calldata edge = edges[e];
            if (
                (edge.field != FIELD_RUBC && edge.field != FIELD_RUBX) ||
                edge.hardToken == address(0) ||
                edge.hardReserve == 0 ||
                edge.monetaryReserve == 0 ||
                edge.feeBps >= BPS
            ) revert BadEdge(e);
            _tokenIndexCalldata(flashTokens, edge.hardToken);
        }

        for (uint256 a; a < actions.length; ++a) {
            Action calldata action = actions[a];
            if (action.amountIn == 0) revert BadAction(a);

            if (
                action.kind == ACTION_QE_PULSE ||
                action.kind == ACTION_HARD_TO_MONETARY ||
                action.kind == ACTION_MONETARY_TO_HARD
            ) {
                if (action.edgeIndex >= edges.length) revert BadAction(a);
            } else if (action.kind == ACTION_AERODROME_V2 || action.kind == ACTION_CL) {
                if (
                    action.pool == address(0) ||
                    action.tokenIn == address(0) ||
                    action.tokenOut == address(0) ||
                    action.tokenIn == action.tokenOut
                ) revert BadAction(a);
                _tokenIndexCalldata(flashTokens, action.tokenIn);
                _tokenIndexCalldata(flashTokens, action.tokenOut);
            } else {
                revert UnsupportedAction(action.kind);
            }
        }
    }

    function _swapAeroV2(
        address[] calldata tokens,
        uint256[] memory locked,
        Action memory action,
        uint256 actionIndex
    ) internal returns (uint256 amountOut) {
        uint256 inIndex = _tokenIndex(tokens, action.tokenIn);
        _tokenIndex(tokens, action.tokenOut);
        uint256 freeHard = _freeHard(action.tokenIn, locked[inIndex]);
        if (freeHard < action.amountIn) {
            revert InsufficientFreeHard(action.tokenIn, action.amountIn, freeHard);
        }

        IAeroV2PoolV8GM pool = IAeroV2PoolV8GM(action.pool);
        address t0 = pool.token0();
        address t1 = pool.token1();
        bool zeroForOne;
        if (action.tokenIn == t0 && action.tokenOut == t1) zeroForOne = true;
        else if (action.tokenIn == t1 && action.tokenOut == t0) zeroForOne = false;
        else revert PoolTokenMismatch(actionIndex);

        amountOut = pool.getAmountOut(action.amountIn, action.tokenIn);
        if (amountOut == 0) revert ZeroOutput(actionIndex);
        _safeTransfer(action.tokenIn, action.pool, action.amountIn);
        if (zeroForOne) pool.swap(0, amountOut, address(this), bytes(""));
        else pool.swap(amountOut, 0, address(this), bytes(""));
    }

    function _swapCL(
        address[] calldata tokens,
        uint256[] memory locked,
        Action memory action,
        uint256 actionIndex
    ) internal returns (uint256 amountOut) {
        uint256 inIndex = _tokenIndex(tokens, action.tokenIn);
        _tokenIndex(tokens, action.tokenOut);
        uint256 freeHard = _freeHard(action.tokenIn, locked[inIndex]);
        if (freeHard < action.amountIn) {
            revert InsufficientFreeHard(action.tokenIn, action.amountIn, freeHard);
        }

        ICLPoolV8GM pool = ICLPoolV8GM(action.pool);
        address t0 = pool.token0();
        address t1 = pool.token1();
        bool zeroForOne;
        if (action.tokenIn == t0 && action.tokenOut == t1) zeroForOne = true;
        else if (action.tokenIn == t1 && action.tokenOut == t0) zeroForOne = false;
        else revert PoolTokenMismatch(actionIndex);

        activeCLPool = action.pool;
        activeCLTokenIn = action.tokenIn;
        activeCLSpendable = freeHard;

        (int256 amount0, int256 amount1) = pool.swap(
            address(this),
            zeroForOne,
            int256(action.amountIn),
            zeroForOne ? MIN_SQRT_RATIO_PLUS_ONE : MAX_SQRT_RATIO_MINUS_ONE,
            abi.encode(action.tokenIn)
        );

        activeCLPool = address(0);
        activeCLTokenIn = address(0);
        activeCLSpendable = 0;

        int256 outDelta = zeroForOne ? amount1 : amount0;
        if (outDelta >= 0) revert ZeroOutput(actionIndex);
        amountOut = uint256(-outDelta);
    }

    function uniswapV3SwapCallback(int256 amount0Delta, int256 amount1Delta, bytes calldata) external {
        if (msg.sender != activeCLPool || activeCLPool == address(0)) revert NotActivePool();

        uint256 owed;
        if (amount0Delta > 0) owed = uint256(amount0Delta);
        else if (amount1Delta > 0) owed = uint256(amount1Delta);
        else revert NotActivePool();

        if (owed > activeCLSpendable) {
            revert InsufficientFreeHard(activeCLTokenIn, owed, activeCLSpendable);
        }
        activeCLSpendable -= owed;
        _safeTransfer(activeCLTokenIn, msg.sender, owed);
    }

    // Slipstream uses the same callback signature under a different selector on some generations.
    function aerodromeSlipstreamSwapCallback(int256 amount0Delta, int256 amount1Delta, bytes calldata data) external {
        data;
        if (msg.sender != activeCLPool || activeCLPool == address(0)) revert NotActivePool();

        uint256 owed;
        if (amount0Delta > 0) owed = uint256(amount0Delta);
        else if (amount1Delta > 0) owed = uint256(amount1Delta);
        else revert NotActivePool();

        if (owed > activeCLSpendable) {
            revert InsufficientFreeHard(activeCLTokenIn, owed, activeCLSpendable);
        }
        activeCLSpendable -= owed;
        _safeTransfer(activeCLTokenIn, msg.sender, owed);
    }

    function _quoteHardToMonetary(RuntimeEdge memory edge, uint256 hardIn) internal pure returns (uint256) {
        return _cpmmQuote(edge.hardReserve, edge.monetaryReserve, hardIn, edge.feeBps);
    }

    function _quoteMonetaryToHard(RuntimeEdge memory edge, uint256 monetaryIn) internal pure returns (uint256) {
        return _cpmmQuote(edge.monetaryReserve, edge.hardReserve, monetaryIn, edge.feeBps);
    }

    function _cpmmQuote(
        uint256 reserveIn,
        uint256 reserveOut,
        uint256 amountIn,
        uint16 feeBps
    ) internal pure returns (uint256) {
        if (reserveIn == 0 || reserveOut == 0 || amountIn == 0 || feeBps >= BPS) return 0;
        uint256 effective = amountIn * (BPS - feeBps);
        return reserveOut * effective / (reserveIn * BPS + effective);
    }

    function _freeHard(address token, uint256 lockedAmount) internal view returns (uint256) {
        uint256 bal = IERC20V8GM(token).balanceOf(address(this));
        if (lockedAmount > bal) revert LockedReserveOverflow(token, lockedAmount, bal);
        return bal - lockedAmount;
    }

    function _tokenIndex(address[] calldata tokens, address token) internal pure returns (uint256 index) {
        for (uint256 i; i < tokens.length; ++i) {
            if (tokens[i] == token) return i;
        }
        revert TokenNotInFlashSet(token);
    }

    function _tokenIndexCalldata(address[] calldata tokens, address token) internal pure returns (uint256 index) {
        for (uint256 i; i < tokens.length; ++i) {
            if (tokens[i] == token) return i;
        }
        revert TokenNotInFlashSet(token);
    }

    function _safeTransfer(address token, address to, uint256 amount) internal {
        (bool ok, bytes memory ret) = token.call(abi.encodeWithSelector(IERC20V8GM.transfer.selector, to, amount));
        if (!ok || (ret.length != 0 && !abi.decode(ret, (bool)))) revert TransferFailed(token);
    }
}
