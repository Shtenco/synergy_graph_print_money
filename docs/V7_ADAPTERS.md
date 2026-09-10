# V7 execution adapters

## Validation rule

`DISCOVERED` is never treated as profit. A route becomes economically meaningful only after it passes a pinned-block protocol-native quote. It becomes executable evidence only after the same route succeeds on a Base fork, repays the real Balancer Vault principal plus the callback-reported fee, and remains positive after measured gas plus the configured MEV guard.

## Uniswap V3 on Base — exact quote + fork path implemented

Canonical Base addresses used by the adapter:

- V3 factory: `0x33128a8fC17869897dcE68Ed026d694621f6FDfD`
- QuoterV2: `0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a`
- SwapRouter02: `0x2626664c2603336E57B271c5C0b26F421741e481`

A discovered `uniswap-v3-base` pool is accepted only if on-chain `token0()`, `token1()`, `fee()` and `factory()` are readable at the pinned block, the factory is canonical, and `factory.getPool(token0,token1,fee)` returns that exact pool address. The route is then encoded as the native V3 `token|fee|token|...` byte path and quoted through `QuoterV2.quoteExactInput(bytes,uint256)` at that same block.

The optimizer rotates a closed cycle so the start token can be chosen according to real Balancer Vault liquidity, sizes the trade up to the configured `$50,000` ceiling, and records exact amount-out, fee tiers, Quoter gas estimate, gross edge, MEV guard and guarded net USD.

`render_fork_test.py` converts a `QUOTE_VERIFIED` Uniswap V3 cycle into a concrete Solidity test. On the pinned Base fork it flash-borrows the selected start token from the real Balancer V2 Vault, calls the real Base SwapRouter02 with the exact encoded path, repays principal plus the callback's actual `feeAmount`, and requires the remaining start-token profit to exceed measured execution gas plus the MEV guard.

## Aerodrome classic / V2 — exact quote + fork path implemented

V7 identifies an Aerodrome classic pool only when on-chain `token0()`, `token1()`, `stable()`, `factory()` and the canonical factory `getPool(token0,token1,stable)` agree. The exact quote uses the pool's own `getAmountOut(uint256,address)` at the pinned Base block. This means the pool itself applies its current `PoolFactory.getFee(pool,stable)` and, for stable pools, its actual stable invariant. V7 separately records the on-chain fee in basis points.

A `QUOTE_VERIFIED` candidate must be a closed cycle of these verified pools, have enough of its start token in the Balancer V2 Vault for the selected notional, and remain positive after the configured MEV and gas reserve guards. The generated fork proof routes through the real Aerodrome Router and applies the same Balancer repayment invariant.

## Generic CPMM/V2, Aerodrome Slipstream, Pancake V3 and Uniswap V4 — next coverage

These protocols must not be silently converted to a 50/50 CPMM when their real invariant is different. The V7 discovery graph may contain them, but they are not promoted to `QUOTE_VERIFIED` until their protocol-native adapter has validated the route at the pinned block.

Uniswap V4 deserves special handling because GeckoTerminal-style data can expose a bytes32 pool id rather than a standalone pool contract address. Such ids must never be sent to `eth_getCode` as if they were V2/V3 pair addresses; validation must go through PoolManager/StateView/Quoter using the V4 pool key.
