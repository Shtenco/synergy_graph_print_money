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
| Unique foreign tokens | 104 |
| Conceptual own complete graph with RUBC/RUBX | `C(106,2) = 5,565` pools |
| Total conceptual physical pools | 5,776 |
| Broad DISCOVERED candidates retained | 500 |
| Discovery expansions | 300,001 |
| Discovery exhaustive? | No — bounded/truncated |
| Exact candidates attempted | 120 |
| Exact quotes completed | 0 |
| Positive after-cost quotes | 0 |
| FORK_EXECUTABLE | 0 |
| Proven max net edge | none |

The zero exact-complete count is not evidence that no arbitrage exists. The V7.0 exact layer classified all 51 unique pools used by the first 120 discovery candidates as `unsupported` / `v3_like_unsupported`. The same run showed symptoms of public-RPC loss/throttling: only 26/30 probed pool addresses returned bytecode, only 3/30 token-pair probes matched, and known V3-style calls were often empty. V7.0 `safe_call()` swallowed RPC exceptions into empty strings, so protocol classification could not distinguish a true unsupported ABI from a transient RPC failure.

## V7.1 correction now in main

V7.1 adds:

1. `ReliableRpc`: persistent HTTP session, pacing, retry/backoff, `Retry-After`, retryable JSON-RPC error handling and explicit transport metrics.
2. Source-aware exact adapters: GeckoTerminal `dex_id` is used as a protocol-family hint so healthy Uniswap V3 / Aerodrome V2 / Aerodrome Slipstream pools are not rejected merely because an unnecessary probe failed.
3. Separate discovery files:
   - `v7_candidates.csv` — broad research frontier;
   - `v7_candidates_quoteable.csv` — only DEX families for which V7.1 has an exact pinned-block adapter.
4. Uniswap V4 pool IDs are excluded from the exact adapter frontier until a V4 StateView/Quoter adapter is implemented; they remain in broad discovery.
5. Hybrid pool acquisition remains explicit: public ranked set plus on-chain Aerodrome PoolFactory supplement. It must not be described as literal top-240-by-TVL when public pagination is capped.

On the run #36 snapshot, 120 of the 211 foreign rows belonged to currently supported exact-quote source families. A bounded supported-only discovery over that historical snapshot still produced 500 candidate cycles, so the next meaningful test is exact same-block quoting of that supported frontier rather than spending the candidate budget on unsupported V4 pool IDs.

## GitHub Actions infrastructure boundary

Commits containing V7.1 triggered runs #37, #38, #39, #40 and #41. Those jobs did **not** execute V7.1: GitHub returned `steps = null`, no job logs, and run #41 reported `0 ms` billable Ubuntu runner time on both attempts. Therefore these failures are runner-start / Actions-infrastructure failures, not economic falsification results and not Python test failures.

The last valid economic/live conclusion remains:

```text
104 unique external tokens
→ 5,565 conceptual own RUBC/RUBX cross-pools
→ 500 broad DISCOVERED candidates
→ 0 QUOTE_VERIFIED under the flawed V7.0 adapter/transport layer
→ 0 FORK_EXECUTABLE
→ no proven positive net edge yet
```

V7.1 is the pending execution layer. No positive return should be claimed until a runner actually executes it and a candidate passes exact pinned-block quote, flash-liquidity, gas/MEV/fee accounting and Foundry fork repayment/profit gates.
