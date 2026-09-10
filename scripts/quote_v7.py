from __future__ import annotations

import argparse, csv, json, os
from dataclasses import fields
from pathlib import Path

from synergy_graph.quotes import optimize_aerodrome_v2_cycle
from synergy_graph.v7 import Pool, Rpc, write_csv


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
    p=argparse.ArgumentParser();p.add_argument("--artifacts",default="artifacts");p.add_argument("--max-candidates",type=int,default=60);p.add_argument("--max-flash-usd",type=float,default=50000);p.add_argument("--mev-guard-bps",type=float,default=5);p.add_argument("--gas-reserve-usd",type=float,default=.05);args=p.parse_args()
    root=Path(args.artifacts);report_path=root/"v7_report.json";report=json.loads(report_path.read_text(encoding="utf-8"));block_number=int(report["block_number"]);block=hex(block_number)
    rpc_url=os.environ.get("BASE_RPC_URL","").strip()
    if not rpc_url:raise SystemExit("BASE_RPC_URL is required for quote verification")
    rpc=Rpc(rpc_url);pools=load_pools(root/"v7_pools.csv");cands=load_csv(root/"v7_candidates.csv")[:args.max_candidates]
    rows=[]
    for c in cands:
        q=optimize_aerodrome_v2_cycle(rpc,c,pools,block,max_flash_usd=args.max_flash_usd,mev_guard_bps=args.mev_guard_bps,gas_reserve_usd=args.gas_reserve_usd)
        if q is not None:rows.append(q)
    rows.sort(key=lambda x:float(x["guarded_net_usd"]),reverse=True);write_csv(root/"v7_quote_results.csv",rows)
    verified=[x for x in rows if x["stage"]=="QUOTE_VERIFIED"]
    best=verified[0] if verified else None
    (root/"v7_best_quote.json").write_text(json.dumps(best or {},indent=2),encoding="utf-8")
    report["aerodrome_v2_cycles_exactly_quoted"]=len(rows);report["quote_verified_cycles"]=len(verified);report["best_quote"]=best;report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"quoted":len(rows),"verified":len(verified),"best":best},indent=2))

if __name__=="__main__":main()
