# V7.4 FULL-FORK GRAPH EXECUTOR — token conservation before HardNAV

Snapshot basis: Base run #36, pinned block `51148993`.

V7.4 keeps the full Economic-OS graph — 98 canonical external assets, RUBC, RUBX, 4,950 conceptual protocol cross-pools and 211 observed foreign pools — but strengthens the execution invariant. The V7.3 USD-valued 36-leg packet is retained as a useful settlement upper bound; it is **not** labelled flash-executable after V7.4.

## 1. The missing invariant in V7.3

Balancer does not lend a scalar `$50,000` balance sheet. It lends concrete ERC-20 amounts and requires those same token addresses to be returned in the callback, plus the protocol fee.

For every flash token `A_i`, the atomic packet therefore needs

`B_after[A_i] >= B_preexisting[A_i] + FlashPrincipal[A_i] + FlashFee[A_i]`.

Only after this vector constraint passes may balances be aggregated into USD HardNAV.

The protocol-owned graph cannot repair a consolidated hard-token deficit for free. A move through an own `A/RUBC`, `RUBC/RUBX`, `RUBX/B` or `A/B` pool transfers hard inventory between router/Treasury/POL, but after consolidation the aggregate hard-token vector is unchanged by the own-only part of the operation.

Therefore, for an atomic self-routed transaction,

`DeltaHardTokenVector_protocol = sum(DeltaHardTokenVector_foreign_swaps) - external costs`.

Temporary RUBC/RUBX mint/burn changes monetary inventory and graph state, not the conserved hard-token vector.

## 2. Re-audit of the V7.3 36-leg packet

The old packet has positive oracle-valued foreign transfer:

`sum_i p_i * Delta q_i = +$169.064923` before the 35% competition/MEV haircut and gas.

But the vector itself is not closed:

- gross token-specific deficits: about **$14,697.51**;
- gross token-specific surpluses: about **$14,866.57**;
- net oracle value: about **+$169.06**;
- deficit token denominations: **11**.

Largest deficits include approximately:

- USDC: `-$6,558.35`;
- VIRTUAL: `-$2,279.59`;
- WETH: `-$2,219.74`;
- METAc: `-$758.56`;
- NVDAc: `-$645.25`;
- SNDKc: `-$563.81`;
- DIEM: `-$488.96`.

With only `$100` of permanent personal HardNAV, these deficits cannot be covered token-by-token. A surplus in CP, cbBTC or another ERC-20 is not repayment of a USDC/WETH flash debt until an **external** conversion closes it.

The detailed vector is stored in `data/results/v7_4_packet36_token_conservation.csv`.

### Consequence

The V7.3 `+$107.73` result is reclassified as a **finite settlement / external-value upper-bound result under relaxed denomination closure**, not a Balancer-flash executable result.

This is exactly why V7.4 exists.

## 3. Strict stateful closed-cycle re-optimization

The adapter-supported run-36 subset was re-optimized with the stronger constraints:

1. each selected foreign route begins and ends in the same hard ERC-20;
2. the corresponding flash principal can therefore be repaid in-kind;
3. after an accepted cycle, every touched foreign CPMM surrogate is mutated;
4. the graph is rescanned before the next cycle, preventing repeated use of stale shared liquidity;
5. the same returned principal can be reused in later cycles;
6. 35% of positive gross external capture is reserved for competition/MEV;
7. modelled gas is `$0.02` per foreign swap;
8. RUBC/RUBX marks and protocol-owned LP transfers remain excluded from HardNAV.

The strict stateful solver selected **6 sequential closed cycles / 14 foreign swaps**.

### Result

- gross external hard-value transfer: **$25.0007367**;
- competition/MEV haircut at 35%: **$8.7502579**;
- modelled foreign-swap gas: **$0.28**;
- strict post-cost `DeltaHardNAV`: **+$15.9704789**;
- personal HardNAV: `$100 -> $115.9704789`;
- token closure: **true for every selected cycle**.

This remains a CPMM-surrogate result until the pinned fork executes exact CLMM/V3/Aerodrome state.

## 4. Six-cycle execution packet

The candidate packet is stored in `data/results/v7_4_stateful_token_closed_packet.csv`.

The four WETH cycles are parallel VIRTUAL/WETH market dislocations against the same Aerodrome V2 pool, executed sequentially so its state is not reused at the old reserve point. Two further USDC cycles are:

`USDC -> USDT -> WETH -> USDC`

and

`USDC -> EURC -> WETH -> USDC`.

