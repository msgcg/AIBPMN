# BPMN-as-Code: Примеры процессов (Few-Shot)

## Пример 1: Обработка заказа интернет-магазина
```
process "Обработка заказа"

start: order_created "Поступил новый заказ"
end: order_completed "Заказ успешно доставлен"
end: order_cancelled "Заказ аннулирован"

task: check_stock "Проверить наличие на складе" service
gateway: stock_ok "Товар в наличии?" exclusive

task: reserve_items "Зарезервировать товар" service
task: process_payment "Списать оплату" service
gateway: payment_ok "Оплата прошла?" exclusive

gateway: parallel_fulfillment "Подготовка к отправке" parallel
task: assemble_package "Собрать посылку" manual by "Склад"
task: print_invoice "Распечатать накладную" service
gateway: join_fulfillment "Посылка готова" parallel

task: delivery "Доставка курьером" by "Служба доставки"

order_created -> check_stock -> stock_ok
stock_ok --[Да]--> reserve_items -> process_payment -> payment_ok
stock_ok --[Нет]--> order_cancelled

payment_ok --[Успех]--> parallel_fulfillment
payment_ok --[Ошибка]--> order_cancelled

parallel_fulfillment -> assemble_package -> join_fulfillment
parallel_fulfillment -> print_invoice -> join_fulfillment

join_fulfillment -> delivery -> order_completed
```

## Пример 2: Согласование кредитной заявки
```
process "Согласование кредита"

start: app_submitted "Заявка подана клиентом"
end: credit_issued "Кредит выдан"
end: app_rejected "Заявка отклонена"

task: scoring "Автоматический скоринг" service
gateway: score_check "Скоринг пройден?" exclusive

task: underwriter_review "Ручная андеррайтинг-проверка" user by "Андеррайтер"
gateway: underwriter_decision "Решение андеррайтера" exclusive

task: generate_agreement "Сформировать кредитный договор" service
task: sign_agreement "Подписание договора клиентом" user by "Клиент"
task: disburse_funds "Перечисление денежных средств" service

app_submitted -> scoring -> score_check
score_check --[Высокий балл]--> generate_agreement
score_check --[Средний балл]--> underwriter_review -> underwriter_decision
score_check --[Низкий балл]--> app_rejected

underwriter_decision --[Одобрено]--> generate_agreement
underwriter_decision --[Отклонено]--> app_rejected

generate_agreement -> sign_agreement -> disburse_funds -> credit_issued
```

