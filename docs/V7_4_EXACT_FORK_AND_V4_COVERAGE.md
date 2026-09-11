# V7.4 exact fork proof + Uniswap V4 coverage

This document continues the full Economic-OS experiment after the stricter token-denomination audit. It does not replace the huge graph with one isolated route.

## Graph under test

Run #36 remains the pinned evidence basis:

- Base block: `51,148,993`;
- canonical external assets: `98`;
- monetary/control vertices: `RUBC`, `RUBX`;
- total graph vertices: `100`;
- protocol conceptual complete cross graph: `K_100 = 4,950` own pools;
- observed foreign physical pools: `211`;
- total conceptual physical pools: `5,161`.

The global graph is the discovery/control object. Exact execution is naturally sparse: after stateful token-conservation optimization, only the subset of edges needed by the optimum packet should be touched in the atomic transaction. Unused `K_100` edges remain available alternatives but are not charged gas merely for existing in the graph model.

## Why V7.3 was demoted from executable profit

The V7.3 36-leg settlement packet had positive oracle-valued aggregate transfer, but token-specific deficits and surpluses were allowed to cancel by USD value. Balancer requires repayment in the same ERC-20 denominations. V7.4 therefore treats V7.3 `+$107.73` only as a relaxed-denomination settlement upper bound.

The stricter stateful surrogate optimizer found six sequential token-closed cycles (14 foreign swaps):

- gross external value: `$25.0007367`;
- 35% competition/MEV reserve: `$8.7502579`;
- surrogate gas: `$0.28`;
- post-cost candidate: `+$15.9704789`;
- optimized concurrent flash draw: about `$2,171.93` (`~$1,556.64` WETH-equivalent plus `~$615.29` USDC-equivalent);
- mathematical personal HardNAV: `$100 -> $115.9704789`.

This remains **PENDING**, not `FORK_EXECUTABLE`, until the exact fork passes.

## Strengthened exact fork assertion

`test/V7_4Run36Packet.t.sol` now checks all of the following at Base block `51,148,993`:

1. Balancer Vault actually holds at least the requested WETH and USDC amounts.
2. `V7_4GlobalPacketExecutor` returns from `startPacket()` only after every borrowed ERC-20 has been repaid in-kind with the actual `feeAmounts[]` supplied by Balancer.
3. WETH and USDC each have positive post-repayment balances; USD aggregation cannot hide a token deficit.
4. WETH profit is converted using the Chainlink Standard ETH/USD proxy on Base at the same pinned fork state (`0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70`). USDC is the HardNAV numeraire.
5. Execution gas is measured around the entire packet and converted to USD using `block.basefee` and the same pinned ETH/USD feed.
6. Only 65% of raw external profit is retained after a 35% competition/MEV reserve.
7. An additional fixed `$1` L1-data/miscellaneous cost reserve is deducted.
8. Final modeled HardNAV after these reserves must exceed the permanent personal baseline of `$100`.

The actual Balancer flash fee is already part of the executor settlement and is not hard-coded to zero in Solidity.

## Exact CLMM/V3 behavior

The six-cycle strict candidate uses only protocol families already represented by exact execution code:

- Aerodrome V2: direct `getAmountOut` + `swap`;
- Uniswap V3: direct pool `swap` with `uniswapV3SwapCallback`;
- Aerodrome Slipstream: V3-compatible direct pool `swap` with the same callback form.

All six cycles mutate the real shared pool state sequentially on the fork. In particular, the same Aerodrome VIRTUAL/WETH pool is not reset between the four WETH cycles, and the same Uniswap V3 WETH/USDC pool is not reset between the two USDC cycles.

## Uniswap V4 expansion for the full foreign graph

Run #36 contains 48 `uniswap-v4-base` rows. In V4 a pool is not an independent contract address: aggregators commonly expose the 32-byte `PoolId`. Exact execution therefore cannot probe it as a V2/V3 contract.

`src/synergy_graph/v7_4_uniswap_v4.py` implements the correct pinned-block recovery path:

`PoolId -> PoolManager Initialize log -> PoolKey(currency0,currency1,fee,tickSpacing,hooks) -> V4Quoter.quoteExactInputSingle`.

Base deployment constants used by the adapter:

- V4 PoolManager: `0x498581ff718922c3f8e6a244956af099b2652b2b`;
- StateView: `0xa3c0c9b65bad0b08107aa264b0f3db444b867a71`;
- V4Quoter: `0x0d5e0f971ed27fbff6c2837bf31316121532048d`.

Pool-key recovery is based on the indexed `Initialize(bytes32,address,address,uint24,int24,address,uint160,int24)` event. It scans backwards at/before the pinned block and reduces `eth_getLogs` range if the RPC rejects a large range. A pool that cannot be recovered or quoted is marked as a failure; it is never replaced by a CPMM surrogate in the exact layer.

`scripts/run_v7_4_v4_exact.py` batch-processes the V4 rows, checks snapshot currency-pair consistency and attempts exact directional V4Quoter calls at one pinned block. Pools whose hooks require non-empty custom `hookData` may fail explicitly until a hook-specific adapter is supplied.

## Evidence state after these changes

Current strongest proof ladder:

`5,161-pool global graph`

`-> V7.3 relaxed 36-leg upper bound +$107.73`

`-> denomination audit rejects that packet as flash-executable`

`-> V7.4 stateful token-closed surrogate packet: 6 cycles / 14 foreign swaps / +$15.9705 candidate`

`-> exact V3/Slipstream/V2 multi-token fork executor written`

`-> strengthened post-repayment + risk + gas + HardNAV assertion written`

`-> Uniswap V4 PoolId recovery/exact-quote adapter written for expanding exact graph coverage`

`-> hosted GitHub runner still fails before first workflow step (no checkout, steps=null)`

`-> FORK_EXECUTABLE: not proven yet`.

No exact positive Base-mainnet claim should be made until a runner or another archive-capable execution environment actually completes the fork test.
