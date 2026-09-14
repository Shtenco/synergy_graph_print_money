# ALL VERSIONS PROFIT AUDIT — 2026-09-14

This audit answers one question: **is there actual profit anywhere in the system, and at what evidence level?**

The only accepted economic metric is consolidated external `HardNAV` after token-by-token flash repayment, gas, competition/MEV reserve and external liabilities. Protocol-owned LP movements, RUBC/RUBX minting, virtual reserve marks and self-swaps are not profit.

## Evidence ladder

1. `SYNTHETIC` — Monte-Carlo/regression only.
2. `SURROGATE` — real Base snapshot but simplified pool mathematics.
3. `TOKEN_CLOSED` — every borrowed denomination closes in-kind in the model.
4. `EXACT_QUOTE` — exact same-block protocol quote.
5. `FORK_EXECUTABLE` — exact packet executes on a pinned Base fork and repays actual flash fees.
6. `LIVE` — real production transaction.

A lower level must never be advertised as a higher one.

## Version-by-version result

| Version | Best stored result | Audit status | Profit conclusion |
|---|---:|---|---|
| V1–V2 | fair graph optimum `m*=0` | analytical | **No self-mint profit.** Own issuance/liquidity alone cannot create HardNAV. |
| V3 | `+$847.91` in the 50 bps 10k-state run | synthetic | Positive regression evidence only; not Base profit. |
| V4 | `+$277.6334` in the K12 50 bps 10k-state run | synthetic | Positive regression evidence only. |
| V5 | up to `+$24,249.6764` | invalidated | **False-positive interpretation.** Later consolidation proved self-LP/self-swap cannot be counted as conversion profit. |
| V6 | `+$11.34` at 5 bps; `+$13,028.91` at 10 bps | synthetic strict cycles | Positive foreign-cycle mechanism in synthetic data, but highly sensitive to flash fee. |
| V7 / V7.2 | thousands of QE-created graph directions | Base snapshot / graph preflight | QE changes graph prices, but this stage does **not** prove external HardNAV. |
| V7.3 | no-QE `+$66.0079`; 5% dual-QE `+$107.7322` | real Base snapshot + CPMM surrogate | Positive upper bound, **not flash-repayable** after denomination audit. |
| V7.4 | `+$15.9704789` on `$2,171.9290` concurrent draw | stateful token-closed CPMM surrogate | **Strongest positive candidate.** Token closure survives; exact fork still pending. |
| V8 | positive mock external-spread unit scenario | deterministic mock | Architecture/accounting proof only; does not establish Base profit or QE uplift. |
| V8.1 | authored `<$2k` QE-gated WETH fork test | fork test not executed | No executable result yet. Current QE gate is based on internally locked flash inventory. |
| V8.2 | positive off-chain designs inherited from V7.4 opportunities | design search | Does not independently prove QE economic uplift; current causality metric compares against an artificially locked no-QE state. |

## Recalculation checks

### V3

For the 50 bps reference run:

`$1,346.69 gross foreign transfer - $498.78 gas+MEV = $847.91`

which matches the stored HardNAV increase.

### V5 falsification

The large V5 number is arithmetically consistent:

`$26,472.0818 gross - $855.617 gas - $1,366.7884 MEV = $24,249.6764`.

But the economic interpretation was later falsified: self-swapping through 100%-protocol-owned LP cannot transfer external value. Therefore the large number must remain historical regression output, not profit evidence.

### V7.3 relaxed packet

The stored token-conservation vector sums to approximately:

- token-specific deficits: **$14,697.5066**;
- token-specific surpluses: **$14,866.5715**;
- oracle-valued net: **+$169.0649233**;
- deficit denominations: **11**.

Applying the V7.3 model cost assumptions:

`$169.0649233 × 65% - $2.16 gas = $107.7322002`.

So the published V7.3 result is numerically correct but economically non-executable under Balancer denomination closure. This is the key reason the 5% QE uplift from `$66.01` to `$107.73` is **not accepted as atomic flash profit**.

### V7.4 strict packet

The six selected token-closed cycles sum to:

