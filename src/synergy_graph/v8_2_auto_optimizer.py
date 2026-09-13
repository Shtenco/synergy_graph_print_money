from __future__ import annotations

"""V8.2 QE-aware auto optimizer.

This module searches execution *designs*, not relaxed USD PnL.

Core invariants:
1. RUBC/RUBX have zero HardNAV value.
2. QE is an actuator / liquidity-unlock mechanism, never the source of hard value.
3. Every borrowed ERC-20 must settle principal + fee in-kind.
4. A candidate may only be credited to QE when the same design is infeasible
   before QE and feasible after QE (or an explicit graph-uplift test says so).
5. Final objective is risk-adjusted external HardNAV after gas, flash fees and
   any permanent-liquidity (POL) dependence.

The live Base scanner can feed exact same-block external opportunities into
this optimizer. V8.2 then searches:
- RUBC and RUBX independently or together,
- q/R from 0..5%,
- flash budget from $500..$10,000,
- 2..10 active virtual edges,
- lock fraction / pulse count,
- PURE_FLASH and FLASH_MIN_POL settlement modes.
"""

from dataclasses import dataclass
from enum import Enum
from itertools import product
from math import inf
from typing import Iterable, Mapping, Sequence

BPS = 10_000
QE_MAX_RATIO = 0.05


class CapitalMode(str, Enum):
    PURE_FLASH = "PURE_FLASH"
    FLASH_MIN_POL = "FLASH_MIN_POL"


@dataclass(frozen=True)
class HardToken:
    symbol: str
    price_usd: float = 1.0


@dataclass(frozen=True)
class ExternalOpportunity:
    """Strict external hard-flow opportunity.

    `token_delta_usd` is the final external hard-token change after *all*
    foreign legs of the packet have executed. Internal RUBC/RUBX movements
    are excluded by definition.
    """

    name: str
    route_required_usd: float
    token_delta_usd: Mapping[str, float]
    gas_usd: float = 0.0
    metadata: Mapping[str, object] | None = None

    @property
    def gross_external_hardnav_usd(self) -> float:
        return float(sum(self.token_delta_usd.values()))


@dataclass(frozen=True)
class SearchSpace:
    flash_budgets_usd: Sequence[float] = (
        500.0, 750.0, 1000.0, 1500.0, 2000.0, 2500.0,
        3000.0, 5000.0, 7500.0, 10000.0,
    )
    qe_ratios: Sequence[float] = (0.0, 0.005, 0.0125, 0.025, 0.0375, 0.05)
    edge_counts: Sequence[int] = tuple(range(2, 11))
    lock_fractions: Sequence[float] = (0.10, 0.20, 0.205, 0.21, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90)
    pulse_edge_counts: Sequence[int] = (1, 2, 3, 4)
    virtual_fee_bps: int = 30
    flash_fee_bps: float = 0.0
    mev_reserve_fraction: float = 0.35
    max_pol_usd: float = 0.0


@dataclass(frozen=True)
class QEVector:
    rubc_ratio: float
    rubx_ratio: float
    rubc_pulsed_edges: int
    rubx_pulsed_edges: int

    @property
    def active(self) -> bool:
        return self.rubc_ratio > 0 or self.rubx_ratio > 0

    @property
    def label(self) -> str:
        if self.rubc_ratio > 0 and self.rubx_ratio > 0:
            return "RUBC+RUBX"
        if self.rubc_ratio > 0:
            return "RUBC"
        if self.rubx_ratio > 0:
            return "RUBX"
        return "NO_QE"


@dataclass(frozen=True)
class SettlementAudit:
    repayable: bool
    required_pol_usd: float
    required_pol_by_token_usd: Mapping[str, float]
    gross_external_hardnav_usd: float
    competition_reserve_usd: float
    flash_fee_usd: float
    gas_usd: float
    net_hardnav_usd: float


