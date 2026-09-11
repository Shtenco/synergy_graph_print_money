# V7 live status — 2026-09-11

This file records what has actually been demonstrated on Base Mainnet and what has not. It is intentionally conservative: CI success, aggregator spot edges, own-token marks, flash principal and self-owned LP movements are never treated as profit.

## Last fully executed live baseline: run #36

Pinned Base block: `51148993`.

| Gate / quantity | Result |
|---|---:|
| Public ranked pools collected | 200 |
| Public pagination boundary | page 11 HTTP 401 |
| Aerodrome on-chain factory supplement | 11 |
| Foreign physical pools in snapshot | 211 |
| Raw distinct token IDs in run report | 99 |
| Native-ETH sentinel | 1: `address(0)` |
| Canonical external asset nodes (`address(0) -> WETH`) | **98** |
| Nodes after RUBC + RUBX | **100** |
| Conceptual own complete graph with RUBC/RUBX | **`C(100,2) = 4,950` pools** |
| Total conceptual physical pools | **5,161** |
| Broad DISCOVERED candidates retained | 500 |
| Discovery expansions | 300,001 |
| Discovery exhaustive? | No — bounded/truncated |
| Exact candidates attempted by V7.0 | 120 |
| Exact quotes completed by V7.0 | 0 |
| Positive after-cost quotes | 0 |
| FORK_EXECUTABLE | 0 |
| Proven max net edge | none |

### Node-accounting correction

The run-36 JSON itself contains `unique_foreign_tokens = 99` and calculated `C(101,2)=5,050` because the old runner treated `0x0000000000000000000000000000000000000000` as a separate token node. In the source snapshot that zero address is used as a native-ETH sentinel by V4/Infinity-style pools. The Base execution graph already contains WETH, therefore protocol accounting canonicalizes `address(0) -> WETH` rather than inventing a second ETH node. Recomputing directly from `v7_pools.csv` gives 98 canonical external assets, 100 nodes after RUBC/RUBX, 4,950 own cross-pools and 5,161 total conceptual physical pools.

V7.1 now enforces this with `v7_nodes.canonical_external_tokens()` and a regression test.

## Why V7.0 produced zero exact quotes

The zero exact-complete count is not evidence that no arbitrage exists. The V7.0 exact layer classified all 51 unique pools used by the first 120 discovery candidates as `unsupported` / `v3_like_unsupported`. The same run showed symptoms of public-RPC loss/throttling: only 26/30 probed pool addresses returned bytecode and only 3/30 token-pair probes matched. V7.0 `safe_call()` swallowed RPC exceptions into empty strings, so protocol classification could not distinguish a truly unsupported ABI from a transient RPC failure.

## V7.1 correction now in main

V7.1 adds:

1. `ReliableRpc`: persistent HTTP session, pacing, retry/backoff, `Retry-After`, retryable JSON-RPC error handling and explicit transport metrics.
2. Source-aware exact adapters: GeckoTerminal `dex_id` is used as a protocol-family hint so healthy Uniswap V3 / Aerodrome V2 / Aerodrome Slipstream pools are not rejected merely because an unnecessary probe failed.
3. Separate discovery files:
   - `v7_candidates.csv` — broad research frontier;
   - `v7_candidates_quoteable.csv` — only DEX families for which V7.1 has an exact pinned-block adapter.
4. Uniswap V4 pool IDs are excluded from the exact adapter frontier until a V4 StateView/Quoter adapter is implemented; they remain in broad discovery.
5. Hybrid pool acquisition remains explicit: public ranked set plus on-chain Aerodrome PoolFactory supplement. It must not be described as literal top-240-by-TVL when public pagination is capped.
6. Native ETH sentinels are normalized to WETH for external-node and `K_n` accounting.

## Offline V7.1 preflight on the exact run-36 artifact

The artifact contains **120** foreign pool rows belonging to exact-adapter source families:

- Aerodrome Slipstream generation 3: 41
- Uniswap V3 Base: 27
- Aerodrome Slipstream generation 1: 25
- Aerodrome Base/V2: 22 combined
- Aerodrome Slipstream generation 2: 5

A bounded supported-only graph search (`max_hops=5`, `top_k=500`, `max_expansions=300,000`) produced:

- 57 connected token nodes inside the supported priced subgraph;
- 2,423 unique positive spot-cycle candidates encountered before truncation;
- top 500 retained;
- 300,001 expansions, therefore not exhaustive.

The largest raw spot edge, about **710.41 bps**, is rejected as a useful institutional lead because one contributing pool has only about **$0.016** reported reserve. With both pools required to have at least **$10,000** reported reserve, the supported artifact still fills the top-500 frontier and the largest raw spot edge is about **186.49 bps**, a two-pool `VIRTUAL/WETH` discrepancy between Aerodrome Slipstream and Aerodrome V2/Base liquidity. This is only an asynchronous aggregator-level discovery signal. It is **not** `QUOTE_VERIFIED`, because exact fee, slippage, current state and execution costs have not yet been confirmed on-chain for that path.

## GitHub Actions infrastructure boundary

Commits containing V7.1 triggered runs #37 through #42. Those jobs did **not** execute V7.1: GitHub returned `steps = null`, no job logs, and zero billable hosted-runner time for the inspected attempts. Therefore these failures occur before job execution and are not economic falsification results or Python test failures.

The last valid economic/live conclusion is:

```text
211 foreign physical pools in run #36
→ 99 raw token IDs
→ 98 canonical external asset nodes after native ETH -> WETH
→ 100 nodes with RUBC/RUBX
→ 4,950 conceptual own cross-pools
→ 5,161 total conceptual physical pools
→ 500 broad DISCOVERED candidates retained
→ 120 source-family quoteable pools in the artifact
→ 500 supported-only DISCOVERED candidates in offline V7.1 preflight
→ 0 QUOTE_VERIFIED in the last actually executed V7.0 live run
→ 0 FORK_EXECUTABLE
→ no proven positive net edge yet
```

V7.1 is the pending execution layer. No positive return should be claimed until a runner actually executes it and a candidate passes exact pinned-block quote, flash-liquidity, gas/MEV/fee accounting and Foundry fork repayment/profit gates.
