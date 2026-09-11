from __future__ import annotations

"""V7.2 deterministic global-graph research simulator.

This module deliberately models the *whole* own + foreign multigraph.  It is
not a production executor and it does not treat protocol-owned LP transfers or
RUBC/RUBX marks as profit.  Synthetic own pools use CPMM curves; live foreign
pools must later be replaced/requoted by pinned-block protocol adapters.
"""

from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Iterable, Mapping, Sequence

RUBC = "RUBC"
RUBX = "RUBX"
DEFAULT_INTERNAL = frozenset({RUBC, RUBX})


@dataclass
class SimPool:
    pool_id: str
    token0: str
    token1: str
    reserve0: float
    reserve1: float
    fee_bps: float = 30.0
    owner: str = "protocol"  # protocol | foreign
    kind: str = "cpmm"

    def _sides(self, token_in: str) -> tuple[float, float, bool]:
        if token_in == self.token0:
            return self.reserve0, self.reserve1, True
        if token_in == self.token1:
            return self.reserve1, self.reserve0, False
        raise ValueError(f"{token_in} not in {self.pool_id}")

    def other(self, token_in: str) -> str:
        if token_in == self.token0:
            return self.token1
        if token_in == self.token1:
            return self.token0
        raise ValueError(f"{token_in} not in {self.pool_id}")

    def spot_rate(self, token_in: str) -> float:
        x, y, _ = self._sides(token_in)
        if x <= 0 or y <= 0:
            return 0.0
        return (y / x) * (1.0 - self.fee_bps / 10_000.0)

    def quote(self, token_in: str, amount_in: float) -> float:
        if self.kind != "cpmm":
            raise ValueError("surrogate simulator currently implements CPMM only")
        if amount_in <= 0:
            return 0.0
        x, y, _ = self._sides(token_in)
        if x <= 0 or y <= 0:
            return 0.0
        gamma = 1.0 - self.fee_bps / 10_000.0
        effective = amount_in * gamma
        return y * effective / (x + effective)

    def swap(self, token_in: str, amount_in: float) -> tuple[str, float]:
        amount_out = self.quote(token_in, amount_in)
        token_out = self.other(token_in)
        if amount_out <= 0:
            raise ValueError(f"zero output in {self.pool_id}")
        if token_in == self.token0:
            self.reserve0 += amount_in
            self.reserve1 -= amount_out
        else:
            self.reserve1 += amount_in
            self.reserve0 -= amount_out
        if self.reserve0 <= 0 or self.reserve1 <= 0:
            raise ValueError(f"invalid post-swap reserve in {self.pool_id}")
        return token_out, amount_out


@dataclass(frozen=True)
class CycleCandidate:
    start_token: str
    token_path: tuple[str, ...]
    pool_path: tuple[str, ...]
    gross_spot_edge_bps: float


@dataclass(frozen=True)
class PacketTrade:
    start_token: str
    pool_path: tuple[str, ...]
    amount_in: float
    amount_out: float
    gross_profit_usd: float
    gas_usd: float
    mev_usd: float
    net_profit_usd: float


@dataclass(frozen=True)
class AbundanceReport:
    hard_nav_before: float
    hard_nav_after: float
    delta_hard_nav: float
    supply_before: float
    supply_after: float
    delta_supply: float
    backing_before: float
    backing_after: float
    abundance_surplus: float
    passes: bool


def build_protocol_complete_graph(
    tokens: Sequence[str],
    prices_usd: Mapping[str, float],
    tvl_usd_per_pool: float = 20_000.0,
    fee_bps: float = 30.0,
    prefix: str = "OWN",
) -> list[SimPool]:
    """Build conceptual K_n protocol-owned CPMM graph at reference prices.

    `prices_usd` must contain a positive reference price for every vertex,
    including research reference values for RUBC/RUBX.  Those internal-token
    reference values are used only to initialize pool geometry; they are never
    counted as HardNAV.
    """
    uniq = list(dict.fromkeys(tokens))
    if len(uniq) < 2:
        return []
    if tvl_usd_per_pool <= 0:
        raise ValueError("tvl_usd_per_pool must be positive")
    for t in uniq:
        if prices_usd.get(t, 0.0) <= 0:
            raise ValueError(f"missing positive reference price for {t}")
    half = tvl_usd_per_pool / 2.0
    pools: list[SimPool] = []
    for i, a in enumerate(uniq):
        for b in uniq[i + 1 :]:
            pools.append(
                SimPool(
                    pool_id=f"{prefix}:{a}/{b}",
                    token0=a,
                    token1=b,
                    reserve0=half / prices_usd[a],
                    reserve1=half / prices_usd[b],
                    fee_bps=fee_bps,
                    owner="protocol",
                )
            )
    return pools


