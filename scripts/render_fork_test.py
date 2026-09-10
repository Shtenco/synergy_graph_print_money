from __future__ import annotations

import argparse, json
from pathlib import Path


def skip(root: Path, out: Path, reason: str) -> None:
    if out.exists():out.unlink()
    plan={"rendered":False,"reason":reason};(root/"v7_fork_plan.json").write_text(json.dumps(plan,indent=2),encoding="utf-8");print(json.dumps(plan))


def main() -> None:
    p=argparse.ArgumentParser();p.add_argument("--artifacts",default="artifacts");p.add_argument("--out",default="test/generated/V7Candidate.t.sol");args=p.parse_args()
    root=Path(args.artifacts);out=Path(args.out);best_path=root/"v7_best_quote.json";best=json.loads(best_path.read_text(encoding="utf-8")) if best_path.exists() else {}
    if not best:
        skip(root,out,"no QUOTE_VERIFIED Aerodrome V2 cycle");return
    eth_px=float(best.get("eth_price_usd_snapshot") or 0);gas_price=int(best.get("gas_price_wei_snapshot") or 0)
    if eth_px<=0 or gas_price<=0:
        skip(root,out,"missing live ETH/USD or gas-price snapshot; gas guard cannot be proven");return
    tokens=best["token_path"].split("|");stables=best["stable_flags"].split("|");factories=best["factory_addresses"].split("|");hops=int(best["hops"])
    if len(tokens)!=hops+1 or len(stables)!=hops or len(factories)!=hops or tokens[0].lower()!=tokens[-1].lower():raise SystemExit("invalid best quote route")
    route_lines=[]
    for i in range(hops):
        stable="true" if stables[i]=="1" else "false"
        route_lines.append(f"        routes[{i}] = IAeroRouter.Route({tokens[i]}, {tokens[i+1]}, {stable}, {factories[i]});")
    start=tokens[0];amount=int(best["amount_in_raw"]);decimals=int(best["start_token_decimals"]);scale=10**decimals;start_px_e8=round(float(best["start_token_price_usd"])*1e8);eth_px_e8=round(eth_px*1e8);mev_bps=max(0,round(float(best.get("mev_guard_bps") or 0)));block=int(best["block_number"])
    if start_px_e8<=0 or eth_px_e8<=0:
        skip(root,out,"invalid USD price snapshot");return
    code=f'''// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface VmV7 {{ function createSelectFork(string calldata,uint256) external returns(uint256); function envString(string calldata) external returns(string memory); }}
interface IERC20V7 {{ function balanceOf(address) external view returns(uint256); function approve(address,uint256) external returns(bool); function transfer(address,uint256) external returns(bool); }}
interface IFlashRecipientV7 {{ function receiveFlashLoan(IERC20V7[] memory,uint256[] memory,uint256[] memory,bytes memory) external; }}
interface IVaultV7 {{ function flashLoan(IFlashRecipientV7 recipient,IERC20V7[] memory tokens,uint256[] memory amounts,bytes memory userData) external; }}
interface IAeroRouter {{
    struct Route {{ address from; address to; bool stable; address factory; }}
    function swapExactTokensForTokens(uint256 amountIn,uint256 amountOutMin,Route[] calldata routes,address to,uint256 deadline) external returns(uint256[] memory amounts);
}}

contract V7GeneratedExecutor is IFlashRecipientV7 {{
    address constant VAULT=0xBA12222222228d8Ba445958a75a0704d566BF2C8;
    address constant ROUTER=0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43;
    address constant START={start};
    uint256 constant AMOUNT={amount};
    uint256 public lastProfitRaw; uint256 public lastFeeRaw; uint256 public lastGasUsed;
    function run() external {{
        IERC20V7[] memory ts=new IERC20V7[](1);ts[0]=IERC20V7(START);uint256[] memory amts=new uint256[](1);amts[0]=AMOUNT;
        uint256 g=gasleft();IVaultV7(VAULT).flashLoan(this,ts,amts,"");lastGasUsed=g-gasleft()+30000;
    }}
    function receiveFlashLoan(IERC20V7[] memory tokens,uint256[] memory amounts,uint256[] memory fees,bytes memory) external override {{
        require(msg.sender==VAULT,"vault");require(tokens.length==1&&address(tokens[0])==START,"token");uint256 repay=amounts[0]+fees[0];lastFeeRaw=fees[0];
        require(IERC20V7(START).approve(ROUTER,amounts[0]),"approve");IAeroRouter.Route[] memory routes=new IAeroRouter.Route[]({hops});
{chr(10).join(route_lines)}
        IAeroRouter(ROUTER).swapExactTokensForTokens(amounts[0],repay+1,routes,address(this),block.timestamp);
        uint256 bal=IERC20V7(START).balanceOf(address(this));require(bal>repay,"not profitable");require(IERC20V7(START).transfer(VAULT,repay),"repay");lastProfitRaw=IERC20V7(START).balanceOf(address(this));
    }}
}}

contract V7GeneratedForkTest {{
    VmV7 constant vm=VmV7(address(uint160(uint256(keccak256("hevm cheat code")))));
    address constant VAULT=0xBA12222222228d8Ba445958a75a0704d566BF2C8; address constant START={start};
    uint256 constant BLOCK_NUMBER={block}; uint256 constant AMOUNT={amount}; uint256 constant START_SCALE={scale};
    uint256 constant START_PRICE_E8={start_px_e8}; uint256 constant ETH_PRICE_E8={eth_px_e8}; uint256 constant GAS_PRICE_WEI={gas_price}; uint256 constant MEV_BPS={mev_bps};
    function testForkExecutable() public {{
        vm.createSelectFork(vm.envString("BASE_RPC_URL"),BLOCK_NUMBER);uint256 vb=IERC20V7(START).balanceOf(VAULT);require(vb>=AMOUNT,"vault liquidity");
        V7GeneratedExecutor ex=new V7GeneratedExecutor();ex.run();uint256 profit=ex.lastProfitRaw();require(profit>0,"zero profit");uint256 va=IERC20V7(START).balanceOf(VAULT);require(va>=vb,"flash not repaid");
        uint256 profitUsdE8=profit*START_PRICE_E8/START_SCALE;uint256 gasUsdE8=ex.lastGasUsed()*GAS_PRICE_WEI*ETH_PRICE_E8/1e18;uint256 mevUsdE8=AMOUNT*START_PRICE_E8/START_SCALE*MEV_BPS/10000;
        require(profitUsdE8>gasUsdE8+mevUsdE8,"fails gas+MEV guard");
    }}
}}
'''
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(code,encoding="utf-8");plan={"rendered":True,"candidate":best,"test_file":str(out)};(root/"v7_fork_plan.json").write_text(json.dumps(plan,indent=2),encoding="utf-8");print(json.dumps({"rendered":True,"test_file":str(out),"block":block,"hops":hops}))

if __name__=="__main__":main()
