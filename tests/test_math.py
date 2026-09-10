from synergy_graph.v7 import Pool, own_complete_graph_count, find_discovery_cycles

def test_complete_graph_counts():
    assert own_complete_graph_count(10)==66
    assert own_complete_graph_count(20)==231
    assert own_complete_graph_count(48)==1225

def test_discovery_cycle_is_only_discovered():
    pools=[Pool("0x1","x","ab","a","b",token0_price_usd=2,token1_price_usd=1),Pool("0x2","x","bc","b","c",token0_price_usd=2,token1_price_usd=1),Pool("0x3","x","ca","c","a",token0_price_usd=1,token1_price_usd=3.333333333)]
    out=find_discovery_cycles(pools,max_hops=3,top_k=10)
    assert out and all(x["stage"]=="DISCOVERED" for x in out)