All 14 foreign swaps belong to already implemented adapter families: Uniswap V3, Aerodrome Slipstream and Aerodrome V2. The current strict lower-bound packet does not require a Uniswap V4 adapter.

## 5. Flash capital after token closure

Because every cycle returns its start token, sequential cycle notionals are **not** added together to determine the flash principal. We need the maximum concurrent amount for each denomination:

- WETH equivalent: **$1,556.6380**;
- USDC equivalent: **$615.2910**;
- optimized total multi-token draw: **$2,171.9290**.

The sum of all cycle inputs is about `$4,765.28`, but returned WETH/USDC is reused in later cycles. The requested `$50,000` Balancer facility is therefore capacity, not required principal, for this candidate packet.

If flash fee is nonzero, borrowing only what is needed is materially better than requesting the full `$50k`.

## 6. Flash-fee sensitivity

Using the optimized `$2,171.929` draw and the surrogate post-MEV/gas result:

| flash fee | net candidate HardNAV gain |
|---:|---:|
| 0 bps | +$15.9705 |
| 1 bps | +$15.7533 |
| 3 bps | +$15.3189 |
| 5 bps | +$14.8845 |
| 10 bps | +$13.7985 |
| 25 bps | +$10.5407 |
| 50 bps | +$5.1108 |

Surrogate break-even is roughly **73.53 bps** on the actual optimized draw.

If a full `$50,000` were borrowed unnecessarily, each 1 bps costs `$5`, so the same candidate would break even at only about **3.19 bps**. V7.4 therefore sizes flash principal per asset rather than treating `$50k` as a mandatory draw.

## 7. What happens to QE/RUBC/RUBX under the stronger invariant

The huge `K_100` graph remains the discovery/control topology. QE still changes monetary edge weights and can reveal or reshape many cycles. But for a **single atomic transaction in which all protocol-owned pools are ours**, own-only QE cannot convert a net hard-token deficit in token A into a real surplus of token A after consolidation.

Consequently the V7.3 claim that atomic dual-QE raised executable capture from `$66.01` to `$107.73` does not survive the strict Balancer token-denomination gate. The uplift came from allowing different hard-token surpluses/deficits to settle by USD value through the protocol-owned graph.

This does not make the Economic OS or the huge graph useless. It separates two regimes:

### Atomic flash regime

`foreign token-closed cycles -> in-kind flash repayment -> hard profit`.

QE/RUBC/RUBX is a routing/price-field layer but cannot be counted as an external hard-value source. If it merely adds own swaps to an already token-closed packet, it adds gas/complexity and does not improve consolidated HardNAV by itself.

### Multi-block / external-absorption regime

QE can become economically productive when an **external agent** crosses the protocol-created RUBC/RUBX dislocation: external users/arbitrageurs pay hard assets into protocol-owned pools, or external holders permanently absorb newly issued RUBC/RUBX. That hard inflow changes the conserved protocol hard-token vector and can create true seigniorage.

V7.5 should model this separately rather than silently granting atomic self-QE the power of an external counterparty.

## 8. Fork executor

`contracts/V7_4GlobalPacketExecutor.sol` implements the stronger execution rule:

- one Balancer multi-token flash call;
- multiple sequential token-closed cycles;
- Aerodrome V2 and CL/V3 swap adapters;
- per-token pre-existing balance tracking;
- in-kind principal + actual `feeAmounts[]` repayment;
- per-token profit floor;
- no USD netting inside the repayment gate.

`test/V7_4Run36Packet.t.sol` freezes Base block `51148993`, borrows only the candidate WETH + USDC principals, executes all six cycles sequentially and performs one consolidated post-repayment HardNAV assertion.

The test deliberately uses actual Balancer callback `feeAmounts[]`. It does not hard-code a zero flash fee in the Solidity settlement logic.

## 9. Evidence status

Current strongest result is:

`5,161-pool conceptual graph`

`-> V7.3 36-leg relaxed-denomination packet: +$107.73 model result`

`-> token-level audit: NOT flash repayable`

`-> strict stateful token-closed re-optimization`

`-> 6 cycles / 14 foreign swaps`

`-> +$15.9705 post-cost CPMM-surrogate HardNAV candidate`

`-> exact pinned-block fork: PENDING`.

GitHub hosted Actions is currently failing before the first job step (`steps=null`) and the present compute environment cannot resolve the Base RPC hostname. Therefore this document does **not** claim that the new packet is `FORK_EXECUTABLE` yet.

The promotion condition remains:

`FORK_EXECUTABLE && DeltaHardNAV_after_actual_flash_fee_and_gas > 0`.

Only after that may the candidate be called a demonstrated same-block Base execution edge.
