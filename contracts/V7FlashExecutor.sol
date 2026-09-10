// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20V7 { function balanceOf(address) external view returns (uint256); function transfer(address,uint256) external returns (bool); }
interface IBalancerV2VaultV7 { function flashLoan(address recipient,address[] calldata tokens,uint256[] calldata amounts,bytes calldata userData) external; }
interface IFlashLoanRecipientV7 { function receiveFlashLoan(address[] calldata tokens,uint256[] calldata amounts,uint256[] calldata feeAmounts,bytes calldata userData) external; }

/// @notice Research/fork-validation scaffold. Not audited or production-ready.
contract V7FlashExecutor is IFlashLoanRecipientV7 {
    address public constant BALANCER_V2_VAULT=0xBA12222222228d8Ba445958a75a0704d566BF2C8;
    address public immutable owner; mapping(address=>bool) public allowedTarget;
    struct Call { address target; uint256 value; bytes data; }
    error NotOwner(); error NotVault(); error TargetNotAllowed(address target); error ExternalCallFailed(uint256 index,bytes reason); error FlashNotRepayable(address token,uint256 need,uint256 have); error TransferFailed(address token);
    modifier onlyOwner(){if(msg.sender!=owner)revert NotOwner();_;}
    constructor(){owner=msg.sender;} receive() external payable {}
    function setAllowedTarget(address target,bool allowed) external onlyOwner {allowedTarget[target]=allowed;}
    function start(address[] calldata tokens,uint256[] calldata amounts,Call[] calldata calls) external onlyOwner {IBalancerV2VaultV7(BALANCER_V2_VAULT).flashLoan(address(this),tokens,amounts,abi.encode(calls));}
    function receiveFlashLoan(address[] calldata tokens,uint256[] calldata amounts,uint256[] calldata feeAmounts,bytes calldata userData) external override {
        if(msg.sender!=BALANCER_V2_VAULT)revert NotVault(); Call[] memory calls=abi.decode(userData,(Call[]));
        for(uint256 i=0;i<calls.length;++i){Call memory c=calls[i];if(!allowedTarget[c.target])revert TargetNotAllowed(c.target);(bool ok,bytes memory ret)=c.target.call{value:c.value}(c.data);if(!ok)revert ExternalCallFailed(i,ret);}
        for(uint256 i=0;i<tokens.length;++i){uint256 need=amounts[i]+feeAmounts[i];uint256 have=IERC20V7(tokens[i]).balanceOf(address(this));if(have<need)revert FlashNotRepayable(tokens[i],need,have);if(!IERC20V7(tokens[i]).transfer(BALANCER_V2_VAULT,need))revert TransferFailed(tokens[i]);}
    }
    function sweep(address token,address to,uint256 amount) external onlyOwner {if(!IERC20V7(token).transfer(to,amount))revert TransferFailed(token);}
}
