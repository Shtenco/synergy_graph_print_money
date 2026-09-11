from __future__ import annotations

from typing import Iterable

from .v7 import Pool, Rpc, decode_address, decode_uint, safe_call
from .v7_exact import (
    AERODROME_CL_QUOTERS,
    UNISWAP_V3_FACTORY_BASE,
    PoolState,
    calldata,
    exact_step_quote,
)

# GeckoTerminal currently exposes these Aerodrome generations as separate dex ids.
# Addresses are taken from Aerodrome's official Slipstream deployment metadata.
AERODROME_CL_SOURCE_FACTORY = {
    "aerodrome-slipstream": "0x5e7bb104d84c7cb9b682aac2f3d509f5f406809a",
    "aerodrome-slipstream-2": "0xade65c38cd4849adba595a4323a8c7ddfe89716a",
    "aerodrome-slipstream-3": "0xf8f2eb4940cfe7d13603dddd87f123820fc061ef",
}

SUPPORTED_SOURCE_DEX = {
    "uniswap-v3-base",
    "aerodrome-base",
    "aerodrome-v2",
    *AERODROME_CL_SOURCE_FACTORY.keys(),
}


def is_source_quoteable(p: Pool) -> bool:
    return p.dex_id.lower() in SUPPORTED_SOURCE_DEX and len(p.address) == 42 and p.address.startswith("0x")


def quoteable_pool_subset(pools: Iterable[Pool]) -> list[Pool]:
    return [p for p in pools if is_source_quoteable(p)]


def _signed_int24_from_uint256(raw: int) -> int:
    # ABI int24 is sign-extended to 256 bits.
    if raw >= 1 << 255:
        raw -= 1 << 256
    return int(raw)


def classify_pool_v2(rpc: Rpc, p: Pool, block: str) -> PoolState:
    """Classify using the source DEX identity first, then minimal on-chain probes.

    The V7.0 classifier called token0/token1/factory/stable/reserves/fee/tickSpacing
    for every candidate pool. On a public RPC, transient failures in any of those
    calls could collapse a healthy pool into `unsupported`. V7.1 uses the known
    source family to request only the state needed by that adapter.
    """
    source = p.dex_id.lower()
    t0 = p.token0.lower()
    t1 = p.token1.lower()

    # Override API ordering only when pool-native token0/token1 are available.
    on_t0 = decode_address(safe_call(rpc, p.address, "0x0dfe1681", block)).lower()
    on_t1 = decode_address(safe_call(rpc, p.address, "0xd21220a7", block)).lower()
    if on_t0 and on_t1:
        t0, t1 = on_t0, on_t1

    if source == "uniswap-v3-base":
        fee_data = safe_call(rpc, p.address, calldata("fee()", [], []), block)
        fee = decode_uint(fee_data) if fee_data and fee_data != "0x" else None
        tick_data = safe_call(rpc, p.address, calldata("tickSpacing()", [], []), block)
        tick_spacing = _signed_int24_from_uint256(decode_uint(tick_data)) if tick_data and tick_data != "0x" else None
        kind = "uniswap_v3" if fee is not None else "unsupported"
        return PoolState(p.address.lower(), t0, t1, UNISWAP_V3_FACTORY_BASE, kind, None, None, None, fee, tick_spacing, p.dex_id)

    if source in AERODROME_CL_SOURCE_FACTORY:
        tick_data = safe_call(rpc, p.address, calldata("tickSpacing()", [], []), block)
        tick_spacing = _signed_int24_from_uint256(decode_uint(tick_data)) if tick_data and tick_data != "0x" else None
        factory = AERODROME_CL_SOURCE_FACTORY[source]
        kind = "aerodrome_cl" if tick_spacing is not None and factory in AERODROME_CL_QUOTERS else "unsupported"
        return PoolState(p.address.lower(), t0, t1, factory, kind, None, None, None, None, tick_spacing, p.dex_id)

    if source in {"aerodrome-base", "aerodrome-v2"}:
        stable_data = safe_call(rpc, p.address, calldata("stable()", [], []), block)
        stable = bool(decode_uint(stable_data)) if stable_data and stable_data != "0x" else None
        reserves = safe_call(rpc, p.address, "0x0902f1ac", block)
        r0 = r1 = None
        if reserves and reserves != "0x":
            h = reserves[2:]
            if len(h) >= 128:
                r0, r1 = int(h[:64], 16), int(h[64:128], 16)
        probe = safe_call(
            rpc,
            p.address,
            calldata("getAmountOut(uint256,address)", ["uint256", "address"], [10**6, t0]),
            block,
        )
        kind = "aerodrome_v2" if probe and r0 is not None and r1 is not None else "unsupported"
        return PoolState(p.address.lower(), t0, t1, "", kind, r0, r1, stable, None, None, p.dex_id)

    return PoolState(p.address.lower(), t0, t1, "", "unsupported", source_dex=p.dex_id)


def exact_step_quote_v2(
    rpc: Rpc,
    p: Pool,
    state: PoolState,
    token_in: str,
    token_out: str,
    amount_in: int,
    block: str,
) -> tuple[int, int]:
    # V7.0's exact quote implementations are retained; V7.1 improves how the
    # state is classified and how the matching quoter/factory is selected.
    return exact_step_quote(rpc, p, state, token_in, token_out, amount_in, block)
