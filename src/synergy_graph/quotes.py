from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from eth_abi import encode
from eth_utils import keccak

from .v7 import BALANCER_V2_VAULT, Pool, Rpc, decode_address, decode_uint

AERODROME_V2_FACTORY = "0x420dd381b31aef6683db6b902084cb0ffec40da"
AERODROME_V2_ROUTER = "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43"


def abi_call(signature: str, types: list[str] | None = None, values: list[Any] | None = None) -> str:
    types = types or []
    values = values or []
    selector = keccak(text=signature)[:4]
    payload = selector + (encode(types, values) if types else b"")
    return "0x" + payload.hex()


def call_uint(rpc: Rpc, to: str, signature: str, types: list[str], values: list[Any], block: str) -> int:
    data = rpc.eth_call(to, abi_call(signature, types, values), block)
    return decode_uint(data)


def call_bool(rpc: Rpc, to: str, signature: str, block: str) -> bool:
    return bool(call_uint(rpc, to, signature, [], [], block))


def call_address(rpc: Rpc, to: str, signature: str, types: list[str], values: list[Any], block: str) -> str:
    data = rpc.eth_call(to, abi_call(signature, types, values), block)
    return decode_address(data).lower()


def erc20_decimals(rpc: Rpc, token: str, block: str) -> int:
    return call_uint(rpc, token, "decimals()", [], [], block)


def erc20_balance(rpc: Rpc, token: str, account: str, block: str) -> int:
    return call_uint(rpc, token, "balanceOf(address)", ["address"], [account], block)


@dataclass
class AeroPoolMeta:
    address: str
    token0: str
    token1: str
    stable: bool
    factory: str
    fee_bps: int


def inspect_aerodrome_v2_pool(rpc: Rpc, pool: Pool, block: str) -> AeroPoolMeta | None:
    try:
        token0 = call_address(rpc, pool.address, "token0()", [], [], block)
        token1 = call_address(rpc, pool.address, "token1()", [], [], block)
        stable = call_bool(rpc, pool.address, "stable()", block)
        factory = call_address(rpc, pool.address, "factory()", [], [], block)
        if factory != AERODROME_V2_FACTORY:
            return None
        if {token0, token1} != {pool.token0.lower(), pool.token1.lower()}:
            return None
        canonical = call_address(
            rpc,
            factory,
            "getPool(address,address,bool)",
            ["address", "address", "bool"],
            [token0, token1, stable],
            block,
        )
        if canonical != pool.address.lower():
            return None
        fee_bps = call_uint(
            rpc,
            factory,
            "getFee(address,bool)",
            ["address", "bool"],
            [pool.address, stable],
            block,
        )
        return AeroPoolMeta(pool.address.lower(), token0, token1, stable, factory, fee_bps)
    except Exception:
        return None


def aerodrome_v2_amount_out(rpc: Rpc, pool: str, amount_in: int, token_in: str, block: str) -> int:
    return call_uint(
        rpc,
        pool,
        "getAmountOut(uint256,address)",
        ["uint256", "address"],
        [amount_in, token_in],
        block,
    )


def token_price_usd(token: str, pools: list[Pool]) -> float:
    token = token.lower()
    vals: list[tuple[float, float]] = []
    for p in pools:
        if p.token0.lower() == token and p.token0_price_usd > 0:
            vals.append((p.reserve_usd, p.token0_price_usd))
        elif p.token1.lower() == token and p.token1_price_usd > 0:
            vals.append((p.reserve_usd, p.token1_price_usd))
    if not vals:
        return 0.0
    vals.sort(reverse=True)
    return vals[0][1]


def _usd_grid(min_usd: float, max_usd: float, points: int) -> list[float]:
    if max_usd <= 0:
        return []
    min_usd = min(max(min_usd, 1e-9), max_usd)
    if points <= 1 or math.isclose(min_usd, max_usd):
        return [max_usd]
    ratio = max_usd / min_usd
    return sorted({min_usd * (ratio ** (i / (points - 1))) for i in range(points)} | {max_usd})


