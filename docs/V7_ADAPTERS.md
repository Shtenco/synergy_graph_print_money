# V7 execution adapters

## Aerodrome classic / V2 — implemented

V7 identifies an Aerodrome classic pool only when on-chain `token0()`, `token1()`, `stable()`, `factory()` and the canonical factory `getPool(token0,token1,stable)` agree. The exact quote uses the pool's own `getAmountOut(uint256,address)` at the pinned Base block. This means the pool itself applies its current `PoolFactory.getFee(pool,stable)` and, for stable pools, its actual stable invariant. V7 separately records the on-chain fee in basis points.

A `QUOTE_VERIFIED` candidate must be a closed cycle of these verified pools, have enough of its start token in the Balancer V2 Vault for the selected notional, and remain positive after the configured MEV and gas reserve guards.

## Foundry/Balancer fork — implemented for Aerodrome classic cycles

`render_fork_test.py` converts the best exact cycle into a concrete Solidity test. On the pinned Base fork it requests the selected start token from the real Balancer V2 Vault, routes through the real Aerodrome Router, repays principal plus the callback's actual `feeAmount`, and requires a positive start-token remainder. The test also compares that remainder with measured execution gas using the live gas-price snapshot and a configurable MEV guard.

## Uniswap V3 / Aerodrome Slipstream / Pancake V3 — discovery/state only for now

These pools are intentionally not approximated as CPMM. They require protocol-specific tick-aware quote adapters. Until those adapters are present they may be `DISCOVERED`, `RPC_VERIFIED` or `STATE_VERIFIED`, but not `QUOTE_VERIFIED`/`FORK_EXECUTABLE`.
