# V7.3 GLOBAL ABUNDANCE SOLVER — numerical result

Snapshot basis: Base run #36, pinned block `51148993`.

This document records a **mathematical/falsification result**, not a claim of live executable profit. Foreign CLMM/V4 pools are converted to the project's requested 50/50 CPMM surrogate for the global V7.3 calculation. Exact same-block adapter/fork verification remains a later gate.

## Graph

After canonicalizing native ETH to WETH:

- 98 external asset nodes;
- RUBC + RUBX;
- 100 total vertices;
- `K_100 = C(100,2) = 4,950` conceptual protocol-owned cross pools;
- 211 foreign physical pools in run #36;
- 5,161 conceptual physical pools in the combined multigraph.

The actual post-cost opportunity subset used for the conservative execution calculation contains 120 foreign pools from currently supported adapter families (Aerodrome V2/Base, Aerodrome Slipstream, Uniswap V3). Thirty-six physical foreign pools have a positive finite CPMM hard-value opportunity after the modelled foreign fee, before internal settlement constraints.

## Accounting

Personal starting HardNAV is exactly `$100`.

The temporary flash facility is `$50,000`. It is an external liability and is never counted as protocol NAV. The solver assumes `0 bps` flash fee for this requested experiment, but V7.1/V7.2 live code reads Balancer's fee from the pinned block rather than hard-coding zero.

RUBC and RUBX created by QE are temporary protocol inventory. After each atomic liquidity wave the own LP is removed and all protocol-held temporary RUBC/RUBX is burned. Therefore final `DeltaSupply = 0` in this experiment and:

`AbundanceSurplus = DeltaHardNAV`.

A protocol-owned swap or QE BUY is never booked as profit. The only positive HardNAV source is net hard-asset value transferred from foreign pools, minus MEV/competition and gas.

## Foreign hard-value ceiling

For a foreign 50/50 CPMM with input reserve `x`, output reserve `y`, input/output oracle prices `p_x,p_y`, and `gamma=1-fee`, the external hard-value function is

`pi(q) = p_y * y*gamma*q/(x+gamma*q) - p_x*q`.

The unconstrained optimum is

`q* = (sqrt(p_y*y*gamma*x/p_x)-x)/gamma`,

clipped at zero and the `$50k` flash cap.

Because own-pool movements consolidate to zero HardNAV, any global multi-cycle packet is bounded by the sum of the positive per-foreign-pool maxima. On the adapter-supported run-36 subset:

- gross foreign-value ceiling before 35% competition/MEV haircut and gas: about `$558.07`;
- post-cost ceiling used by the solver: **`$360.5859`**;
- largest individual optimal foreign input is only about `$14,767`, so the `$50k` flash ceiling is not the binding directional-trade limit. It is mainly useful as temporary LP depth / settlement inventory.

Across every priced CPMM-surrogate foreign pool, including protocols not yet covered by exact adapters, the post-cost research ceiling is about **`$423.7665`**. That number is explicitly an upper-bound research figure, not executable evidence.

## 98x2 QE optimization

V7.3 optimizes two independent node-potential fields:

- `r_C[i] = q_RUBC[i] / R_RUBC[i]`;
- `r_X[i] = q_RUBX[i] / R_RUBX[i]`.

Each field has 98 components. The finite solver uses five levels between 0 and the chosen `r_max`, then performs randomized coordinate ascent over the interacting foreign opportunity graph. Components with no contribution to post-cost HardNAV remain zero.

For each foreign opportunity the packet may use:

1. direct protocol `A/B` cross-pool settlement;
2. `A -> RUBC -> B` settlement;
3. `A -> RUBX -> B` settlement.

Own LP depth and starting notional share the same `$50k` atomic flash budget. The own pools are removed after each wave and the same flash capacity can be reused sequentially across the packet. Foreign physical pool state is used at most once per opportunity, preventing duplicate counting of the same LP edge.

## Conservative adapter-supported results

