from eth_abi import encode

from synergy_graph.v7_4_uniswap_v4 import (
    INITIALIZE_TOPIC0,
    V4PoolKey,
    decode_initialize_log,
    normalize_pool_id,
)


def topic_address(addr: str) -> str:
    return "0x" + addr.lower().replace("0x", "").rjust(64, "0")


def test_v4_pool_id_is_bytes32():
    pid = "0x" + "11" * 32
    assert normalize_pool_id(pid) == pid


def test_decode_initialize_log_recovers_full_pool_key():
    pid = "0x" + "ab" * 32
    c0 = "0x0000000000000000000000000000000000000000"
    c1 = "0x4200000000000000000000000000000000000006"
    hooks = "0x1111111111111111111111111111111111111111"
    fee = 3000
    tick_spacing = 60
    sqrt_price = 2**96
    tick = -7
    data = "0x" + encode(
        ["uint24", "int24", "address", "uint160", "int24"],
        [fee, tick_spacing, hooks, sqrt_price, tick],
    ).hex()
    log = {
        "topics": [INITIALIZE_TOPIC0, pid, topic_address(c0), topic_address(c1)],
        "data": data,
        "blockNumber": hex(12_345_678),
        "transactionHash": "0x" + "22" * 32,
    }
    key = decode_initialize_log(log)
    assert key.pool_id == pid
    assert key.currency0 == c0
    assert key.currency1 == c1
    assert key.fee == fee
    assert key.tick_spacing == tick_spacing
    assert key.hooks == hooks
    assert key.sqrt_price_x96_at_initialize == sqrt_price
    assert key.tick_at_initialize == tick
    assert key.initialize_block == 12_345_678


def test_quote_tuple_matches_uniswap_pool_key_layout():
    key = V4PoolKey(
        pool_id="0x" + "33" * 32,
        currency0="0x0000000000000000000000000000000000000000",
        currency1="0x4200000000000000000000000000000000000006",
        fee=500,
        tick_spacing=10,
        hooks="0x0000000000000000000000000000000000000000",
        sqrt_price_x96_at_initialize=2**96,
        tick_at_initialize=0,
        initialize_block=1,
        initialize_tx="0x" + "44" * 32,
    )
    assert key.as_quote_tuple() == (
        key.currency0,
        key.currency1,
        500,
        10,
        key.hooks,
    )