@dataclass(frozen=True)
class DesignEvaluation:
    opportunity: ExternalOpportunity
    mode: CapitalMode
    flash_budget_usd: float
    edge_count: int
    lock_fraction: float
    total_locked_usd: float
    per_edge_locked_usd: float
    qe: QEVector
    baseline_free_hard_usd: float
    qe_unlock_usd: float
    post_qe_free_hard_usd: float
    qe_created_feasibility: bool
    settlement: SettlementAudit
    score: float

    @property
    def feasible(self) -> bool:
        return (
            self.qe.active
            and self.qe_created_feasibility
            and self.settlement.repayable
            and self.settlement.net_hardnav_usd > 0
        )


def cpmm_release_fraction(qe_ratio: float, fee_bps: int = 30) -> float:
    """Fraction of hard reserve released by money->hard QE BUY."""
    if qe_ratio < 0 or qe_ratio > QE_MAX_RATIO + 1e-15:
        raise ValueError(f"qe_ratio must be in [0,{QE_MAX_RATIO}]")
    if fee_bps < 0 or fee_bps >= BPS:
        raise ValueError("invalid virtual fee")
    effective_ratio = qe_ratio * (BPS - fee_bps) / BPS
    return effective_ratio / (1.0 + effective_ratio)


def _validate_space(space: SearchSpace) -> None:
    if not space.flash_budgets_usd:
        raise ValueError("empty flash grid")
    if any(x < 500 - 1e-12 or x > 10_000 + 1e-12 for x in space.flash_budgets_usd):
        raise ValueError("V8.2 flash grid must stay inside $500..$10,000")
    if any(r < 0 or r > QE_MAX_RATIO + 1e-15 for r in space.qe_ratios):
        raise ValueError("QE grid outside 0..5%")
    if any(n < 2 or n > 10 for n in space.edge_counts):
        raise ValueError("edge_count must be 2..10")
    if any(f <= 0 or f >= 1 for f in space.lock_fractions):
        raise ValueError("lock_fraction must be in (0,1)")
    if any(n <= 0 for n in space.pulse_edge_counts):
        raise ValueError("pulse edge count must be positive")
    if not (0 <= space.mev_reserve_fraction < 1):
        raise ValueError("bad MEV reserve")
    if space.flash_fee_bps < 0:
        raise ValueError("negative flash fee")
    if space.max_pol_usd < 0:
        raise ValueError("negative max POL")


def strict_settlement_audit(
    opportunity: ExternalOpportunity,
    *,
    flash_budget_usd: float,
    flash_fee_bps: float,
    mev_reserve_fraction: float,
    mode: CapitalMode,
    max_pol_usd: float,
) -> SettlementAudit:
    """Audit external hard flow after internal graph collapse.

    Deficits are never netted against surpluses of another ERC-20.
    """
    if flash_budget_usd <= 0:
        raise ValueError("flash budget must be positive")

    required: dict[str, float] = {
        symbol: -float(delta)
        for symbol, delta in opportunity.token_delta_usd.items()
        if float(delta) < -1e-12
    }
    required_pol = sum(required.values())

    if mode == CapitalMode.PURE_FLASH:
        repayable = required_pol <= 1e-12
    else:
        repayable = required_pol <= max_pol_usd + 1e-12

    gross = opportunity.gross_external_hardnav_usd
    competition = max(0.0, gross) * mev_reserve_fraction
    flash_fee = flash_budget_usd * flash_fee_bps / BPS
    net = gross - competition - opportunity.gas_usd - flash_fee

    return SettlementAudit(
        repayable=repayable,
        required_pol_usd=required_pol,
        required_pol_by_token_usd=required,
        gross_external_hardnav_usd=gross,
        competition_reserve_usd=competition,
        flash_fee_usd=flash_fee,
        gas_usd=opportunity.gas_usd,
        net_hardnav_usd=net,
    )


