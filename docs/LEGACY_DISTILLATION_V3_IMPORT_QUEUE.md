# LEGACY DISTILLATION V3 — synergy_graph_print_money

Assigned primitives:

- P003 AMM_SWAP_LIQUIDITY — REWRITE
- P004 AMM_SWAP_LIQUIDITY — REWRITE
- P005 AMM_SWAP_LIQUIDITY — PROMOTE
- P006 AMM_SWAP_LIQUIDITY — REWRITE
- P007 ARBITRAGE — PROMOTE
- P008 ARBITRAGE — PROMOTE
- P023 EMISSION_MINT_BURN — REWRITE
- P024 EMISSION_MINT_BURN — PROMOTE
- P025 EMISSION_MINT_BURN — REWRITE
- P026 EMISSION_MINT_BURN — PROMOTE
- P027 EMISSION_MINT_BURN — PROMOTE
- P028 FEE_DIVIDEND_REBATE — REWRITE
- P029 FEE_DIVIDEND_REBATE — PROMOTE
- P030 FEE_DIVIDEND_REBATE — PROMOTE
- P031 FEE_DIVIDEND_REBATE — PROMOTE

Core gates: AMM reserve conservation/slippage; every mint/burn has a balanced backing/liability/counter-entry; every distribution traces to an external payer/source; arbitrage PnL is recognized only net of gas, fees, MEV, slippage and flash liabilities. Internal token marks, self-LP and QE ex nihilo are never external profit.