def graph_counts(pools: Iterable[SimPool]) -> dict[str, int]:
    rows = list(pools)
    vertices = {p.token0 for p in rows} | {p.token1 for p in rows}
    own = sum(p.owner == "protocol" for p in rows)
    foreign = sum(p.owner == "foreign" for p in rows)
    return {"vertices": len(vertices), "own_pools": own, "foreign_pools": foreign, "total_pools": len(rows)}


def hard_nav(
    pools: Iterable[SimPool],
    treasury: Mapping[str, float],
    prices_usd: Mapping[str, float],
    internal_tokens: frozenset[str] = DEFAULT_INTERNAL,
    external_liabilities_usd: float = 0.0,
) -> float:
    """Consolidated hard NAV: Treasury + protocol-owned LP hard reserves.

    Internal monetary tokens are excluded regardless of their pool-implied or
    initialization price. Foreign LP reserves are also excluded because they
    are not protocol assets.
    """
    nav = 0.0
    for token, amount in treasury.items():
        if token not in internal_tokens:
            nav += amount * prices_usd.get(token, 0.0)
    for p in pools:
        if p.owner != "protocol":
            continue
        if p.token0 not in internal_tokens:
            nav += p.reserve0 * prices_usd.get(p.token0, 0.0)
        if p.token1 not in internal_tokens:
            nav += p.reserve1 * prices_usd.get(p.token1, 0.0)
    return nav - external_liabilities_usd


def _pool_map(pools: Sequence[SimPool]) -> dict[str, SimPool]:
    out = {p.pool_id: p for p in pools}
    if len(out) != len(pools):
        raise ValueError("duplicate pool_id")
    return out


def _adjacency(pools: Sequence[SimPool], branch_width: int) -> dict[str, list[tuple[str, str, float]]]:
    adj: dict[str, list[tuple[str, str, float]]] = {}
    for p in pools:
        for src in (p.token0, p.token1):
            rate = p.spot_rate(src)
            if rate > 0 and math.isfinite(rate):
                adj.setdefault(src, []).append((p.other(src), p.pool_id, rate))
    for src, edges in adj.items():
        # Keep the best parallel/alternative marginal edges. This makes search
        # bounded even for K_100 while preserving the strongest dislocations.
        edges.sort(key=lambda e: e[2], reverse=True)
        adj[src] = edges[:branch_width]
    return adj


def discover_cycle_field(
    pools: Sequence[SimPool],
    starts: Iterable[str] | None = None,
    max_hops: int = 5,
    top_k: int = 1000,
    beam_width: int = 96,
    branch_width: int = 32,
    min_edge_bps: float = 0.0,
) -> list[CycleCandidate]:
    """Bounded beam discovery across the whole directed multigraph.

    The result is a spot candidate field, not executable PnL. Pool state,
    slippage and route interaction must be evaluated with finite-size swaps.
    """
    if max_hops < 2:
        return []
    adj = _adjacency(pools, branch_width)
    start_nodes = list(dict.fromkeys(starts if starts is not None else adj.keys()))
    found: dict[tuple[str, tuple[str, ...]], CycleCandidate] = {}

    for start in start_nodes:
        if start not in adj:
            continue
        # state = (log_rate, current_token, token_path, pool_path)
        beam: list[tuple[float, str, tuple[str, ...], tuple[str, ...]]] = [(0.0, start, (start,), ())]
        for _depth in range(max_hops):
            nxt_beam: list[tuple[float, str, tuple[str, ...], tuple[str, ...]]] = []
            for log_rate, node, token_path, pool_path in beam:
                for nxt, pid, rate in adj.get(node, ()):  # already branch-pruned
                    if pid in pool_path:
                        continue
                    if nxt in token_path and nxt != start:
                        continue
                    nr = log_rate + math.log(rate)
                    new_pools = pool_path + (pid,)
                    new_tokens = token_path + (nxt,)
                    if nxt == start and len(new_pools) >= 2:
                        edge_bps = math.expm1(nr) * 10_000.0
                        if edge_bps > min_edge_bps:
                            key = (start, new_pools)
                            cand = CycleCandidate(start, new_tokens, new_pools, edge_bps)
                            old = found.get(key)
                            if old is None or cand.gross_spot_edge_bps > old.gross_spot_edge_bps:
                                found[key] = cand
                        continue
                    nxt_beam.append((nr, nxt, new_tokens, new_pools))
            if not nxt_beam:
                break
            nxt_beam.sort(key=lambda s: s[0], reverse=True)
            beam = nxt_beam[:beam_width]

    return sorted(found.values(), key=lambda c: c.gross_spot_edge_bps, reverse=True)[:top_k]


