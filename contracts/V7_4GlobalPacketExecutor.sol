// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20V74 {
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
}

interface IBalancerV2VaultV74 {
    function flashLoan(address recipient, address[] calldata tokens, uint256[] calldata amounts, bytes calldata userData) external;
}

interface IAeroV2PoolV74 {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function getAmountOut(uint256 amountIn, address tokenIn) external view returns (uint256);
    function swap(uint256 amount0Out, uint256 amount1Out, address to, bytes calldata data) external;
}

interface ICLPoolV74 {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function swap(address recipient, bool zeroForOne, int256 amountSpecified, uint160 sqrtPriceLimitX96, bytes calldata data)
        external returns (int256 amount0, int256 amount1);
}

interface IFlashLoanRecipientV74 {
    function receiveFlashLoan(address[] calldata tokens, uint256[] calldata amounts, uint256[] calldata feeAmounts, bytes calldata userData) external;
}

/// @notice Research/fork executor for a packet of token-closed foreign cycles.
/// @dev Protocol-owned LP movements and RUBC/RUBX marks are never booked as profit.
///      Every cycle starts and ends in the same borrowed hard token; Balancer is
///      repaid token-by-token. Not audited for production use.
contract V7_4GlobalPacketExecutor is IFlashLoanRecipientV74 {
    address public constant BALANCER_V2_VAULT = 0xBA12222222228d8Ba445958a75a0704d566BF2C8;
    uint160 private constant MIN_SQRT_RATIO_PLUS_ONE = 4295128740;
    uint160 private constant MAX_SQRT_RATIO_MINUS_ONE = 1461446703485210103287273052203988822378723970341;

    // kind 0 = Aerodrome V2; kind 1 = Uniswap V3 / Aerodrome Slipstream CL.
    struct Step { address pool; address tokenIn; address tokenOut; uint8 kind; }
    struct Cycle { address startToken; uint256 amountIn; Step[] steps; }

    address public immutable owner;
    address private activeCLPool;
    address private activeCLTokenIn;
    bool private flashActive;

    error NotOwner(); error NotVault(); error NestedFlash(); error BadFlashShape();
    error FlashTokensNotStrictlySorted(); error EmptyPacket(); error BadCycle(uint256 cycleIndex);
    error BadStep(uint256 cycleIndex,uint256 stepIndex); error UnsupportedKind(uint8 kind);
    error PoolTokenMismatch(uint256 cycleIndex,uint256 stepIndex); error ZeroOutput(uint256 cycleIndex,uint256 stepIndex);
    error NotActivePool(); error FlashNotRepayable(address token,uint256 need,uint256 have);
    error ProfitFloorNotMet(address token,uint256 floor,uint256 actual);
    error InsufficientCycleInventory(address token,uint256 need,uint256 have); error TransferFailed(address token);

    event CycleExecuted(uint256 indexed cycleIndex,address indexed startToken,uint256 amountIn,uint256 amountOut);
    event PacketSettled(address indexed token,uint256 principal,uint256 fee,uint256 profit);

    modifier onlyOwner(){ if(msg.sender!=owner) revert NotOwner(); _; }
    constructor(){ owner=msg.sender; }

    function startPacket(address[] calldata flashTokens,uint256[] calldata flashAmounts,Cycle[] calldata cycles,uint256[] calldata minProfitRaw) external onlyOwner {
        if(flashActive) revert NestedFlash();
        if(cycles.length==0) revert EmptyPacket();
        if(flashTokens.length==0 || flashTokens.length!=flashAmounts.length || flashTokens.length!=minProfitRaw.length) revert BadFlashShape();
        for(uint256 i;i<flashTokens.length;++i){
            if(flashTokens[i]==address(0) || flashAmounts[i]==0) revert BadFlashShape();
            if(i>0 && uint160(flashTokens[i-1])>=uint160(flashTokens[i])) revert FlashTokensNotStrictlySorted();
        }
        for(uint256 c;c<cycles.length;++c) _validateCycle(cycles[c],c,flashTokens);
        flashActive=true;
        IBalancerV2VaultV74(BALANCER_V2_VAULT).flashLoan(address(this),flashTokens,flashAmounts,abi.encode(cycles,minProfitRaw));
        flashActive=false;
    }

    function receiveFlashLoan(address[] calldata tokens,uint256[] calldata amounts,uint256[] calldata feeAmounts,bytes calldata userData) external override {
        if(msg.sender!=BALANCER_V2_VAULT) revert NotVault();
        if(!flashActive) revert NestedFlash();
        if(tokens.length==0 || tokens.length!=amounts.length || tokens.length!=feeAmounts.length) revert BadFlashShape();
        (Cycle[] memory cycles,uint256[] memory minProfitRaw)=abi.decode(userData,(Cycle[],uint256[]));
        if(minProfitRaw.length!=tokens.length) revert BadFlashShape();

        uint256[] memory preExisting=new uint256[](tokens.length);
        for(uint256 i;i<tokens.length;++i){
            uint256 bal=IERC20V74(tokens[i]).balanceOf(address(this));
            if(bal<amounts[i]) revert FlashNotRepayable(tokens[i],amounts[i],bal);
            preExisting[i]=bal-amounts[i];
        }

        for(uint256 c;c<cycles.length;++c){
            Cycle memory cycle=cycles[c];
            uint256 have=IERC20V74(cycle.startToken).balanceOf(address(this));
            if(have<cycle.amountIn) revert InsufficientCycleInventory(cycle.startToken,cycle.amountIn,have);
            uint256 out=_executeCycle(cycle,c);
            emit CycleExecuted(c,cycle.startToken,cycle.amountIn,out);
        }

        // Core V7.4 invariant: settle each ERC-20 independently; never net a
        // deficit in token A against a USD-valued surplus in token B.
        for(uint256 i;i<tokens.length;++i){
            uint256 have=IERC20V74(tokens[i]).balanceOf(address(this));
            uint256 baseNeed=preExisting[i]+amounts[i]+feeAmounts[i];
            if(have<baseNeed) revert FlashNotRepayable(tokens[i],baseNeed,have);
            uint256 actualProfit=have-baseNeed;
            if(actualProfit<minProfitRaw[i]) revert ProfitFloorNotMet(tokens[i],minProfitRaw[i],actualProfit);
            _safeTransfer(tokens[i],BALANCER_V2_VAULT,amounts[i]+feeAmounts[i]);
            emit PacketSettled(tokens[i],amounts[i],feeAmounts[i],actualProfit);
        }
    }

    function _validateCycle(Cycle calldata cycle,uint256 cycleIndex,address[] calldata flashTokens) internal pure {
        if(cycle.startToken==address(0) || cycle.amountIn==0 || cycle.steps.length<2) revert BadCycle(cycleIndex);
        if(cycle.steps[0].tokenIn!=cycle.startToken || cycle.steps[cycle.steps.length-1].tokenOut!=cycle.startToken) revert BadCycle(cycleIndex);
        bool borrowed;
        for(uint256 i;i<flashTokens.length;++i) if(flashTokens[i]==cycle.startToken) borrowed=true;
        if(!borrowed) revert BadCycle(cycleIndex);
        for(uint256 s;s<cycle.steps.length;++s){
            Step calldata step=cycle.steps[s];
            if(step.pool==address(0) || step.tokenIn==address(0) || step.tokenOut==address(0)) revert BadStep(cycleIndex,s);
            if(s+1<cycle.steps.length && step.tokenOut!=cycle.steps[s+1].tokenIn) revert BadStep(cycleIndex,s);
            if(step.kind>1) revert UnsupportedKind(step.kind);
        }
    }

    function _executeCycle(Cycle memory cycle,uint256 cycleIndex) internal returns(uint256 amount){
        amount=cycle.amountIn;
        for(uint256 s;s<cycle.steps.length;++s){
            Step memory step=cycle.steps[s];
            if(step.kind==0) amount=_swapAeroV2(step,amount,cycleIndex,s);
            else if(step.kind==1) amount=_swapCL(step,amount,cycleIndex,s);
            else revert UnsupportedKind(step.kind);
        }
    }

    function _swapAeroV2(Step memory step,uint256 amountIn,uint256 cycleIndex,uint256 stepIndex) internal returns(uint256 amountOut){
        IAeroV2PoolV74 pool=IAeroV2PoolV74(step.pool); address t0=pool.token0(); address t1=pool.token1(); bool zeroForOne;
        if(step.tokenIn==t0 && step.tokenOut==t1) zeroForOne=true;
        else if(step.tokenIn==t1 && step.tokenOut==t0) zeroForOne=false;
        else revert PoolTokenMismatch(cycleIndex,stepIndex);
        amountOut=pool.getAmountOut(amountIn,step.tokenIn); if(amountOut==0) revert ZeroOutput(cycleIndex,stepIndex);
        _safeTransfer(step.tokenIn,step.pool,amountIn);
        if(zeroForOne) pool.swap(0,amountOut,address(this),bytes("")); else pool.swap(amountOut,0,address(this),bytes(""));
    }

    function _swapCL(Step memory step,uint256 amountIn,uint256 cycleIndex,uint256 stepIndex) internal returns(uint256 amountOut){
        ICLPoolV74 pool=ICLPoolV74(step.pool); address t0=pool.token0(); address t1=pool.token1(); bool zeroForOne;
        if(step.tokenIn==t0 && step.tokenOut==t1) zeroForOne=true;
        else if(step.tokenIn==t1 && step.tokenOut==t0) zeroForOne=false;
        else revert PoolTokenMismatch(cycleIndex,stepIndex);
        activeCLPool=step.pool; activeCLTokenIn=step.tokenIn;
        (int256 a0,int256 a1)=pool.swap(address(this),zeroForOne,int256(amountIn),zeroForOne?MIN_SQRT_RATIO_PLUS_ONE:MAX_SQRT_RATIO_MINUS_ONE,abi.encode(step.tokenIn));
        activeCLPool=address(0); activeCLTokenIn=address(0);
        int256 outDelta=zeroForOne?a1:a0; if(outDelta>=0) revert ZeroOutput(cycleIndex,stepIndex); amountOut=uint256(-outDelta);
    }

    function uniswapV3SwapCallback(int256 amount0Delta,int256 amount1Delta,bytes calldata) external {
        if(msg.sender!=activeCLPool || activeCLPool==address(0)) revert NotActivePool();
        uint256 owed=amount0Delta>0?uint256(amount0Delta):uint256(amount1Delta); if(owed==0) revert NotActivePool();
        _safeTransfer(activeCLTokenIn,msg.sender,owed);
    }

    function sweep(address token,address to,uint256 amount) external onlyOwner { _safeTransfer(token,to,amount); }
    function _safeTransfer(address token,address to,uint256 amount) internal {
        (bool ok,bytes memory ret)=token.call(abi.encodeWithSelector(IERC20V74.transfer.selector,to,amount));
        if(!ok || (ret.length!=0 && !abi.decode(ret,(bool)))) revert TransferFailed(token);
    }
}
