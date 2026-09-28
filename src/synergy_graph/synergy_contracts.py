from __future__ import annotations
from typing import Any

from .v7_4_eurasian_qe import simulate_packets

CONTRACT_ID = "synergy.economy.monetary-simulation/v1"
AUTHORITY = "monetary_simulation"


def monetary_simulation_payload(*, run_id: str, packets: int = 1, starting_hardnav_usd: float = 1.0) -> dict[str, Any]:
    if not run_id.strip() or packets <= 0:
        raise ValueError("run_id and positive packets required")
    _, _, rows = simulate_packets(packets, starting_hardnav_usd=starting_hardnav_usd)
    last = rows[-1]
    return {
        "run_id": run_id,
        "packets": packets,
        "starting_hardnav_usd": float(starting_hardnav_usd),
        "modeled_consolidated_hardnav_usd": float(last.consolidated_system_hardnav_usd),
        "modeled_external_lp_value_usd": float(last.system_external_lp_value_usd),
        "modeled_bridge_reserve_usd": float(last.bridge_reserve_usd),
        "transient_price_impact_fraction": float(last.transient_price_impact_fraction),
        "simulation_only": True,
        "external_profit_realized": False,
        "accounting_authority": False,
        "capital_authorization": False,
    }
