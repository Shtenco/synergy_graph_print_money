import math

from synergy_graph.v7_2_global import (
    RUBC,
    RUBX,
    abundance_report,
    apply_qe_buy_vector,
    build_protocol_complete_graph,
    discover_cycle_field,
    graph_counts,
    hard_nav,
)


def test_complete_own_graph_is_true_kn():
    prices = {RUBC: 1.0, RUBX: 1.0, "USDC": 1.0, "WETH": 2500.0, "AERO": 0.75}
    pools = build_protocol_complete_graph(list(prices), prices, tvl_usd_per_pool=10_000.0)
    counts = graph_counts(pools)
    assert counts["vertices"] == 5
    assert counts["own_pools"] == 10  # C(5,2)
    assert counts["foreign_pools"] == 0
    assert counts["total_pools"] == 10


def test_qe_buy_on_protocol_owned_pool_does_not_fake_hard_nav():
    prices = {RUBC: 1.0, RUBX: 1.0, "USDC": 1.0, "WETH": 2500.0}
    pools = build_protocol_complete_graph(list(prices), prices, tvl_usd_per_pool=100_000.0, fee_bps=30.0)
    treasury = {RUBC: 0.0, RUBX: 0.0, "USDC": 0.0, "WETH": 0.0}
    before = hard_nav(pools, treasury, prices)
    apply_qe_buy_vector(pools, treasury, mint_rubc=1_000.0, buy_allocations={"OWN:RUBC/USDC": 1_000.0})
    after = hard_nav(pools, treasury, prices)
    # Hard USDC moved from protocol-owned LP reserve to protocol Treasury.
    # Consolidation must cancel it exactly; RUBC is excluded from HardNAV.
    assert math.isclose(after, before, rel_tol=0.0, abs_tol=1e-8)


def test_qe_pulse_creates_cycle_field_in_large_own_graph():
    prices = {RUBC: 1.0, RUBX: 1.0, "USDC": 1.0, "WETH": 1.0, "A": 1.0, "B": 1.0}
    pools = build_protocol_complete_graph(list(prices), prices, tvl_usd_per_pool=20_000.0, fee_bps=0.0)
    treasury = {t: 0.0 for t in prices}
    before = discover_cycle_field(pools, max_hops=5, top_k=500, min_edge_bps=1e-9)
    assert before == []

    apply_qe_buy_vector(
        pools,
        treasury,
        mint_rubc=2_000.0,
        buy_allocations={
            "OWN:RUBC/USDC": 1_000.0,
            "OWN:RUBC/WETH": 600.0,
            "OWN:RUBC/A": 400.0,
        },
    )
    after = discover_cycle_field(pools, max_hops=5, top_k=500, min_edge_bps=0.01)
    assert len(after) > 0
    assert max(c.gross_spot_edge_bps for c in after) > 0.01
    assert any(RUBC in c.token_path for c in after)


def test_own_only_qe_without_external_capture_fails_abundance_gate():
    prices = {RUBC: 1.0, RUBX: 1.0, "USDC": 1.0, "WETH": 2500.0}
    pools = build_protocol_complete_graph(list(prices), prices, tvl_usd_per_pool=50_000.0, fee_bps=30.0)
    treasury = {t: 0.0 for t in prices}
    h0 = hard_nav(pools, treasury, prices)
    s0 = 1_000_000.0
    mint = 10_000.0
    apply_qe_buy_vector(pools, treasury, mint_rubc=mint, buy_allocations={"OWN:RUBC/USDC": mint})
    h1 = hard_nav(pools, treasury, prices)
    report = abundance_report(h0, h1, s0, gross_mint=mint, burned=0.0)
    assert math.isclose(report.delta_hard_nav, 0.0, rel_tol=0.0, abs_tol=1e-8)
    assert report.delta_supply == mint
    assert report.abundance_surplus < 0
    assert not report.passes
