from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

from eth_abi import decode, encode
from eth_utils import keccak

from synergy_graph.v7 import BALANCER_V2_VAULT, Pool, Rpc, decode_address, decode_uint, pad_address, safe_call

UNISWAP_V3_FACTORY_BASE = "0x33128a8fc17869897dce68ed026d694621f6fdfd"
UNISWAP_V3_QUOTER_V2_BASE = "0x3d4e44eb1374240ce5f1b871ab261cd16335b76a"
AERODROME_CL_QUOTERS = {
    "0x5e7bb104d84c7cb9b682aac2f3d509f5f406809a": "0x254cf9e1e6e233aa1ac962cb9b05b2cfeaae15b0",
    "0xade65c38cd4849adba595a4323a8c7ddfe89716a": "0x3d4c22254f86f64b7ec90ab8f7aec1fbfd271c6c",
    "0xf8f2eb4940cfe7d13603dddd87f123820fc061ef": "0x514c8b5f54112481e28028f1166bd78501089259",
}
WETH_BASE = "0x4200000000000000000000000000000000000006"


def selector(signature: str) -> bytes:
    return keccak(text=signature)[:4]


def calldata(signature: str, types: list[str], values: list[Any]) -> str:
    return "0x" + (selector(signature) + encode(types, values)).hex()


def decode_one(type_name: str, data: str) -> Any:
    if not data or data == "0x":
        raise ValueError("empty eth_call result")
    return decode([type_name], bytes.fromhex(data[2:]))[0]


@dataclass
class PoolState:
    address: str
    token0: str
    token1: str
    factory: str = ""
    kind: str = "unsupported"
    reserve0: int | None = None
    reserve1: int | None = None
    stable: bool | None = None
    fee: int | None = None
    tick_spacing: int | None = None
    source_dex: str = ""


@dataclass
class QuoteStep:
    pool: str
    token_in: str
    token_out: str
    kind: str
    amount_in: int
    amount_out: int
    gas_estimate: int = 0


@dataclass
class CycleQuote:
    candidate_index: int
    start_token: str
    amount_in: int
    amount_out: int
    profit_raw: int
    profit_usd: float
    gas_usd: float
    mev_usd: float
    flash_fee_usd: float
    net_usd: float
    stage: str
    steps: list[QuoteStep]


def classify_pool(rpc: Rpc, p: Pool, block: str) -> PoolState:
    t0 = decode_address(safe_call(rpc, p.address, "0x0dfe1681", block)) or p.token0
    t1 = decode_address(safe_call(rpc, p.address, "0xd21220a7", block)) or p.token1
    factory_data = safe_call(rpc, p.address, calldata("factory()", [], []), block)
    factory = decode_address(factory_data).lower() if factory_data else ""
    stable_data = safe_call(rpc, p.address, calldata("stable()", [], []), block)
    stable = bool(decode_uint(stable_data)) if stable_data and stable_data != "0x" else None
    reserves = safe_call(rpc, p.address, "0x0902f1ac", block)
    r0 = r1 = None
    if reserves and reserves != "0x":
        h = reserves[2:]
        if len(h) >= 128:
            r0, r1 = int(h[:64], 16), int(h[64:128], 16)
    fee_data = safe_call(rpc, p.address, calldata("fee()", [], []), block)
    fee = decode_uint(fee_data) if fee_data else None
    tick_data = safe_call(rpc, p.address, calldata("tickSpacing()", [], []), block)
    tick_spacing = None
    if tick_data and tick_data != "0x":
        raw = decode_uint(tick_data)
        if raw >= 1 << 255:
            raw -= 1 << 256
        tick_spacing = int(raw)
    kind = "unsupported"
    if r0 is not None and r1 is not None:
        probe = safe_call(rpc, p.address, calldata("getAmountOut(uint256,address)", ["uint256", "address"], [1, t0]), block)
        kind = "aerodrome_v2" if probe else "v2_cpmm"
    elif tick_spacing is not None and factory in AERODROME_CL_QUOTERS:
        kind = "aerodrome_cl"
    elif fee is not None and factory == UNISWAP_V3_FACTORY_BASE:
        kind = "uniswap_v3"
    elif fee is not None:
        kind = "v3_like_unsupported"
    return PoolState(p.address.lower(), t0.lower(), t1.lower(), factory, kind, r0, r1, stable, fee, tick_spacing, p.dex_id)


