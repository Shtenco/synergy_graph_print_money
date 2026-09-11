# SAG V1–V6 — distilled experiment record

This file preserves the numerical research trail that led to V7. Synthetic Monte-Carlo outputs are regression evidence only; they are **not** forecasts, APY, or proof of executable Base profit.

## Core accounting invariant

The protocol is consolidated as one economic actor. Protocol-owned LP, router and treasury transfers are internal. `HardNAV = external hard assets - external liabilities`; RUBC/RUBX are not marked at prices created only by protocol-owned thin pools. Flash principal is debt and never increases HardNAV.

For permanent issuance, dilution is forbidden unless `ΔH >= h_t ΔS`, with `h_t=H_t/S_t`. `AbundanceSurplus = ΔH - h_t ΔS`.

## V1–V2 — emission actuator and HardNAV gate

The initial hypothesis used RUBC minting to perturb 50/50 CPMM edges and search for cycles through a foreign graph. For a CPMM `(x,y)`, `q_eff=(1-f)q`, `out=y q_eff/(x+q_eff)`. A fair closed graph chooses optimal mint `m*=0`: minting against protocol-owned liquidity alone cannot create HardNAV.

The useful distinction introduced here was token-side TVL versus hard-dollar NAV. Only the latter is an economic success criterion.

## V3 — foreign-LP graph

Foreign pools were explicitly separated from protocol-owned pools. Gross arbitrage gain is the foreign LP's adverse-selection loss at common external marks: `ΔH_SYNERGY(gross) = -ΣΔV_foreignLP`.

10,000-state synthetic references:

- 3-hop graph, residual sigma 25 bps: 2,607 executed cycles; HardNAV `$10,000 → $10,029.41`; RUBC supply `14,285.71 → 14,127.52`; HardNAV/RUBC `0.7000 → 0.70992`; gross foreign-LP transfer `$162.99`; gas+MEV `$133.57`.
- 3-hop graph, residual sigma 50 bps: 9,346 cycles; HardNAV `$10,000 → $10,847.91`; HardNAV/RUBC `0.821453`; gross transfer `$1,346.69`; gas+MEV `$498.78`.
- One external edge at 25 bps found no executable cycles in the same calibration, while the graph found 2,607. This motivated the multigraph architecture.

## V4 — complete cross graph

With 10 hard assets plus RUBC/RUBX, the protocol graph is `K12`: `C(12,2)=66` protocol-owned physical CPMMs. Adding 20 foreign pools gives 86 physical pools. Foreign pools remain parallel edges even when a protocol pool has the same token pair.

Reference 10,000-state run, residual sigma 50 bps: initial HardNAV `$55,000`, 7,793 executed cycles, final HardNAV `$55,277.6334`, return `0.504788%` over synthetic states, HardNAV/RUBC `0.710264`, cumulative abundance surplus `$802.6039`, gross foreign-LP transfer `$582.0156`.

The complete graph exposed capital fragmentation: equal liquidity across every protocol cross-pool can increase own slippage. Liquidity allocation therefore became an optimizer variable.

## V5 — atomic liquidity allocation, then falsification

A synthetic model allowed temporary `ADDLP → route → REMOVELP`. Reference outputs with `$100,000` initial HardNAV and 120 foreign pools included `$10,452.18` gain for a `$20k` atomic liquidity budget and `$24,249.68` for `$50k` under 50 bps residual sigma.

**Important falsification/correction:** these V5 figures must not be interpreted as executable conversion profit when the route relies on self-swapping through a 100%-protocol-owned pool. No foreign transaction can interleave inside one EVM transaction. After router+LP consolidation, self-swap transfer is zero external value. V6 and all later versions enforce this correction. V5 remains stored only as a regression/history artifact.

## V6 — strict closed foreign cycles and `$100 + flash` accounting

Calibration: 48 foreign hard assets + RUBC/RUBX = 50 nodes; complete protocol graph `C(50,2)=1,225`; 240 synthetic foreign pools; 1,465 conceptual physical pools. Initial own HardNAV is exactly `$100`. A `$50,000` flash facility is an external liability until repaid and therefore does not increase NAV.

Strict synthetic foreign-cycle results after a modeled 35% MEV/competition haircut:

- sigma 5 bps, 3,000 states: 17 executions; gross foreign-LP transfer `$76.89`; net `$11.34`; final HardNAV `$111.34`; mean deployed flash principal `$4,411.76`.
- sigma 10 bps, 10,000 states: 4,720 executions; gross transfer `$40,391.55`; net `$13,028.91`; final HardNAV `$13,128.91`; mean deployed principal `$3,420.87`; mean foreign hops across up to two cycles `5.58`.
- sigma 25/50 bps outputs were deliberately labeled upper stress and are not realistic forecasts.

Flash-fee sensitivity for the fixed full `$50k` request at sigma 10 bps: 0 bps → 4,720 executions / `$13,028.91` net; 1 bps → 800 / `$2,770.71`; 5 and 10 bps → none. This motivated dynamic principal sizing and reading actual fee terms rather than assuming zero forever.

## RUBC / RUBX role after falsification

Temporary RUBC/RUBX mint can alter internal inventory/accounting state, but cannot manufacture an external hard asset. True seigniorage requires an external holder to give a hard asset for newly issued RUBC/RUBX. Therefore V7 separates:

1. **Foreign-cycle arbitrage:** external LP/market value transfer, flash-repayable on the same pinned block.
2. **Seigniorage:** external demand adapter, separately tested under the accretive issuance invariant.

## V7 acceptance target

Synthetic sigma assumptions are removed. A candidate is useful only if the same real Base block passes exact protocol quotes and then a pinned fork execution, fully repays flash principal+fee, and leaves positive hard-asset balance after gas/MEV margin. Discovery spot edges alone are never counted as PnL.
