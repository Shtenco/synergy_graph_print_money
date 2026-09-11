# V7 live adapters and proof ladder

V7 intentionally separates a cheap discovery layer from executable proof.

## Discovery

`src/synergy_graph/v7.py` downloads up to 240 Base pools from GeckoTerminal, normalizes pool/token addresses, pins one Base block, probes bytecode/state, emits physical multigraph edges and candidate closed cycles. Aggregator spot prices are candidate generation only.

## Exact quote engine

`src/synergy_graph/v7_exact.py` classifies each candidate pool at the pinned block and supports:

- Aerodrome V2 pools: direct pool `getAmountOut(amountIn, tokenIn)` quote.
- Generic Uniswap-V2-style CPMM pools: exact integer reserve formula when `getReserves` and a reliable fee are available; these are quote-only unless a safe execution adapter exists.
- Uniswap V3 on Base: QuoterV2 exact-input-single at the pinned block.
- Aerodrome Slipstream concentrated-liquidity pools: factory-aware Quoter at the pinned block.

For every candidate it sweeps a dollar-sized input grid capped by both `$50,000` configured flash capacity and the actual Balancer Vault balance of the start token. It then deducts estimated gas, configured flash fee, and an explicit competition/MEV haircut. `QUOTE_VERIFIED` requires positive net hard-asset value.

## Fork executor

`contracts/V7ForeignCycleExecutor.sol` deliberately supports only explicit pool kinds for which the route can be reproduced on fork. The callback stores the contract's pre-existing start-token balance so seed capital cannot be mislabeled as arbitrage profit. A route must chain token-to-token, end in the flash token, repay `amount + feeAmount`, and retain at least `minProfitRaw` over the pre-flash balance.

The workflow writes a generated Foundry test only when the best candidate is composed entirely of fork-supported adapters. The test forks **the exact block used by discovery/quotes** and invokes the Balancer flash route. A successful Forge transaction is the `FORK_EXECUTABLE` gate.

## Status semantics

- `DISCOVERED`: candidate from snapshot prices.
- `RPC_VERIFIED`: pool/token contracts and identities verified.
- `STATE_VERIFIED`: required reserves/slot/fee state read at the pinned block.
- `QUOTE_VERIFIED`: exact adapter route has positive post-cost estimate.
- `FORK_EXECUTABLE`: generated same-block Base fork transaction succeeds, repays flash loan, and leaves positive hard-asset delta.

Anything below `QUOTE_VERIFIED` must never be presented as executable arbitrage. Anything below `FORK_EXECUTABLE` must never be presented as a validated transaction strategy.