Assumptions: own fee 30 bps in route geometry, foreign fees parsed from snapshot/name with 30 bps fallback, `$0.02` gas per swap, 35% haircut on positive external hard-value capture, zero flash fee in this requested scenario.

| max QE `q/R` | max own-pool price displacement | executable foreign routes | net `DeltaHardNAV` | final HardNAV from $100 | share of post-cost external ceiling |
|---:|---:|---:|---:|---:|---:|
| 0% | 0% | 4 | $66.01 | $166.01 | 18.31% |
| 1% | 2.01% | 36 | $71.54 | $171.54 | 19.84% |
| 2% | 4.03% | 36 | $79.99 | $179.99 | 22.18% |
| **5%** | **10.23%** | **36** | **$107.73** | **$207.73** | **29.88%** |
| 10% | 20.97% | 36 | $159.46 | $259.46 | 44.22% |
| 20% | 43.93% | 36 | $215.53 | $315.53 | 59.77% |
| 50% | 124.78% | 36 | $311.99 | $411.99 | 86.52% |
| 100% | 299.40% | 36 | $352.20 | $452.20 | 97.67% |

The 100% pulse is an unconstrained mathematical stress limit, not a recommended control regime. A more useful risk-capped point is `r_max = 5%`, whose own-pool marginal price displacement is about 10.23%.

### 5% risk-capped packet

At `r_max = 5%`:

- external hard-value captured before haircut/gas: **`$169.0649`**;
- 35% competition/MEV haircut: **`$59.1727`**;
- modelled gas: **`$2.16`**;
- net `DeltaHardNAV`: **`+$107.7322`**;
- final HardNAV from `$100`: **`$207.7322`**;
- 36 foreign physical opportunities executed in the packet;
- 22 settled through RUBC;
- 14 settled through RUBX;
- no direct hard/hard route remains optimal at this control point;
- gross temporary QE over all sequential waves: about `43,339` RUBC/RUBX-reference units;
- peak temporary QE outstanding in one wave: about `2,206` units if each wave is burned before the next;
- final net RUBC/RUBX supply change: **0**.

Against the no-QE finite settlement result of `$66.0079`, the 5% dual-QE field raises strict post-cost HardNAV capture by about **63.2%**. This uplift is **not new external value created by minting**; it is additional pre-existing foreign LP mispricing that becomes atomically settleable through the controlled monetary graph.

## RUBX contribution

At the 5% control cap:

- best single-monetary-field (RUBC only) result: about `$103.0845`;
- dual RUBC+RUBX result: **`$107.7322`**;
- incremental contribution from the second independent monetary field: about **`+$4.6477`**, or **`+4.51%`** versus the best single-field result.

RUBX therefore does not double the economic source. Its value is graph-theoretic: a second potential field resolves conflicting settlement directions that a single scalar RUBC field cannot satisfy simultaneously.

## Main falsification result

V7.3 changes the interpretation of the earlier QE-edge count.

`QE -> BUY` can create thousands of negative cycles in the **quoted own+foreign graph**, but those cycles are not automatically new HardNAV sources. Under consolidated accounting:

`DeltaHardNAV = sum(foreign hard-value transfers) - external costs`.

The actual role of dual QE is:

`foreign mispricing -> QE/RUBC/RUBX settlement field -> atomically repayable route -> external hard capture -> REMOVE LP -> BURN`.

Thus QE is an **edge/settlement actuator**, while foreign liquidity/order-flow mispricing remains the external energy source.

The key positive numerical finding is that, on the run-36 snapshot and under the project's CPMM surrogate assumptions, a 5% dual-QE control field increases finite, post-cost, flash-capped hard-value capture from roughly `$66.01` to `$107.73`; very large control amplitudes asymptotically approach the independently computed foreign-value ceiling.

## Remaining proof gate

These numbers are not yet `FORK_EXECUTABLE`. The next live gate must replace each foreign CPMM surrogate with its pinned-block exact adapter, enforce token-by-token Balancer repayment and actual flash fee, execute the selected packet on a Base fork, and then recompute consolidated HardNAV. A claim of live profitability requires that stage to remain positive.
