# V7.2 QE Curl Field Mathematics

## 1. Why a heterogeneous QE vector matters

Consider a protocol-owned CPMM `RUBC/A_i` initialized at the common reference price. Let its RUBC reserve be `R_i`, let `q_i` newly minted RUBC be sold through it, let

`r_i = q_i / R_i`,

and let `gamma = 1 - fee`.

After the SELL-RUBC pulse, the reciprocal marginal-price displacement factor is

`g(r_i) = (1+r_i)(1+gamma*r_i)`.

With zero fee this becomes `(1+r_i)^2`.

The post-pulse `A_i -> RUBC` marginal rate is multiplied by `g(r_i)`, while `RUBC -> A_i` is divided by `g(r_i)`.

If every RUBC edge receives exactly the same reserve-relative pulse `r`, then the same `g(r)` appears on every monetary spoke and largely cancels from closed cycles. Therefore the abundance engine must not be modeled as a scalar QE pulse. The control variable is a **heterogeneous vector**

`r = (r_1, ..., r_N)`.

## 2. Own RUBC triangle

Take the own cycle

`A_i -> RUBC -> A_j -> A_i`.

If all three own pools charge the same fee factor `gamma`, its marginal cycle multiplier after QE is

`M_ij = gamma^3 * g(r_i)/g(r_j)`.

The cycle has a positive spot edge exactly when

`ln g(r_i) - ln g(r_j) > -3 ln gamma`.

For small pulses,

`ln g(r) ~= (1+gamma) r`.

At 30 bps, `gamma=0.997`, so the approximate reserve-fraction difference needed to overcome three 30-bps fees is

`Delta r_threshold ~= [-3 ln(0.997)] / 1.997 ~= 0.00452`,

or about **0.452 percentage points**.

This explains the run-36 global preflight: a centrality-weighted vector with maximum `q/R = 1%` already makes a large number of the 4,851 structural RUBC triangles cross from non-positive to positive spot edge.

## 3. Foreign-linked monetary triangle

Now replace the `A_j/A_i` own edge with a foreign Base pool. Define its normalized external basis

`beta_ji = ln( rho_foreign(A_j -> A_i) * P_i/P_j )`,

where `P_i, P_j` are the protocol reference prices and the foreign rate includes its trading fee.

Then the monetary cycle

`A_i -> RUBC -> A_j -> foreign(A_j -> A_i)`

has log edge

`L_ij = [ln g(r_i) - ln g(r_j)] + 2 ln(gamma_own) + beta_ji`.

The QE controller therefore does not need a foreign pool to be independently mispriced enough for arbitrage. A previously negative foreign-linked cycle can become positive when the **relative QE displacement** adds enough signed basis:

`ln g(r_i) - ln g(r_j) > -2 ln(gamma_own) - beta_ji`.

This is the precise mathematical meaning of "QE creates a fork connected to foreign pools".

It is still not a claim of free HardNAV: the own-pool deformation has a protocol balance-sheet cost that cancels under consolidated Treasury+POL accounting unless external flow/capture contributes hard assets.

## 4. Edge field as cycle curl

Let each directed graph edge have log weight

`w_e = -ln(rate_e)`.

A QE vector changes only a controlled subset of edge weights. Write the change as `Delta w_e(u)` for control vector `u`.

For any closed cycle `C`, define its QE curl

`kappa_C(u) = sum_{e in C} Delta w_e(u)`.

A cycle becomes more profitable when `kappa_C(u) < 0` and becomes a discovery edge when

`sum_{e in C} [w_e^0 + Delta w_e(u)] < 0`.

The global actuator problem is therefore to choose `u` so that negative curl is created preferentially on cycles that contain external hard-liquidity edges and can be captured after all internal transfers are consolidated.

## 5. RUBX creates a second control field

If RUBX is used as a second reserve/stabilization monetary node, define analogous spoke displacements

`x_i = ln g_X(r_i^X)`

for `RUBX/A_i`, and optionally a controlled `RUBC/RUBX` displacement `c_x`.

Then mixed cycles such as

`RUBC -> A_i -> foreign(A_i/A_j) -> A_j -> RUBX -> RUBC`

depend on combinations of the two fields, schematically

`L_mixed = external_basis + (RUBC field term) + (RUBX field term) + c_x - fees`.

This increases the actuator rank: instead of one scalar monetary price, the protocol controls two coupled relative-price fields over the same Base asset graph.

## 6. Outer optimization

Let `r_i >= 0` be reserve-relative QE pulses and let `m` be the total RUBC mint budget. With RUBC reserves `R_i`, impose

`sum_i R_i r_i <= m`.

The outer controller must not maximize the raw number of positive cycles because overlapping cycles share the same liquidity. A useful discovery objective is

`Score(u) = sum_C W_C * softplus(-cycle_weight_C(u)) - lambda ||u||^2`,

where `W_C` is high only for cycles containing verified external liquidity.

The final objective is bilevel:

`u* = argmax_u J(u, z*(u))`,

where

`z*(u) = argmax_z ExternalHardCapture(z | post-QE graph state)`

is the nonlinear multi-route circulation problem after the graph has been deformed, and

`J = DeltaHardNAV - h0*DeltaSupply - Gas - MEV - RiskPenalty`.

Thus QE chooses the graph deformation, while the inner optimizer chooses the interacting packet of arbitrage/capture flows.

## 7. Promotion criterion

The mechanism is promoted only if, after `QE -> BUY -> global circulation -> BUYBACK -> BURN`, all of the following hold:

`DeltaHardNAV > 0`

`AbundanceSurplus = DeltaHardNAV - h0*DeltaSupply > 0`

`HardNAV_after / Supply_after >= HardNAV_before / Supply_before`

and the same control/capture packet survives exact pinned-block quotes and Base-fork execution.
