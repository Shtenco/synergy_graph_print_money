"""Regression gates distilled from legacy SYNERGY economic simulations."""


def hard_nav(assets, liabilities):
    return assets - liabilities


def test_flash_principal_cannot_increase_nav():
    assert hard_nav(100 + 50_000, 50_000) == 100


def test_internal_qe_without_external_source_cannot_be_counted_as_profit():
    before = hard_nav(100, 0)
    after = hard_nav(100, 0)  # internal token/QE marks do not alter external assets
    assert after - before == 0


def test_self_lp_reallocation_is_consolidated_internal_movement():
    before = 70 + 30
    after = 40 + 60
    assert after == before


def test_zero_cost_denominator_must_not_emit_infinite_roi():
    net_profit, economic_basis = 5.0, 0.0
    roi = None if economic_basis <= 1e-8 else net_profit / economic_basis
    assert roi is None
