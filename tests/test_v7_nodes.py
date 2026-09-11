from synergy_graph.v7 import Pool, own_complete_graph_count
from synergy_graph.v7_nodes import ZERO_ADDRESS, WETH_BASE, canonical_external_tokens


def test_native_eth_sentinel_maps_to_existing_weth_node():
    pools = [
        Pool("0xpool1", "v4", "ETH/USDC", ZERO_ADDRESS, "0xusdc"),
        Pool("0xpool2", "v3", "WETH/USDC", WETH_BASE, "0xusdc"),
    ]
    nodes = canonical_external_tokens(pools)
    assert ZERO_ADDRESS not in nodes
    assert nodes == [WETH_BASE, "0xusdc"]
    # 2 external assets + RUBC + RUBX => C(4,2) = 6, not C(5,2) = 10.
    assert own_complete_graph_count(len(nodes)) == 6
