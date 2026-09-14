from __future__ import annotations

from dataclasses import dataclass

BPS = 10_000.0
V74_NET_CANDIDATE_USD = 15.970478870354315
V74_CONCURRENT_FLASH_USD = 2171.9290383524276


@dataclass(frozen=True)
class AllocationPolicy:
    owner: float = 0.25
    bridge: float = 0.25
    insurance: float = 0.20
    rebase: float = 0.10
    qe: float = 0.20

    def validate(self) -> None:
        total = self.owner + self.bridge + self.insurance + self.rebase + self.qe
        if abs(total - 1.0) > 1e-12:
            raise ValueError(f"allocation fractions must sum to 1, got {total}")
        if min(self.owner, self.bridge, self.insurance, self.rebase, self.qe) < 0:
            raise ValueError("allocation fractions must be non-negative")


@dataclass
class PoolState:
    quote_reserve: float
    base_reserve: float
    fair_price: float
    fee_bps: float = 30.0
    total_lp_units: float = 1.0

    @property
    def spot_price(self) -> float:
        return self.quote_reserve / self.base_reserve

    @property
    def fair_tvl(self) -> float:
        return self.quote_reserve + self.base_reserve * self.fair_price


@dataclass
class SystemState:
    owner_liquid: float = 1.0
    bridge_reserve: float = 0.0
    insurance_fund: float = 0.0
    rebase_fund: float = 0.0
    qe_treasury: float = 0.0
    owned_lp_units: float = 0.0

    @property
    def non_lp_hardnav(self) -> float:
        return (
            self.owner_liquid
            + self.bridge_reserve
            + self.insurance_fund
            + self.rebase_fund
            + self.qe_treasury
        )


@dataclass(frozen=True)
class PacketResult:
    packet_index: int
    packet_profit_usd: float
    qe_inflow_usd: float
    qe_swap_usd: float
    qe_pair_quote_usd: float
    transient_price_impact_fraction: float
    pool_tvl_gain_usd: float
    system_external_lp_value_usd: float
    owner_liquid_usd: float
    bridge_reserve_usd: float
    insurance_fund_usd: float
    rebase_fund_usd: float
    qe_treasury_end_usd: float
    consolidated_system_hardnav_usd: float


def swap_quote_for_base(pool: PoolState, amount_quote: float) -> tuple[PoolState, float]:
    if amount_quote < 0:
        raise ValueError("amount_quote must be non-negative")
    fee = pool.fee_bps / BPS
    effective = amount_quote * (1.0 - fee)
    base_out = pool.base_reserve * effective / (pool.quote_reserve + effective)
    return (
        PoolState(
            quote_reserve=pool.quote_reserve + amount_quote,
            base_reserve=pool.base_reserve - base_out,
            fair_price=pool.fair_price,
            fee_bps=pool.fee_bps,
            total_lp_units=pool.total_lp_units,
        ),
        base_out,
    )


def _matched_qe_split(pool: PoolState, qe_budget: float) -> tuple[float, float, float, PoolState]:
    """Split QE budget into a buy and matching quote-side LP contribution.

    We solve for the quote amount used to buy base so the purchased base amount
    exactly pairs with the remaining quote amount at the post-swap reserve ratio.
    This is an accounting/risk simulator, not a trade execution router.
    """
    if qe_budget < 0:
        raise ValueError("qe_budget must be non-negative")
    if qe_budget == 0:
        return 0.0, 0.0, 0.0, pool

    lo, hi = 0.0, qe_budget
    for _ in range(120):
        buy = (lo + hi) / 2.0
        post_swap, base_bought = swap_quote_for_base(pool, buy)
        quote_for_lp = qe_budget - buy
        required_base = quote_for_lp * post_swap.base_reserve / post_swap.quote_reserve
        if base_bought < required_base:
            lo = buy
        else:
            hi = buy

    buy = (lo + hi) / 2.0
    post_swap, base_bought = swap_quote_for_base(pool, buy)
    return buy, qe_budget - buy, base_bought, post_swap


def add_matched_liquidity(
    pool: PoolState, quote_amount: float, base_amount: float
) -> tuple[PoolState, float]:
    if quote_amount == 0 and base_amount == 0:
        return pool, 0.0
    quote_ratio = quote_amount / pool.quote_reserve
    base_ratio = base_amount / pool.base_reserve
    if abs(quote_ratio - base_ratio) > 1e-9 * max(1.0, quote_ratio, base_ratio):
        raise ValueError("liquidity must match the current pool reserve ratio")
    ratio = (quote_ratio + base_ratio) / 2.0
    minted = pool.total_lp_units * ratio
    return (
        PoolState(
            quote_reserve=pool.quote_reserve + quote_amount,
            base_reserve=pool.base_reserve + base_amount,
            fair_price=pool.fair_price,
            fee_bps=pool.fee_bps,
            total_lp_units=pool.total_lp_units + minted,
        ),
        minted,
    )


