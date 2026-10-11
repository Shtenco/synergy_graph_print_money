"""Conservative triangle-arbitrage and MEV accounting for SAG V7.4.

This module is an accounting/validation layer, not an on-chain quote source.
A route is eligible only when every leg is an exact quote from the same pinned
block. Surrogate spot prices must never be passed as exact quotes.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Sequence


D = Decimal


class PoolOwner(str, Enum):
    PROTOCOL = "protocol"
    FOREIGN = "foreign"


class ExecutionMode(str, Enum):
    PROTOCOL_EXECUTOR = "protocol_executor"
    CONTROLLED_EXTERNAL_EXECUTOR = "controlled_external_executor"
    CONTROLLED_HOOK = "controlled_hook"
    UNCONTROLLED_EXTERNAL_POOLS = "uncontrolled_external_pools"


@dataclass(frozen=True)
class TriangleLeg:
    pool_id: str
    token_in: str
    token_out: str
    amount_in: Decimal
    amount_out: Decimal
    owner: PoolOwner
    block_number: int
    exact_quote: bool


@dataclass(frozen=True)
class TriangleAudit:
    start_token: str
    gross_start_token_profit: Decimal
    all_foreign_pools: bool
    hardnav_eligible: bool
    block_number: int
    reason: str


@dataclass(frozen=True)
class MevSettlement:
    gross_external_profit_usd: Decimal
    protocol_fee_revenue_usd: Decimal
    executor_gross_share_usd: Decimal
    protocol_costs_usd: Decimal
    protocol_net_hardnav_delta_usd: Decimal
    executor_net_before_its_own_costs_usd: Decimal
    execution_mode: ExecutionMode


def audit_triangle(legs: Sequence[TriangleLeg]) -> TriangleAudit:
    """Validate a closed A->B->C->A route with exact same-block quotes.

    This only grants the simple start-token PnL interpretation when all three
    pools are foreign. Mixed protocol/foreign routes need a consolidated
    token-balance ledger before HardNAV attribution; own-only loops cannot
    create external HardNAV.
    """
    if len(legs) != 3:
        raise ValueError("triangle must contain exactly three legs")
    if len({leg.pool_id.lower() for leg in legs}) != 3:
        raise ValueError("triangle must use three distinct pools")
    if any(not leg.exact_quote for leg in legs):
        raise ValueError("every leg must have an exact pinned-block quote")
    blocks = {leg.block_number for leg in legs}
    if len(blocks) != 1:
        raise ValueError("all quotes must use the same pinned block")
    if any(leg.amount_in <= 0 or leg.amount_out <= 0 for leg in legs):
        raise ValueError("all input and output amounts must be positive")
    for i, leg in enumerate(legs):
        nxt = legs[(i + 1) % 3]
        if leg.token_out.lower() != nxt.token_in.lower():
            raise ValueError("token path is not continuous/closed")
        if leg.amount_out != nxt.amount_in:
            raise ValueError("next leg input must equal prior leg output exactly")
    start = legs[0].token_in
    if legs[-1].token_out.lower() != start.lower():
        raise ValueError("triangle does not return to its start token")
    profit = legs[-1].amount_out - legs[0].amount_in
    all_foreign = all(leg.owner == PoolOwner.FOREIGN for leg in legs)
    eligible = all_foreign and profit > 0
    if not all_foreign:
        reason = "mixed/own-pool route: require consolidated external-token ledger; do not book own LP transfers as profit"
    elif profit <= 0:
        reason = "exact closed route has no positive gross start-token profit"
    else:
        reason = "positive exact closed route across foreign pools; subtract all costs before HardNAV credit"
    return TriangleAudit(start, profit, all_foreign, eligible, next(iter(blocks)), reason)


def settle_mev_share(
    *,
    gross_external_profit_usd: Decimal,
    protocol_fee_rate: Decimal,
    protocol_costs_usd: Decimal,
    execution_mode: ExecutionMode,
) -> MevSettlement:
    """Account for MEV capture without inventing an enforceable external tax.

    A protocol fee/share is recognized only for controlled hooks or an
    executor/solver agreement. In protocol-owned execution, the protocol's
    trading PnL is not double-counted as a separate fee. Arbitrary independent
    external pools cannot be taxed by this accounting layer.
    """
    gross = D(gross_external_profit_usd)
    rate = D(protocol_fee_rate)
    costs = D(protocol_costs_usd)
    if gross < 0:
        raise ValueError("gross external profit must be non-negative")
    if costs < 0:
        raise ValueError("protocol costs must be non-negative")
    if rate < 0 or rate > 1:
        raise ValueError("protocol fee rate must be between 0 and 1")
    if execution_mode == ExecutionMode.UNCONTROLLED_EXTERNAL_POOLS and rate > 0:
        raise ValueError("cannot charge an involuntary protocol fee on uncontrolled external pools")

    if execution_mode == ExecutionMode.PROTOCOL_EXECUTOR:
        fee = D("0")
        executor_share = D("0")
        protocol_net = gross - costs
    elif execution_mode in (
        ExecutionMode.CONTROLLED_EXTERNAL_EXECUTOR,
        ExecutionMode.CONTROLLED_HOOK,
    ):
        fee = gross * rate
        executor_share = gross - fee
        protocol_net = fee - costs
    else:
        fee = D("0")
        executor_share = gross
        protocol_net = -costs

    return MevSettlement(
        gross_external_profit_usd=gross,
        protocol_fee_revenue_usd=fee,
        executor_gross_share_usd=executor_share,
        protocol_costs_usd=costs,
        protocol_net_hardnav_delta_usd=protocol_net,
        executor_net_before_its_own_costs_usd=executor_share,
        execution_mode=execution_mode,
    )


def scenario_net_after_reserve(
    gross_external_profit_usd: Decimal,
    reserve_rate: Decimal,
    costs_usd: Decimal,
) -> Decimal:
    """Return a scenario estimate only; this is not realized protocol revenue."""
    gross = D(gross_external_profit_usd)
    rate = D(reserve_rate)
    costs = D(costs_usd)
    if gross < 0 or costs < 0 or rate < 0 or rate > 1:
        raise ValueError("invalid scenario inputs")
    return gross * (D("1") - rate) - costs
