# BPMN-as-Code: Шлюзы и потоки управления (Gateways & Flows)

## 1. Типы шлюзов (Gateways)
Формат: `gateway: <id> "<Лейбл-вопрос или действие>" [<тип>]`

### Типы:
1. `exclusive` (по умолчанию, исключающее «ИЛИ» / XOR): выбирается ровно одна ветка.
   Пример: `gateway: is_approved "Заявка одобрена?" exclusive`
2. `parallel` (параллельное «И» / AND): все исходящие ветки выполняются одновременно.
   Пример: `gateway: fork_checks "Запуск параллельных проверок" parallel`
3. `inclusive` (неисключающее «ИЛИ» / OR): активируется одна или несколько веток по условиям.
   Пример: `gateway: split_options "Дополнительные услуги" inclusive`
4. `eventbased` (шлюз по событиям): процесс ждет, какое из событий наступит первым.
   Пример: `gateway: wait_choice "Ожидание действия" eventbased`

## 2. Потоки управления (Sequence Flows)

- Простая стрелка:
  `step1 -> step2`
- Цепочка потоков:
  `start_node -> step1 -> step2 -> gateway_check`
- Условный переход (для ветвления из шлюзов):
  `gateway_check --[Да]--> step_approve`
  `gateway_check --[Нет]--> step_reject`
- Поток по умолчанию (default flow):
  `gateway_check ==> step_default`
- Потоки сообщений между пулами:
  `client_step ~> server_step`

## 3. Правило парных параллельных шлюзов
Если процесс разделяется параллельным шлюзом (`parallel`), то перед дальнейшим общим шагом потоки должны обязательно объединяться парным параллельным шлюзом:
```
fork_gateway -> check_docs -> join_gateway
fork_gateway -> check_credit -> join_gateway
join_gateway -> final_decision
```

