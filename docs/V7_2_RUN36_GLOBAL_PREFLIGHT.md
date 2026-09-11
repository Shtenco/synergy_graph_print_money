# V7.2 run-36 global graph preflight

This is the first explicit **huge-graph** QE edge-creation experiment. It is not a two-pool shortlist and it is not an executable-profit claim.

## Snapshot and graph

Input is the V7 run #36 Base evidence snapshot:

- 211 foreign physical pool rows;
- 98 canonical external asset vertices after native-ETH sentinel normalization;
- RUBC + RUBX add two monetary vertices;
- 100 total vertices;
- protocol-owned conceptual `K_100 = 4,950` cross-pools;
- 5,161 total conceptual own + foreign physical pools.

The direct QE actuator is incident to RUBC. In this snapshot 86 external asset vertices have usable positive price and non-zero reported foreign liquidity and therefore receive a non-zero pulse in this deterministic preflight. Twelve unpriced/zero-liquidity vertices remain in graph topology but receive zero pulse.

The QE allocation is intentionally heterogeneous and deterministic, using foreign-graph degree/liquidity centrality. It is **not** claimed optimal. The purpose is to test whether a vector pulse can create a broad edge field before building the outer optimizer.

## Assumptions used only for this preflight

- synthetic protocol-owned cross pools: CPMM;
- own fee: 30 bps;
- own pool reference TVL for absolute scaling: $10,000 per conceptual pool;
- RUBC initialization reference: $1 only for pool geometry, never as HardNAV;
- unknown foreign fee fallback: 30 bps;
- foreign triangle price signals use the run-36 aggregator snapshot and are therefore discovery-only;
- protocol-owned LP asset movements are consolidated with Treasury and are not profit.

Because spot dislocation depends mainly on `q / RUBC_reserve`, the pulse sweep is reported as a maximum reserve fraction. Absolute RUBC mint shown below assumes the $10,000-per-own-pool geometry.

## Results

| Max pulse `q/R` | QE RUBC used | Positive own RUBC triangle directions | Max own edge | Foreign monetary positive dirs | **New foreign-linked dirs created by QE** | Max new foreign edge | RUBC recovered by immediate reverse BUYBACK | Net RUBC after reverse |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0% | 0 | 0 | 0 bps | 28 | 0 | 0 bps | 0 | 0 |
| 0.5% | 960.09 | 72 | 9.47 bps | 45 | **18** | 83.36 bps | 954.35 | 5.73 |
| 1% | 1,920.17 | **1,386** | **109.17 bps** | 90 | **64** | **168.38 bps** | 1,908.74 | 11.44 |
| 2% | 3,840.35 | **2,738** | **310.04 bps** | 113 | **88** | **339.14 bps** | 3,817.61 | 22.74 |
| 5% | 9,600.86 | **3,913** | **924.51 bps** | 140 | **116** | **857.15 bps** | 9,545.01 | 55.86 |

There are `C(99,2)=4,851` distinct structural RUBC triangles in `K_100`. The table counts profitable **directions** under the centrality-weighted QE vector after own-pool fees.

The run-36 foreign rows provide 200 foreign pools with usable token-price pairs for this triangle preflight. There are already 28 positive directions at zero QE because the aggregator snapshot is asynchronous / heterogeneous. The important column is therefore **new foreign-linked directions created from a non-positive baseline by the QE pulse**, not the total.

## What the result means

The requested mechanism exists at the **graph-dislocation level** in the model:

`heterogeneous QE -> BUY across many RUBC/A_i edges -> thousands of altered composite paths -> many newly positive own cycles + newly positive cycles containing foreign Base edges`.

At the 1% pulse, the actuator produces 1,386 positive own RUBC-triangle directions and creates 64 new foreign-linked monetary directions. At 2%, those numbers rise to 2,738 and 88 respectively.

This demonstrates that the complete cross graph behaves as a **price-dislocation field**, not as a collection of independent pools.

It does **not** yet demonstrate positive external HardNAV. Own-only positive cycles are self-funded dislocations: when Treasury and protocol-owned liquidity are consolidated, the QE BUY pulse itself has `DeltaHardNAV = 0` before costs. Their economic role is to route/propagate the impulse and expose foreign edges; they are not themselves counted as wealth.

The next proof is therefore global capture, not single-route ranking:

1. apply an optimized QE allocation vector across many RUBC incident edges;
2. recompute the entire 5,161-pool state;
3. solve a joint nonlinear multi-route circulation over own + foreign edges;
4. mutate all shared reserves after each accepted flow;
5. execute BUYBACK + BURN closure;
6. measure consolidated `DeltaHardNAV`, net RUBC supply and `AbundanceSurplus`;
7. require the same packet to survive exact pinned-block adapters and a Base fork.

The promotion criterion remains:

`DeltaHardNAV > 0`

and

`AbundanceSurplus = DeltaHardNAV - (HardNAV_0 / Supply_0) * DeltaSupply > 0`.

A huge number of created edges is useful only if the joint solver can turn some of them into **external hard-asset capture after the internal accounting cancellation**.

## Reproduction

Use `scripts/run_v7_2_global_preflight.py --pools artifacts/v7_pools.csv` on a V7 evidence snapshot. The script emits `artifacts/v7_2_global_preflight.json` and sweeps the pulse vector over `0, 0.5%, 1%, 2%, 5%` by default.