def quote_v2_cpmm(state: PoolState, token_in: str, amount_in: int, fee_fraction: float) -> tuple[int, int]:
    if state.reserve0 is None or state.reserve1 is None:
        raise ValueError("missing reserves")
    if token_in.lower() == state.token0:
        x, y = state.reserve0, state.reserve1
    elif token_in.lower() == state.token1:
        x, y = state.reserve1, state.reserve0
    else:
        raise ValueError("token not in pool")
    if x <= 0 or y <= 0:
        raise ValueError("zero reserve")
    fee_ppm = max(0, min(999_999, int(round(fee_fraction * 1_000_000))))
    effective = amount_in * (1_000_000 - fee_ppm)
    return int(y * effective // (x * 1_000_000 + effective)), 0


def exact_step_quote(rpc: Rpc, p: Pool, state: PoolState, token_in: str, token_out: str, amount_in: int, block: str) -> tuple[int, int]:
    if state.kind == "aerodrome_v2":
        data = rpc.eth_call(state.address, calldata("getAmountOut(uint256,address)", ["uint256", "address"], [amount_in, token_in]), block)
        return int(decode_one("uint256", data)), 0
    if state.kind == "v2_cpmm":
        if p.reported_fee_pct <= 0:
            raise ValueError("generic v2 fee unavailable: refusing optimistic exact quote")
        return quote_v2_cpmm(state, token_in, amount_in, p.reported_fee_pct / 100.0)
    if state.kind == "uniswap_v3":
        sig = "quoteExactInputSingle((address,address,uint256,uint24,uint160))"
        data = rpc.eth_call(UNISWAP_V3_QUOTER_V2_BASE, calldata(sig, ["(address,address,uint256,uint24,uint160)"], [(token_in, token_out, amount_in, state.fee, 0)]), block)
        out, _sqrt_after, _ticks, gas_est = decode(["uint256", "uint160", "uint32", "uint256"], bytes.fromhex(data[2:]))
        return int(out), int(gas_est)
    if state.kind == "aerodrome_cl":
        quoter = AERODROME_CL_QUOTERS.get(state.factory)
        if not quoter or state.tick_spacing is None:
            raise ValueError("unknown Aerodrome CL factory/tick spacing")
        sig = "quoteExactInputSingle((address,address,uint256,int24,uint160))"
        data = rpc.eth_call(quoter, calldata(sig, ["(address,address,uint256,int24,uint160)"], [(token_in, token_out, amount_in, state.tick_spacing, 0)]), block)
        out, _sqrt_after, _ticks, gas_est = decode(["uint256", "uint160", "uint32", "uint256"], bytes.fromhex(data[2:]))
        return int(out), int(gas_est)
    raise ValueError(f"unsupported pool kind: {state.kind}")


def load_pools(path: Path) -> dict[str, Pool]:
    out: dict[str, Pool] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            p = Pool(row["address"].lower(), row.get("dex_id", ""), row.get("name", ""), row["token0"].lower(), row["token1"].lower(), row.get("token0_symbol", ""), row.get("token1_symbol", ""), float(row.get("reserve_usd") or 0), float(row.get("token0_price_usd") or 0), float(row.get("token1_price_usd") or 0), float(row.get("reported_fee_pct") or 0))
            out[p.address] = p
    return out


def token_price_usd(pools: Iterable[Pool], token: str) -> float:
    token = token.lower(); vals = []
    for p in pools:
        if p.token0 == token and p.token0_price_usd > 0: vals.append(p.token0_price_usd)
        elif p.token1 == token and p.token1_price_usd > 0: vals.append(p.token1_price_usd)
    if not vals: return 0.0
    vals.sort(); return vals[len(vals)//2]


def token_decimals(rpc: Rpc, token: str, block: str) -> int:
    data = safe_call(rpc, token, "0x313ce567", block)
    d = decode_uint(data) if data else 18
    return int(d if 0 <= d <= 36 else 18)


def vault_balance_raw(rpc: Rpc, token: str, block: str) -> int:
    data = safe_call(rpc, token, "0x70a08231" + pad_address(BALANCER_V2_VAULT), block)
    return decode_uint(data) if data else 0


def choose_amount_grid(price: float, decimals: int, max_flash_usd: float) -> list[int]:
    if price <= 0: return []
    sizes = [1,5,10,25,50,100,250,500,1000,2500,5000,10000,25000,50000]
    return sorted({int(usd / price * 10**decimals) for usd in sizes if usd <= max_flash_usd and int(usd / price * 10**decimals) > 0})


def quote_cycle(rpc: Rpc, pools: dict[str, Pool], states: dict[str, PoolState], cand: dict[str,str], idx: int, amount_in: int, start_price: float, start_decimals: int, eth_price: float, gas_price: int, flash_fee_bps: float, mev_haircut: float, block: str) -> CycleQuote:
    paddrs = [x.lower() for x in cand["pool_addresses"].split("|") if x]
    tokens = [x.lower() for x in cand["token_path"].split("|") if x]
    if len(tokens) != len(paddrs)+1 or tokens[0] != tokens[-1]: raise ValueError("candidate path malformed")
    amount = amount_in; steps: list[QuoteStep] = []
    for j, pa in enumerate(paddrs):
        out, qgas = exact_step_quote(rpc, pools[pa], states[pa], tokens[j], tokens[j+1], amount, block)
        if out <= 0: raise ValueError("zero quote")
        steps.append(QuoteStep(pa, tokens[j], tokens[j+1], states[pa].kind, amount, out, qgas)); amount = out
    scale = 10**start_decimals; profit_raw = amount-amount_in; profit_usd = profit_raw/scale*start_price
    flash_fee_usd = amount_in/scale*start_price*flash_fee_bps/10000.0
    gas_units = 180000 + sum(85000 if s.kind in {"aerodrome_v2","v2_cpmm"} else max(110000,s.gas_estimate) for s in steps)
    gas_usd = gas_units*gas_price/1e18*eth_price if gas_price > 0 and eth_price > 0 else 0.0
    mev_usd = max(0.0,profit_usd)*mev_haircut; net = profit_usd-flash_fee_usd-gas_usd-mev_usd
    return CycleQuote(idx,tokens[0],amount_in,amount,profit_raw,profit_usd,gas_usd,mev_usd,flash_fee_usd,net,"QUOTE_VERIFIED" if net>0 else "QUOTE_REJECTED",steps)


def _write_csv(path: Path, rows: list[dict[str,Any]]) -> None:
    if not rows: path.write_text("",encoding="utf-8"); return
    fields=[]
    for row in rows:
        for k in row:
            if k not in fields: fields.append(k)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)


def _write_generated_fork_test(path: Path, q: CycleQuote, block_number: int) -> None:
    kind_map={"aerodrome_v2":0,"uniswap_v3":1,"aerodrome_cl":1}
    lines=["// SPDX-License-Identifier: MIT","pragma solidity ^0.8.24;",'import "../contracts/V7ForeignCycleExecutor.sol";',"interface VmV7Generated { function envString(string calldata) external returns (string memory); function createSelectFork(string calldata,uint256) external returns (uint256); }","contract V7GeneratedForkTest {",'VmV7Generated constant vm=VmV7Generated(address(uint160(uint256(keccak256("hevm cheat code")))));',"function testPinnedCandidateRepaysAndProfits() public {",f'vm.createSelectFork(vm.envString("BASE_RPC_URL"), {block_number});',"V7ForeignCycleExecutor ex=new V7ForeignCycleExecutor();",f"V7ForeignCycleExecutor.Step[] memory steps=new V7ForeignCycleExecutor.Step[]({len(q.steps)});"]
    for i,s in enumerate(q.steps): lines.append(f"steps[{i}]=V7ForeignCycleExecutor.Step(address({s.pool}),address({s.token_in}),address({s.token_out}),{kind_map[s.kind]});")
    lines += [f"address flashToken=address({q.start_token});","uint256 beforeBal=IERC20V7Cycle(flashToken).balanceOf(address(ex));",f"ex.startFlash(flashToken,{q.amount_in},steps,1);","uint256 afterBal=IERC20V7Cycle(flashToken).balanceOf(address(ex));",'require(afterBal>beforeBal,"no raw-token profit after flash repayment");',"}","}",""]
    path.write_text("\n".join(lines),encoding="utf-8")


def validate_candidates(args: argparse.Namespace) -> dict[str,Any]:
    rpc=Rpc(args.rpc_url); block_number=args.block if args.block is not None else rpc.latest_block(); block=hex(block_number)
    pools=load_pools(Path(args.pools)); pool_list=list(pools.values())
    with Path(args.candidates).open(newline="",encoding="utf-8") as f: candidates=list(csv.DictReader(f))[:args.max_candidates]
    eth_price=token_price_usd(pool_list,WETH_BASE)
    try: gas_price=int(rpc.call("eth_gasPrice",[]),16)
    except Exception: gas_price=0
    states: dict[str,PoolState]={}; results=[]; failures=[]; decimals_cache={}; vault_cache={}
    for idx,cand in enumerate(candidates):
        paddrs=[x.lower() for x in cand.get("pool_addresses","").split("|") if x]
        if not paddrs or any(pa not in pools for pa in paddrs): continue
        try:
            for pa in paddrs:
                if pa not in states: states[pa]=classify_pool(rpc,pools[pa],block)
            if any(states[pa].kind in {"unsupported","v3_like_unsupported"} for pa in paddrs):
                failures.append({"candidate_index":idx,"reason":"unsupported_protocol","pools":"|".join(paddrs)}); continue
            start=cand["start_token"].lower(); decimals_cache.setdefault(start,token_decimals(rpc,start,block)); dec=decimals_cache[start]; price=token_price_usd(pool_list,start)
            if start not in vault_cache: vault_cache[start]=vault_balance_raw(rpc,start,block)
            grid=[x for x in choose_amount_grid(price,dec,args.max_flash_usd) if x<=vault_cache[start]]
            if not grid: failures.append({"candidate_index":idx,"reason":"no_price_or_vault_liquidity"}); continue
            best=None
            for amount in grid:
                try: q=quote_cycle(rpc,pools,states,cand,idx,amount,price,dec,eth_price,gas_price,args.flash_fee_bps,args.mev_haircut,block)
                except Exception as e: failures.append({"candidate_index":idx,"reason":"quote_error","error":str(e)[:240]}); continue
                if best is None or q.net_usd>best.net_usd: best=q
            if best is not None: results.append(best)
        except Exception as e: failures.append({"candidate_index":idx,"reason":"candidate_error","error":str(e)[:240]})
    results.sort(key=lambda q:q.net_usd,reverse=True); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    _write_csv(out/"v7_exact_pool_state.csv",[asdict(s) for s in states.values()]); _write_csv(out/"v7_quote_failures.csv",failures)
    rows=[]
    for q in results:
        r={k:v for k,v in asdict(q).items() if k!="steps"}; r["pool_path"]="|".join(s.pool for s in q.steps); r["token_path"]="|".join([q.steps[0].token_in]+[s.token_out for s in q.steps]) if q.steps else ""; r["kind_path"]="|".join(s.kind for s in q.steps); rows.append(r)
    _write_csv(out/"v7_exact_quotes.csv",rows)
    positive=[q for q in results if q.net_usd>=args.min_net_usd]; forkable=[q for q in positive if all(s.kind in {"aerodrome_v2","uniswap_v3","aerodrome_cl"} for s in q.steps)]
    kinds={}
    for s in states.values(): kinds[s.kind]=kinds.get(s.kind,0)+1
    report={"network":"base","block_number":block_number,"foreign_pools_input":len(pools),"discovery_candidates_input":len(candidates),"pools_exactly_classified":len(states),"protocol_breakdown":kinds,"exact_quotes_completed":len(results),"positive_quote_candidates":len(positive),"forkable_positive_candidates":len(forkable),"max_flash_usd":args.max_flash_usd,"flash_fee_bps_assumed":args.flash_fee_bps,"mev_haircut":args.mev_haircut,"gas_price_wei":gas_price,"weth_price_usd":eth_price,"balancer_vault_start_token_balances_raw":vault_cache,"best_net_usd":positive[0].net_usd if positive else None,"best_candidate_index":positive[0].candidate_index if positive else None,"best_forkable_candidate_index":forkable[0].candidate_index if forkable else None,"note":"QUOTE_VERIFIED is a pinned-block eth_call estimate; production claim requires same-block FORK_EXECUTABLE."}
    (out/"v7_exact_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    if forkable: _write_generated_fork_test(out/"V7GeneratedFork.t.sol",forkable[0],block_number)
    else: (out/"V7GeneratedFork.t.sol").write_text("// no positive forkable quote candidate\n",encoding="utf-8")
    return report


def cli() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--pools",default="artifacts/v7_pools.csv"); p.add_argument("--candidates",default="artifacts/v7_candidates.csv"); p.add_argument("--out",default="artifacts"); p.add_argument("--rpc-url",default=os.getenv("BASE_RPC_URL","https://mainnet.base.org")); p.add_argument("--block",type=int); p.add_argument("--max-candidates",type=int,default=80); p.add_argument("--max-flash-usd",type=float,default=50000.0); p.add_argument("--flash-fee-bps",type=float,default=0.0); p.add_argument("--mev-haircut",type=float,default=0.35); p.add_argument("--min-net-usd",type=float,default=0.01); args=p.parse_args(); print(json.dumps(validate_candidates(args),indent=2))


if __name__ == "__main__": cli()
