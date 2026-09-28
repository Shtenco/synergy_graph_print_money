from synergy_graph.synergy_contracts import CONTRACT_ID, monetary_simulation_payload

def test_monetary_simulation_cannot_create_realized_pnl_claim():
    p=monetary_simulation_payload(run_id="sim-1",packets=1)
    assert CONTRACT_ID=="synergy.economy.monetary-simulation/v1"
    assert p["simulation_only"] is True
    assert p["external_profit_realized"] is False
    assert p["accounting_authority"] is False
