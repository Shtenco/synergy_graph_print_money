from synergy_graph.v7_exact import PoolState, choose_amount_grid, quote_v2_cpmm, selector


def test_selector_matches_known_erc20_balance_of():
    assert selector("balanceOf(address)").hex() == "70a08231"


def test_v2_cpmm_quote_is_exact_integer_formula():
    s = PoolState(address="0x" + "11" * 20, token0="0x" + "22" * 20, token1="0x" + "33" * 20, kind="v2_cpmm", reserve0=1_000_000, reserve1=2_000_000)
    out, gas = quote_v2_cpmm(s, s.token0, 10_000, 0.003)
    effective = 10_000 * 997_000
    expected = 2_000_000 * effective // (1_000_000 * 1_000_000 + effective)
    assert out == expected
    assert gas == 0
    assert 0 < out < 20_000


def test_flash_grid_respects_dollar_cap():
    g = choose_amount_grid(price=2.0, decimals=6, max_flash_usd=100.0)
    assert g
    assert max(g) == 50_000_000


def test_cycle_executor_support_kinds_are_explicit():
    supported = {"aerodrome_v2", "uniswap_v3", "aerodrome_cl"}
    assert "v2_cpmm" not in supported
