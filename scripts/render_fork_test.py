from __future__ import annotations

import argparse, json
from pathlib import Path


def skip(root: Path, out: Path, reason: str) -> None:
    if out.exists(): out.unlink()
    plan={"rendered":False,"reason":reason}
    (root/"v7_fork_plan.json").write_text(json.dumps(plan,indent=2),encoding="utf-8")
    print(json.dumps(plan))


def common_values(root: Path, out: Path, best: dict):
    eth_px=float(best.get("eth_price_usd_snapshot") or 0);gas_price=int(best.get("gas_price_wei_snapshot") or 0)
    if eth_px<=0 or gas_price<=0:
        skip(root,out,"missing live ETH/USD or gas-price snapshot; gas guard cannot be proven");return None
    start=best["start_token"];amount=int(best["amount_in_raw"]);decimals=int(best["start_token_decimals"]);scale=10**decimals
    start_px_e8=round(float(best["start_token_price_usd"])*1e8);eth_px_e8=round(eth_px*1e8);mev_bps=max(0,round(float(best.get("mev_guard_bps") or 0)));block=int(best["block_number"])
    if start_px_e8<=0 or eth_px_e8<=0:
        skip(root,out,"invalid USD price snapshot");return None
    return start,amount,scale,start_px_e8,eth_px_e8,gas_price,mev_bps,block


def header() -> str:
    return '''// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
interface VmV7 { function createSelectFork(string calldata,uint256) external returns(uint256); function envString(string calldata) external returns(string memory); }
interface IERC20V7 { function balanceOf(address) external view returns(uint256); function approve(address,uint256) external returns(bool); function transfer(address,uint256) external returns(bool); }
interface IFlashRecipientV7 { function receiveFlashLoan(IERC20V7[] memory,uint256[] memory,uint256[] memory,bytes memory) external; }
interface IVaultV7 { function flashLoan(IFlashRecipientV7 recipient,IERC20V7[] memory tokens,uint256[] memory amounts,bytes memory userData) external; }
'''


def footer(start:str,amount:int,scale:int,start_px_e8:int,eth_px_e8:int,gas_price:int,mev_bps:int,block:int)->str:
    return f'''contract V7GeneratedForkTest {{
    VmV7 constant vm=VmV7(address(uint160(uint256(keccak256("hevm cheat code")))));
    address constant VAULT=0xBA12222222228d8Ba445958a75a0704d566BF2C8; address constant START={start};
    uint256 constant BLOCK_NUMBER={block}; uint256 constant AMOUNT={amount}; uint256 constant START_SCALE={scale};
    uint256 constant START_PRICE_E8={start_px_e8}; uint256 constant ETH_PRICE_E8={eth_px_e8}; uint256 constant GAS_PRICE_WEI={gas_price}; uint256 constant MEV_BPS={mev_bps};
    function testForkExecutable() public {{
        vm.createSelectFork(vm.envString("BASE_RPC_URL"),BLOCK_NUMBER);
        uint256 vb=IERC20V7(START).balanceOf(VAULT); require(vb>=AMOUNT,"vault liquidity");
        V7GeneratedExecutor ex=new V7GeneratedExecutor(); ex.run();
        uint256 profit=ex.lastProfitRaw(); require(profit>0,"zero profit");
        uint256 va=IERC20V7(START).balanceOf(VAULT); require(va>=vb,"flash not repaid");
        uint256 profitUsdE8=profit*START_PRICE_E8/START_SCALE;
        uint256 gasUsdE8=ex.lastGasUsed()*GAS_PRICE_WEI*ETH_PRICE_E8/1e18;
        uint256 mevUsdE8=AMOUNT*START_PRICE_E8/START_SCALE*MEV_BPS/10000;
        require(profitUsdE8>gasUsdE8+mevUsdE8,"fails gas+MEV guard");
    }}
}}
'''


def finish(root:Path,out:Path,adapter:str,best:dict,code:str)->None:
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(code,encoding="utf-8")
    plan={"rendered":True,"adapter":adapter,"candidate":best,"test_file":str(out)}
    (root/"v7_fork_plan.json").write_text(json.dumps(plan,indent=2),encoding="utf-8")
    print(json.dumps({"rendered":True,"adapter":adapter,"test_file":str(out),"block":best.get("block_number"),"hops":best.get("hops")}))


