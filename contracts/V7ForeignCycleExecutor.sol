// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20V7Cycle { function balanceOf(address account) external view returns (uint256); function transfer(address to,uint256 value) external returns (bool); }
interface IBalancerV2VaultCycle { function flashLoan(address recipient,address[] calldata tokens,uint256[] calldata amounts,bytes calldata userData) external; }
interface IAeroV2PoolCycle { function token0() external view returns(address); function token1() external view returns(address); function getAmountOut(uint256 amountIn,address tokenIn) external view returns(uint256); function swap(uint256 amount0Out,uint256 amount1Out,address to,bytes calldata data) external; }
interface ICLPoolCycle { function token0() external view returns(address); function token1() external view returns(address); function swap(address recipient,bool zeroForOne,int256 amountSpecified,uint160 sqrtPriceLimitX96,bytes calldata data) external returns(int256 amount0,int256 amount1); }
interface IFlashLoanRecipientCycle { function receiveFlashLoan(address[] calldata tokens,uint256[] calldata amounts,uint256[] calldata feeAmounts,bytes calldata userData) external; }

/// @notice Research/fork executor for closed foreign cycles on Base. Not audited for production.
contract V7ForeignCycleExecutor is IFlashLoanRecipientCycle {
    address public constant BALANCER_V2_VAULT=0xBA12222222228d8Ba445958a75a0704d566BF2C8;
    uint160 private constant MIN_SQRT_RATIO_PLUS_ONE=4295128740;
    uint160 private constant MAX_SQRT_RATIO_MINUS_ONE=1461446703485210103287273052203988822378723970341;
    struct Step { address pool; address tokenIn; address tokenOut; uint8 kind; }
    address public immutable owner; address private activeCLPool; address private activeCLTokenIn; bool private flashActive;
    error NotOwner(); error NotVault(); error NotActivePool(); error NestedFlash(); error BadFlashShape(); error EmptyRoute(); error BadRoute(uint256 index); error UnsupportedKind(uint8 kind); error PoolTokenMismatch(uint256 index); error ZeroOutput(uint256 index); error FlashNotRepayable(uint256 need,uint256 have); error ProfitFloorNotMet(uint256 floor,uint256 actual); error TransferFailed(address token);
    modifier onlyOwner(){if(msg.sender!=owner)revert NotOwner();_;}
    constructor(){owner=msg.sender;}

    function startFlash(address token,uint256 amount,Step[] calldata steps,uint256 minProfitRaw) external onlyOwner {
        if(flashActive)revert NestedFlash(); if(steps.length==0)revert EmptyRoute();
        if(steps[0].tokenIn!=token||steps[steps.length-1].tokenOut!=token)revert BadRoute(0);
        for(uint256 i;i<steps.length;++i){if(steps[i].tokenIn==address(0)||steps[i].tokenOut==address(0)||steps[i].pool==address(0))revert BadRoute(i);if(i+1<steps.length&&steps[i].tokenOut!=steps[i+1].tokenIn)revert BadRoute(i);}
        address[] memory tokens=new address[](1); uint256[] memory amounts=new uint256[](1); tokens[0]=token; amounts[0]=amount; flashActive=true;
        IBalancerV2VaultCycle(BALANCER_V2_VAULT).flashLoan(address(this),tokens,amounts,abi.encode(steps,minProfitRaw)); flashActive=false;
    }

    function receiveFlashLoan(address[] calldata tokens,uint256[] calldata amounts,uint256[] calldata feeAmounts,bytes calldata userData) external override {
        if(msg.sender!=BALANCER_V2_VAULT)revert NotVault(); if(!flashActive)revert NestedFlash(); if(tokens.length!=1||amounts.length!=1||feeAmounts.length!=1)revert BadFlashShape();
        (Step[] memory steps,uint256 minProfitRaw)=abi.decode(userData,(Step[],uint256)); address flashToken=tokens[0]; uint256 principal=amounts[0]; uint256 fee=feeAmounts[0];
        uint256 callbackBalance=IERC20V7Cycle(flashToken).balanceOf(address(this)); if(callbackBalance<principal)revert FlashNotRepayable(principal,callbackBalance); uint256 preExisting=callbackBalance-principal;
        uint256 amount=principal; for(uint256 i;i<steps.length;++i){Step memory s=steps[i];if(s.kind==0)amount=_swapAeroV2(s,amount,i);else if(s.kind==1)amount=_swapCL(s,amount,i);else revert UnsupportedKind(s.kind);if(amount==0)revert ZeroOutput(i);}
        uint256 have=IERC20V7Cycle(flashToken).balanceOf(address(this)); uint256 repay=preExisting+principal+fee; if(have<repay)revert FlashNotRepayable(repay,have); uint256 actualProfit=have-repay; if(actualProfit<minProfitRaw)revert ProfitFloorNotMet(minProfitRaw,actualProfit); _safeTransfer(flashToken,BALANCER_V2_VAULT,principal+fee);
    }

    function _swapAeroV2(Step memory s,uint256 amountIn,uint256 index) internal returns(uint256 amountOut){IAeroV2PoolCycle pool=IAeroV2PoolCycle(s.pool);address t0=pool.token0();address t1=pool.token1();bool zeroForOne;if(s.tokenIn==t0&&s.tokenOut==t1)zeroForOne=true;else if(s.tokenIn==t1&&s.tokenOut==t0)zeroForOne=false;else revert PoolTokenMismatch(index);amountOut=pool.getAmountOut(amountIn,s.tokenIn);if(amountOut==0)revert ZeroOutput(index);_safeTransfer(s.tokenIn,s.pool,amountIn);if(zeroForOne)pool.swap(0,amountOut,address(this),bytes(""));else pool.swap(amountOut,0,address(this),bytes(""));}

    function _swapCL(Step memory s,uint256 amountIn,uint256 index) internal returns(uint256 amountOut){ICLPoolCycle pool=ICLPoolCycle(s.pool);address t0=pool.token0();address t1=pool.token1();bool zeroForOne;if(s.tokenIn==t0&&s.tokenOut==t1)zeroForOne=true;else if(s.tokenIn==t1&&s.tokenOut==t0)zeroForOne=false;else revert PoolTokenMismatch(index);activeCLPool=s.pool;activeCLTokenIn=s.tokenIn;(int256 a0,int256 a1)=pool.swap(address(this),zeroForOne,int256(amountIn),zeroForOne?MIN_SQRT_RATIO_PLUS_ONE:MAX_SQRT_RATIO_MINUS_ONE,abi.encode(s.tokenIn));activeCLPool=address(0);activeCLTokenIn=address(0);int256 outDelta=zeroForOne?a1:a0;if(outDelta>=0)revert ZeroOutput(index);amountOut=uint256(-outDelta);}

    function uniswapV3SwapCallback(int256 amount0Delta,int256 amount1Delta,bytes calldata) external {if(msg.sender!=activeCLPool||activeCLPool==address(0))revert NotActivePool();uint256 owed=amount0Delta>0?uint256(amount0Delta):uint256(amount1Delta);if(owed==0)revert NotActivePool();_safeTransfer(activeCLTokenIn,msg.sender,owed);}
    function sweep(address token,address to,uint256 amount) external onlyOwner {_safeTransfer(token,to,amount);}
    function _safeTransfer(address token,address to,uint256 amount) internal {(bool ok,bytes memory ret)=token.call(abi.encodeWithSelector(IERC20V7Cycle.transfer.selector,to,amount));if(!ok||(ret.length!=0&&!abi.decode(ret,(bool))))revert TransferFailed(token);}
}
