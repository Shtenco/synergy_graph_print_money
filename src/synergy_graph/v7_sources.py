from __future__ import annotations

import time
from dataclasses import dataclass

import requests
from eth_abi import encode
from eth_utils import keccak

from .v7 import GECKO, Pool, Rpc, _addr, _num, decode_address, decode_uint, safe_call

AERODROME_V2_FACTORY = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
SEL_ALL_POOLS_LENGTH = "0x" + keccak(text="allPoolsLength()")[:4].hex()
SEL_ALL_POOLS = "0x" + keccak(text="allPools(uint256)")[:4].hex()
SEL_STABLE = "0x" + keccak(text="stable()")[:4].hex()
SEL_GET_FEE = "0x" + keccak(text="getFee(address,bool)")[:4].hex()
SEL_TOKEN0 = "0x0dfe1681"
SEL_TOKEN1 = "0xd21220a7"
SEL_GET_RESERVES = "0x0902f1ac"
SEL_DECIMALS = "0x313ce567"


@dataclass
class SourceStats:
    public_pages_ok: int = 0
    public_boundary: str | None = None
    ranked_count: int = 0
    factory_added: int = 0
    factory_scanned: int = 0


def fetch_public_ranked(pages: int, max_pools: int, sleep_s: float, retries: int = 10) -> tuple[list[Pool], SourceStats]:
    out: list[Pool] = []
    stats = SourceStats()
    s = requests.Session()
    s.headers.update({"accept":"application/json;version=20230203","user-agent":"synergy-graph-v7/0.7.5"})
    for page in range(1, pages + 1):
        payload = None
        for attempt in range(retries):
            r = s.get(f"{GECKO}/networks/base/pools", params={"page":page,"include":"base_token,quote_token,dex"}, timeout=40)
            if r.status_code in (401,403):
                stats.public_boundary = f"HTTP {r.status_code} at page {page}"
                break
            if r.status_code == 429:
                ra = r.headers.get("Retry-After")
                try: delay = float(ra) if ra else sleep_s * (attempt + 2)
                except ValueError: delay = sleep_s * (attempt + 2)
                time.sleep(min(90.0, max(sleep_s, delay)))
                continue
            if 500 <= r.status_code < 600:
                time.sleep(min(60.0, sleep_s * (attempt + 1)))
                continue
            r.raise_for_status(); payload = r.json(); break
        if stats.public_boundary: break
        if payload is None: raise RuntimeError(f"public pool page {page} exhausted retries")
        stats.public_pages_ok = page
        included = {x.get("id",""):x for x in payload.get("included",[])}
        for item in payload.get("data",[]):
            a=item.get("attributes",{}); rel=item.get("relationships",{})
            bid=(((rel.get("base_token") or {}).get("data") or {}).get("id")); qid=(((rel.get("quote_token") or {}).get("data") or {}).get("id")); did=(((rel.get("dex") or {}).get("data") or {}).get("id")) or ""
            bi=included.get(bid or "",{}).get("attributes",{}); qi=included.get(qid or "",{}).get("attributes",{})
            p=Pool((a.get("address") or _addr(item.get("id"))).lower(),did,a.get("name") or "",_addr(bid).lower(),_addr(qid).lower(),bi.get("symbol") or "",qi.get("symbol") or "",_num(a.get("reserve_in_usd")),_num(a.get("base_token_price_usd")),_num(a.get("quote_token_price_usd")),_num(a.get("pool_fee_percentage")))
            if p.address and p.token0 and p.token1: out.append(p)
            if len(out)>=max_pools:
                stats.ranked_count=len(out); return out[:max_pools],stats
        time.sleep(sleep_s)
    stats.ranked_count=len(out)
    return out[:max_pools],stats


def _uint_arg(selector: str, n: int) -> str:
    return selector + n.to_bytes(32,"big").hex()


def supplement_aerodrome_v2(rpc: Rpc, block: str, pools: list[Pool], target: int, scan_limit: int = 800) -> tuple[list[Pool], SourceStats]:
    stats=SourceStats(ranked_count=len(pools))
    if len(pools)>=target: return pools[:target],stats
    seen={p.address.lower() for p in pools}; price={}; symbol={}
    for p in pools:
        for token,px,sym in ((p.token0,p.token0_price_usd,p.token0_symbol),(p.token1,p.token1_price_usd,p.token1_symbol)):
            if px>0: price[token]=px
            if sym: symbol[token]=sym
    length=decode_uint(safe_call(rpc,AERODROME_V2_FACTORY,SEL_ALL_POOLS_LENGTH,block))
    candidates=[]
    for i in range(length-1,max(-1,length-scan_limit-1),-1):
        stats.factory_scanned+=1
        addr=decode_address(safe_call(rpc,AERODROME_V2_FACTORY,_uint_arg(SEL_ALL_POOLS,i),block)).lower()
        if not addr or addr in seen: continue
        t0=decode_address(safe_call(rpc,addr,SEL_TOKEN0,block)).lower(); t1=decode_address(safe_call(rpc,addr,SEL_TOKEN1,block)).lower()
        if not t0 or not t1: continue
        stable=bool(decode_uint(safe_call(rpc,addr,SEL_STABLE,block)))
        fee_data=SEL_GET_FEE+encode(["address","bool"],[addr,stable]).hex(); fee_raw=decode_uint(safe_call(rpc,AERODROME_V2_FACTORY,fee_data,block))
        p0=price.get(t0,0.0); p1=price.get(t1,0.0); reserve_usd=0.0
        res=safe_call(rpc,addr,SEL_GET_RESERVES,block)
        h=res[2:] if res.startswith("0x") else res
        if len(h)>=128 and p0>0 and p1>0:
            r0=int(h[:64],16); r1=int(h[64:128],16)
            d0=decode_uint(safe_call(rpc,t0,SEL_DECIMALS,block)) or 18; d1=decode_uint(safe_call(rpc,t1,SEL_DECIMALS,block)) or 18
            reserve_usd=r0/(10**d0)*p0+r1/(10**d1)*p1
        candidates.append(Pool(addr,"aerodrome-v2","Aerodrome V2 factory supplement",t0,t1,symbol.get(t0,""),symbol.get(t1,""),reserve_usd,p0,p1,fee_raw/100.0))
        seen.add(addr)
        if len(candidates)>=max(80,target-len(pools)): break
    candidates.sort(key=lambda p:(p.token0_price_usd>0 and p.token1_price_usd>0,p.reserve_usd),reverse=True)
    add=candidates[:max(0,target-len(pools))]; stats.factory_added=len(add)
    return pools+add,stats
