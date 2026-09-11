from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import requests

from synergy_graph.v7 import GECKO, BALANCER_V2_VAULT, Pool, Rpc, _addr, _num, balancer_balances, find_discovery_cycles, own_complete_graph_count, probe_pool, write_csv


def fetch_top_pools_resilient(pages: int, max_pools: int, base_sleep: float, max_retries: int = 10) -> list[Pool]:
    pools: list[Pool] = []
    session = requests.Session()
    session.headers.update({"accept": "application/json;version=20230203", "user-agent": "synergy-graph-v7-live/0.7.3"})
    for page in range(1, pages + 1):
        payload = None
        for attempt in range(max_retries):
            r = session.get(f"{GECKO}/networks/base/pools", params={"page": page, "include": "base_token,quote_token,dex"}, timeout=40)
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else min(90.0, base_sleep * (attempt + 2))
                except ValueError:
                    delay = min(90.0, base_sleep * (attempt + 2))
                time.sleep(max(base_sleep, delay))
                continue
            if 500 <= r.status_code < 600:
                time.sleep(min(60.0, base_sleep * (attempt + 1)))
                continue
            r.raise_for_status()
            payload = r.json()
            break
        if payload is None:
            raise RuntimeError(f"GeckoTerminal page {page} exhausted {max_retries} retries")
        included = {x.get("id", ""): x for x in payload.get("included", [])}
        for item in payload.get("data", []):
            a = item.get("attributes", {}); rel = item.get("relationships", {})
            b_id = (((rel.get("base_token") or {}).get("data") or {}).get("id"))
            q_id = (((rel.get("quote_token") or {}).get("data") or {}).get("id"))
            d_id = (((rel.get("dex") or {}).get("data") or {}).get("id")) or ""
            bi = included.get(b_id or "", {}).get("attributes", {}); qi = included.get(q_id or "", {}).get("attributes", {})
            p = Pool((a.get("address") or _addr(item.get("id"))).lower(), d_id, a.get("name") or "", _addr(b_id).lower(), _addr(q_id).lower(), bi.get("symbol") or "", qi.get("symbol") or "", _num(a.get("reserve_in_usd")), _num(a.get("base_token_price_usd")), _num(a.get("quote_token_price_usd")), _num(a.get("pool_fee_percentage")))
            if p.address and p.token0 and p.token1:
                pools.append(p)
            if len(pools) >= max_pools:
                return pools[:max_pools]
        time.sleep(base_sleep)
    return pools[:max_pools]


def run(args: argparse.Namespace) -> dict:
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    pools = fetch_top_pools_resilient(args.pages, args.max_pools, args.sleep, args.max_retries)
    write_csv(out / "v7_pools.csv", [asdict(p) for p in pools])
    tokens = sorted({p.token0 for p in pools} | {p.token1 for p in pools})
    candidates = find_discovery_cycles(pools, args.max_hops, args.top_candidates)
    write_csv(out / "v7_candidates.csv", candidates)
    rpc = Rpc(args.rpc_url)
    block_number = rpc.latest_block(); block = hex(block_number)
    states = []
    for p in sorted(pools, key=lambda x: x.reserve_usd, reverse=True)[:args.rpc_probe_pools]:
        try:
            states.append(probe_pool(rpc, p, block))
        except Exception as e:
            states.append({"address": p.address, "dex_id": p.dex_id, "error": str(e)})
    write_csv(out / "v7_rpc_state.csv", states)
    report = {
        "network": "base", "chain_id": 8453, "block_number": block_number,
        "foreign_pools_discovered": len(pools), "unique_foreign_tokens": len(tokens),
        "own_complete_graph_pools_with_RUBC_RUBX": own_complete_graph_count(len(tokens)),
        "total_physical_pools_conceptual": len(pools) + own_complete_graph_count(len(tokens)),
        "discovery_candidates": len(candidates), "rpc_pools_probed": len(states),
        "rpc_contracts_with_code": sum(bool(x.get("has_code")) for x in states),
        "rpc_token_matches": sum(bool(x.get("token_match")) for x in states),
        "rpc_cpmm_like": sum(bool(x.get("has_getReserves")) for x in states),
        "rpc_clmm_like": sum(bool(x.get("has_slot0")) for x in states),
        "balancer_v2_vault": BALANCER_V2_VAULT,
        "balancer_v2_vault_has_code": bool(rpc.code(BALANCER_V2_VAULT, block) not in ("", "0x")),
        "balancer_token_balance_checks": balancer_balances(rpc, tokens[:args.vault_token_checks], block),
        "note": "DISCOVERED cycles are candidate generation only; exact same-block quote/fork gates follow."
    }
    (out / "v7_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def cli() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pages", type=int, default=12); p.add_argument("--max-pools", type=int, default=240)
    p.add_argument("--max-hops", type=int, default=5); p.add_argument("--top-candidates", type=int, default=500)
    p.add_argument("--rpc-probe-pools", type=int, default=30); p.add_argument("--vault-token-checks", type=int, default=20)
    p.add_argument("--sleep", type=float, default=8.0); p.add_argument("--max-retries", type=int, default=10)
    p.add_argument("--rpc-url", default="https://mainnet.base.org"); p.add_argument("--out", default="artifacts")
    args = p.parse_args(); print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    cli()