def optimize_aerodrome_v2_cycle(
    rpc: Rpc,
    candidate: dict[str, Any],
    pools: list[Pool],
    block: str,
    max_flash_usd: float = 50_000.0,
    min_trade_usd: float = 0.25,
    grid_points: int = 24,
    mev_guard_bps: float = 5.0,
    gas_reserve_usd: float = 0.05,
) -> dict[str, Any] | None:
    pool_map = {p.address.lower(): p for p in pools}
    addresses = [x.lower() for x in str(candidate["pool_addresses"]).split("|") if x]
    tokens = [x.lower() for x in str(candidate["token_path"]).split("|") if x]
    if len(tokens) != len(addresses) + 1 or not tokens or tokens[0] != tokens[-1]:
        return None

    metas: list[AeroPoolMeta] = []
    route_pools: list[Pool] = []
    for i, address in enumerate(addresses):
        pool = pool_map.get(address)
        if pool is None:
            return None
        meta = inspect_aerodrome_v2_pool(rpc, pool, block)
        if meta is None or {tokens[i], tokens[i + 1]} != {meta.token0, meta.token1}:
            return None
        metas.append(meta)
        route_pools.append(pool)

    start = tokens[0]
    decimals = erc20_decimals(rpc, start, block)
    if decimals > 36:
        return None
    px = token_price_usd(start, pools)
    if px <= 0:
        return None
    vault_raw = erc20_balance(rpc, start, BALANCER_V2_VAULT, block)
    vault_usd = vault_raw / (10**decimals) * px
    max_usd = min(max_flash_usd, vault_usd)
    if max_usd < min_trade_usd:
        return None

    best: dict[str, Any] | None = None
    quote_errors = 0
    for usd in _usd_grid(min_trade_usd, max_usd, grid_points):
        amount_in = int(usd / px * (10**decimals))
        if amount_in <= 0 or amount_in > vault_raw:
            continue
        amount = amount_in
        try:
            for i, meta in enumerate(metas):
                amount = aerodrome_v2_amount_out(rpc, meta.address, amount, tokens[i], block)
                if amount <= 0:
                    raise RuntimeError("zero quote")
        except Exception:
            quote_errors += 1
            continue
        profit_raw = amount - amount_in
        profit_usd = profit_raw / (10**decimals) * px
        gross_bps = (amount / amount_in - 1.0) * 10_000.0
        guarded_net_usd = profit_usd - usd * mev_guard_bps / 10_000.0 - gas_reserve_usd
        row = {
            "stage": "QUOTE_VERIFIED" if guarded_net_usd > 0 else "QUOTE_REJECTED",
            "block_number": int(block, 16),
            "start_token": start,
            "start_token_decimals": decimals,
            "start_token_price_usd": px,
            "vault_balance_raw": vault_raw,
            "vault_balance_usd": vault_usd,
            "amount_in_raw": amount_in,
            "amount_in_usd": usd,
            "amount_out_raw": amount,
            "gross_profit_raw": profit_raw,
            "gross_profit_usd": profit_usd,
            "gross_edge_bps_exact": gross_bps,
            "mev_guard_bps": mev_guard_bps,
            "gas_reserve_usd": gas_reserve_usd,
            "guarded_net_usd": guarded_net_usd,
            "hops": len(addresses),
            "pool_addresses": "|".join(addresses),
            "token_path": "|".join(tokens),
            "stable_flags": "|".join("1" if m.stable else "0" for m in metas),
            "factory_addresses": "|".join(m.factory for m in metas),
            "fee_bps_onchain": "|".join(str(m.fee_bps) for m in metas),
            "router": AERODROME_V2_ROUTER,
            "quote_errors_during_grid": quote_errors,
        }
        if best is None or row["guarded_net_usd"] > best["guarded_net_usd"]:
            best = row
    return best