- gross external hard transfer: **$25.0007367236**;
- 35% competition reserve: **$8.7502578533**;
- modeled gas: **$0.28**;
- resulting candidate HardNAV gain: **$15.9704788704**.

The required reusable principals are:

- WETH equivalent: **$1,556.6380341**;
- USDC equivalent: **$615.2910042**;
- total concurrent draw: **$2,171.9290384**.

Candidate return on concurrent flash draw is therefore about **0.735313%** before any additional unmodeled execution costs. This equals roughly **73.53 bps** break-even flash fee under the surrogate assumptions.

This is currently the most credible positive number in the repository, but it remains `TOKEN_CLOSED SURROGATE`, not `FORK_EXECUTABLE`.

## QE audit — critical result

The atomic hard-token conservation identity is:

`DeltaHardVector_protocol = sum(external swap deltas) - external costs`.

Minting RUBC/RUBX, changing own virtual reserves, own-pool swaps and ADDLP/REMOVELP can change prices and the location of inventory, but they do not increase the consolidated hard-token vector.

### What survived

QE **does** create graph dislocations in V7.2 and changes the surrogate settlement solution in V7.3.

### What did not survive

The V7.3 apparent QE uplift relied on allowing hard-token deficits and surpluses to settle by oracle USD value through the protocol-owned graph. V7.4 proves that this cannot repay Balancer token-by-token.

### V8.1 / V8.2 causality issue

The current V8.1 fork test deliberately locks part of flash WETH in a virtual RUBC/WETH edge. It then declares the external cycle infeasible before QE and feasible after a 5% pulse releases some of that locked WETH.

That is a valid **accounting-gate test**, but it is not evidence of economic QE uplift: with the same total flash principal and without the self-imposed virtual lock, the external cycle already has the capital available.

V8.2 has the same structural issue. Its search first requires `flash_budget >= route_required`, then subtracts `total_locked` to create `baseline_free_hard`, and credits QE when it releases enough of the locked amount. Therefore the current `qe_created_feasibility` flag means:

`QE repaired a protocol-imposed liquidity lock`,

not:

`QE created additional external HardNAV versus the best no-QE packet with the same capital`.

A valid QE economic proof must compare against an **external-only null model using the same flash principal with no artificial virtual lock** and must require:

`HardNAV_with_QE > HardNAV_best_no_QE_same_capital + all_incremental_QE_costs`.

Under the current V8.2 opportunity model the external hard flow is fixed before QE, so there is no independent QE hard-value uplift to prove yet.

## Bottom line

### Is there profit in the project?

**Yes, there is a positive historical external-arbitrage candidate.** The strongest surviving accounting result is V7.4: approximately **+$15.97** on a **$2,171.93** reusable flash draw in the run-36 CPMM surrogate.

### Is that profit proven executable on Base?

**No.** The exact pinned-block Foundry fork has never successfully executed because the available GitHub-hosted jobs fail before the first step and the present compute environment has no working Base RPC/Foundry path.

### Is the extra profit specifically from QE proven?

**No.** V7.3's large atomic QE uplift fails token-denomination closure, while V8.1/V8.2 currently demonstrate an internal liquidity-unlock gate rather than a higher external HardNAV than the best no-QE packet with the same capital.

## Promotion rule for the next version

No future version may claim QE profit unless all of the following are simultaneously true on the same pinned Base block:

1. exact external pool state and adapters;
2. same flash principal in QE and no-QE controls;
3. no artificial virtual-edge lock in the no-QE control;
4. token-by-token principal + actual fee closure;
5. shared external state mutated sequentially;
6. all RUBC/RUBX and own LP positions consolidated/burned;
7. gas + L1 data + MEV/competition reserve deducted;
8. `HardNAV_QE > HardNAV_best_no_QE` by a positive safety margin;
9. Foundry fork actually executes successfully;
10. only then consider a small live transaction.

Until that gate passes, the honest status is:

**external arbitrage candidate: YES; exact executable profit: UNPROVEN; atomic QE incremental profit: UNPROVEN.**
