# GRAPH ECONOMY V7.4

## Оригинальная исследовательская задача

Token-closed Base multigraph / external HardNAV. RUBC and RUBX monetary actuators; external liquidity venues; exact flash debt repayment; matched protocol-owned LP accounting.

## Реализация и фактический исследовательский статус

The canonical CURRENT_VERSION.json records six simulated token-closed cycles, 14 foreign swaps, modeled 15.9704789 USD candidate net HardNAV and 2171.9290 USD concurrent flash usage. Exact pinned-block fork validation is still pending.

## Математическая модель и научная интерпретация

Formal CPMM: output = reserve_out * input_net / (reserve_in + input_net), where input_net = input*(1-fee). Profit is externally reconciled balances minus obligations and execution costs; internal self-token marks do not create independently redeemable assets.

## План воспроизводимых исследований и профессиональное применение

Run the V7_4Run36Packet.t.sol scenario on a pinned chain fork, validate all token balances and flash fees, net gas, MEV risk, and token closure before promoting economic performance.

Исследовательское направление имеет потенциальную практическую ценность в собственной предметной области, если эффективность подтверждается новым независимым экспериментом. Алгоритмическое описание, код, результат симуляции и фактическое развёртывание необходимо документировать как разные уровни доказательности.

## Файлы и воспроизводимость

- [CURRENT_VERSION.json](../CURRENT_VERSION.json)
- [src/synergy_graph/v7_4_eurasian_qe.py](../src/synergy_graph/v7_4_eurasian_qe.py)
- [test/V7_4Run36Packet.t.sol](../test/V7_4Run36Packet.t.sol)

**Публикационный стандарт:** точный source commit, набор входов, контрольные суммы, версии окружения, независимые тесты и открытые ограничения. Этот раздел дополняет прежний README, не сокращая исторические исследования.
