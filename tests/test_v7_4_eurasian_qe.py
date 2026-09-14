from synergy_graph.v7_4_eurasian_qe import (
    AllocationPolicy,
    V74_NET_CANDIDATE_USD,
    simulate_packets,
)


def test_one_packet_from_one_dollar_separates_ledgers():
    pool, system, rows = simulate_packets(1)
    row = rows[-1]

    assert row.packet_profit_usd == V74_NET_CANDIDATE_USD
    assert abs(row.qe_inflow_usd - 0.20 * V74_NET_CANDIDATE_USD) < 1e-12
    assert abs(system.bridge_reserve - 0.25 * V74_NET_CANDIDATE_USD) < 1e-12
    assert abs(system.insurance_fund - 0.20 * V74_NET_CANDIDATE_USD) < 1e-12
    assert abs(system.rebase_fund - 0.10 * V74_NET_CANDIDATE_USD) < 1e-12
    assert system.qe_treasury == 0.0
    assert row.system_external_lp_value_usd > 0.0
    assert row.pool_tvl_gain_usd > 0.0
    assert row.transient_price_impact_fraction > 0.0


def test_qe_does_not_create_free_hardnav():
    _, _, rows = simulate_packets(1)
    row = rows[-1]
    theoretical_before_qe_execution_cost = 1.0 + V74_NET_CANDIDATE_USD
    assert row.consolidated_system_hardnav_usd <= theoretical_before_qe_execution_cost
    assert theoretical_before_qe_execution_cost - row.consolidated_system_hardnav_usd > 0.0


def test_repeated_packets_are_conditional_but_accounting_accumulates():
    pool, system, rows = simulate_packets(100)
    assert len(rows) == 100
    assert pool.fair_tvl > 118_000_000.0
    assert system.bridge_reserve > 0.0
    assert rows[-1].system_external_lp_value_usd > rows[0].system_external_lp_value_usd
    assert rows[-1].consolidated_system_hardnav_usd > rows[0].consolidated_system_hardnav_usd


def test_allocation_policy_must_sum_to_one():
    bad = AllocationPolicy(owner=0.30)
    try:
        bad.validate()
    except ValueError:
        return
    raise AssertionError("invalid policy was accepted")
