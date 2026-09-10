# SYNERGY Graph Print Money — Economic OS / SAG V7

Экспериментальная исследовательская система для построения единого мультиграфа ликвидности Base Mainnet вокруг двух протокольных денежных узлов `RUBC` и `RUBX`.

Главная идея проекта — не считать печать собственных токенов или перемещение активов между собственными LP прибылью. Единственная бухгалтерская истина — **консолидированный HardNAV** во внешних активах после возврата flash-loan, gas, MEV/competition haircut и всех обязательств.

## Текущая архитектура

- `RUBC` — эластичный monetary/settlement actuator.
- `RUBX` — reserve/rebalancing actuator.
- наши пулы — 50/50 CPMM `x*y=k`; при `M` внешних валютах полный собственный cross-graph содержит `C(M+2,2)` пулов;
- чужие Base pools остаются отдельными параллельными рёбрами multigraph и принадлежат чужим LP;
- стартовый собственный HardNAV исследовательской модели: **$100**;
- доступная внешняя покупательная способность: до **$50,000 Balancer V2 flash loan**, но principal никогда не включается в NAV;
- временные `ADDLP/REMOVELP` в собственные пулы — только перераспределение нашего/заёмного инвентаря, не источник PnL;
- внешний PnL признаётся только как value transfer с внешних рынков/LP либо как настоящий seigniorage от внешнего спроса на RUBC/RUBX.

Для V6-калибровки использовалось 48 внешних активов: `50` узлов с RUBC/RUBX, `1,225` наших кросс-пулов + `240` чужих = `1,465` физических пулов.

## V7: live Base Mainnet

V7 убирает синтетический foreign graph. Pipeline:

```text
GeckoTerminal top Base pools
        ↓
normalize token/pool addresses
        ↓
RPC snapshot at one Base block
        ↓
probe pool bytecode + token0/token1 + getReserves/slot0/fee
        ↓
build directed multigraph
        ↓
find closed candidate cycles
        ↓
exact protocol quote adapters / eth_call
        ↓
flash principal optimizer
        ↓
Foundry/Base fork execution
        ↓
HardNAV accounting
```

Статусы кандидата: `DISCOVERED → RPC_VERIFIED → STATE_VERIFIED → QUOTE_VERIFIED → FORK_EXECUTABLE`.

**Нельзя** объявлять найденную по агрегаторным spot-данным петлю прибылью до `QUOTE_VERIFIED`, а production-кандидатом — до `FORK_EXECUTABLE`.

## Быстрый запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export BASE_RPC_URL=https://mainnet.base.org
python scripts/run_v7.py --pages 12 --max-pools 240 --out artifacts
```

Ожидаемые файлы: `artifacts/v7_pools.csv`, `artifacts/v7_rpc_state.csv`, `artifacts/v7_candidates.csv`, `artifacts/v7_report.json`.

## Бухгалтерские инварианты

- Flash principal: `HardNAV = hard_assets - external_liabilities`; при заимствовании $50k и наличии $100 капитала NAV остаётся $100.
- Собственный LP: `ΔH_router + ΔH_ownLP = 0` для self-swap, если нет внешнего контрагента.
- Арбитраж чужого LP: `ΔHardNAV_SYNERGY(gross) = -Σ ΔV_foreignLP` до gas/MEV.
- Аккретивная постоянная эмиссия: `ΔH >= h_t * ΔS`, где `h_t = H_t / S_t`.
- Abundance Surplus: `AS = ΔH - h_t ΔS`.

## Важная коррекция V5

Атомарный `ADDLP → self swap → REMOVELP` в пуле, который на 100% принадлежит протоколу, сам по себе не создаёт HardNAV: чужая транзакция не может вклиниться внутрь нашей EVM-транзакции. В V7 собственные пулы рассматриваются как маршрутизация/инвентарь, а не как внешний источник стоимости.

## Balancer V2 Base

Официальные deployment metadata Balancer для Base указывают V2 Vault `0xBA12222222228d8Ba445958a75a0704d566BF2C8`. V7 проверяет код контракта и балансы требуемых токенов на выбранном block tag. Flash fee не считается вечной константой: production execution обязан читать/проверять фактические условия перед сделкой.

## Структура

- `docs/ECONOMIC_OS.md` — модель V1–V6 и экономические границы;
- `docs/V7_LIVE_SPEC.md` — live pipeline и acceptance criteria;
- `src/synergy_graph/v7.py` — discovery/RPC/graph engine;
- `contracts/V7FlashExecutor.sol` — guarded Balancer receiver/executor scaffold;
- `data/history_results.csv` — контрольные синтетические результаты прошлых версий;
- `.github/workflows/v7-live.yml` — CI + live discovery snapshot.

V7 — **research / simulation / fork-validation code**, не production trading contract. Реальная доходность не выводится из количества синтетических snapshots. Главный критерий: наличие на одном и том же Base block реальных циклов, которые проходят exact quote и fork execution после gas/MEV/flash fee.
