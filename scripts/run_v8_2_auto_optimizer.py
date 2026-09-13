from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from synergy_graph.v8_2_auto_optimizer import (
    ExternalOpportunity,
    SearchSpace,
    compare_capital_modes,
)


def _load_strict_packet(path: Path) -> list[ExternalOpportunity]:
    out: list[ExternalOpportunity] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sym = row["start_symbol"].upper()
            input_usd = float(row["input_usd"])
            gross_usd = float(row["gross_usd"])
            out.append(
                ExternalOpportunity(
                    name=f"run36-r{row['round']}-{sym}-{row['name_path']}",
                    route_required_usd=input_usd,
                    token_delta_usd={sym: gross_usd},
                    gas_usd=max(0.0, gross_usd - float(row["net_usd"])) * 0.15,
                    metadata={
                        "round": int(row["round"]),
                        "pool_path": row["pool_path"],
                        "token_path": row["token_path"],
                        "dex_path": row["dex_path"],
                        "source": "v7_4_stateful_token_closed_packet.csv",
                    },
                )
            )
    return out


def _serialize(ev):
    return {
        "opportunity": ev.opportunity.name,
        "mode": ev.mode.value,
        "flash_budget_usd": ev.flash_budget_usd,
        "edge_count": ev.edge_count,
        "lock_fraction": ev.lock_fraction,
        "total_locked_usd": ev.total_locked_usd,
        "per_edge_locked_usd": ev.per_edge_locked_usd,
        "qe_field": ev.qe.label,
        "rubc_q_over_r": ev.qe.rubc_ratio,
        "rubx_q_over_r": ev.qe.rubx_ratio,
        "rubc_pulsed_edges": ev.qe.rubc_pulsed_edges,
        "rubx_pulsed_edges": ev.qe.rubx_pulsed_edges,
        "baseline_free_hard_usd": ev.baseline_free_hard_usd,
        "qe_unlock_usd": ev.qe_unlock_usd,
        "post_qe_free_hard_usd": ev.post_qe_free_hard_usd,
        "route_required_usd": ev.opportunity.route_required_usd,
        "qe_created_feasibility": ev.qe_created_feasibility,
        "gross_external_hardnav_usd": ev.settlement.gross_external_hardnav_usd,
        "competition_reserve_usd": ev.settlement.competition_reserve_usd,
        "flash_fee_usd": ev.settlement.flash_fee_usd,
        "gas_usd": ev.settlement.gas_usd,
        "required_pol_usd": ev.settlement.required_pol_usd,
        "net_hardnav_usd": ev.settlement.net_hardnav_usd,
        "score": ev.score,
        "metadata": ev.opportunity.metadata or {},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="V8.2 QE-aware $500-$10k auto optimizer")
    ap.add_argument("--strict-packet", default="data/results/v7_4_stateful_token_closed_packet.csv")
    ap.add_argument("--out", default="data/results/v8_2_qe_auto_optimizer.json")
    ap.add_argument("--top-k", type=int, default=50)
    ap.add_argument("--max-pol-usd", type=float, default=500.0)
    ap.add_argument("--flash-fee-bps", type=float, default=0.0)
    args = ap.parse_args()

    opportunities = _load_strict_packet(Path(args.strict_packet))
    space = SearchSpace(
        flash_budgets_usd=(500.0, 750.0, 1000.0, 1500.0, 2000.0, 2500.0, 3000.0, 5000.0, 7500.0, 10000.0),
        qe_ratios=(0.0, 0.005, 0.0125, 0.025, 0.0375, 0.05),
        edge_counts=tuple(range(2, 11)),
        lock_fractions=(0.10, 0.20, 0.205, 0.21, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90),
        pulse_edge_counts=(1, 2, 3, 4),
        virtual_fee_bps=30,
        flash_fee_bps=args.flash_fee_bps,
        mev_reserve_fraction=0.35,
        max_pol_usd=args.max_pol_usd,
    )
    modes = compare_capital_modes(
        opportunities,
        space=space,
        min_pol_cap_usd=args.max_pol_usd,
        top_k=args.top_k,
    )
    result = {
        "version": "V8.2",
        "qe_value_source": "NONE_INTERNAL; external LP only",
        "causality_rule": "same external route infeasible before QE, feasible after QE",
        "search_space": {
            "flash_usd": [500, 750, 1000, 1500, 2000, 2500, 3000, 5000, 7500, 10000],
            "qe_q_over_r": [0, 0.005, 0.0125, 0.025, 0.0375, 0.05],
            "fields": ["RUBC", "RUBX", "RUBC+RUBX"],
            "active_virtual_edges": [2, 3, 4, 5, 6, 7, 8, 9, 10],
            "capital_modes": ["PURE_FLASH", "FLASH_MIN_POL"],
            "max_pol_usd": args.max_pol_usd,
        },
        "source_opportunities": len(opportunities),
        "PURE_FLASH": [_serialize(x) for x in modes["PURE_FLASH"]],
        "FLASH_MIN_POL": [_serialize(x) for x in modes["FLASH_MIN_POL"]],
        "status": "OFFCHAIN DESIGN SEARCH; exact same-block Base quotes and Foundry fork remain the execution gate",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