def qe_unlock_usd(
    *,
    per_edge_locked_usd: float,
    edge_count: int,
    qe: QEVector,
    virtual_fee_bps: int,
) -> float:
    if per_edge_locked_usd < 0:
        raise ValueError("negative reserve")
    if edge_count < 2 or edge_count > 10:
        raise ValueError("edge_count outside 2..10")
    if qe.rubc_pulsed_edges < 0 or qe.rubx_pulsed_edges < 0:
        raise ValueError("negative pulse count")
    if qe.rubc_pulsed_edges + qe.rubx_pulsed_edges > edge_count:
        raise ValueError("more pulsed edges than active edges")

    rubc = qe.rubc_pulsed_edges * per_edge_locked_usd * cpmm_release_fraction(qe.rubc_ratio, virtual_fee_bps)
    rubx = qe.rubx_pulsed_edges * per_edge_locked_usd * cpmm_release_fraction(qe.rubx_ratio, virtual_fee_bps)
    return rubc + rubx


def evaluate_design(
    opportunity: ExternalOpportunity,
    *,
    mode: CapitalMode,
    flash_budget_usd: float,
    edge_count: int,
    lock_fraction: float,
    qe: QEVector,
    virtual_fee_bps: int = 30,
    flash_fee_bps: float = 0.0,
    mev_reserve_fraction: float = 0.35,
    max_pol_usd: float = 0.0,
    pol_penalty: float = 0.02,
    flash_penalty: float = 0.0001,
) -> DesignEvaluation:
    if opportunity.route_required_usd <= 0:
        raise ValueError("route_required_usd must be positive")

    if flash_budget_usd < opportunity.route_required_usd:
        impossible = strict_settlement_audit(
            opportunity,
            flash_budget_usd=flash_budget_usd,
            flash_fee_bps=flash_fee_bps,
            mev_reserve_fraction=mev_reserve_fraction,
            mode=mode,
            max_pol_usd=max_pol_usd,
        )
        return DesignEvaluation(
            opportunity=opportunity,
            mode=mode,
            flash_budget_usd=flash_budget_usd,
            edge_count=edge_count,
            lock_fraction=lock_fraction,
            total_locked_usd=0.0,
            per_edge_locked_usd=0.0,
            qe=qe,
            baseline_free_hard_usd=flash_budget_usd,
            qe_unlock_usd=0.0,
            post_qe_free_hard_usd=flash_budget_usd,
            qe_created_feasibility=False,
            settlement=impossible,
            score=-inf,
        )

    total_locked = flash_budget_usd * lock_fraction
    per_edge = total_locked / edge_count
    baseline_free = flash_budget_usd - total_locked
    unlock = qe_unlock_usd(
        per_edge_locked_usd=per_edge,
        edge_count=edge_count,
        qe=qe,
        virtual_fee_bps=virtual_fee_bps,
    )
    post_qe_free = baseline_free + unlock

    created = (
        qe.active
        and baseline_free + 1e-12 < opportunity.route_required_usd
        and post_qe_free + 1e-12 >= opportunity.route_required_usd
    )

    settlement = strict_settlement_audit(
        opportunity,
        flash_budget_usd=flash_budget_usd,
        flash_fee_bps=flash_fee_bps,
        mev_reserve_fraction=mev_reserve_fraction,
        mode=mode,
        max_pol_usd=max_pol_usd,
    )

    if not created or not settlement.repayable or settlement.net_hardnav_usd <= 0:
        score = -inf
    else:
        score = (
            settlement.net_hardnav_usd
            - pol_penalty * settlement.required_pol_usd
            - flash_penalty * flash_budget_usd
            - 0.001 * edge_count
        )

    return DesignEvaluation(
        opportunity=opportunity,
        mode=mode,
        flash_budget_usd=flash_budget_usd,
        edge_count=edge_count,
        lock_fraction=lock_fraction,
        total_locked_usd=total_locked,
        per_edge_locked_usd=per_edge,
        qe=qe,
        baseline_free_hard_usd=baseline_free,
        qe_unlock_usd=unlock,
        post_qe_free_hard_usd=post_qe_free,
        qe_created_feasibility=created,
        settlement=settlement,
        score=score,
    )


