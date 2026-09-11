from synergy_graph.v7_4_token_flow import (
    TokenDelta,
    aggregate_token_deltas,
    audit_post_foreign_packet,
    break_even_flash_fee_bps,
    required_flash_principal_usd,
    token_closed_path,
)


def test_usd_positive_does_not_imply_token_repayable():
    ds = aggregate_token_deltas([
        TokenDelta("A", -10, 1),
        TokenDelta("B", 11, 1),
    ])
    a = audit_post_foreign_packet(ds)
    assert a.net_usd == 1
    assert not a.repayable
    assert a.deficits_usd == 10


def test_permanent_inventory_can_cover_exact_token_only():
    ds = aggregate_token_deltas([TokenDelta("A", -10, 1), TokenDelta("B", 11, 1)])
    assert audit_post_foreign_packet(ds, {"A": 10}).repayable
    assert not audit_post_foreign_packet(ds, {"B": 100}).repayable


def test_closed_cycle_and_reusable_principal():
    assert token_closed_path(["WETH", "VIRTUAL", "WETH"])
    assert not token_closed_path(["WETH", "USDC"])
    r = required_flash_principal_usd([("WETH", 1500), ("WETH", 500), ("USDC", 600)])
    assert r == {"weth": 1500.0, "usdc": 600.0}
    assert abs(break_even_flash_fee_bps(15, r) - 71.4285714286) < 1e-6
