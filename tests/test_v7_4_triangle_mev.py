from decimal import Decimal as D
import pytest
from synergy_graph.v7_4_triangle_mev import ExecutionMode, PoolOwner, TriangleLeg, audit_triangle, scenario_net_after_reserve, settle_mev_share

def route(owner=PoolOwner.FOREIGN):
    return [
        TriangleLeg("pool-ab", "A", "B", D("100"), D("200"), owner, 123, True),
        TriangleLeg("pool-bc", "B", "C", D("200"), D("300"), owner, 123, True),
        TriangleLeg("pool-ca", "C", "A", D("300"), D("102"), owner, 123, True),
    ]

def test_exact_foreign_triangle_is_eligible():
    a = audit_triangle(route())
    assert a.gross_start_token_profit == D("2")
    assert a.all_foreign_pools and a.hardnav_eligible and a.block_number == 123

def test_own_only_triangle_is_not_external_hardnav():
    a = audit_triangle(route(PoolOwner.PROTOCOL))
    assert a.gross_start_token_profit == D("2")
    assert not a.hardnav_eligible
    assert "consolidated external-token ledger" in a.reason

def test_rejects_mixed_block_and_non_exact_quotes():
    legs = route()
    legs[2] = TriangleLeg("pool-ca", "C", "A", D("300"), D("102"), PoolOwner.FOREIGN, 124, True)
    with pytest.raises(ValueError, match="same pinned block"): audit_triangle(legs)
    legs = route()
    legs[0] = TriangleLeg("pool-ab", "A", "B", D("100"), D("200"), PoolOwner.FOREIGN, 123, False)
    with pytest.raises(ValueError, match="exact pinned-block"): audit_triangle(legs)

def test_rejects_amount_discontinuity():
    legs = route()
    legs[1] = TriangleLeg("pool-bc", "B", "C", D("199"), D("300"), PoolOwner.FOREIGN, 123, True)
    with pytest.raises(ValueError, match="prior leg output"): audit_triangle(legs)

def test_controlled_executor_share_is_protocol_fee_not_extra_gross_profit():
    s = settle_mev_share(gross_external_profit_usd=D("25"), protocol_fee_rate=D("0.35"),
        protocol_costs_usd=D("1"), execution_mode=ExecutionMode.CONTROLLED_EXTERNAL_EXECUTOR)
    assert s.protocol_fee_revenue_usd == D("8.75")
    assert s.executor_gross_share_usd == D("16.25")
    assert s.protocol_net_hardnav_delta_usd == D("7.75")

def test_owned_execution_does_not_double_count_a_fee():
    s = settle_mev_share(gross_external_profit_usd=D("25"), protocol_fee_rate=D("0.35"),
        protocol_costs_usd=D("1"), execution_mode=ExecutionMode.PROTOCOL_EXECUTOR)
    assert s.protocol_fee_revenue_usd == D("0")
    assert s.protocol_net_hardnav_delta_usd == D("24")

def test_uncontrolled_external_pools_cannot_be_taxed_by_assumption():
    with pytest.raises(ValueError, match="cannot charge an involuntary"):
        settle_mev_share(gross_external_profit_usd=D("25"), protocol_fee_rate=D("0.35"),
            protocol_costs_usd=D("1"), execution_mode=ExecutionMode.UNCONTROLLED_EXTERNAL_POOLS)

def test_v74_haircut_is_only_a_scenario_reserve():
    assert scenario_net_after_reserve(D("25.000736723622023"), D("0.35"), D("0.28")) == D("15.97047887035431495")
