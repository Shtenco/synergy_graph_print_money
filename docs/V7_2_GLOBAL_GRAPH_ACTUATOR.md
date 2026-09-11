# V7.2 Global Graph Actuator — QE → BUY → GRAPH ARBITRAGE → BURN

## Scope

V7.2 does **not** reduce the problem to one two-pool arbitrage. The object under test is the entire heterogeneous Base graph plus a protocol-owned cross-pool graph.

For the corrected run-36 snapshot:

- canonical external asset nodes: 98;
- monetary nodes: RUBC and RUBX;
- total nodes: 100;
- conceptual protocol-owned complete graph: `K_100`, therefore `C(100,2)=4,950` own pools;
- foreign physical pools in run #36: 211;
- total conceptual multi-pool graph: 5,161 pools before adding further live sources.

The foreign and own graphs are not separate. They share the same token vertices. A foreign pool is therefore a parallel or alternative edge to one or more protocol-owned paths. This is what allows a controlled price displacement in an own RUBC edge to propagate into many foreign/own cycles.

## Graph

Let

`G = (V, E_own ∪ E_foreign)`

with

`V = {RUBC, RUBX} ∪ A`,

where `A` is the canonical set of external Base assets.

`E_own = K_|V|` conceptually. Every pair of vertices may have a protocol-owned cross pool. `E_foreign` contains observed Base pools (Aerodrome, Uniswap and other adapters as they are implemented).

Each physical pool is a stateful nonlinear edge

`e = (token0, token1, state, fee, curve, owner)`

with swap map

`y = Phi_e(x ; state_e)`.

For CPMM research pools:

`y = Y * (1-f) x / (X + (1-f)x)`.

For live CLMM/V4/etc., `Phi_e` must come from the exact pinned-block adapter, not the CPMM surrogate.

## Monetary actuator

The control variable is a **vector**, not a single trade:

`u = (m, q_1 ... q_k, z_1 ... z_r, b)`

where:

- `m` = QE mint of RUBC;
- `q_i` = RUBC allocated to BUY pulses on selected own `RUBC/A_i` or `RUBC/RUBX` edges;
- `z_j` = graph-routing/arbitrage flows through arbitrary own + foreign edges;
- `b` = terminal RUBC burn.

The state transition is

`S_{t+1} = BURN_b( ARB_z( BUY_q( QE_m(S_t) ) ) )`.

### QE

QE changes supply but does not itself create HardNAV:

`S_RUBC' = S_RUBC + m`.

### BUY pulse

Minted RUBC is sold through a vector of own RUBC cross-pools to acquire other assets. For an own CPMM `RUBC/A_i` with reserves `(R_i, A_i)`, a pulse `q_i` gives

`A_out_i = A_i * (1-f) q_i / (R_i + (1-f) q_i)`.

This changes the pool's marginal RUBC price and therefore the weights of every cycle touching `RUBC`, `A_i`, and all alternative paths between them.

The purpose of BUY is **not** to call the removed own-pool asset profit. With protocol-owned liquidity, Treasury gain and POL loss cancel in consolidated accounting. BUY is an actuator that creates a temporary graph disequilibrium.

### Graph propagation

After the pulse, recompute the whole directed multigraph. For a marginal edge define

`w_e = -ln(rate_e)`.

Any cycle `C` with

`sum_{e in C} w_e < 0`

is a spot arbitrage candidate. This is only discovery. Finite-size execution uses the nonlinear `Phi_e` maps and must include all costs.

V7.2 tracks the **edge field** at four moments:

1. `F_0`: before QE;
2. `F_QE`: after QE+BUY;
3. `F_ARB`: after the multi-cycle arbitrage packet;
4. `F_BURN`: after RUBC buyback/burn.

The key experiment is therefore not "did one route make money?" but:

`DeltaEdge_created = F_QE - F_0`

and

`DeltaHardNAV_captured = HardNAV_after - HardNAV_before`.

The first measures how strongly the actuator deforms the graph. The second determines whether any of that deformation was captured from external economic flow rather than merely moved between protocol-owned accounts.

## Multi-cycle packet optimizer

The optimizer searches a packet of flows, not a single cycle.

At each state:

1. build all directed edges from own and foreign pools;
2. generate bounded negative-cycle / beam-search candidates over 2..H hops;
3. obtain exact finite-size quote curves for the candidate frontier;
4. choose a set of routes jointly, accounting for shared-pool liquidity and route interaction;
5. mutate pool state after each accepted flow and requote the remaining packet;
6. stop when no positive **post-cost** route remains;
7. execute the RUBC buyback/burn leg;
8. recompute consolidated HardNAV and supply backing.

