from __future__ import annotations

"""Pinned-block Uniswap V4 PoolId -> PoolKey recovery and exact quoting.

Uniswap V4 pools are not separate contracts.  Aggregators commonly expose the
32-byte PoolId where older AMMs expose a pool address.  The PoolManager does
not persist the full PoolKey, so an exact adapter must recover the key from the
PoolManager Initialize event before asking the V4Quoter for a quote.

This module is deliberately independent of aggregator spot prices.  All RPC
reads are pinned to the requested Base block.
"""

from dataclasses import asdict, dataclass
from typing import Any

from eth_abi import decode
from eth_utils import keccak

from .v7_exact import calldata
from .v7_rpc import ReliableRpc

BASE_V4_POOL_MANAGER = "0x498581ff718922c3f8e6a244956af099b2652b2b"
BASE_V4_STATE_VIEW = "0xa3c0c9b65bad0b08107aa264b0f3db444b867a71"
BASE_V4_QUOTER = "0x0d5e0f971ed27fbff6c2837bf31316121532048d"

INITIALIZE_EVENT_SIGNATURE = "Initialize(bytes32,address,address,uint24,int24,address,uint160,int24)"
INITIALIZE_TOPIC0 = "0x" + keccak(text=INITIALIZE_EVENT_SIGNATURE).hex()


@dataclass(frozen=True)
class V4PoolKey:
    pool_id: str
    currency0: str
    currency1: str
    fee: int
    tick_spacing: int
    hooks: str
    sqrt_price_x96_at_initialize: int
    tick_at_initialize: int
    initialize_block: int
    initialize_tx: str

    def as_quote_tuple(self) -> tuple[str, str, int, int, str]:
        return (self.currency0, self.currency1, self.fee, self.tick_spacing, self.hooks)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_pool_id(pool_id: str) -> str:
    p = pool_id.lower()
    if not p.startswith("0x"):
        p = "0x" + p
    if len(p) != 66:
        raise ValueError(f"V4 PoolId must be bytes32, got {pool_id}")
    int(p[2:], 16)
    return p


def _topic_address(topic: str) -> str:
    h = topic[2:] if topic.startswith("0x") else topic
    if len(h) != 64:
        raise ValueError("indexed address topic must be 32 bytes")
    return "0x" + h[-40:].lower()


def _signed_int24(value: int) -> int:
    # eth_abi decode('int24') already returns a signed value; retained as a
    # defensive helper for callers passing an unsigned representation.
    if value >= 1 << 23:
        value -= 1 << 24
    return value


def decode_initialize_log(log: dict[str, Any]) -> V4PoolKey:
    topics = log.get("topics") or []
    if len(topics) < 4 or topics[0].lower() != INITIALIZE_TOPIC0.lower():
        raise ValueError("not a V4 Initialize log")
    pool_id = normalize_pool_id(topics[1])
    currency0 = _topic_address(topics[2])
    currency1 = _topic_address(topics[3])
    raw = bytes.fromhex((log.get("data") or "0x")[2:])
    fee, tick_spacing, hooks, sqrt_price_x96, tick = decode(
        ["uint24", "int24", "address", "uint160", "int24"], raw
    )
    block_number = int(log.get("blockNumber", "0x0"), 16)
    return V4PoolKey(
        pool_id=pool_id,
        currency0=currency0,
        currency1=currency1,
        fee=int(fee),
        tick_spacing=int(tick_spacing),
        hooks=str(hooks).lower(),
        sqrt_price_x96_at_initialize=int(sqrt_price_x96),
        tick_at_initialize=int(tick),
        initialize_block=block_number,
        initialize_tx=(log.get("transactionHash") or "").lower(),
    )


def recover_pool_key(
    rpc: ReliableRpc,
    pool_id: str,
    pinned_block: int,
    *,
    min_block: int = 0,
    initial_chunk: int = 100_000,
    min_chunk: int = 1_000,
) -> V4PoolKey:
    """Recover PoolKey by scanning indexed Initialize logs backwards.

    Many public RPCs cap eth_getLogs block ranges.  The scanner therefore
    reduces the range on provider errors instead of silently treating an RPC
    failure as 'pool not found'.  Since PoolId is indexed, a successful query
    normally returns at most one Initialize event.
    """
    pid = normalize_pool_id(pool_id)
    hi = pinned_block
    chunk = max(min_chunk, initial_chunk)
    while hi >= min_block:
        lo = max(min_block, hi - chunk + 1)
        filt = {
            "address": BASE_V4_POOL_MANAGER,
            "fromBlock": hex(lo),
            "toBlock": hex(hi),
            "topics": [INITIALIZE_TOPIC0, pid],
        }
        try:
            logs = rpc.call("eth_getLogs", [filt])
        except Exception:
            if chunk <= min_chunk:
                raise
            chunk = max(min_chunk, chunk // 2)
            continue
        if logs:
            decoded = [decode_initialize_log(x) for x in logs]
            decoded = [x for x in decoded if x.pool_id == pid and x.initialize_block <= pinned_block]
            if not decoded:
                raise RuntimeError("Initialize log returned but did not match requested PoolId")
            return min(decoded, key=lambda x: x.initialize_block)
        hi = lo - 1
    raise LookupError(f"Initialize event not found for V4 PoolId {pid} at/before block {pinned_block}")


def quote_exact_input_single(
    rpc: ReliableRpc,
    key: V4PoolKey,
    token_in: str,
    amount_in: int,
    pinned_block: int,
    hook_data: bytes = b"",
) -> tuple[int, int]:
    if amount_in <= 0 or amount_in >= 1 << 128:
        raise ValueError("V4 exactAmount must fit uint128 and be positive")
    token = token_in.lower()
    if token == key.currency0:
        zero_for_one = True
    elif token == key.currency1:
        zero_for_one = False
    else:
        raise ValueError("token_in is not a PoolKey currency")

    signature = "quoteExactInputSingle(((address,address,uint24,int24,address),bool,uint128,bytes))"
    params = (key.as_quote_tuple(), zero_for_one, amount_in, hook_data)
    data = calldata(signature, ["((address,address,uint24,int24,address),bool,uint128,bytes)"], [params])
    result = rpc.eth_call(BASE_V4_QUOTER, data, hex(pinned_block))
    amount_out, gas_estimate = decode(["uint256", "uint256"], bytes.fromhex(result[2:]))
    return int(amount_out), int(gas_estimate)


def recover_and_quote(
    rpc: ReliableRpc,
    pool_id: str,
    token_in: str,
    amount_in: int,
    pinned_block: int,
) -> tuple[V4PoolKey, int, int]:
    key = recover_pool_key(rpc, pool_id, pinned_block)
    amount_out, gas_estimate = quote_exact_input_single(rpc, key, token_in, amount_in, pinned_block)
    return key, amount_out, gas_estimate
