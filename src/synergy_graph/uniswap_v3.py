from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from eth_abi import encode
from eth_utils import keccak

from .quotes import erc20_balance, erc20_decimals, token_price_usd
from .v7 import BALANCER_V2_VAULT, Pool, Rpc, decode_address, decode_uint

UNISWAP_V3_FACTORY = "0x33128a8fc17869897dce68ed026d694621f6fdfd"
UNISWAP_V3_QUOTER_V2 = "0x3d4e44eb1374240ce5f1b871ab261cd16335b76a"
UNISWAP_SWAP_ROUTER_02 = "0x2626664c2603336e57b271c5c0b26f421741e481"
SUPPORTED_DEX_IDS = {"uniswap-v3-base"}


def _call(signature: str, types: list[str] | None = None, values: list[Any] | None = None) -> str:
    types = types or []
    values = values or []
    selector = keccak(text=signature)[:4]
    payload = selector + (encode(types, values) if types else b"")
    return "0x" + payload.hex()


def _address(rpc: Rpc, to: str, signature: str, block: str) -> str:
    return decode_address(rpc.eth_call(to, _call(signature), block)).lower()


def _uint(rpc: Rpc, to: str, signature: str, block: str) -> int:
    return decode_uint(rpc.eth_call(to, _call(signature), block))


def _factory_pool(rpc: Rpc, token0: str, token1: str, fee: int, block: str) -> str:
    data = rpc.eth_call(UNISWAP_V3_FACTORY,_call("getPool(address,address,uint24)",["address","address","uint24"],[token0,token1,fee]),block)
    return decode_address(data).lower()


def inspect_uniswap_v3_pool(rpc: Rpc, pool: Pool, block: str) -> dict[str, Any] | None:
    if pool.dex_id not in SUPPORTED_DEX_IDS:
        return None
    try:
        if rpc.code(pool.address, block) in ("", "0x"):
            return None
        token0 = _address(rpc, pool.address, "token0()", block)
        token1 = _address(rpc, pool.address, "token1()", block)
        fee = _uint(rpc, pool.address, "fee()", block)
        factory = _address(rpc, pool.address, "factory()", block)
        if factory != UNISWAP_V3_FACTORY:return None
        if {token0, token1} != {pool.token0.lower(), pool.token1.lower()}:return None
        if _factory_pool(rpc, token0, token1, fee, block) != pool.address.lower():return None
        return {"address":pool.address.lower(),"token0":token0,"token1":token1,"fee":fee,"factory":factory}
    except Exception:
        return None


def encode_path(tokens: list[str], fees: list[int]) -> bytes:
    if len(tokens) != len(fees) + 1:raise ValueError("tokens/fees length mismatch")
    out=bytes.fromhex(tokens[0].lower().removeprefix("0x"))
    for fee,token in zip(fees,tokens[1:]):
        if not (0 <= int(fee) < 2**24):raise ValueError("invalid uint24 fee")
        out += int(fee).to_bytes(3,"big") + bytes.fromhex(token.lower().removeprefix("0x"))
    return out


def quote_exact_input(rpc: Rpc, path: bytes, amount_in: int, block: str) -> tuple[int,int]:
    data=rpc.eth_call(UNISWAP_V3_QUOTER_V2,_call("quoteExactInput(bytes,uint256)",["bytes","uint256"],[path,amount_in]),block)
    h=data[2:] if data.startswith("0x") else data
    if len(h)<64*4:raise RuntimeError("short QuoterV2 response")
    return int(h[0:64],16),int(h[64*3:64*4],16)


def _usd_grid(min_usd: float,max_usd: float,points: int)->list[float]:
    if max_usd<=0:return []
    min_usd=min(max(min_usd,1e-9),max_usd)
    if points<=1 or math.isclose(min_usd,max_usd):return [max_usd]
    ratio=max_usd/min_usd
    return sorted({min_usd*ratio**(i/(points-1)) for i in range(points)}|{max_usd})