def quote_route(pools: Sequence[SimPool], start_token: str, amount_in: float, pool_path: Sequence[str]) -> tuple[str, float]:
    sim = deepcopy(list(pools))
    pm = _pool_map(sim)
    token = start_token
    amount = amount_in
    for pid in pool_path:
        token, amount = pm[pid].swap(token, amount)
    return token, amount


def execute_route(
    pools: Sequence[SimPool],
    treasury: dict[str, float],
    start_token: str,
    amount_in: float,
    pool_path: Sequence[str],
) -> tuple[str, float]:
    if treasury.get(start_token, 0.0) + 1e-18 < amount_in:
        raise ValueError("insufficient treasury balance")
    pm = _pool_map(pools)
    treasury[start_token] = treasury.get(start_token, 0.0) - amount_in
    token = start_token
    amount = amount_in
    for pid in pool_path:
        token, amount = pm[pid].swap(token, amount)
    treasury[token] = treasury.get(token, 0.0) + amount
    return token, amount


def apply_qe_buy_vector(
    pools: Sequence[SimPool],
    treasury: dict[str, float],
    mint_rubc: float,
    buy_allocations: Mapping[str, float],
    rubc: str = RUBC,
) -> dict[str, float]:
    """Mint RUBC and distribute it over many own RUBC/* actuator edges."""
    if mint_rubc < 0:
        raise ValueError("negative mint")
    if any(v < 0 for v in buy_allocations.values()):
        raise ValueError("negative allocation")
    total = sum(buy_allocations.values())
    if total > mint_rubc + 1e-12:
        raise ValueError("QE allocations exceed minted RUBC")
    pm = _pool_map(pools)
    treasury[rubc] = treasury.get(rubc, 0.0) + mint_rubc
    outputs: dict[str, float] = {}
    for pid, amount in buy_allocations.items():
        p = pm[pid]
        if p.owner != "protocol":
            raise ValueError("QE BUY actuator may directly pulse protocol-owned pools only")
        if rubc not in (p.token0, p.token1):
            raise ValueError(f"QE actuator pool {pid} is not incident to RUBC")
        treasury[rubc] -= amount
        out_token, out_amount = p.swap(rubc, amount)
        treasury[out_token] = treasury.get(out_token, 0.0) + out_amount
        outputs[out_token] = outputs.get(out_token, 0.0) + out_amount
    return outputs


def burn_rubc(treasury: dict[str, float], amount: float, rubc: str = RUBC) -> float:
    if amount < 0:
        raise ValueError("negative burn")
    actual = min(amount, max(0.0, treasury.get(rubc, 0.0)))
    treasury[rubc] = treasury.get(rubc, 0.0) - actual
    return actual


def evaluate_cycle_finite_size(
    pools: Sequence[SimPool],
    candidate: CycleCandidate,
    notional_usd: float,
    prices_usd: Mapping[str, float],
    gas_usd_per_swap: float = 0.0,
    mev_haircut: float = 0.0,
    internal_tokens: frozenset[str] = DEFAULT_INTERNAL,
) -> PacketTrade | None:
    start = candidate.start_token
    px = prices_usd.get(start, 0.0)
    if start in internal_tokens or px <= 0 or notional_usd <= 0:
        return None
    amount_in = notional_usd / px
    end_token, amount_out = quote_route(pools, start, amount_in, candidate.pool_path)
    if end_token != start:
        return None
    gross_profit_usd = (amount_out - amount_in) * px
    gas_usd = gas_usd_per_swap * len(candidate.pool_path)
    mev_usd = max(0.0, gross_profit_usd) * max(0.0, mev_haircut)
    net = gross_profit_usd - gas_usd - mev_usd
    return PacketTrade(start, candidate.pool_path, amount_in, amount_out, gross_profit_usd, gas_usd, mev_usd, net)


