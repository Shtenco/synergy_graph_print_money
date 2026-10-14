from synergy_graph.v8_2_auto_optimizer import (
    CapitalMode,
    ExternalOpportunity,
    QEVector,
    SearchSpace,
    cpmm_release_fraction,
    evaluate_design,
    optimize,
    strict_settlement_audit,
)


def test_cpmm_release_fraction_is_positive_and_bounded_at_5pct():
    r = cpmm_release_fraction(0.05, 30)
    assert 0.04 < r < 0.05


def test_qe_causality_requires_route_to_be_infeasible_before_and_feasible_after():
    opp = ExternalOpportunity(
        name="strict WETH loop",
        route_required_usd=800.0,
        token_delta_usd={"WETH": 10.0},
        gas_usd=1.0,
    )
    ev = evaluate_design(
        opp,
        mode=CapitalMode.PURE_FLASH,
        flash_budget_usd=1000.0,
        edge_count=2,
        lock_fraction=0.205,
        qe=QEVector(0.05, 0.0, 2, 0),
        mev_reserve_fraction=0.35,
    )
    assert ev.baseline_free_hard_usd == 795.0
    assert ev.post_qe_free_hard_usd > 800.0
    assert ev.qe_created_feasibility
    assert ev.feasible
    assert ev.settlement.net_hardnav_usd == 5.5


def test_no_qe_never_gets_causality_credit():
    opp = ExternalOpportunity(
        name="already profitable",
        route_required_usd=500.0,
        token_delta_usd={"WETH": 10.0},
    )
    ev = evaluate_design(
        opp,
        mode=CapitalMode.PURE_FLASH,
        flash_budget_usd=1000.0,
        edge_count=2,
        lock_fraction=0.2,
        qe=QEVector(0.0, 0.0, 0, 0),
    )
    assert not ev.qe_created_feasibility
    assert not ev.feasible


def test_pure_flash_rejects_cross_token_usd_netting():
    opp = ExternalOpportunity(
        name="false relaxed pnl",
        route_required_usd=500.0,
        token_delta_usd={"USDC": -100.0, "WETH": 110.0},
    )
    audit = strict_settlement_audit(
        opp,
        flash_budget_usd=500.0,
        flash_fee_bps=0.0,
        mev_reserve_fraction=0.35,
        mode=CapitalMode.PURE_FLASH,
        max_pol_usd=0.0,
    )
    assert audit.gross_external_hardnav_usd == 10.0
    assert audit.required_pol_usd == 100.0
    assert not audit.repayable


def test_min_pol_reports_exact_hard_deficit():
    opp = ExternalOpportunity(
        name="small settlement buffer",
        route_required_usd=500.0,
        token_delta_usd={"USDC": -80.0, "WETH": 100.0},
    )
    audit = strict_settlement_audit(
        opp,
        flash_budget_usd=500.0,
        flash_fee_bps=0.0,
        mev_reserve_fraction=0.35,
        mode=CapitalMode.FLASH_MIN_POL,
        max_pol_usd=100.0,
    )
    assert audit.repayable
    assert audit.required_pol_usd == 80.0
    assert audit.required_pol_by_token_usd["USDC"] == 80.0


def test_optimizer_searches_rubc_rubx_0_to_5pct_and_2_to_10_edges():
    opp = ExternalOpportunity(
        name="candidate",
        route_required_usd=800.0,
        token_delta_usd={"WETH": 12.0},
        gas_usd=1.0,
    )
    space = SearchSpace(
        flash_budgets_usd=(1000.0,),
        qe_ratios=(0.0, 0.025, 0.05),
        edge_counts=(2, 3, 10),
        lock_fractions=(0.20, 0.205, 0.21, 0.25),
        pulse_edge_counts=(1, 2, 3),
        flash_fee_bps=0.0,
        max_pol_usd=0.0,
    )
    rows = optimize([opp], mode=CapitalMode.PURE_FLASH, space=space, top_k=200)
    assert rows
    assert all(2 <= r.edge_count <= 10 for r in rows)
    assert all(0 <= r.qe.rubc_ratio <= 0.05 for r in rows)
    assert all(0 <= r.qe.rubx_ratio <= 0.05 for r in rows)
    assert all(r.qe_created_feasibility for r in rows)
    assert any(r.qe.label == "RUBC" for r in rows)
    assert any(r.qe.label == "RUBX" for r in rows)
    assert any(r.qe.label == "RUBC+RUBX" for r in rows)


def test_flash_fee_is_charged_on_full_flash_budget():
    opp = ExternalOpportunity(
        name="fee",
        route_required_usd=800.0,
        token_delta_usd={"WETH": 20.0},
        gas_usd=1.0,
    )
    ev = evaluate_design(
        opp,
        mode=CapitalMode.PURE_FLASH,
        flash_budget_usd=1000.0,
        edge_count=2,
        lock_fraction=0.205,
        qe=QEVector(0.05, 0.0, 2, 0),
        flash_fee_bps=10.0,
        mev_reserve_fraction=0.35,
    )
    assert ev.settlement.flash_fee_usd == 1.0
    assert ev.settlement.net_hardnav_usd == 11.0
