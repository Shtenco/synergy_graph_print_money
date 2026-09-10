from __future__ import annotations

import argparse, csv, json, os
from dataclasses import fields
from pathlib import Path

from synergy_graph.quotes import optimize_aerodrome_v2_cycle, token_price_usd
from synergy_graph.uniswap_v3 import uniswap_v3_discovery_candidates, optimize_uniswap_v3_cycle
from synergy_graph.v7 import Pool, Rpc, write_csv

BASE_WETH = "0x4200000000000000000000000000000000000006"


def load_pools(path: Path) -> list[Pool]:
    allowed = {f.name for f in fields(Pool)}
    out = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            kwargs = {k: v for k, v in row.items() if k in allowed}
            for k in ("reserve_usd","token0_price_usd","token1_price_usd","token0_price_token1","token1_price_token0","reported_fee_pct"):
                kwargs[k] = float(kwargs.get(k) or 0)
            out.append(Pool(**kwargs))
    return out


def load_csv(path: Path) -> list[dict[str,str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--artifacts",default="artifacts")
    p.add_argument("--max-candidates",type=int,default=60)
    p.add_argument("--max-flash-usd",type=float,default=50000)
    p.add_argument("--mev-guard-bps",type=float,default=5)
    p.add_argument("--gas-reserve-usd",type=float,default=.05)
    p.add_argument("--max-hops",type=int,default=4)
    args=p.parse_args()

    root=Path(args.artifacts)
    report_path=root/"v7_report.json"
    report=json.loads(report_path.read_text(encoding="utf-8"))
    block_number=int(report["block_number"]);block=hex(block_number)
    rpc_url=os.environ.get("BASE_RPC_URL","").strip()
    if not rpc_url:raise SystemExit("BASE_RPC_URL is required for quote verification")
    rpc=Rpc(rpc_url)
    pools=load_pools(root/"v7_pools.csv")
    gas_price_wei=int(rpc.call("eth_gasPrice",[]),16)
    eth_price_usd=token_price_usd(BASE_WETH,pools)

    rows=[]

    # 1) Exact Uniswap V3: build fresh candidates only from pools that can be
    # validated against the canonical Base V3 factory and quoted at the pinned block.
    uni_candidates=uniswap_v3_discovery_candidates(pools,max_hops=args.max_hops,top_k=args.max_candidates)
    write_csv(root/"v7_uniswap_v3_candidates.csv",uni_candidates)
    for c in uni_candidates:
        q=optimize_uniswap_v3_cycle(
            rpc,c,pools,block,
            max_flash_usd=args.max_flash_usd,
            mev_guard_bps=args.mev_guard_bps,
            gas_reserve_usd=args.gas_reserve_usd,
        )
        if q is not None:
            q["gas_price_wei_snapshot"]=gas_price_wei
            q["eth_price_usd_snapshot"]=eth_price_usd
            rows.append(q)

    # 2) Retain classic Aerodrome V2 exact validation for any discovery route
    # composed entirely of pools verified by its factory.
    discovery_candidates=load_csv(root/"v7_candidates.csv")[:args.max_candidates]
    for c in discovery_candidates:
        q=optimize_aerodrome_v2_cycle(
            rpc,c,pools,block,
            max_flash_usd=args.max_flash_usd,
            mev_guard_bps=args.mev_guard_bps,
            gas_reserve_usd=args.gas_reserve_usd,
        )
        if q is not None:
            q["adapter"]="aerodrome_v2"
            q["gas_price_wei_snapshot"]=gas_price_wei
            q["eth_price_usd_snapshot"]=eth_price_usd
            rows.append(q)

    rows.sort(key=lambda x:float(x["guarded_net_usd"]),reverse=True)
    write_csv(root/"v7_quote_results.csv",rows)
    verified=[x for x in rows if x["stage"]=="QUOTE_VERIFIED"]
    best=verified[0] if verified else None
    (root/"v7_best_quote.json").write_text(json.dumps(best or {},indent=2),encoding="utf-8")

    report["gas_price_wei_snapshot"]=gas_price_wei
    report["eth_price_usd_snapshot"]=eth_price_usd
    report["uniswap_v3_topology_candidates_for_exact_quote"]=len(uni_candidates)
    report["exact_quote_rows"]=len(rows)
    report["quote_verified_cycles"]=len(verified)
    report["quote_verified_by_adapter"]={
        "uniswap_v3":sum(x.get("adapter")=="uniswap_v3" and x.get("stage")=="QUOTE_VERIFIED" for x in rows),
        "aerodrome_v2":sum(x.get("adapter")=="aerodrome_v2" and x.get("stage")=="QUOTE_VERIFIED" for x in rows),
    }
    report["best_quote"]=best
    report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"quoted":len(rows),"verified":len(verified),"by_adapter":report["quote_verified_by_adapter"],"best":best},indent=2))

if __name__=="__main__":main()
