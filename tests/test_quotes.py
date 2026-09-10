from synergy_graph.quotes import abi_call


def test_abi_selector_balance_of():
    assert abi_call("balanceOf(address)",["address"],["0x0000000000000000000000000000000000000001"]).startswith("0x70a08231")


def test_abi_selector_factory():
    assert abi_call("factory()") == "0xc45a0155"
