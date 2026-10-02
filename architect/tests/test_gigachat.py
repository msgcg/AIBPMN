from django.test import TestCase
from architect.services.gigachat_client import GigaChatService

class GigaChatServiceTests(TestCase):
    def test_extract_dsl_and_explanation(self):
        text = """Вот сформированная диаграмма процесса:
```bac
process "Онбординг"
start: s "Начало"
task: t "Инструктаж" user by "HR"
end: e "Завершение"
s -> t -> e
```
В данном процессе заложен инструктаж нового сотрудника."""

        dsl, explanation = GigaChatService.extract_dsl_and_explanation(text)
        self.assertIn('process "Онбординг"', dsl)
        self.assertIn('start: s "Начало"', dsl)
        self.assertIn('В данном процессе заложен инструктаж', explanation)

    def test_extract_pure_consultation_qa(self):
        text = """В вашей схеме процесс начинается с узла start: s "Подача заявки".
Далее согласование производит Бухгалтер. При отказе процесс завершается.
Код менять не требуется."""
        dsl, explanation = GigaChatService.extract_dsl_and_explanation(text)
        self.assertIsNone(dsl)
        self.assertEqual(explanation, text.strip())

    def test_extract_generic_code_block_with_process(self):
        text = """Схема:
```
process "Закупка"
start: s "Старт"
end: e "Финиш"
s -> e
```
Готово."""
        dsl, explanation = GigaChatService.extract_dsl_and_explanation(text)
        self.assertIsNotNone(dsl)
        self.assertIn('process "Закупка"', dsl)
        self.assertIn('Готово.', explanation)

    def test_auto_correction_preserves_initial_explanation(self):
        from unittest.mock import patch
        first_resp = """Вот подробный архитектурный обзор бизнес-процесса:
1. Инициация заявки
2. Проверка остатков
```bac
process "Склад"
start: s
```"""
        second_resp = """Исправил синтаксис кода:
```bac
process "Склад"
start: s "Старт"
end: e "Конец"
s -> e
```"""
        with patch.object(GigaChatService, '_call_completions', side_effect=[first_resp, second_resp]):
            result = GigaChatService.generate_diagram("Тестовый запрос", max_retries=2)
            self.assertTrue(result['success'])
            self.assertEqual(result['attempts'], 2)
            # The explanation MUST be the initial architectural text, not the retry's "Исправил синтаксис..."
            self.assertIn("Вот подробный архитектурный обзор", result['explanation'])
            self.assertNotIn("Исправил синтаксис", result['explanation'])

    def test_status_check(self):
        status = GigaChatService.check_status()
        self.assertTrue(status.get('ok'), f"GigaChat status check failed: {status.get('error')}")
        self.assertEqual(status.get('model'), 'GigaChat-3-Ultra')

    def test_logical_gap_detection_and_warning(self):
        from unittest.mock import patch
        mock_response = """Обнаружен процесс с разорванной логикой:
```bac
process "Процесс с разрывом"
start: s "Подача заявки"
task: t1 "Оформление заявки"
task: t2 "Выплата компенсации"
end: e "Завершено"

s -> t1
t2 -> e
```
В описании нарушена логика."""
        with patch.object(GigaChatService, '_call_completions', return_value=mock_response):
            result = GigaChatService.generate_diagram("Пользователь подает заявку, а потом внезапно выплата", max_retries=1)
            self.assertTrue(result['success'])
            self.assertIn("⚠️ **Обнаружен логический разрыв:**", result['explanation'])
            self.assertIn("Связь намеренно не построена", result['explanation'])
            self.assertIn("разрыв", result['validation_report'])
            self.assertTrue(any("связывает" in q or "инициирует" in q for q in result['proactive_questions']))

