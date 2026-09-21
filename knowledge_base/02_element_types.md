# BPMN-as-Code: Семантика элементов

## 1. События (Events)
### Начальные события (Start Events)
- Простое начало: `start: start_id "Лейбл"`
- Начало по сообщению: `start: msg_start "Получено сообщение" message`
- Начало по таймеру: `start: timer_start "В 09:00 каждый день" timer`

### Конечные события (End Events)
- Простое завершение: `end: done "Процесс завершен"`
- Завершение с ошибкой: `end: fail "Ошибка обработки" error`
- Принудительное прерывание: `end: cancel "Заказ отменен" terminate`

### Промежуточные и граничные события (Intermediate & Boundary)
- Ожидание события: `catch: wait_msg "Ожидание оплаты" message`
- Генерация события: `throw: send_alert "Отправка сигнала" signal`
- Граничное событие на задаче:
  `boundary: timeout "Таймаут 24 часа" timer on task_id`
  `boundary: err_handler "Ошибка API" error on task_id noninterrupting`

## 2. Задачи (Tasks)
Формат задачи:
`task: <id> "<Лейбл>" [<тип>] [by "<Исполнитель>"] [loop [parallel|sequential]]`

### Типы задач:
- `user`: Пользовательская задача с участием человека (например: `task: t1 "Согласовать заявку" user by "Руководитель"`)
- `service`: Автоматическая системная задача / API (например: `task: t2 "Списать средства" service`)
- `script`: Автоматический скрипт / расчет (например: `task: t3 "Рассчитать скидку" script`)
- `send`: Отправка сообщения / email (например: `task: t4 "Отправить чек клиенту" send`)
- `receive`: Ожидание внешнего сообщения (например: `task: t5 "Получить ответ банка" receive`)
- `manual`: Ручная физическая операция (например: `task: t6 "Упаковать товар" manual by "Кладовщик"`)
- `businessrule`: Принятие решения по таблице решений (DMN)

## 3. Подпроцессы и вызовы (Subprocesses & Call Activities)
- `subprocess: sub1 "Обработка претензии" by "Юристы"`
- `call: global_auth "Единая авторизация SSO"`

## 4. Данные и аннотации
- `data: doc1 "Заявление клиента"`
- `datastore: db1 "База клиентов CRM"`
- `note: n1 "SLA не более 2 часов" on t1`

