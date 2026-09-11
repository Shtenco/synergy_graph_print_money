from __future__ import annotations

"""V7.2 global graph actuator preflight.

Consumes the V7 `v7_pools.csv` evidence snapshot and measures how a
heterogeneous QE->BUY vector changes RUBC-linked cycle fields in the complete
protocol-owned K_n graph and in monetary triangles containing one foreign
Base pool. This is discovery/falsification tooling, not executable PnL.
"""

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import median

ZERO = "0x0000000000000000000000000000000000000000"
WETH = "0x4200000000000000000000000000000000000006"
RUBC = "RUBC"
RUBX = "RUBX"


def f(v: object) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def canon(token: str) -> str:
    t = (token or "").lower()
    return WETH if t == ZERO else t


def fee_fraction(row: dict[str, str], fallback_bps: float) -> float:
    # Names in the snapshot often contain the fee even when the dedicated
    # aggregator field is zero.
    m = re.search(r"([0-9]*\.?[0-9]+)%", row.get("name", ""))
    if m:
        return float(m.group(1)) / 100.0
    reported = f(row.get("reported_fee_pct"))
    if reported > 0:
        return reported / 100.0
    return fallback_bps / 10_000.0


def percentile_rank(values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(values.values())
    n = len(ordered)
    out: dict[str, float] = {}
    for key, value in values.items():
        # deterministic empirical CDF, in (0, 1]
        out[key] = sum(x <= value for x in ordered) / n
    return out


def gfactor(r: float, gamma: float) -> float:
    # Post SELL-RUBC pulse reciprocal price factor. With no fee this is
    # (1+r)^2. For CPMM with fee: (1+r)(1+gamma*r).
    return (1.0 + r) * (1.0 + gamma * r)


def run(args: argparse.Namespace) -> dict[str, object]:
    with Path(args.pools).open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    for row in rows:
        row["token0"] = canon(row["token0"])
        row["token1"] = canon(row["token1"])

    tokens = sorted({r["token0"] for r in rows} | {r["token1"] for r in rows})
    degree: dict[str, int] = defaultdict(int)
    liquidity: dict[str, float] = defaultdict(float)
    price_obs: dict[str, list[float]] = defaultdict(list)
    symbols: dict[str, str] = {}

    for row in rows:
        t0, t1 = row["token0"], row["token1"]
        reserve = f(row.get("reserve_usd"))
        degree[t0] += 1
        degree[t1] += 1
        liquidity[t0] += reserve
        liquidity[t1] += reserve
        p0, p1 = f(row.get("token0_price_usd")), f(row.get("token1_price_usd"))
        if p0 > 0:
            price_obs[t0].append(p0)
        if p1 > 0:
            price_obs[t1].append(p1)
        if row.get("token0_symbol"):
            symbols[t0] = row["token0_symbol"]
        if row.get("token1_symbol"):
            symbols[t1] = row["token1_symbol"]

    price = {t: (median(price_obs[t]) if price_obs[t] else 0.0) for t in tokens}
    active = [t for t in tokens if price[t] > 0 and liquidity[t] > 0]
    inactive = [t for t in tokens if t not in active]

    centrality = {
        t: math.log1p(max(0.0, liquidity[t])) * math.sqrt(max(1, degree[t]))
        for t in tokens
    }
    ranks = percentile_rank(centrality)
    # This vector is intentionally deterministic, heterogeneous and NOT
    # claimed optimal. The outer V7.2 optimizer will replace it later.
    score = {
        t: ((0.1 + 0.9 * ranks[t] ** 2) if t in active else 0.0)
        for t in tokens
    }

    gamma_own = 1.0 - args.own_fee_bps / 10_000.0
    rubc_reserve_per_incident_pool = (args.own_tvl_usd_per_pool / 2.0) / args.rubc_reference_usd

    # Baseline foreign monetary triangles, used to distinguish genuinely
    # QE-created edges from pre-existing asynchronous aggregator discrepancies.
    def foreign_edges(rmax: float) -> dict[tuple[int, int], float]:
        rs = {t: rmax * score[t] for t in tokens}
        out: dict[tuple[int, int], float] = {}
        for idx, row in enumerate(rows):
            a, b = row["token0"], row["token1"]
            p0, p1 = f(row.get("token0_price_usd")), f(row.get("token1_price_usd"))
            if p0 <= 0 or p1 <= 0:
                continue
            pa, pb = price[a], price[b]
            if pa <= 0 or pb <= 0:
                continue
            gf = 1.0 - fee_fraction(row, args.foreign_fee_fallback_bps)
            # A -> RUBC -> B -> foreign(B->A)
            r1 = (
                pa * gamma_own * gfactor(rs[a], gamma_own)
                * (1.0 / pb) * gamma_own / gfactor(rs[b], gamma_own)
                * (p1 / p0) * gf
            )
            # B -> RUBC -> A -> foreign(A->B)
            r2 = (
                pb * gamma_own * gfactor(rs[b], gamma_own)
                * (1.0 / pa) * gamma_own / gfactor(rs[a], gamma_own)
                * (p0 / p1) * gf
            )
            out[(idx, 0)] = (r1 - 1.0) * 10_000.0
            out[(idx, 1)] = (r2 - 1.0) * 10_000.0
        return out

    baseline_foreign = foreign_edges(0.0)
    grid_results = []

    for rmax in args.pulse_grid:
        rs = {t: rmax * score[t] for t in tokens}

        # Complete K_n contains C(N-1,2) distinct RUBC triangles. Count both
        # directions, but at most one direction of a pair is normally positive.
        own_positive: list[float] = []
        for i, a in enumerate(tokens):
            for b in tokens[i + 1 :]:
                rate_ab = gamma_own**3 * gfactor(rs[a], gamma_own) / gfactor(rs[b], gamma_own)
                rate_ba = gamma_own**3 * gfactor(rs[b], gamma_own) / gfactor(rs[a], gamma_own)
                e1, e2 = (rate_ab - 1.0) * 10_000.0, (rate_ba - 1.0) * 10_000.0
                if e1 > 0:
                    own_positive.append(e1)
                if e2 > 0:
                    own_positive.append(e2)

        fedges = foreign_edges(rmax)
        foreign_positive = [x for x in fedges.values() if x > 0]
        newly_created = [
            x for key, x in fedges.items()
            if x > 0 and baseline_foreign.get(key, float("-inf")) <= 0
        ]
        destroyed = sum(
            1 for key, old in baseline_foreign.items()
            if old > 0 and fedges.get(key, float("-inf")) <= 0
        )

        qe_used = rubc_reserve_per_incident_pool * sum(rs.values())

        # If each actuator leg is immediately reversed using all of the hard
        # asset it just acquired, this is the RUBC recovered by BUYBACK before
        # burn. It is a closure diagnostic only; it does not count as HardNAV.
        recovered = 0.0
        for t in tokens:
            r = rs[t]
            if r <= 0:
                continue
            R = rubc_reserve_per_incident_pool
            q = r * R
            A = (args.own_tvl_usd_per_pool / 2.0) / price[t]
            a_out = A * gamma_own * q / (R + gamma_own * q)
            Rp = R + q
            Ap = A - a_out
            c_back = Rp * gamma_own * a_out / (Ap + gamma_own * a_out)
            recovered += c_back

        burned_if_full_reverse = recovered
        net_supply_if_full_reverse = qe_used - burned_if_full_reverse

        grid_results.append({
            "max_pulse_reserve_fraction": rmax,
            "qe_rubc_used": qe_used,
            "own_rubc_triangle_positive_directions": len(own_positive),
            "own_rubc_triangle_max_edge_bps": max(own_positive) if own_positive else 0.0,
            "own_rubc_triangle_median_edge_bps": median(own_positive) if own_positive else 0.0,
            "foreign_monetary_triangle_positive_directions": len(foreign_positive),
            "foreign_monetary_triangle_newly_created": len(newly_created),
            "foreign_monetary_triangle_destroyed_from_baseline": destroyed,
            "new_foreign_edge_max_bps": max(newly_created) if newly_created else 0.0,
            "new_foreign_edge_median_bps": median(newly_created) if newly_created else 0.0,
            "rubc_recovered_if_all_actuator_legs_reversed": recovered,
            "net_rubc_supply_if_immediate_full_reverse": net_supply_if_full_reverse,
            "buyback_recovery_fraction": recovered / qe_used if qe_used > 0 else 1.0,
        })

    top_nodes = sorted(
        tokens,
        key=lambda t: (centrality[t], liquidity[t], degree[t]),
        reverse=True,
    )[:20]

    n = len(tokens) + 2
    own_kn = n * (n - 1) // 2
    report: dict[str, object] = {
        "stage": "V7_2_GLOBAL_PREFLIGHT",
        "foreign_physical_pools_input": len(rows),
        "canonical_external_assets": len(tokens),
        "active_priced_liquid_external_assets": len(active),
        "inactive_or_unpriced_external_assets": len(inactive),
        "total_vertices_with_RUBC_RUBX": n,
        "conceptual_own_Kn_pools": own_kn,
        "total_conceptual_pools": own_kn + len(rows),
        "distinct_rubc_own_triangles": (n - 1) * (n - 2) // 2,
        "foreign_triangles_with_usable_price_pairs": len(baseline_foreign) // 2,
        "own_fee_bps_assumed": args.own_fee_bps,
        "foreign_unknown_fee_fallback_bps": args.foreign_fee_fallback_bps,
        "own_tvl_usd_per_pool_for_absolute_qe_scaling": args.own_tvl_usd_per_pool,
        "rubc_reference_usd_for_geometry_only": args.rubc_reference_usd,
        "qe_vector": "centrality-weighted deterministic preflight; not optimized",
        "baseline_foreign_positive_directions": sum(x > 0 for x in baseline_foreign.values()),
        "top_foreign_graph_nodes": [
            {
                "token": t,
                "symbol": symbols.get(t, ""),
                "degree": degree[t],
                "foreign_incident_reserve_usd_sum": liquidity[t],
                "qe_score": score[t],
            }
            for t in top_nodes
        ],
        "pulse_grid_results": grid_results,
        "accounting_note": (
            "QE->BUY against protocol-owned pools is an actuator, not profit. "
            "Its Treasury hard-asset gain cancels the same POL hard-asset loss in consolidated HardNAV. "
            "Foreign-linked spot edges are discovery only until exact pinned-block finite-size quote and fork execution."
        ),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def parse_grid(text: str) -> list[float]:
    vals = [float(x.strip()) for x in text.split(",") if x.strip()]
    if any(x < 0 for x in vals):
        raise argparse.ArgumentTypeError("pulse fractions must be non-negative")
    return vals


def cli() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pools", default="artifacts/v7_pools.csv")
    p.add_argument("--out", default="artifacts/v7_2_global_preflight.json")
    p.add_argument("--own-tvl-usd-per-pool", type=float, default=10_000.0)
    p.add_argument("--rubc-reference-usd", type=float, default=1.0)
    p.add_argument("--own-fee-bps", type=float, default=30.0)
    p.add_argument("--foreign-fee-fallback-bps", type=float, default=30.0)
    p.add_argument(
        "--pulse-grid",
        type=parse_grid,
        default=parse_grid("0,0.005,0.01,0.02,0.05"),
        help="comma-separated maximum q/R pulse ratios, e.g. 0.01 = 1%",
    )
    run(p.parse_args())


if __name__ == "__main__":
    cli()
