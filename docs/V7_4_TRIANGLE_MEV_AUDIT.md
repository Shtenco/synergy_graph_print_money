# V7.4 recovery audit: triangle arbitrage + enforceable MEV capture

## Recovery baseline
Canonical repository: `Shtenco/synergy_graph_print_money`, branch `main`, commit
`3bcac56deaafca498d815b5166a2a2f44a3e9524`. Canonical version is V7.4,
Base block `51,148,993`; `CURRENT_VERSION.json` says
`TOKEN_CLOSED_SURROGATE_CANDIDATE` and `fork_executable=false`.

Artifacts:
- `contracts/V7_4GlobalPacketExecutor.sol`
- `test/V7_4Run36Packet.t.sol`
- `data/results/v7_4_stateful_token_closed_packet.csv`
- `data/results/v7_4_stateful_token_closed_summary.json`
- `docs/V7_4_TOKEN_CONSERVATION_AND_FORK.md`
- `docs/V7_4_EXACT_FORK_AND_V4_COVERAGE.md`

## Existing result — not fork-proven
The CPMM surrogate records six sequential cycles, 14 foreign swaps, gross
external capture of about $25.0007367, a 35% competition/MEV reserve of
$8.7502579, $0.28 modeled swap gas, and $15.9704789 estimated residual.
The estimated reusable flash draw is $2,171.9290 ($1,556.6380 WETH-equivalent
and $615.2910 USDC). This is not verified Base-mainnet profit.

## Recovered packet inconsistency and branch fix

The `main` branch's original `test/V7_4Run36Packet.t.sol` had stale USDC
amounts that did not match the canonical CSV/summary:

| Item | Canonical packet CSV | Original Solidity test |
|---|---:|---:|
| USDC cycle 1 input | 615.291004 USDC | 613.997129 USDC |
| USDC cycle 2 input | 469.664999 USDC | 468.677356 USDC |
| USDC reusable flash principal | 615.291004 USDC | 613.997129 USDC |

The four WETH amounts already matched the CSV at the snapshot model price
$2,450.43/WETH. In this audit branch, the USDC flash principal and both USDC
cycle inputs have been aligned to the canonical packet values. This is a
source-level consistency fix, **not** proof that the fork executes or that
the modeled $15.9704789 is realized.

The Solidity assertion currently proves only positive post-reserve HardNAV,
not that the realized gain equals the surrogate estimate. Exact fork execution
and gas/fee evidence remain mandatory.

## Route coverage boundary
The global discovery graph records 211 foreign pools, but the strict candidate
summary says only 109 supported/priced foreign pools entered the surrogate
optimizer. The selected six-cycle packet uses:
- four WETH → VIRTUAL → WETH cycles, sharing one Aerodrome V2 pool and
  mutating its state sequentially;
- USDC → USDT → WETH → USDC;
- USDC → EURC → WETH → USDC.

The last two are three-token cycles, but not the separate monetary triangle
RUBC/USDC + RUBX/USDC + RUBC/RUBX. That triangle is not integrated into the
exact executor. The snapshot contains 48 V4 rows and a PoolId recovery/quote
adapter, but the current Solidity executor has no V4 swap implementation.
Thus “all 211 pools/routes tested” is not a supported claim.

## Correct combined accounting model
Keep distinct:
1. `gross_external_pnl`: realized transfer from independent external markets,
   valued from a pinned-block token-balance ledger.
2. `protocol_fee_revenue`: a fee actually transferred through a controlled
   hook/pool or enforceable executor/solver agreement.
3. `competition_reserve`: a risk haircut, not revenue.
4. Gas + L1 + flash fee + slippage + executor payment: actual costs, each once.

For protocol-owned execution:
`DeltaHardNAV = gross_external_pnl - flash_fee - gas - L1 - slippage - other costs`.

For a controlled external executor/solver, protocol fee is
`tau * distributable_gross_profit`; protocol HardNAV receives only that fee
less protocol costs, while the executor receives the remainder less its costs.
Do not count full gross PnL and the fee share as two revenue streams.

A protocol cannot impose a universal involuntary tax on bots trading arbitrary
independent pools. Fees are enforceable at controlled points (e.g. a pool using
the protocol hook) or through an explicit executor/solver agreement. The V7.4
35% haircut is not evidence that 35% is collected from MEV bots.

## Triangle eligibility gates
- Three distinct pools; A→B→C→A closes exactly.
- All quotes exact, same-block, and state-aware; shared pool state mutates after
  each swap.
- Never use aggregator spot rates as execution quotes.
- Own-only RUBC/RUBX triangle: external HardNAV credit = zero.
- Mixed own/foreign route: credit only after consolidated external-token
  accounting attributes the transfer; own LP reserve shifts are not profit.
- Repay every borrowed ERC-20 principal plus actual fee in-kind.
- Promote only after exact fork execution and positive post-cost HardNAV.

## New unit-test layer
`src/synergy_graph/v7_4_triangle_mev.py` and
`tests/test_v7_4_triangle_mev.py` add pure accounting validation: exact closed
triangle, same-block enforcement, own-pool exclusion, and MEV-share accounting
that rejects assumed taxes on uncontrolled pools. These tests do not replace
the exact Base fork test.