def render_uniswap_v3(root:Path,out:Path,best:dict,vals)->None:
    start,amount,scale,start_px_e8,eth_px_e8,gas_price,mev_bps,block=vals;encoded=str(best.get("encoded_path") or "")
    if not encoded.startswith("0x") or len(encoded)<=42:skip(root,out,"missing encoded Uniswap V3 path");return
    code=header()+f'''interface IUniRouter02 {{ struct ExactInputParams {{ bytes path; address recipient; uint256 amountIn; uint256 amountOutMinimum; }} function exactInput(ExactInputParams calldata params) external payable returns(uint256); }}
contract V7GeneratedExecutor is IFlashRecipientV7 {{
 address constant VAULT=0xBA12222222228d8Ba445958a75a0704d566BF2C8; address constant ROUTER=0x2626664c2603336E57B271c5C0b26F421741e481; address constant START={start}; uint256 constant AMOUNT={amount}; uint256 public lastProfitRaw; uint256 public lastFeeRaw; uint256 public lastGasUsed;
 function run() external {{ IERC20V7[] memory ts=new IERC20V7[](1);ts[0]=IERC20V7(START);uint256[] memory amts=new uint256[](1);amts[0]=AMOUNT;uint256 g=gasleft();IVaultV7(VAULT).flashLoan(this,ts,amts,"");lastGasUsed=g-gasleft()+30000; }}
 function receiveFlashLoan(IERC20V7[] memory tokens,uint256[] memory amounts,uint256[] memory fees,bytes memory) external override {{ require(msg.sender==VAULT&&tokens.length==1&&address(tokens[0])==START,"flash");uint256 repay=amounts[0]+fees[0];lastFeeRaw=fees[0];require(IERC20V7(START).approve(ROUTER,amounts[0]),"approve");uint256 amountOut=IUniRouter02(ROUTER).exactInput(IUniRouter02.ExactInputParams({{path:hex"{encoded[2:]}",recipient:address(this),amountIn:amounts[0],amountOutMinimum:repay+1}}));require(amountOut>repay,"not profitable");require(IERC20V7(START).transfer(VAULT,repay),"repay");lastProfitRaw=IERC20V7(START).balanceOf(address(this)); }}
}}
'''+footer(start,amount,scale,start_px_e8,eth_px_e8,gas_price,mev_bps,block)
    finish(root,out,"uniswap_v3",best,code)


def render_slipstream(root:Path,out:Path,best:dict,vals)->None:
    start,amount,scale,start_px_e8,eth_px_e8,gas_price,mev_bps,block=vals
    pools=[x for x in str(best.get("pool_addresses") or "").split("|") if x];tokens=[x for x in str(best.get("token_path") or "").split("|") if x];hops=int(best.get("hops") or 0)
    if hops<2 or len(pools)!=hops or len(tokens)!=hops+1 or tokens[0].lower()!=tokens[-1].lower():skip(root,out,"invalid Slipstream physical route");return
    pool_assign='\n'.join(f'        ps[{i}]={p};' for i,p in enumerate(pools));token_assign='\n'.join(f'        tsPath[{i}]={t};' for i,t in enumerate(tokens))
    code=header()+f'''interface ICLPoolV7 {{ function swap(address,bool,int256,uint160,bytes calldata) external returns(int256,int256); }}
contract V7GeneratedExecutor is IFlashRecipientV7 {{
    address constant VAULT=0xBA12222222228d8Ba445958a75a0704d566BF2C8; address constant START={start}; uint256 constant AMOUNT={amount};
    uint160 constant MIN_SQRT_PLUS_ONE=4295128740; uint160 constant MAX_SQRT_MINUS_ONE=1461446703485210103287273052203988822378723970341;
    uint256 public lastProfitRaw; uint256 public lastFeeRaw; uint256 public lastGasUsed; address private activePool; address private activeTokenIn;
    function run() external {{ IERC20V7[] memory ts=new IERC20V7[](1);ts[0]=IERC20V7(START);uint256[] memory amts=new uint256[](1);amts[0]=AMOUNT;uint256 g=gasleft();IVaultV7(VAULT).flashLoan(this,ts,amts,"");lastGasUsed=g-gasleft()+30000; }}
    function uniswapV3SwapCallback(int256 amount0Delta,int256 amount1Delta,bytes calldata) external {{ require(msg.sender==activePool,"pool");uint256 owed=amount0Delta>0?uint256(amount0Delta):uint256(amount1Delta);require(IERC20V7(activeTokenIn).transfer(msg.sender,owed),"callback pay"); }}
    function receiveFlashLoan(IERC20V7[] memory tokens,uint256[] memory amounts,uint256[] memory fees,bytes memory) external override {{
        require(msg.sender==VAULT&&tokens.length==1&&address(tokens[0])==START,"flash"); uint256 repay=amounts[0]+fees[0]; lastFeeRaw=fees[0];
        address[] memory ps=new address[]({hops}); address[] memory tsPath=new address[]({hops+1});
{pool_assign}
{token_assign}
        uint256 cur=amounts[0];
        for(uint256 i=0;i<{hops};i++) {{
            activePool=ps[i];activeTokenIn=tsPath[i];bool zeroForOne=tsPath[i]<tsPath[i+1];
            (int256 a0,int256 a1)=ICLPoolV7(ps[i]).swap(address(this),zeroForOne,int256(cur),zeroForOne?MIN_SQRT_PLUS_ONE:MAX_SQRT_MINUS_ONE,"");
            int256 outDelta=zeroForOne?a1:a0;require(outDelta<0,"no output");cur=uint256(-outDelta);
        }}
        require(cur>repay,"not profitable");require(IERC20V7(START).transfer(VAULT,repay),"repay");lastProfitRaw=IERC20V7(START).balanceOf(address(this));activePool=address(0);activeTokenIn=address(0);
    }}
}}
'''+footer(start,amount,scale,start_px_e8,eth_px_e8,gas_price,mev_bps,block)
    finish(root,out,"aerodrome_slipstream",best,code)


