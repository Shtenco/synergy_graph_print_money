from synergy_graph.v8_flash_optimizer import (
    Audit,
    Candidate,
    CapitalMode,
    ExternalLeg,
    Token,
    audit_candidate,
    minimum_pol_for_candidate,
)


def _tokens():
    return {
        "WETH": Token("WETH", 18, 2500.0),
        "USDC": Token("USDC", 6, 1.0),
    }


def test_pure_flash_rejects_cross_denomination_usdc_deficit():
    c = Candidate(
        name="false-usd-netting",
        flash_principal={"WETH": 0.4, "USDC": 1000.0},
        external_legs=[
            ExternalLeg("USDC", "WETH", 1000.0, 0.41, "foreign"),
        ],
        qe_field="RUBC",
        qe_edge_hard="USDC",
        qe_ratio=0.05,
        baseline_graph_profit_usd=-1.0,
        post_qe_graph_profit_usd=15.0,
    )
    a = audit_candidate(c, _tokens(), 0.0, CapitalMode.PURE_FLASH)
    assert not a.repayable
    assert a.required_pol["USDC"] == 1000.0


def test_min_pol_reports_real_hard_buffer_not_internal_rub_value():
    c = Candidate(
        name="min-pol",
        flash_principal={"WETH": 0.4, "USDC": 1000.0},
        external_legs=[ExternalLeg("USDC", "WETH", 125.0, 0.051, "foreign")],
        qe_field="RUBX",
        qe_edge_hard="USDC",
        qe_ratio=0.05,
        baseline_graph_profit_usd=-0.5,
        post_qe_graph_profit_usd=3.0,
    )
    assert minimum_pol_for_candidate(c, _tokens()) == 125.0


def test_token_closed_external_packet_is_repayable_and_keeps_only_hard_profit():
    c = Candidate(
        name="closed",
        flash_principal={"WETH": 0.4},
        external_legs=[
            ExternalLeg("WETH", "USDC", 0.4, 1010.0, "venue-a"),
            ExternalLeg("USDC", "WETH", 1000.0, 0.402, "venue-b"),
        ],
        qe_field="RUBC",
        qe_edge_hard="WETH",
        qe_ratio=0.05,
        baseline_graph_profit_usd=-1.0,
        post_qe_graph_profit_usd=5.0,
        gas_usd=0.20,
        mev_haircut=0.35,
    )
    a = audit_candidate(c, _tokens(), 0.0, CapitalMode.PURE_FLASH)
    assert a.repayable
    assert a.gross_hard_profit_usd > 0
    assert a.net_hardnav_usd > 0
    assert a.qe_created_cycle
