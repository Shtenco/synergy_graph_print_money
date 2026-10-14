from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _grid(lo: float, hi: float) -> list[float]:
    base = [lo, 2000.0, 2500.0, 3000.0, 5000.0, 7500.0, 10000.0, hi]
    return sorted({round(x, 2) for x in base if lo <= x <= hi})


def main() -> None:
    ap = argparse.ArgumentParser(description="V8 strict 2k-10k flash/POL capital envelope")
    ap.add_argument("--mode", choices=["pure", "min-pol", "both"], default="both")
    ap.add_argument("--min-flash-usd", type=float, default=2000.0)
    ap.add_argument("--max-flash-usd", type=float, default=10000.0)
    ap.add_argument("--strict-packet", default="data/results/v7_4_stateful_token_closed_packet.csv")
    ap.add_argument("--qe-packet", default="data/results/v7_3_optimal_packet_5pct.csv")
    ap.add_argument("--out", default="data/results/v8_flash_2k_10k_envelope.json")
    args = ap.parse_args()

    if args.min_flash_usd <= 0 or args.max_flash_usd < args.min_flash_usd:
        raise SystemExit("bad flash range")

    strict = _rows(Path(args.strict_packet))
    qe = _rows(Path(args.qe_packet))

    # Sequential token-closed cycles reuse the same principal denomination.
    principal_by_symbol: dict[str, float] = {}
    for r in strict:
        sym = r["start_symbol"]
        principal_by_symbol[sym] = max(principal_by_symbol.get(sym, 0.0), float(r["input_usd"]))

    strict_draw = sum(principal_by_symbol.values())
    strict_gross = sum(float(r["gross_usd"]) for r in strict)
    strict_model_net = sum(float(r["net_usd"]) for r in strict)

    # V7.3 is useful only as QE-potential evidence. It is intentionally NOT
    # promoted to executable status because V7.4 found denomination deficits.
    qe_model_net = sum(float(r["strict_net_after_mev_gas"]) for r in qe)
    qe_peak_temp = max(float(r["peak_qe"]) for r in qe) if qe else 0.0
    qe_routes_rubc = sum(r["route"].upper() == "RUBC" for r in qe)
    qe_routes_rubx = sum(r["route"].upper() == "RUBX" for r in qe)

    envelope = []
    for budget in _grid(args.min_flash_usd, args.max_flash_usd):
        pure = budget + 1e-9 >= strict_draw
        min_pol = max(0.0, strict_draw - budget)
        envelope.append(
            {
                "flash_budget_usd": budget,
                "known_strict_draw_usd": strict_draw,
                "pure_flash_known_packet_fits": pure,
                "minimum_pol_to_cover_draw_shortfall_usd": min_pol,
                "strict_surrogate_gross_usd": strict_gross,
                "strict_surrogate_net_after_existing_cost_model_usd": strict_model_net,
                "qe_5pct_relaxed_surrogate_net_usd": qe_model_net,
                "qe_5pct_peak_temporary_qe_reference_units": qe_peak_temp,
                "exact_v8_1_fork_status": "REQUIRES_FOUNDRY_FORK_EXECUTION",
            }
        )

    result = {
        "accounting_contract": {
            "hardnav": "external ERC20 only",
            "rubc_rubx_value_in_hardnav": 0,
            "flash_settlement": "token-by-token principal + actual fee",
            "modes": ["PURE_FLASH", "FLASH_MIN_POL"],
        },
        "known_strict_v7_4_packet": {
            "principal_by_symbol_usd": principal_by_symbol,
            "concurrent_draw_usd": strict_draw,
            "gross_hard_transfer_usd": strict_gross,
            "model_net_usd": strict_model_net,
            "cycle_count": len(strict),
            "status": "TOKEN_CLOSED_SURROGATE; EXACT V8.1 FORK STILL REQUIRED",
        },
        "qe_5pct_v7_3_evidence": {
            "model_net_usd": qe_model_net,
            "peak_temporary_qe_reference_units": qe_peak_temp,
            "rubc_routes": qe_routes_rubc,
            "rubx_routes": qe_routes_rubx,
            "status": "QE UPLIFT EVIDENCE ONLY; RELAXED DENOMINATION NETTING NOT EXECUTABLE",
        },
        "v8_1_target_proof": {
            "contract": "contracts/V8_1SingleContractFlashGraph.sol",
            "fork_test": "test/V8SingleContractFlashFork.t.sol",
            "pinned_block": 51_148_993,
            "test_flash_weth": 0.65,
            "qe_ratio": 0.05,
            "goal": "QE-gated WETH->VIRTUAL->WETH cycle; repay WETH in-kind; retain post-repayment WETH HardNAV",
        },
        "envelope": envelope,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
