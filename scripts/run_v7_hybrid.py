from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from run_v7_live import find_cycles_bounded
from synergy_graph.v7 import BALANCER_V2_VAULT, Rpc, balancer_balances, own_complete_graph_count, probe_pool, write_csv
from synergy_graph.v7_sources import fetch_public_ranked, supplement_aerodrome_v2


def run(args):
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    rpc=Rpc(args.rpc_url); bn=rpc.latest_block(); block=hex(bn)
    ranked,src=fetch_public_ranked(args.pages,args.max_pools,args.sleep,args.max_retries)
    pools,sup=supplement_aerodrome_v2(rpc,block,ranked,args.max_pools,args.factory_scan)
    write_csv(out/"v7_pools.csv",[asdict(p) for p in pools])
    tokens=sorted({p.token0 for p in pools}|{p.token1 for p in pools})
    cands,exp,trunc=find_cycles_bounded(pools,args.max_hops,args.top_candidates,args.max_expansions)
    write_csv(out/"v7_candidates.csv",cands)
    states=[]
    for p in sorted(pools,key=lambda x:x.reserve_usd,reverse=True)[:args.rpc_probe_pools]:
        try: states.append(probe_pool(rpc,p,block))
        except Exception as e: states.append({"address":p.address,"dex_id":p.dex_id,"error":str(e)})
    write_csv(out/"v7_rpc_state.csv",states)
    report={
      "network":"base","chain_id":8453,"block_number":bn,
      "foreign_pools_discovered":len(pools),"public_ranked_pools":len(ranked),
      "public_pages_ok":src.public_pages_ok,"public_pagination_boundary":src.public_boundary,
      "aerodrome_factory_supplement":sup.factory_added,"aerodrome_factory_entries_scanned":sup.factory_scanned,
      "unique_foreign_tokens":len(tokens),
      "priced_foreign_pools_for_discovery":sum(p.token0_price_usd>0 and p.token1_price_usd>0 for p in pools),
      "own_complete_graph_pools_with_RUBC_RUBX":own_complete_graph_count(len(tokens)),
      "total_physical_pools_conceptual":len(pools)+own_complete_graph_count(len(tokens)),
      "discovery_candidates":len(cands),"cycle_search_expansions":exp,"cycle_search_truncated":trunc,
      "rpc_pools_probed":len(states),"rpc_contracts_with_code":sum(bool(x.get("has_code")) for x in states),
      "rpc_token_matches":sum(bool(x.get("token_match")) for x in states),
      "rpc_cpmm_like":sum(bool(x.get("has_getReserves")) for x in states),
      "rpc_clmm_like":sum(bool(x.get("has_slot0")) for x in states),
      "balancer_v2_vault":BALANCER_V2_VAULT,
      "balancer_v2_vault_has_code":bool(rpc.code(BALANCER_V2_VAULT,block) not in ("","0x")),
      "balancer_token_balance_checks":balancer_balances(rpc,tokens[:args.vault_token_checks],block),
      "note":"240-pool graph = public ranked pages plus on-chain Aerodrome V2 factory supplement when public pagination stops. DISCOVERED is not executable PnL."
    }
    (out/"v7_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


def cli():
    p=argparse.ArgumentParser()
    p.add_argument("--pages",type=int,default=12); p.add_argument("--max-pools",type=int,default=240)
    p.add_argument("--max-hops",type=int,default=5); p.add_argument("--top-candidates",type=int,default=500)
    p.add_argument("--max-expansions",type=int,default=300000); p.add_argument("--factory-scan",type=int,default=800)
    p.add_argument("--rpc-probe-pools",type=int,default=30); p.add_argument("--vault-token-checks",type=int,default=20)
    p.add_argument("--sleep",type=float,default=8.0); p.add_argument("--max-retries",type=int,default=10)
    p.add_argument("--rpc-url",default="https://mainnet.base.org"); p.add_argument("--out",default="artifacts")
    run(p.parse_args())

if __name__=="__main__": cli()
