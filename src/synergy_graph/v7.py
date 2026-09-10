from __future__ import annotations

import argparse, csv, json, math, os, time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
import requests

GECKO = "https://api.geckoterminal.com/api/v2"
BASE_CHAIN_ID = 8453
BALANCER_V2_VAULT = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
SEL_TOKEN0="0x0dfe1681"; SEL_TOKEN1="0xd21220a7"; SEL_GET_RESERVES="0x0902f1ac"; SEL_SLOT0="0x3850c7bd"; SEL_FEE="0xddca3f43"; SEL_DECIMALS="0x313ce567"; SEL_BALANCE_OF="0x70a08231"

@dataclass
class Pool:
    address:str; dex_id:str; name:str; token0:str; token1:str
    token0_symbol:str=""; token1_symbol:str=""; reserve_usd:float=0.0
    token0_price_usd:float=0.0; token1_price_usd:float=0.0
    token0_price_token1:float=0.0; token1_price_token0:float=0.0
    reported_fee_pct:float=0.0; discovery_source:str="global"
    def discovery_rate(self,src:str,dst:str)->float|None:
        fee=max(0.0,self.reported_fee_pct)/100.0
        if src.lower()==self.token0.lower() and dst.lower()==self.token1.lower():
            raw=self.token0_price_token1 or (self.token0_price_usd/self.token1_price_usd if self.token0_price_usd>0 and self.token1_price_usd>0 else 0)
        elif src.lower()==self.token1.lower() and dst.lower()==self.token0.lower():
            raw=self.token1_price_token0 or (self.token1_price_usd/self.token0_price_usd if self.token0_price_usd>0 and self.token1_price_usd>0 else 0)
        else:return None
        return raw*(1-fee) if raw>0 and math.isfinite(raw) else None

class Rpc:
    def __init__(self,url:str,timeout:int=20):self.url=url;self.timeout=timeout;self._id=0
    def call(self,method:str,params:list[Any])->Any:
        self._id+=1
        r=requests.post(self.url,json={"jsonrpc":"2.0","id":self._id,"method":method,"params":params},timeout=self.timeout);r.raise_for_status();j=r.json()
        if "error" in j:raise RuntimeError(f"RPC {method}: {j['error']}")
        return j["result"]
    def latest_block(self)->int:return int(self.call("eth_blockNumber",[]),16)
    def code(self,address:str,block:str)->str:return self.call("eth_getCode",[address,block])
    def eth_call(self,to:str,data:str,block:str)->str:return self.call("eth_call",[{"to":to,"data":data},block])

def _num(x:Any)->float:
    try:return float(x or 0)
    except (TypeError,ValueError):return 0.0

def _addr(v:str|None)->str:
    if not v:return ""
    return v.split("_",1)[-1] if "_" in v else v

def _request_json(s:requests.Session,url:str,params:dict[str,Any],sleep_s:float,retries:int=10)->dict[str,Any]:
    last_status=None
    for attempt in range(1,retries+1):
        r=s.get(url,params=params,timeout=30);last_status=r.status_code
        if r.status_code==429:
            retry_after=r.headers.get("Retry-After")
            try:wait=max(60.0,float(retry_after)) if retry_after else 60.0
            except ValueError:wait=60.0
            print(f"GeckoTerminal 429 attempt={attempt}; cooling down {wait:.0f}s",flush=True);time.sleep(min(wait,90.0));continue
        r.raise_for_status();return r.json()
    raise RuntimeError(f"GeckoTerminal remained unavailable after {retries} attempts; last status={last_status}")

def _parse_pool_payload(payload:dict[str,Any],source:str)->list[Pool]:
    included={x.get("id",""):x for x in payload.get("included",[])};out=[]
    for item in payload.get("data",[]):
        a=item.get("attributes",{});rel=item.get("relationships",{});b_id=(((rel.get("base_token") or {}).get("data") or {}).get("id"));q_id=(((rel.get("quote_token") or {}).get("data") or {}).get("id"));d_id=(((rel.get("dex") or {}).get("data") or {}).get("id")) or "";bi=included.get(b_id or "",{}).get("attributes",{});qi=included.get(q_id or "",{}).get("attributes",{})
        p=Pool((a.get("address") or _addr(item.get("id"))).lower(),d_id,a.get("name") or "",_addr(b_id).lower(),_addr(q_id).lower(),bi.get("symbol") or "",qi.get("symbol") or "",_num(a.get("reserve_in_usd")),_num(a.get("base_token_price_usd")),_num(a.get("quote_token_price_usd")),_num(a.get("base_token_price_quote_token")),_num(a.get("quote_token_price_base_token")),_num(a.get("pool_fee_percentage")),source)
        if p.address and p.token0 and p.token1:out.append(p)
    return out

