# SYNERGY Economic OS — модель V1–V6

## 1. Узлы и физические пулы

Пусть внешний слой содержит `M` уникальных hard-assets. Добавляются RUBC и RUBX. Полный собственный 50/50 CPMM-граф: `E_own = C(M+2,2)`.

Чужие DEX-пулы не сливаются с нашими одинаковыми парами: они являются отдельными физическими рёбрами multigraph. При 48 hard-assets и 240 foreign pools: 50 узлов, 1,225 own pools, 1,465 total pools.

## 2. CPMM

Для резерва `(x,y)`, входа `q` и fee `f`: `q_eff=(1-f)q`, `y_out = y*q_eff/(x+q_eff)`.

Маршрут нелинеен; Bellman-Ford по `-log(rate)` допустим только как infinitesimal detector. Размер сделки должен оптимизироваться точным quote/state transition.

## 3. HardNAV

`H = Σ p_i * hard_asset_i - external_debt`. RUBC/RUBX не оцениваются по цене, нарисованной собственным тонким пулом. Flash principal — обязательство и не увеличивает H.

## 4. Собственные LP и консолидация

Если Treasury/Router и LP принадлежат одному протоколу, swap между ними не создаёт внешнюю стоимость. `ΔH_self = ΔH_router + ΔH_ownLP = 0` до внешних расходов. Mint собственного токена и покупка hard-asset из собственного LP — не seigniorage и не прибыль.

## 5. Чужие LP

Чужие пулы — настоящие внешние контрагенты. При adverse selection: `ΔH_SYNERGY(gross) = -Σ ΔV_foreignLP`. После расходов: `ΔH = -Σ ΔV_foreignLP - Gas - MEV - FlashFee`.

## 6. RUBC / RUBX

RUBC: transactional monetary actuator. RUBX: reserve/rebalancing actuator. Временный mint может выступать внутрисистемным inventory actuator, но не считается внешней стоимостью.

Настоящий постоянный seigniorage возникает только при внешнем покупателе: `external hard asset → protocol`, `new RUBC/RUBX → external holder`.

Аккретивность: `(H+ΔH)/(S+ΔS) >= H/S`, или `ΔH >= h*ΔS`, `h=H/S`. `AS = ΔH - hΔS`.

## 7. ADDLP / REMOVELP

Liquidity allocation — отдельная оптимизационная переменная. Но атомарный ADDLP в собственный пул и REMOVELP после собственного swap не создают value. Их функция — изменение slippage/route state и размещение уже существующего инвентаря. В одной атомарной arbitrage transaction external value должен приходить через foreign swap edges или внешний спрос.

## 8. V3–V6 контрольные результаты

Синтетические результаты сохранены только как regression/reference и не являются прогнозом доходности. Ключевые выводы: fair graph → optimal arb=0; связность повышает число составных cycles; foreign residual mispricing является источником arbitrage PnL; low flash fee критичен для малых edges; V5 переоценивал self-owned liquidity, V6 исправляет бухгалтерию.

## 9. Целевая функция Economic OS

`maximize ΔHardNAV_after_all_costs` по route(s), flash principal, temporary RUBC/RUBX mint/burn, liquidity allocation и execution order. Permanent issuance допустим только против external demand.

Constraints: same-block quotes; full flash repayment; no double counting own LP; no self-marked RUBC/RUBX NAV; post-cost profit > 0; при росте permanent supply — `AS > 0`.