def restore_external_fair_price(pool: PoolState) -> PoolState:
    """Model external arbitrage restoring a QE-raised pool price to fair price."""
    if pool.spot_price <= pool.fair_price * (1.0 + 1e-15):
        return pool

    fee = pool.fee_bps / BPS

    def price_after_base_in(base_in: float) -> float:
        effective = base_in * (1.0 - fee)
        quote_out = pool.quote_reserve * effective / (pool.base_reserve + effective)
        return (pool.quote_reserve - quote_out) / (pool.base_reserve + base_in)

    lo = 0.0
    hi = max(pool.base_reserve * 1e-12, 1e-18)
    while price_after_base_in(hi) > pool.fair_price:
        hi *= 2.0

    for _ in range(150):
        mid = (lo + hi) / 2.0
        if price_after_base_in(mid) > pool.fair_price:
            lo = mid
        else:
            hi = mid

    base_in = (lo + hi) / 2.0
    effective = base_in * (1.0 - fee)
    quote_out = pool.quote_reserve * effective / (pool.base_reserve + effective)
    return PoolState(
        quote_reserve=pool.quote_reserve - quote_out,
        base_reserve=pool.base_reserve + base_in,
        fair_price=pool.fair_price,
        fee_bps=pool.fee_bps,
        total_lp_units=pool.total_lp_units,
    )


def system_external_lp_value(pool: PoolState, system: SystemState) -> float:
    if pool.total_lp_units <= 0:
        return 0.0
    return system.owned_lp_units / pool.total_lp_units * pool.fair_tvl


def simulate_successful_packet(
    pool: PoolState,
    system: SystemState,
    *,
    packet_index: int,
    packet_profit_usd: float = V74_NET_CANDIDATE_USD,
    policy: AllocationPolicy = AllocationPolicy(),
) -> tuple[PoolState, SystemState, PacketResult]:
    """Apply one already-profitable V7.4 packet, then deploy its QE allocation.

    `packet_profit_usd` is treated as external hard profit already net of the
    packet's modeled MEV reserve and gas. This function does not create or
    discover an arbitrage opportunity and does not assume a stale opportunity
    can be repeated. Repetition is a conditional scenario: each packet must be
    independently replenished/proven by the V7.4 execution gate.
    """
    if packet_profit_usd <= 0:
        raise ValueError("packet_profit_usd must be positive")
    policy.validate()

    tvl_before = pool.fair_tvl
    system.owner_liquid += policy.owner * packet_profit_usd
    system.bridge_reserve += policy.bridge * packet_profit_usd
    system.insurance_fund += policy.insurance * packet_profit_usd
    system.rebase_fund += policy.rebase * packet_profit_usd
    system.qe_treasury += policy.qe * packet_profit_usd

    qe_budget = system.qe_treasury
    qe_buy, qe_pair_quote, base_bought, post_swap = _matched_qe_split(pool, qe_budget)
    impact = post_swap.spot_price / pool.fair_price - 1.0

    post_lp, minted = add_matched_liquidity(post_swap, qe_pair_quote, base_bought)
    system.owned_lp_units += minted
    system.qe_treasury = 0.0

    final_pool = restore_external_fair_price(post_lp)
    lp_value = system_external_lp_value(final_pool, system)
    consolidated = system.non_lp_hardnav + lp_value

    result = PacketResult(
        packet_index=packet_index,
        packet_profit_usd=packet_profit_usd,
        qe_inflow_usd=qe_budget,
        qe_swap_usd=qe_buy,
        qe_pair_quote_usd=qe_pair_quote,
        transient_price_impact_fraction=impact,
        pool_tvl_gain_usd=final_pool.fair_tvl - tvl_before,
        system_external_lp_value_usd=lp_value,
        owner_liquid_usd=system.owner_liquid,
        bridge_reserve_usd=system.bridge_reserve,
        insurance_fund_usd=system.insurance_fund,
        rebase_fund_usd=system.rebase_fund,
        qe_treasury_end_usd=system.qe_treasury,
        consolidated_system_hardnav_usd=consolidated,
    )
    return final_pool, system, result


def simulate_packets(
    count: int,
    *,
    starting_hardnav_usd: float = 1.0,
    initial_external_pool_tvl_usd: float = 118_000_000.0,
    fair_base_price_usd: float = 2_500.0,
    external_pool_fee_bps: float = 30.0,
    packet_profit_usd: float = V74_NET_CANDIDATE_USD,
    policy: AllocationPolicy = AllocationPolicy(),
) -> tuple[PoolState, SystemState, list[PacketResult]]:
    if count < 0:
        raise ValueError("count must be non-negative")
    if starting_hardnav_usd < 0:
        raise ValueError("starting_hardnav_usd must be non-negative")
    quote = initial_external_pool_tvl_usd / 2.0
    pool = PoolState(
        quote_reserve=quote,
        base_reserve=quote / fair_base_price_usd,
        fair_price=fair_base_price_usd,
        fee_bps=external_pool_fee_bps,
    )
    system = SystemState(owner_liquid=starting_hardnav_usd)
    rows: list[PacketResult] = []
    for idx in range(1, count + 1):
        pool, system, row = simulate_successful_packet(
            pool,
            system,
            packet_index=idx,
            packet_profit_usd=packet_profit_usd,
            policy=policy,
        )
        rows.append(row)
    return pool, system, rows