def _qe_vectors(space: SearchSpace, edge_count: int) -> Iterable[QEVector]:
    max_pulse = min(edge_count, max(space.pulse_edge_counts))
    counts = sorted({n for n in space.pulse_edge_counts if 1 <= n <= max_pulse})
    if not counts:
        return

    for rc, rx in product(space.qe_ratios, repeat=2):
        if rc == 0 and rx == 0:
            continue
        for total_pulsed in counts:
            if rc > 0 and rx > 0:
                for c_count in range(1, total_pulsed):
                    x_count = total_pulsed - c_count
                    if c_count + x_count <= edge_count:
                        yield QEVector(rc, rx, c_count, x_count)
            elif rc > 0:
                if total_pulsed <= edge_count:
                    yield QEVector(rc, 0.0, total_pulsed, 0)
            else:
                if total_pulsed <= edge_count:
                    yield QEVector(0.0, rx, 0, total_pulsed)


def optimize(
    opportunities: Iterable[ExternalOpportunity],
    *,
    mode: CapitalMode,
    space: SearchSpace = SearchSpace(),
    top_k: int = 100,
) -> list[DesignEvaluation]:
    """Exhaustive deterministic V8.2 grid search."""
    _validate_space(space)
    if top_k <= 0:
        return []

    best: list[DesignEvaluation] = []
    for opp in opportunities:
        for flash_budget, edge_count, lock_fraction in product(
            space.flash_budgets_usd,
            space.edge_counts,
            space.lock_fractions,
        ):
            if flash_budget + 1e-12 < opp.route_required_usd:
                continue
            for qe in _qe_vectors(space, edge_count):
                ev = evaluate_design(
                    opp,
                    mode=mode,
                    flash_budget_usd=flash_budget,
                    edge_count=edge_count,
                    lock_fraction=lock_fraction,
                    qe=qe,
                    virtual_fee_bps=space.virtual_fee_bps,
                    flash_fee_bps=space.flash_fee_bps,
                    mev_reserve_fraction=space.mev_reserve_fraction,
                    max_pol_usd=space.max_pol_usd,
                )
                if ev.feasible:
                    best.append(ev)

    best.sort(
        key=lambda x: (
            x.score,
            x.settlement.net_hardnav_usd,
            -x.settlement.required_pol_usd,
            -x.flash_budget_usd,
            -x.edge_count,
        ),
        reverse=True,
    )
    return best[:top_k]


def minimum_pol_required(opportunity: ExternalOpportunity) -> float:
    return sum(-float(v) for v in opportunity.token_delta_usd.values() if float(v) < 0)


def compare_capital_modes(
    opportunities: Iterable[ExternalOpportunity],
    *,
    space: SearchSpace = SearchSpace(),
    min_pol_cap_usd: float = 500.0,
    top_k: int = 20,
) -> dict[str, list[DesignEvaluation]]:
    pure = optimize(opportunities, mode=CapitalMode.PURE_FLASH, space=space, top_k=top_k)
    pol_space = SearchSpace(
        flash_budgets_usd=space.flash_budgets_usd,
        qe_ratios=space.qe_ratios,
        edge_counts=space.edge_counts,
        lock_fractions=space.lock_fractions,
        pulse_edge_counts=space.pulse_edge_counts,
        virtual_fee_bps=space.virtual_fee_bps,
        flash_fee_bps=space.flash_fee_bps,
        mev_reserve_fraction=space.mev_reserve_fraction,
        max_pol_usd=min_pol_cap_usd,
    )
    pol = optimize(opportunities, mode=CapitalMode.FLASH_MIN_POL, space=pol_space, top_k=top_k)
    return {"PURE_FLASH": pure, "FLASH_MIN_POL": pol}
