from __future__ import annotations

"""V8 joint QE / flash / denomination-closure optimizer.

The point of this module is not to maximize a relaxed USD PnL.  It searches
packets under the accounting rule the on-chain executor must satisfy:

    final[token] >= preexisting[token] + principal[token] + fee[token]

for every borrowed ERC-20 independently.

Two capital modes are supported:

* PURE_FLASH: no permanent inventory is allowed to repair a denomination
  deficit.  Every borrowed token must close in-kind.
* FLASH_MIN_POL: the solver may use a bounded amount of permanent hard-token
  inventory and reports the minimum amount required.  This is the realistic
  mode for testing whether a small $100-$500 buffer can unlock a $2k-$10k
  atomic QE packet.

RUBC/RUBX are internal graph fields.  They are never assigned an oracle value
and never counted as HardNAV.
"""

from dataclasses import dataclass, field
from enum import Enum
from itertools import product
from math import inf
from typing import Callable, Iterable, Mapping, Sequence

BPS = 10_000


class CapitalMode(str, Enum):
    PURE_FLASH = "PURE_FLASH"
    FLASH_MIN_POL = "FLASH_MIN_POL"


@dataclass(frozen=True)
class Token:
    symbol: str
    decimals: int
    price_usd: float


@dataclass(frozen=True)
class VirtualEdge:
    field: str  # RUBC or RUBX
    hard: str
    hard_reserve: float
    monetary_reserve: float
    fee_bps: int = 30


@dataclass(frozen=True)
class ExternalLeg:
    token_in: str
    token_out: str
    amount_in: float
    amount_out: float
    venue: str = ""


@dataclass(frozen=True)
class Candidate:
    name: str
    flash_principal: Mapping[str, float]
    external_legs: Sequence[ExternalLeg]
    qe_field: str | None = None
    qe_edge_hard: str | None = None
    qe_ratio: float = 0.0
    baseline_graph_profit_usd: float = 0.0
    post_qe_graph_profit_usd: float = 0.0
    gas_usd: float = 0.0
    mev_haircut: float = 0.35


@dataclass(frozen=True)
class Audit:
    repayable: bool
    token_delta: Mapping[str, float]
    required_pol: Mapping[str, float]
    required_pol_usd: float
    gross_hard_profit_usd: float
    risk_adjusted_profit_usd: float
    flash_fee_usd: float
    net_hardnav_usd: float
    qe_created_cycle: bool
    external_only_profitable: bool


@dataclass(frozen=True)
class SearchResult:
    candidate: Candidate
    audit: Audit
    score: float


def cpmm_quote(reserve_in: float, reserve_out: float, amount_in: float, fee_bps: int = 30) -> float:
    if reserve_in <= 0 or reserve_out <= 0 or amount_in <= 0:
        return 0.0
    if fee_bps < 0 or fee_bps >= BPS:
        raise ValueError("invalid fee_bps")
    effective = amount_in * (BPS - fee_bps)
    return reserve_out * effective / (reserve_in * BPS + effective)


def apply_qe(edge: VirtualEdge, ratio: float) -> VirtualEdge:
    """Mint internal monetary units and BUY hard asset on one virtual edge."""
    if ratio < 0:
        raise ValueError("negative QE ratio")
    monetary_in = edge.monetary_reserve * ratio
    hard_out = cpmm_quote(edge.monetary_reserve, edge.hard_reserve, monetary_in, edge.fee_bps)
    return VirtualEdge(
        field=edge.field,
        hard=edge.hard,
        hard_reserve=edge.hard_reserve - hard_out,
        monetary_reserve=edge.monetary_reserve + monetary_in,
        fee_bps=edge.fee_bps,
    )


def virtual_hard_to_money(edge: VirtualEdge, amount_hard: float) -> tuple[VirtualEdge, float]:
    out = cpmm_quote(edge.hard_reserve, edge.monetary_reserve, amount_hard, edge.fee_bps)
    return (
        VirtualEdge(edge.field, edge.hard, edge.hard_reserve + amount_hard, edge.monetary_reserve - out, edge.fee_bps),
        out,
    )


def virtual_money_to_hard(edge: VirtualEdge, amount_money: float) -> tuple[VirtualEdge, float]:
    out = cpmm_quote(edge.monetary_reserve, edge.hard_reserve, amount_money, edge.fee_bps)
    return (
        VirtualEdge(edge.field, edge.hard, edge.hard_reserve - out, edge.monetary_reserve + amount_money, edge.fee_bps),
        out,
    )


def external_token_deltas(legs: Sequence[ExternalLeg]) -> dict[str, float]:
    delta: dict[str, float] = {}
    for leg in legs:
        if leg.amount_in < 0 or leg.amount_out < 0:
            raise ValueError("negative external amount")
        delta[leg.token_in] = delta.get(leg.token_in, 0.0) - leg.amount_in
        delta[leg.token_out] = delta.get(leg.token_out, 0.0) + leg.amount_out
    return delta