def fetch_top_pools(pages:int=10,max_pools:int=240,sleep_s:float=15.0,augment_dexes:int=5,augment_pages:int=2)->list[Pool]:
    s=requests.Session();s.headers.update({"accept":"application/json;version=20230203","user-agent":"synergy-graph-v7/0.7"});by_addr={}
    global_pages=min(max(1,pages),10)
    for page in range(1,global_pages+1):
        payload=_request_json(s,f"{GECKO}/networks/base/pools",{"page":page,"include":"base_token,quote_token,dex"},sleep_s)
        for p in _parse_pool_payload(payload,"global"):by_addr.setdefault(p.address,p)
        if len(by_addr)>=max_pools:return list(by_addr.values())[:max_pools]
        if sleep_s and page<global_pages:time.sleep(sleep_s)
    if len(by_addr)<max_pools and augment_dexes>0 and augment_pages>0:
        counts=Counter(p.dex_id for p in by_addr.values() if p.dex_id)
        for dex_id,_ in counts.most_common(augment_dexes):
            for page in range(1,min(augment_pages,10)+1):
                if sleep_s:time.sleep(sleep_s)
                payload=_request_json(s,f"{GECKO}/networks/base/dexes/{dex_id}/pools",{"page":page,"include":"base_token,quote_token,dex"},sleep_s)
                for p in _parse_pool_payload(payload,f"dex:{dex_id}"):by_addr.setdefault(p.address,p)
                if len(by_addr)>=max_pools:return list(by_addr.values())[:max_pools]
    return list(by_addr.values())[:max_pools]

def pad_address(addr:str)->str:return addr.lower().replace("0x","").rjust(64,"0")
def decode_address(data:str)->str:
    h=data[2:] if data.startswith("0x") else data
    return "0x"+h[-40:] if len(h)>=64 else ""
def decode_uint(data:str)->int:return 0 if not data or data=="0x" else int(data,16)
def safe_call(rpc:Rpc,to:str,data:str,block:str)->str:
    try:return rpc.eth_call(to,data,block)
    except Exception:return ""

def probe_pool(rpc:Rpc,pool:Pool,block:str)->dict[str,Any]:
    code=rpc.code(pool.address,block);out={"address":pool.address,"dex_id":pool.dex_id,"name":pool.name,"has_code":bool(code and code!="0x"),"api_token0":pool.token0,"api_token1":pool.token1,"reported_fee_pct":pool.reported_fee_pct}
    if not out["has_code"]:return out
    t0=decode_address(safe_call(rpc,pool.address,SEL_TOKEN0,block));t1=decode_address(safe_call(rpc,pool.address,SEL_TOKEN1,block));res=safe_call(rpc,pool.address,SEL_GET_RESERVES,block);slot=safe_call(rpc,pool.address,SEL_SLOT0,block);fee=safe_call(rpc,pool.address,SEL_FEE,block)
    out.update({"rpc_token0":t0.lower(),"rpc_token1":t1.lower(),"token_match":{t0.lower(),t1.lower()}=={pool.token0.lower(),pool.token1.lower()} if t0 and t1 else False,"has_getReserves":bool(res and res!="0x"),"has_slot0":bool(slot and slot!="0x"),"fee_raw":decode_uint(fee) if fee else None})
    for i,token in enumerate((pool.token0,pool.token1)):
        bal=safe_call(rpc,token,SEL_BALANCE_OF+pad_address(pool.address),block);dec=safe_call(rpc,token,SEL_DECIMALS,block);out[f"balance{i}_raw"]=decode_uint(bal) if bal else None;out[f"decimals{i}"]=decode_uint(dec) if dec else None
    if out["has_getReserves"]:
        h=res[2:] if res.startswith("0x") else res
        if len(h)>=128:out["reserve0_raw"]=int(h[:64],16);out["reserve1_raw"]=int(h[64:128],16)
    return out

def build_adjacency(pools:Iterable[Pool]):
    adj={}
    for p in pools:
        for a,b in ((p.token0,p.token1),(p.token1,p.token0)):
            rate=p.discovery_rate(a,b)
            if rate and rate>0 and math.isfinite(rate):adj.setdefault(a,[]).append((b,p,rate))
    return adj

