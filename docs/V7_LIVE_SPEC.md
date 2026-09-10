# SAG V7 — Live Base Mainnet specification

## Goal

Replace synthetic foreign edges with a reproducible Base block snapshot and separate *price discovery* from *execution proof*.

## Data acquisition

1. Query GeckoTerminal `GET /api/v2/networks/base/pools?page=N` for enough pages to cover top-N (default 240).
2. Persist pool address, dex id, token addresses/symbols, reserve USD and published spot prices.
3. Read one Base latest block number and pin RPC calls to that block tag.
4. Verify bytecode and probe `token0/token1`, `getReserves` (V2/CPMM), `slot0` and `fee` (V3/CLMM).
5. Read ERC20 `balanceOf(pool)` for both tokens.

## Graph

Each physical pool is a separate edge even if multiple pools share the same token pair. Create both directions. Discovery weight uses snapshot price only to identify candidate consistency cycles: `w=-ln(rate_after_reported_fee)`.

## Validation ladder

- `DISCOVERED`: cycle exists in normalized snapshot.
- `RPC_VERIFIED`: addresses have bytecode and token identities are coherent.
- `STATE_VERIFIED`: reserve/slot state read at one block.
- `QUOTE_VERIFIED`: exact protocol adapter quotes complete route with `eth_call` against pinned state.
- `FORK_EXECUTABLE`: Base fork transaction executes, repays flash loan and leaves positive hard-asset delta after gas/MEV.

Only `QUOTE_VERIFIED` and `FORK_EXECUTABLE` may contribute to executable PnL.

## Flash liquidity

Balancer V2 Base Vault: `0xBA12222222228d8Ba445958a75a0704d566BF2C8`. Before a token is considered borrowable, V7 checks the Vault live ERC20 balance. Runtime execution must enforce repayment and actual fee terms.

## Own graph

If the snapshot contains `M` unique tokens, the conceptual own complete graph with RUBC/RUBX is `C(M+2,2)` 50/50 CPMM pools. Discovery does not deploy thousands of pools; it emits the required pair count/set. Deployment and liquidity allocation are separate phases.

## Acceptance criteria

A real positive candidate requires: same pinned Base state; exact route output > exact input + flash fee + gas + MEV margin; complete flash repayment; hard-asset profit; no double-counting own LP; successful fork execution; positive sensitivity under worse gas/fill/competition assumptions.
