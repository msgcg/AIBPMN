from django.test import TestCase
from architect.services.compiler_service import compile_dsl

class CompilerServiceTests(TestCase):
    def test_compile_valid_dsl(self):
        sample_dsl = """process "Order Test"

start: s "Начало"
task: t "Обработка" user by "Оператор"
gateway: g "Успешно?" exclusive
end: ok "Успех"
end: fail "Отказ"

s -> t -> g
g --[Да]--> ok
g --[Нет]--> fail"""

        res = compile_dsl(sample_dsl)
        self.assertTrue(res.get('valid'), f"Compilation failed: {res.get('error')}")
        self.assertIn('<definitions', res.get('xml', ''))
        self.assertIn('Order Test', res.get('xml', ''))
        self.assertGreater(res.get('node_count', 0), 3)
        self.assertGreater(res.get('flow_count', 0), 2)

    def test_compile_invalid_dsl(self):
        invalid_dsl = """process "Invalid"
start: s
this is broken syntax"""
        res = compile_dsl(invalid_dsl)
        self.assertFalse(res.get('valid'))
        self.assertIsNotNone(res.get('error'))

    def test_compile_empty_dsl(self):
        res = compile_dsl("")
        self.assertFalse(res.get('valid'))

    def test_compile_auto_declares_missing_flow_node(self):
        dsl = """process "Missing Node Test"
start: s "Начало"
end: e "Конец"
s -> print_docs -> e"""
        res = compile_dsl(dsl)
        self.assertTrue(res.get('valid'), f"Expected auto-declaration, but got error: {res.get('error')}")
        self.assertIn('print_docs', res.get('xml', ''))