def greedy_multicycle_packet(
    pools: Sequence[SimPool],
    treasury: dict[str, float],
    prices_usd: Mapping[str, float],
    notionals_usd: Sequence[float] = (10.0, 50.0, 100.0, 500.0, 1_000.0),
    max_rounds: int = 25,
    max_hops: int = 5,
    discovery_top_k: int = 500,
    gas_usd_per_swap: float = 0.0,
    mev_haircut: float = 0.0,
    internal_tokens: frozenset[str] = DEFAULT_INTERNAL,
) -> list[PacketTrade]:
    """Greedy interacting route packet over the whole graph.

    After every accepted route, the physical pool state is mutated and the
    complete cycle field is recomputed. This prevents counting the same edge
    many times as if shared liquidity were infinite.
    """
    accepted: list[PacketTrade] = []
    for _ in range(max_rounds):
        starts = [t for t, px in prices_usd.items() if t not in internal_tokens and px > 0 and treasury.get(t, 0.0) > 0]
        if not starts:
            break
        cands = discover_cycle_field(pools, starts=starts, max_hops=max_hops, top_k=discovery_top_k)
        best: PacketTrade | None = None
        for c in cands:
            available_usd = treasury.get(c.start_token, 0.0) * prices_usd.get(c.start_token, 0.0)
            for n in notionals_usd:
                if n > available_usd + 1e-12:
                    continue
                trade = evaluate_cycle_finite_size(
                    pools,
                    c,
                    n,
                    prices_usd,
                    gas_usd_per_swap=gas_usd_per_swap,
                    mev_haircut=mev_haircut,
                    internal_tokens=internal_tokens,
                )
                if trade is not None and trade.net_profit_usd > 0 and (best is None or trade.net_profit_usd > best.net_profit_usd):
                    best = trade
        if best is None:
            break
        end_token, amount_out = execute_route(pools, treasury, best.start_token, best.amount_in, best.pool_path)
        if end_token != best.start_token:
            raise AssertionError("cycle ceased to be closed during execution")
        # The raw simulated swap already credits the full output. Deduct modeled
        # execution costs from the same hard start asset so accounting remains
        # consolidated and explicit.
        px = prices_usd[best.start_token]
        cost_token = (best.gas_usd + best.mev_usd) / px
        treasury[best.start_token] -= cost_token
        accepted.append(PacketTrade(best.start_token, best.pool_path, best.amount_in, amount_out, best.gross_profit_usd, best.gas_usd, best.mev_usd, best.net_profit_usd))
    return accepted


def abundance_report(
    hard_nav_before: float,
    hard_nav_after: float,
    supply_before: float,
    gross_mint: float,
    burned: float,
) -> AbundanceReport:
    if hard_nav_before < 0 or hard_nav_after < 0 or supply_before <= 0:
        raise ValueError("invalid NAV/supply")
    supply_after = supply_before + gross_mint - burned
    if supply_after <= 0:
        raise ValueError("non-positive final supply")
    delta_h = hard_nav_after - hard_nav_before
    delta_s = supply_after - supply_before
    h0 = hard_nav_before / supply_before
    h1 = hard_nav_after / supply_after
    surplus = delta_h - h0 * delta_s
    return AbundanceReport(
        hard_nav_before,
        hard_nav_after,
        delta_h,
        supply_before,
        supply_after,
        delta_s,
        h0,
        h1,
        surplus,
        delta_h > 0 and surplus > 0 and h1 >= h0,
    )


def edge_field_summary(candidates: Sequence[CycleCandidate]) -> dict[str, float | int]:
    if not candidates:
        return {"positive_cycles": 0, "max_edge_bps": 0.0, "median_edge_bps": 0.0}
    edges = sorted(c.gross_spot_edge_bps for c in candidates)
    n = len(edges)
    med = edges[n // 2] if n % 2 else (edges[n // 2 - 1] + edges[n // 2]) / 2.0
    return {"positive_cycles": n, "max_edge_bps": edges[-1], "median_edge_bps": med}
