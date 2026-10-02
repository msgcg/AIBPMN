# BPMN-as-Code: Примеры процессов (Few-Shot)

## Пример 1: Согласование договора (Дорожки ролей + Цикл возврата на доработку)
```bac
process "Согласование договора"

pool: p_corp "Организация"
lane: l_initiator "Инициатор" in p_corp
lane: l_jurist "Юридический отдел" in p_corp
lane: l_director "Генеральный директор" in p_corp

start: s_draft "Проект договора создан" in l_initiator
task: t_submit "Передать на юридическую экспертизу" user in l_initiator
task: t_review "Проверка юридических условий" user in l_jurist
gateway: g_jurist "Условия согласованы?" exclusive in l_jurist

task: t_rework "Устранение замечаний юриста" user in l_initiator

task: t_sign "Подписание договора директором" user in l_director
gateway: g_sign "Договор подписан?" exclusive in l_director

end: e_approved "Договор успешно подписан" in l_director
end: e_rejected "Договор отклонен" in l_director

s_draft -> t_submit -> t_review -> g_jurist

# Цикл возврата на доработку к инициатору
g_jurist --[Замечания]--> t_rework
t_rework -> t_review

# Переход на подписание к директору
g_jurist --[Согласовано]--> t_sign -> g_sign
g_sign --[Да]--> e_approved
g_sign --[Отказ]--> e_rejected
```

## Пример 2: Обработка заказа интернет-магазина (Внешний пул + Внутренние дорожки)
```bac
process "Обработка и доставка заказа"

pool: p_client "Клиент (внешний)"
pool: p_store "Интернет-магазин"
lane: l_sales "Отдел продаж" in p_store
lane: l_warehouse "Склад" in p_store
lane: l_courier "Курьерская служба" in p_store

start: s_order "Поступил новый заказ" in l_sales
task: t_verify "Проверить реквизиты и оплату" service in l_sales
gateway: g_payment "Оплата подтверждена?" exclusive in l_sales

task: t_pick "Скомплектовать и упаковать товар" manual in l_warehouse
task: t_deliver "Доставка заказа клиенту" manual in l_courier

end: e_done "Заказ доставлен покупателю" in l_courier
end: e_cancel "Заказ отменен" in l_sales

s_order -> t_verify -> g_payment
g_payment --[Да]--> t_pick -> t_deliver -> e_done
g_payment --[Нет]--> e_cancel
```

## Пример 3: Выявление логического разрыва (Строгое соблюдение логики)
Если в описании регламента шаг B не имеет условия или связи с шагом A:
```bac
process "Процесс с обнаруженным разрывом"

pool: p_work "Компания"
lane: l_admin "Администратор" in p_work
lane: l_sec "Служба безопасности" in p_work

start: s1 "Поступление анкеты" in l_admin
task: t_check "Первичная проверка анкеты" user in l_admin

# Шаг t_notify оторван в регламенте — отсутствует условие перехода от первичной проверки
task: t_notify "Отправка уведомления соискателю" user in l_sec
end: e_final "Завершение проверки" in l_sec

s1 -> t_check
t_notify -> e_final
```
Ответ архитектора обязательно сопровождается предупреждением:
`⚠️ Обнаружен логический разрыв: в регламенте не указано, при каких условиях и после какого события выполняется «Отправка уведомления соискателю». Связь намеренно не проведена, чтобы подсветить дефект регламента.`