The packet objective is

`max_{m,q,z,b} J`

where

`J = DeltaHardNAV - h_t * DeltaSupply_RUBC - Gas - MEV - HedgeCost - RiskPenalty`

and

`h_t = HardNAV_t / S_RUBC,t`

(or the corresponding two-token reserve-accounting rule when RUBX has its own backing bucket).

## Global nonlinear network-flow formulation

A stronger formulation treats arbitrage as a nonlinear circulation problem.

For every directed pool edge `e`, choose input flow `x_e >= 0`, producing output `Phi_e(x_e)`.

For every intermediate token `v` that is not an allowed source/sink, impose flow conservation:

`sum outputs_into(v) + minted(v) = sum inputs_out_of(v) + burned(v)`.

The optimization target is hard-asset value exported to protocol-controlled hard balances, net of hard-asset value injected and all execution costs.

This formulation naturally allows hundreds of simultaneously interacting pools. It also prevents double-counting the same apparent edge across many overlapping cycles.

## Consolidated accounting invariant

Protocol HardNAV is measured after consolidating Treasury and all protocol-owned liquidity:

`HardNAV = TreasuryHardAssets + POLHardAssets - ExternalLiabilities`.

RUBC and RUBX are not marked as hard assets from prices generated by protocol-owned pools.

Therefore an own-only self-trade satisfies, before costs,

`DeltaHardNAV_internal = 0`.

This is crucial. V7.2 is specifically testing whether the **global graph plus external liquidity/order flow** turns a protocol-created disequilibrium into positive external hard-asset inflow. A positive result is valid only if the final consolidated result survives this cancellation.

## QE/BURN abundance gate

Let `m` be gross RUBC minted and `b` RUBC burned. Net supply change is

`DeltaS = m - b`.

Let `H_0` and `H_1` be consolidated HardNAV before and after the entire packet. Define

`h_0 = H_0 / S_0`.

Then

`AbundanceSurplus = (H_1 - H_0) - h_0 * DeltaS`.

Required gates:

- `DeltaHardNAV > 0`;
- `AbundanceSurplus > 0`;
- `H_1 / S_1 >= H_0 / S_0`;
- all flash liabilities repaid;
- no own-token mark-to-model gain counted as HardNAV;
- no protocol-owned LP transfer counted twice;
- all accepted routes are exact-quoted at one pinned block for live evidence;
- the final packet is reproduced on a fork.

For robust promotion:

`P5(AbundanceSurplus_after_all_costs) > 0`

across block snapshots, gas grids, MEV haircuts, liquidity shocks and order-flow regimes.

## Why the huge graph matters

The complete own graph changes the problem from isolated triangular arbitrage to a controllable network.

A single QE pulse on `RUBC/A_i` changes the direct edge but also changes every composite path containing that edge. Because `K_100` supplies an own cross edge between every pair and 211+ foreign pools add parallel market edges, one pulse can create or destroy a large family of cycles:

`RUBC -> A_i -> A_j -> RUBC`

`RUBC -> A_i -> foreign(A_i/A_j) -> A_j -> RUBX -> RUBC`

`RUBC -> A_i -> A_j -> A_k -> foreign(A_k/A_m) -> RUBC`

and many others.

V7.2 therefore optimizes the **vector field of price dislocations** rather than ranking a single route.

## Execution evidence ladder

V7.2 stages are:

`BASELINE_GRAPH`

`QE_PULSED`

`EDGE_CREATED`

`MULTICYCLE_QUOTED`

`PACKET_POSITIVE`

`BURN_CLOSED`

`FORK_EXECUTABLE`

`ABUNDANCE_VERIFIED`

Only the final stage supports a claim that the mechanism increased protocol hard backing after dilution and all costs.

## Implementation split

`v7_2_global.py` is the deterministic research simulator for complete own graphs, QE pulses, cycle-field discovery and consolidated accounting.

Live execution remains adapter based. The simulator may use CPMM surrogate curves for synthetic protocol-owned pools, but foreign pools must ultimately be re-evaluated by their exact V7.1/V7.2 pinned-block adapters before any production conclusion.

The first V7.2 experiment should use all 98 canonical run-36 external assets, RUBC/RUBX, all 4,950 conceptual own cross-pools and the 211 run-36 foreign pools, then sweep vectors of QE allocations rather than selecting a single best two-pool route.