def audit_candidate(
    candidate: Candidate,
    tokens: Mapping[str, Token],
    flash_fee_bps: float,
    mode: CapitalMode = CapitalMode.PURE_FLASH,
    max_pol_usd: float = 0.0,
) -> Audit:
    """Strict post-collapse audit.

    Internal QE/virtual swaps are intentionally absent from final token deltas:
    after all protocol-owned virtual edges are consolidated, only real external
    transfers can change total hard-token balances.
    """
    deltas = external_token_deltas(candidate.external_legs)

    required_pol: dict[str, float] = {}
    required_pol_usd = 0.0
    for symbol in set(candidate.flash_principal) | set(deltas):
        q = deltas.get(symbol, 0.0)
        if q < 0:
            need = -q
            if mode == CapitalMode.PURE_FLASH:
                required_pol[symbol] = need
            else:
                required_pol[symbol] = need
                tok = tokens[symbol]
                required_pol_usd += need * tok.price_usd

    if mode == CapitalMode.PURE_FLASH:
        repayable = all(v <= 1e-12 for v in required_pol.values())
        required_pol_usd = sum(required_pol[s] * tokens[s].price_usd for s in required_pol)
    else:
        repayable = required_pol_usd <= max_pol_usd + 1e-12

    gross = sum(q * tokens[s].price_usd for s, q in deltas.items())
    flash_fee_usd = sum(
        principal * tokens[s].price_usd * flash_fee_bps / BPS
        for s, principal in candidate.flash_principal.items()
    )
    competition = max(0.0, gross) * candidate.mev_haircut
    risk_adjusted = gross - competition
    net = risk_adjusted - candidate.gas_usd - flash_fee_usd

    qe_created = candidate.baseline_graph_profit_usd <= 0 < candidate.post_qe_graph_profit_usd
    external_only_profitable = gross - candidate.gas_usd - flash_fee_usd > 0

    return Audit(
        repayable=repayable,
        token_delta=deltas,
        required_pol=required_pol,
        required_pol_usd=required_pol_usd,
        gross_hard_profit_usd=gross,
        risk_adjusted_profit_usd=risk_adjusted,
        flash_fee_usd=flash_fee_usd,
        net_hardnav_usd=net,
        qe_created_cycle=qe_created,
        external_only_profitable=external_only_profitable,
    )


def rank_candidates(
    candidates: Iterable[Candidate],
    tokens: Mapping[str, Token],
    flash_fee_bps: float,
    mode: CapitalMode,
    max_pol_usd: float = 0.0,
    require_qe_created: bool = True,
    require_positive_hardnav: bool = True,
) -> list[SearchResult]:
    out: list[SearchResult] = []
    for c in candidates:
        a = audit_candidate(c, tokens, flash_fee_bps, mode, max_pol_usd)
        if not a.repayable:
            continue
        if require_qe_created and not a.qe_created_cycle:
            continue
        if require_positive_hardnav and a.net_hardnav_usd <= 0:
            continue
        # Prefer high net HardNAV and low permanent capital dependence.
        score = a.net_hardnav_usd - 0.02 * a.required_pol_usd
        out.append(SearchResult(c, a, score))
    return sorted(out, key=lambda x: (x.score, x.audit.net_hardnav_usd), reverse=True)


def minimum_pol_for_candidate(
    candidate: Candidate,
    tokens: Mapping[str, Token],
    flash_fee_bps: float = 0.0,
) -> float:
    return audit_candidate(
        candidate,
        tokens,
        flash_fee_bps,
        mode=CapitalMode.FLASH_MIN_POL,
        max_pol_usd=inf,
    ).required_pol_usd


def search_qe_grid(
    *,
    name: str,
    tokens: Mapping[str, Token],
    flash_sizes_usd: Sequence[float],
    qe_ratios: Sequence[float],
    fields: Sequence[str],
    hard_symbols: Sequence[str],
    build_candidate: Callable[[float, float, str, str], Candidate | None],
    flash_fee_bps: float,
    mode: CapitalMode,
    max_pol_usd: float = 0.0,
) -> list[SearchResult]:
    candidates: list[Candidate] = []
    for flash_usd, ratio, field_name, hard in product(flash_sizes_usd, qe_ratios, fields, hard_symbols):
        if flash_usd <= 0 or ratio < 0:
            continue
        c = build_candidate(flash_usd, ratio, field_name, hard)
        if c is not None:
            candidates.append(c)
    return rank_candidates(
        candidates,
        tokens,
        flash_fee_bps,
        mode,
        max_pol_usd=max_pol_usd,
        require_qe_created=True,
        require_positive_hardnav=True,
    )
