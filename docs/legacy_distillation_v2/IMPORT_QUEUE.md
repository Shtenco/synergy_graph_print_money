# LEGACY DISTILLATION V2 — Import Queue

Canonical owner: `Shtenco/synergy_graph_print_money`

Nothing in this queue is auto-promoted to production. Every mechanism must pass the listed gate in this repository authority boundary.

| Priority | ID | Family | Action | Occurrences | Test gate | Representative |
|---|---|---|---|---:|---|---|
| P0_REWRITE | M068 | EMISSION_MINT_BURN | REWRITE_REQUIRED | 572 | `supply_and_backing_counterentry` | mint |
| P0_REWRITE | M083 | FEE_DIVIDEND_REBATE | REWRITE_REQUIRED | 550 | `funded_fee_distribution` | pause |
| P0_REWRITE | M006 | AMM_SWAP_LIQUIDITY | REWRITE_REQUIRED | 211 | `amm_conservation_and_slippage` | totalSupply |
| P0_PROMOTE_WITH_GATE | M069 | EMISSION_MINT_BURN | PROMOTION_CANDIDATE | 379 | `supply_and_backing_counterentry` | totalSupply |
| P0_REWRITE | M070 | EMISSION_MINT_BURN | REWRITE_REQUIRED | 124 | `supply_and_backing_counterentry` | mint |
| P1_REWRITE | M009 | AMM_SWAP_LIQUIDITY | REWRITE_REQUIRED | 90 | `amm_conservation_and_slippage` | addOneSided |
| P1_REWRITE | M011 | AMM_SWAP_LIQUIDITY | REWRITE_REQUIRED | 78 | `amm_conservation_and_slippage` | lockTheSwap |
| P0_PROMOTE_WITH_GATE | M007 | AMM_SWAP_LIQUIDITY | PROMOTION_CANDIDATE | 207 | `amm_conservation_and_slippage` | Pool |
| P1_REWRITE | M084 | FEE_DIVIDEND_REBATE | FALSIFICATION_FIXTURE_OR_REWRITE | 87 | `funded_fee_distribution` | notifyFounderEmission |
| P1_REWRITE | M073 | EMISSION_MINT_BURN | REWRITE_REQUIRED | 68 | `supply_and_backing_counterentry` | transfer |
| P0_PROMOTE_WITH_GATE | M008 | AMM_SWAP_LIQUIDITY | PROMOTION_CANDIDATE | 180 | `amm_conservation_and_slippage` | addToLpBuf |
| P0_PROMOTE_WITH_GATE | M071 | EMISSION_MINT_BURN | PROMOTION_CANDIDATE | 121 | `supply_and_backing_counterentry` | qe_epoch |
| P1_PROMOTE_WITH_GATE | M072 | EMISSION_MINT_BURN | PROMOTION_CANDIDATE | 94 | `supply_and_backing_counterentry` | recordFee |
| P1_PROMOTE_WITH_GATE | M010 | AMM_SWAP_LIQUIDITY | PROMOTION_CANDIDATE | 87 | `amm_conservation_and_slippage` | swapExactTokensForETHSupportingFeeOnTransferTokens |
| P1_PROMOTE_WITH_GATE | M012 | AMM_SWAP_LIQUIDITY | PROMOTION_CANDIDATE | 77 | `amm_conservation_and_slippage` | createPair |
| P1_PROMOTE_WITH_GATE | M013 | AMM_SWAP_LIQUIDITY | PROMOTION_CANDIDATE | 76 | `amm_conservation_and_slippage` | getReserves |
| P1_PROMOTE_WITH_GATE | M085 | FEE_DIVIDEND_REBATE | PROMOTION_CANDIDATE | 72 | `funded_fee_distribution` | recordFee |
| P1_PROMOTE_WITH_GATE | M014 | AMM_SWAP_LIQUIDITY | PROMOTION_CANDIDATE | 64 | `amm_conservation_and_slippage` | _spotPrice |
| P1_PROMOTE_WITH_GATE | M086 | FEE_DIVIDEND_REBATE | PROMOTION_CANDIDATE | 62 | `funded_fee_distribution` | addToBuyback |
| P1_PROMOTE_WITH_GATE | M074 | EMISSION_MINT_BURN | PROMOTION_CANDIDATE | 61 | `supply_and_backing_counterentry` | EmissionEngine |
| P1_PROMOTE_WITH_GATE | M015 | AMM_SWAP_LIQUIDITY | PROMOTION_CANDIDATE | 55 | `amm_conservation_and_slippage` | Anchor |
| P1_PROMOTE_WITH_GATE | M087 | FEE_DIVIDEND_REBATE | PROMOTION_CANDIDATE | 53 | `funded_fee_distribution` | buybackBurn |
| P1_PROMOTE_WITH_GATE | M017 | ARBITRAGE | PROMOTION_CANDIDATE | 51 | `net_external_pnl` | executeArb |
| P1_REWRITE | M093 | FEE_DIVIDEND_REBATE | FALSIFICATION_FIXTURE_OR_REWRITE | 19 | `funded_fee_distribution` | DividendPool |
| P1_PROMOTE_WITH_GATE | M075 | EMISSION_MINT_BURN | PROMOTION_CANDIDATE | 42 | `supply_and_backing_counterentry` | _clamp |
| P1_PROMOTE_WITH_GATE | M016 | AMM_SWAP_LIQUIDITY | PROMOTION_CANDIDATE | 41 | `amm_conservation_and_slippage` | _flushA |
| P1_PROMOTE_WITH_GATE | M076 | EMISSION_MINT_BURN | PROMOTION_CANDIDATE | 39 | `supply_and_backing_counterentry` | constructor |
| P1_PROMOTE_WITH_GATE | M088 | FEE_DIVIDEND_REBATE | PROMOTION_CANDIDATE | 37 | `funded_fee_distribution` | triggerBuyback |
| P1_PROMOTE_WITH_GATE | M018 | ARBITRAGE | PROMOTION_CANDIDATE | 34 | `net_external_pnl` | executeArb |
| P1_PROMOTE_WITH_GATE | M090 | FEE_DIVIDEND_REBATE | PROMOTION_CANDIDATE | 30 | `funded_fee_distribution` | routeFee |
| P1_PROMOTE_WITH_GATE | M089 | FEE_DIVIDEND_REBATE | PROMOTION_CANDIDATE | 30 | `funded_fee_distribution` | FeeRouter |
| P1_PROMOTE_WITH_GATE | M091 | FEE_DIVIDEND_REBATE | PROMOTION_CANDIDATE | 29 | `funded_fee_distribution` | constructor |
| P1_PROMOTE_WITH_GATE | M019 | ARBITRAGE | PROMOTION_CANDIDATE | 24 | `net_external_pnl` | registerPair |
| P1_PROMOTE_WITH_GATE | M092 | FEE_DIVIDEND_REBATE | PROMOTION_CANDIDATE | 23 | `funded_fee_distribution` | _executeBuyback |
| P1_PROMOTE_WITH_GATE | M077 | EMISSION_MINT_BURN | PROMOTION_CANDIDATE | 23 | `supply_and_backing_counterentry` | onALTNBurn |
| P1_PROMOTE_WITH_GATE | M020 | ARBITRAGE | PROMOTION_CANDIDATE | 21 | `net_external_pnl` | _checkArbPremium |
| P1_PROMOTE_WITH_GATE | M078 | EMISSION_MINT_BURN | PROMOTION_CANDIDATE | 20 | `supply_and_backing_counterentry` | init_db |
| P1_PROMOTE_WITH_GATE | M094 | FEE_DIVIDEND_REBATE | PROMOTION_CANDIDATE | 16 | `funded_fee_distribution` | _checkBuyback |
| P1_PROMOTE_WITH_GATE | M021 | ARBITRAGE | PROMOTION_CANDIDATE | 12 | `net_external_pnl` | contribute |
| P1_REWRITE | M082 | EMISSION_MINT_BURN | REWRITE_REQUIRED | 3 | `supply_and_backing_counterentry` | sell |
| P1_PROMOTE_WITH_GATE | M079 | EMISSION_MINT_BURN | PROMOTION_CANDIDATE | 7 | `supply_and_backing_counterentry` | EmissionEngine |
| P1_PROMOTE_WITH_GATE | M080 | EMISSION_MINT_BURN | PROMOTION_CANDIDATE | 6 | `supply_and_backing_counterentry` | anchors_productive_v5_us.csv |
| P1_PROMOTE_WITH_GATE | M081 | EMISSION_MINT_BURN | PROMOTION_CANDIDATE | 6 | `supply_and_backing_counterentry` | banks_productive_v5_us.csv |
