from synergy_graph.uniswap_v3 import encode_path


def test_encode_path_two_hops():
    a="0x"+"11"*20
    b="0x"+"22"*20
    c="0x"+"33"*20
    raw=encode_path([a,b,c],[500,3000])
    assert len(raw)==20+23*2
    assert raw[:20]==bytes.fromhex("11"*20)
    assert raw[20:23]==(500).to_bytes(3,"big")
    assert raw[23:43]==bytes.fromhex("22"*20)
    assert raw[43:46]==(3000).to_bytes(3,"big")
    assert raw[46:66]==bytes.fromhex("33"*20)


def test_encode_path_requires_fee_per_hop():
    a="0x"+"11"*20
    b="0x"+"22"*20
    try:
        encode_path([a,b],[])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