def render_aerodrome_v2(root:Path,out:Path,best:dict,vals)->None:
    start,amount,scale,start_px_e8,eth_px_e8,gas_price,mev_bps,block=vals;tokens=best["token_path"].split("|");stables=best["stable_flags"].split("|");factories=best["factory_addresses"].split("|");hops=int(best["hops"])
    if len(tokens)!=hops+1 or len(stables)!=hops or len(factories)!=hops or tokens[0].lower()!=tokens[-1].lower():skip(root,out,"invalid Aerodrome V2 route");return
    route_lines='\n'.join(f'        routes[{i}]=IAeroRouter.Route({tokens[i]},{tokens[i+1]},{"true" if stables[i]=="1" else "false"},{factories[i]});' for i in range(hops))
    code=header()+f'''interface IAeroRouter {{ struct Route {{ address from; address to; bool stable; address factory; }} function swapExactTokensForTokens(uint256,uint256,Route[] calldata,address,uint256) external returns(uint256[] memory); }}
contract V7GeneratedExecutor is IFlashRecipientV7 {{ address constant VAULT=0xBA12222222228d8Ba445958a75a0704d566BF2C8;address constant ROUTER=0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43;address constant START={start};uint256 constant AMOUNT={amount};uint256 public lastProfitRaw;uint256 public lastFeeRaw;uint256 public lastGasUsed;function run() external {{IERC20V7[] memory ts=new IERC20V7[](1);ts[0]=IERC20V7(START);uint256[] memory amts=new uint256[](1);amts[0]=AMOUNT;uint256 g=gasleft();IVaultV7(VAULT).flashLoan(this,ts,amts,"");lastGasUsed=g-gasleft()+30000;}}function receiveFlashLoan(IERC20V7[] memory tokens,uint256[] memory amounts,uint256[] memory fees,bytes memory) external override {{require(msg.sender==VAULT&&tokens.length==1&&address(tokens[0])==START,"flash");uint256 repay=amounts[0]+fees[0];lastFeeRaw=fees[0];require(IERC20V7(START).approve(ROUTER,amounts[0]),"approve");IAeroRouter.Route[] memory routes=new IAeroRouter.Route[]({hops});
{route_lines}
IAeroRouter(ROUTER).swapExactTokensForTokens(amounts[0],repay+1,routes,address(this),block.timestamp);uint256 bal=IERC20V7(START).balanceOf(address(this));require(bal>repay,"not profitable");require(IERC20V7(START).transfer(VAULT,repay),"repay");lastProfitRaw=IERC20V7(START).balanceOf(address(this));}}}}
'''+footer(start,amount,scale,start_px_e8,eth_px_e8,gas_price,mev_bps,block)
    finish(root,out,"aerodrome_v2",best,code)


def main()->None:
    p=argparse.ArgumentParser();p.add_argument("--artifacts",default="artifacts");p.add_argument("--out",default="test/generated/V7Candidate.t.sol");args=p.parse_args();root=Path(args.artifacts);out=Path(args.out);bp=root/"v7_best_quote.json";best=json.loads(bp.read_text(encoding="utf-8")) if bp.exists() else {}
    if not best:skip(root,out,"no QUOTE_VERIFIED exact cycle");return
    vals=common_values(root,out,best)
    if vals is None:return
    adapter=str(best.get("adapter") or "")
    if adapter=="uniswap_v3":render_uniswap_v3(root,out,best,vals)
    elif adapter=="aerodrome_slipstream":render_slipstream(root,out,best,vals)
    elif adapter=="aerodrome_v2":render_aerodrome_v2(root,out,best,vals)
    else:skip(root,out,f"unsupported executable adapter: {adapter}")

if __name__=="__main__":main()
