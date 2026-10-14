# V8 Single-Contract Flash Graph Engine

## Goal

Implement the original RUBC/RUBX mechanism without deploying a physical complete graph of thousands of pools.

The executable shape is:

1. Borrow hard assets from Balancer V2 in one atomic transaction.
2. Instantiate only the RUBC/RUBX edges required by the selected packet as internal virtual reserves.
3. Apply QE/BUY pulses by minting internal monetary units and changing the selected virtual reserve ratios.
4. Route hard asset -> RUBC/RUBX -> hard asset through those virtual edges.
5. Cross one or more real external pools.
6. Use additional external closure legs when required so every borrowed ERC-20 denomination is repayable in-kind.
7. Collapse all virtual edges and burn all internal RUBC/RUBX units.
8. Repay the flash loan token-by-token.
9. Count only residual external ERC-20 balances as hard profit.

## Why one contract

`V8SynergyGraphMoney.sol` combines four roles:

- Balancer flash-loan receiver;
- sparse Graph Pool Manager;
- RUBC/RUBX internal ledger and QE engine;
- external Aerodrome V2 / UniV3-compatible swap executor.

RUBC and RUBX are internal 18-decimal accounting fields. They are not deployed ERC-20 tokens because they do not need to leave protocol custody. A protocol-owned RUBC/X edge is a temporary reserve record inside the executor, not a separate AMM contract.

Therefore the mathematical search can still reason over a large graph while a transaction activates only the 2-10 edges actually used by the chosen packet.

## HardNAV invariant

Internal monetary units and protocol-owned reserve movements are never profit.

For each flash token `T` the callback enforces:

```text
final_balance(T) >= preexisting_balance(T) + flash_principal(T) + flash_fee(T) + min_profit(T)
```

No USD-value netting is allowed. A WETH surplus cannot repay a USDC deficit.

This is the key V7.4 invariant carried into V8.

## Virtual edge accounting

Each edge has:

```text
field            RUBC or RUBX
hardToken        external ERC-20 denomination
hardReserve      hard units temporarily locked by the edge
monetaryReserve  internal 18-decimal RUBC/RUBX reserve
feeBps           virtual CPMM fee
```

A QE pulse is:

```text
mint internal RUBC/RUBX
-> swap monetary -> hard against one selected virtual edge
-> decrease that edge's hard reserve
-> increase that edge's monetary reserve
-> alter the graph potential of that node
```

The hard released by the QE pulse remains in the same executor contract. It is merely moved from `locked reserve` to `free hard`. This is intentionally not booked as profit.

## External hard-value source

Only real swaps against foreign liquidity can change the contract's consolidated ERC-20 balances.

This keeps the accounting falsifiable:

- QE alone can reshape virtual graph prices but cannot create HardNAV.
- A positive final hard balance must come from external liquidity after all denomination closure legs and flash obligations.

## Current tests

`test/V8SynergyGraphMoney.t.sol` contains two deterministic unit tests.

### 1. QE-only falsification control

A flash loan is taken, a virtual RUBX edge is activated, and a QE pulse is applied. No external pool is crossed. The flash loan is repaid and the engine must end with zero hard profit.

### 2. Sparse graph + external value + strict closure

The test builds two hard assets and two virtual RUBC edges. Before QE, the route:

```text
Hard A -> RUBC -> Hard B -> foreign B/A
```

is non-positive.

A finite QE pulse changes only the A/RUBC virtual edge and makes the same graph route positive. The packet then crosses two external mock venues, with the second external leg restoring the borrowed B denomination. The engine is allowed to retain only the residual Hard A surplus.

The external spread is explicitly the source of hard value; QE is the graph actuator/settlement field, not an ex-nihilo value source.

## Production/fork boundary

The single-contract implementation is intentionally separated from the still-unproven economic claim on Base mainnet.

The next strict milestone is a same-block Base fork packet that satisfies all of the following simultaneously:

1. baseline graph cycle <= 0 before QE;
2. same external state, finite RUBC/RUBX pulse, cycle > 0 after QE;
3. exact external swaps against live Base pools;
4. shared pool state mutated sequentially;
5. every flash denomination repaid in-kind;
6. all internal RUBC/RUBX units collapsed/burned;
7. gas + flash fee + MEV/competition reserve deducted;
8. final consolidated HardNAV > initial HardNAV.

The prior GitHub-hosted runner failed before checkout (`steps=null`), so a successful unit/fork execution must not be claimed until Foundry actually runs.
