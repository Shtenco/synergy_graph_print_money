from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class TokenDelta:
    token: str
    quantity: float
    price_usd: float

    @property
    def usd(self) -> float:
        return self.quantity * self.price_usd


@dataclass(frozen=True)
class RepaymentAudit:
    deficits_usd: float
    surpluses_usd: float
    net_usd: float
    deficit_tokens: int
    surplus_tokens: int
    repayable: bool


def aggregate_token_deltas(rows: Iterable[TokenDelta]) -> dict[str, TokenDelta]:
    qty: dict[str, float] = {}
    px: dict[str, float] = {}
    for r in rows:
        t = r.token.lower()
        if r.price_usd < 0:
            raise ValueError("negative oracle price")
        qty[t] = qty.get(t, 0.0) + r.quantity
        if r.price_usd > 0:
            if t in px and abs(px[t] - r.price_usd) > max(1e-9, 1e-6 * max(px[t], r.price_usd)):
                raise ValueError(f"inconsistent oracle price for {t}")
            px[t] = r.price_usd
    return {t: TokenDelta(t, q, px.get(t, 0.0)) for t, q in qty.items()}


def audit_post_foreign_packet(
    deltas: Mapping[str, TokenDelta],
    permanent_inventory: Mapping[str, float] | None = None,
    eps: float = 1e-12,
) -> RepaymentAudit:
    """Audit token-by-token settlement after all foreign swaps.

    `permanent_inventory` is extra hard-token inventory owned before the flash.
    Protocol-owned LP movements and RUBC/RUBX minting are deliberately absent:
    after consolidation they cannot repair a hard-token deficit.
    """
    inv = {k.lower(): float(v) for k, v in (permanent_inventory or {}).items()}
    deficits = surpluses = 0.0
    n_def = n_sur = 0
    for token, d in deltas.items():
        final_qty = d.quantity + inv.get(token.lower(), 0.0)
        value = final_qty * d.price_usd
        if value < -eps:
            deficits += -value
            n_def += 1
        elif value > eps:
            surpluses += value
            n_sur += 1
    return RepaymentAudit(
        deficits_usd=deficits,
        surpluses_usd=surpluses,
        net_usd=surpluses - deficits,
        deficit_tokens=n_def,
        surplus_tokens=n_sur,
        repayable=n_def == 0,
    )


def token_closed_path(token_path: Sequence[str]) -> bool:
    return len(token_path) >= 3 and token_path[0].lower() == token_path[-1].lower()


def required_flash_principal_usd(cycles: Iterable[tuple[str, float]]) -> dict[str, float]:
    """For sequential token-closed cycles, one principal can be reused.

    Returns the maximum required notional for each start token, not the sum of
    cycle notionals.
    """
    req: dict[str, float] = {}
    for token, notional in cycles:
        if notional < 0:
            raise ValueError("negative notional")
        t = token.lower()
        req[t] = max(req.get(t, 0.0), float(notional))
    return req


def flash_fee_cost_usd(principal_by_token_usd: Mapping[str, float], fee_bps: float) -> float:
    if fee_bps < 0:
        raise ValueError("negative flash fee")
    return sum(max(0.0, float(v)) for v in principal_by_token_usd.values()) * fee_bps / 10_000.0


def break_even_flash_fee_bps(net_before_flash_fee_usd: float, principal_by_token_usd: Mapping[str, float]) -> float:
    draw = sum(max(0.0, float(v)) for v in principal_by_token_usd.values())
    if draw <= 0:
        return float("inf") if net_before_flash_fee_usd > 0 else 0.0
    return max(0.0, net_before_flash_fee_usd) / draw * 10_000.0