def uniswap_v3_discovery_candidates(pools:list[Pool],max_hops:int=4,top_k:int=120)->list[dict[str,Any]]:
    """Enumerate physical closed V3 cycles from topology, not API-estimated profit.

    This deliberately includes both directions and parallel-fee two-pool cycles. Exact
    pinned-block QuoterV2 output, not GeckoTerminal spot ratios, decides profitability.
    """
    supported=[p for p in pools if p.dex_id in SUPPORTED_DEX_IDS]
    adj:dict[str,list[tuple[str,Pool]]]=defaultdict(list)
    for p in supported:
        adj[p.token0.lower()].append((p.token1.lower(),p))
        adj[p.token1.lower()].append((p.token0.lower(),p))
    dedup:dict[tuple[str,...],dict[str,Any]]={}
    for start in sorted(adj):
        stack=[(start,[start],[])]
        while stack:
            node,tokens,route=stack.pop()
            if len(route)>=max_hops:continue
            for nxt,pool in adj.get(node,[]):
                if any(x.address.lower()==pool.address.lower() for x in route):continue
                nr=route+[pool]
                if nxt==start and len(nr)>=2:
                    core=tokens[:]
                    pairs=tuple(f"{core[i]}>{nr[i].address.lower()}" for i in range(len(nr)))
                    rots=[pairs[i:]+pairs[:i] for i in range(len(pairs))]
                    key=min(rots)
                    if key not in dedup:
                        # API edge is only a ranking hint and may be stale/zero; exact quote is authoritative.
                        rate=1.0
                        ok=True
                        closed=tokens+[start]
                        for i,p in enumerate(nr):
                            r=p.discovery_rate(closed[i],closed[i+1])
                            if not r or r<=0:ok=False;break
                            rate*=r
                        dedup[key]={"stage":"TOPOLOGY_DISCOVERED","start_token":start,"hops":len(nr),"gross_spot_edge_bps":((rate-1)*10000 if ok else 0.0),"pool_addresses":"|".join(x.address.lower() for x in nr),"token_path":"|".join(closed),"discovery_adapter":"uniswap_v3"}
                    continue
                if nxt in tokens:continue
                stack.append((nxt,tokens+[nxt],nr))
    rows=list(dedup.values())
    rows.sort(key=lambda x:float(x.get("gross_spot_edge_bps") or 0),reverse=True)
    return rows[:top_k]


def optimize_uniswap_v3_cycle(rpc:Rpc,candidate:dict[str,Any],pools:list[Pool],block:str,max_flash_usd:float=50_000.0,min_trade_usd:float=.25,grid_points:int=16,mev_guard_bps:float=5.0,gas_reserve_usd:float=.05)->dict[str,Any]|None:
    pool_map={p.address.lower():p for p in pools}
    addresses=[x.lower() for x in str(candidate["pool_addresses"]).split("|") if x]
    tokens=[x.lower() for x in str(candidate["token_path"]).split("|") if x]
    if len(tokens)!=len(addresses)+1 or len(addresses)<2 or tokens[0]!=tokens[-1]:return None
    metas=[]
    for i,address in enumerate(addresses):
        pool=pool_map.get(address)
        if pool is None:return None
        meta=inspect_uniswap_v3_pool(rpc,pool,block)
        if meta is None or {tokens[i],tokens[i+1]}!={meta["token0"],meta["token1"]}:return None
        metas.append(meta)
    n=len(addresses);best=None;quote_errors=0
    for rotation in range(n):
        r_addresses=addresses[rotation:]+addresses[:rotation];r_metas=metas[rotation:]+metas[:rotation]
        core=tokens[:-1];r_core=core[rotation:]+core[:rotation];r_tokens=r_core+[r_core[0]];r_fees=[int(x["fee"]) for x in r_metas]
        path=encode_path(r_tokens,r_fees);start=r_tokens[0]
        try:
            decimals=erc20_decimals(rpc,start,block)
            if decimals>36:continue
            px=token_price_usd(start,pools)
            if px<=0:continue
            vault_raw=erc20_balance(rpc,start,BALANCER_V2_VAULT,block)
        except Exception:continue
        vault_usd=vault_raw/10**decimals*px;max_usd=min(max_flash_usd,vault_usd)
        if max_usd<min_trade_usd:continue
        for usd in _usd_grid(min_trade_usd,max_usd,grid_points):
            amount_in=int(usd/px*10**decimals)
            if amount_in<=0 or amount_in>vault_raw:continue
            try:amount_out,quoter_gas=quote_exact_input(rpc,path,amount_in,block)
            except Exception:quote_errors+=1;continue
            if amount_out<=0:continue
            profit_raw=amount_out-amount_in;profit_usd=profit_raw/10**decimals*px;gross_bps=(amount_out/amount_in-1)*10000
            guarded=profit_usd-usd*mev_guard_bps/10000-gas_reserve_usd
            row={"stage":"QUOTE_VERIFIED" if guarded>0 else "QUOTE_REJECTED","adapter":"uniswap_v3","block_number":int(block,16),"cycle_rotation":rotation,"start_token":start,"start_token_decimals":decimals,"start_token_price_usd":px,"vault_balance_raw":vault_raw,"vault_balance_usd":vault_usd,"amount_in_raw":amount_in,"amount_in_usd":usd,"amount_out_raw":amount_out,"gross_profit_raw":profit_raw,"gross_profit_usd":profit_usd,"gross_edge_bps_exact":gross_bps,"mev_guard_bps":mev_guard_bps,"gas_reserve_usd":gas_reserve_usd,"guarded_net_usd":guarded,"quoter_gas_estimate":quoter_gas,"hops":n,"pool_addresses":"|".join(r_addresses),"token_path":"|".join(r_tokens),"fee_tiers":"|".join(str(x) for x in r_fees),"encoded_path":"0x"+path.hex(),"factory":UNISWAP_V3_FACTORY,"quoter":UNISWAP_V3_QUOTER_V2,"router":UNISWAP_SWAP_ROUTER_02,"quote_errors_during_grid":quote_errors}
            if best is None or float(row["guarded_net_usd"])>float(best["guarded_net_usd"]):best=row
    return best