def find_discovery_cycles(pools:list[Pool],max_hops:int=4,top_k:int=200)->list[dict[str,Any]]:
    adj=build_adjacency(pools);found=[]
    for start in adj:
        stack=[(start,[start],[],1.0)]
        while stack:
            node,nodes,paddrs,rp=stack.pop()
            if len(paddrs)>=max_hops:continue
            for nxt,pool,rate in adj.get(node,[]):
                if pool.address in paddrs:continue
                nr=rp*rate;np=paddrs+[pool.address]
                if nxt==start and len(np)>=2:
                    edge=(nr-1)*10000
                    if edge>0:found.append({"stage":"DISCOVERED","start_token":start,"hops":len(np),"gross_spot_edge_bps":edge,"pool_addresses":"|".join(np),"token_path":"|".join(nodes+[start])})
                    continue
                if nxt in nodes:continue
                stack.append((nxt,nodes+[nxt],np,nr))
    dedup={}
    for x in found:
        key=tuple(sorted(x["pool_addresses"].split("|")))
        if key not in dedup or x["gross_spot_edge_bps"]>dedup[key]["gross_spot_edge_bps"]:dedup[key]=x
    return sorted(dedup.values(),key=lambda x:x["gross_spot_edge_bps"],reverse=True)[:top_k]

def balancer_balances(rpc:Rpc,tokens:Iterable[str],block:str):
    out={}
    for token in sorted(set(t.lower() for t in tokens if t)):
        r=safe_call(rpc,token,SEL_BALANCE_OF+pad_address(BALANCER_V2_VAULT),block);out[token]=decode_uint(r) if r else None
    return out

def own_complete_graph_count(m:int)->int:
    n=m+2;return n*(n-1)//2

def write_csv(path:Path,rows:list[dict[str,Any]]):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not rows:path.write_text("",encoding="utf-8");return
    fields=[]
    for row in rows:
        for k in row:
            if k not in fields:fields.append(k)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def run(args):
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True);pools=fetch_top_pools(args.pages,args.max_pools,args.sleep,args.augment_dexes,args.augment_pages);write_csv(out/"v7_pools.csv",[asdict(p) for p in pools]);tokens=sorted({p.token0 for p in pools}|{p.token1 for p in pools});cands=find_discovery_cycles(pools,args.max_hops,args.top_candidates);write_csv(out/"v7_candidates.csv",cands)
    report={"network":"base","chain_id":BASE_CHAIN_ID,"foreign_pools_discovered":len(pools),"unique_foreign_tokens":len(tokens),"own_complete_graph_pools_with_RUBC_RUBX":own_complete_graph_count(len(tokens)),"total_physical_pools_conceptual":len(pools)+own_complete_graph_count(len(tokens)),"discovery_candidates":len(cands),"discovery_source_counts":dict(Counter(p.discovery_source for p in pools)),"dex_counts":dict(Counter(p.dex_id for p in pools)),"note":"DISCOVERED cycles are not executable PnL until exact quote/fork validation."}
    url=os.environ.get("BASE_RPC_URL","").strip()
    if url:
        rpc=Rpc(url);bn=rpc.latest_block();block=hex(bn);report["block_number"]=bn;report["balancer_v2_vault"]=BALANCER_V2_VAULT;report["balancer_v2_vault_has_code"]=bool(rpc.code(BALANCER_V2_VAULT,block) not in ("","0x"));states=[]
        for p in sorted(pools,key=lambda x:x.reserve_usd,reverse=True)[:args.rpc_probe_pools]:
            try:states.append(probe_pool(rpc,p,block))
            except Exception as e:states.append({"address":p.address,"dex_id":p.dex_id,"error":str(e)})
        write_csv(out/"v7_rpc_state.csv",states);report.update({"rpc_pools_probed":len(states),"rpc_contracts_with_code":sum(bool(x.get("has_code")) for x in states),"rpc_token_matches":sum(bool(x.get("token_match")) for x in states),"rpc_cpmm_like":sum(bool(x.get("has_getReserves")) for x in states),"rpc_clmm_like":sum(bool(x.get("has_slot0")) for x in states),"balancer_token_balance_checks":balancer_balances(rpc,tokens[:args.vault_token_checks],block)})
    else:report["rpc_status"]="SKIPPED: set BASE_RPC_URL"
    (out/"v7_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8");return report

def cli():
    p=argparse.ArgumentParser();p.add_argument("--pages",type=int,default=10);p.add_argument("--max-pools",type=int,default=240);p.add_argument("--augment-dexes",type=int,default=5);p.add_argument("--augment-pages",type=int,default=2);p.add_argument("--max-hops",type=int,default=4);p.add_argument("--top-candidates",type=int,default=200);p.add_argument("--rpc-probe-pools",type=int,default=80);p.add_argument("--vault-token-checks",type=int,default=30);p.add_argument("--sleep",type=float,default=15.0);p.add_argument("--out",default="artifacts");args=p.parse_args();print(json.dumps(run(args),indent=2))
if __name__=="__main__":cli()
