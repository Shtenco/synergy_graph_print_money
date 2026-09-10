from synergy_graph.slipstream import encode_mixed_path, FACTORY_MASK, LEGACY_FACTORY_1, LEGACY_FACTORY_2, LATEST_FACTORY


def test_factory_masks_are_distinct():
    assert FACTORY_MASK[LEGACY_FACTORY_1] == 0x100000
    assert FACTORY_MASK[LEGACY_FACTORY_2] == 0
    assert FACTORY_MASK[LATEST_FACTORY] == 0x080000


def test_encode_mixed_path():
    a='0x'+'11'*20
    b='0x'+'22'*20
    c='0x'+'33'*20
    spacings=[0x100000 | 100, 0x080000 | 1]
    raw=encode_mixed_path([a,b,c],spacings)
    assert len(raw)==20+23*2
    assert raw[20:23]==spacings[0].to_bytes(3,'big')
    assert raw[43:46]==spacings[1].to_bytes(3,'big')
