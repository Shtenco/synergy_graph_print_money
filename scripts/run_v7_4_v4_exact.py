from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

from synergy_graph.v7_exact import token_decimals
from synergy_graph.v7_4_uniswap_v4 import quote_exact_input_single, recover_pool_key
from synergy_graph.v7_rpc import ReliableRpc

ZERO = "0x0000000000000000000000000000000000000000"


def num(v: object) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def canon(v: str) -> str:
    return (v or "").lower()


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def run(args: argparse.Namespace) -> dict:
    rpc = ReliableRpc(args.rpc_url)
    block = args.block
    block_hex = hex(block)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    with Path(args.pools).open(newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("dex_id") or "").lower() == "uniswap-v4-base"]

    recovered_rows: list[dict] = []
    failures: list[dict] = []
    quote_successes = 0
    pair_matches = 0

    for idx, row in enumerate(rows):
        pid = (row.get("address") or "").lower()
        try:
            key = recover_pool_key(
                rpc,
                pid,
                block,
                min_block=args.min_block,
                initial_chunk=args.log_chunk,
                min_chunk=args.min_log_chunk,
            )
        except Exception as exc:
            failures.append({"index": idx, "pool_id": pid, "stage": "recover_pool_key", "error": str(exc)[:400]})
            continue

        api0, api1 = canon(row.get("token0", "")), canon(row.get("token1", ""))
        key_pair = {key.currency0.lower(), key.currency1.lower()}
        api_pair = {api0, api1}
        pair_match = key_pair == api_pair
        pair_matches += int(pair_match)

        rec = key.to_dict()
        rec.update({
            "dex_id": row.get("dex_id", ""),
            "name": row.get("name", ""),
            "api_token0": api0,
            "api_token1": api1,
            "pair_match": pair_match,
            "quote_usd_target": args.quote_usd,
        })

        for side, token, price in (
            ("0to1", key.currency0.lower(), num(row.get("token0_price_usd")) if api0 == key.currency0.lower() else num(row.get("token1_price_usd"))),
            ("1to0", key.currency1.lower(), num(row.get("token1_price_usd")) if api1 == key.currency1.lower() else num(row.get("token0_price_usd"))),
        ):
            if price <= 0:
                rec[f"{side}_status"] = "SKIP_NO_PRICE"
                continue
            try:
                decimals = 18 if token == ZERO else token_decimals(rpc, token, block_hex)
                amount_in = int(args.quote_usd / price * (10 ** decimals))
                amount_in = min(amount_in, (1 << 128) - 1)
                if amount_in <= 0:
                    raise ValueError("sized amount is zero")
                amount_out, gas_estimate = quote_exact_input_single(rpc, key, token, amount_in, block)
                rec[f"{side}_status"] = "QUOTE_VERIFIED"
                rec[f"{side}_amount_in_raw"] = amount_in
                rec[f"{side}_amount_out_raw"] = amount_out
                rec[f"{side}_gas_estimate"] = gas_estimate
                quote_successes += 1
            except Exception as exc:
                rec[f"{side}_status"] = "QUOTE_ERROR"
                rec[f"{side}_error"] = str(exc)[:400]

        recovered_rows.append(rec)

    write_csv(outdir / "v7_4_v4_poolkeys_and_quotes.csv", recovered_rows)
    write_csv(outdir / "v7_4_v4_failures.csv", failures)
    report = {
        "stage": "V7_4_V4_PINNED_EXACT",
        "block": block,
        "uniswap_v4_rows_input": len(rows),
        "poolkeys_recovered": len(recovered_rows),
        "snapshot_pair_matches": pair_matches,
        "exact_directional_quotes_completed": quote_successes,
        "recovery_failures": len(failures),
        "quote_usd_target": args.quote_usd,
        "rpc_metrics": rpc.metrics(),
        "note": "V4 PoolId is recovered from PoolManager Initialize logs. Quotes use Base V4Quoter at the same pinned block. Failures are not replaced by CPMM surrogates.",
    }
    (outdir / "v7_4_v4_exact_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def cli() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pools", default="artifacts/v7_pools.csv")
    p.add_argument("--block", type=int, required=True)
    p.add_argument("--rpc-url", default=os.getenv("BASE_RPC_URL", "https://base-rpc.publicnode.com"))
    p.add_argument("--quote-usd", type=float, default=100.0)
    p.add_argument("--min-block", type=int, default=0)
    p.add_argument("--log-chunk", type=int, default=100_000)
    p.add_argument("--min-log-chunk", type=int, default=1_000)
    p.add_argument("--out", default="artifacts")
    run(p.parse_args())


if __name__ == "__main__":
    cli()
