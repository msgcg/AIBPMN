import re
from django.test import TestCase
from architect.services.compiler_service import compile_dsl, decompile_bpmn_xml

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

    def test_compile_pools_and_lanes_containment(self):
        dsl = """process "Hiring Process"
pool: p1 "Компания"
lane: hr "HR-специалист" in p1
lane: boss "Руководитель" in p1
start: s "Новое резюме" in hr
task: t1 "Первичный скрининг" user in hr
task: t2 "Техническое интервью" user in boss
gate: g1 "Одобрить?" in boss
end: e1 "Оффер" in boss
end: e2 "Отказ" in hr
s -> t1 -> t2 -> g1
g1 --[Да]--> e1
g1 --[Нет]--> e2"""
        res = compile_dsl(dsl)
        self.assertTrue(res.get('valid'), f"Compilation failed: {res.get('error')}")
        xml = res.get('xml', '')
        self.assertIn('<laneSet id="LaneSet_1">', xml)
        self.assertIn('<lane id="hr"', xml)
        self.assertIn('<lane id="boss"', xml)
        self.assertIn('<participant id="p1"', xml)
        self.assertIn('id="hr_di"', xml)
        self.assertIn('id="boss_di"', xml)

        # Extract bounds and verify containment
        shape_pattern = r'<bpmndi:BPMNShape id="([^"]+)" bpmnElement="([^"]+)"[^>]*>\s*<dc:Bounds x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)"'
        shapes = {}
        for m in re.finditer(shape_pattern, xml):
            shapes[m.group(2)] = {
                'x': float(m.group(3)),
                'y': float(m.group(4)),
                'w': float(m.group(5)),
                'h': float(m.group(6)),
            }

        hr_lane = shapes['hr']
        boss_lane = shapes['boss']

        # Nodes assigned to hr lane must be within hr_lane Y bounds
        for node_id in ('s', 't1', 'e2'):
            node = shapes[node_id]
            self.assertGreaterEqual(node['y'], hr_lane['y'], f"Node {node_id} Y out of hr lane top")
            self.assertLessEqual(node['y'] + node['h'], hr_lane['y'] + hr_lane['h'], f"Node {node_id} out of hr lane bottom")

        # Nodes assigned to boss lane must be within boss_lane Y bounds
        for node_id in ('t2', 'g1', 'e1'):
            node = shapes[node_id]
            self.assertGreaterEqual(node['y'], boss_lane['y'], f"Node {node_id} Y out of boss lane top")
            self.assertLessEqual(node['y'] + node['h'], boss_lane['y'] + boss_lane['h'], f"Node {node_id} out of boss lane bottom")

    def test_compile_auto_synthesizes_lanes_from_performers(self):
        dsl = """process "Auto Lanes"
start: s "Старт"
task: t1 "Сформировать счет" user by "Менеджер"
task: t2 "Согласовать бюджет" user by "Директор"
end: e "Готово"
s -> t1 -> t2 -> e"""
        res = compile_dsl(dsl)
        self.assertTrue(res.get('valid'), f"Compilation failed: {res.get('error')}")
        xml = res.get('xml', '')
        self.assertIn('<laneSet id="LaneSet_1">', xml)
        self.assertIn('name="Менеджер"', xml)
        self.assertIn('name="Директор"', xml)

    def test_compile_rework_cycle(self):
        dsl = """process "Review"
pool: p "Компания"
lane: author "Автор" in p
lane: head "Руководитель" in p
start: s "Черновик" in author
task: t_write "Подготовить текст" user in author
task: t_check "Проверить текст" user in head
gate: g_ok "Согласовано?" in head
task: t_fix "Внести правки" user in author
end: e_done "Утверждено" in head
s -> t_write -> t_check -> g_ok
g_ok --[Да]--> e_done
g_ok --[На доработку]--> t_fix
t_fix -> t_check"""
        res = compile_dsl(dsl)
        self.assertTrue(res.get('valid'), f"Compilation failed: {res.get('error')}")
        xml = res.get('xml', '')
        self.assertIn('На доработку', xml)
        self.assertIn('t_fix', xml)

    def test_compile_disconnected_flow(self):
        dsl = """process "Logical Gap"
task: t1 "Шаг 1" user by "Менеджер"
task: t2 "Шаг 2 оторванный" user by "Директор" """
        res = compile_dsl(dsl)
        self.assertTrue(res.get('valid'), f"Compilation failed: {res.get('error')}")
        self.assertEqual(res.get('node_count'), 2)
        self.assertEqual(res.get('flow_count'), 0)

    def test_decompile_basic_process(self):
        dsl = """process "Simple Order"
start: s "Поступление заказа"
task: t1 "Проверка остатков" service
gateway: g1 "В наличии?" exclusive
end: e1 "Отгрузка"
end: e2 "Отказ"
s -> t1 -> g1
g1 --[Да]--> e1
g1 --[Нет]--> e2"""
        compile_res = compile_dsl(dsl)
        self.assertTrue(compile_res.get('valid'))
        xml = compile_res.get('xml', '')

        decompiled = decompile_bpmn_xml(xml)
        self.assertIn('process "Simple Order"', decompiled)
        self.assertIn('start: s "Поступление заказа"', decompiled)
        self.assertIn('task: t1 "Проверка остатков" service', decompiled)
        self.assertIn('gateway: g1 "В наличии?" exclusive', decompiled)
        self.assertIn('s -> t1', decompiled)
        self.assertIn('g1 --[Да]--> e1', decompiled)

    def test_decompile_pools_and_swimlanes(self):
        dsl = """process "Hiring"
pool: p1 "Компания"
lane: hr "HR" in p1
lane: it "IT" in p1
start: s "Резюме" in hr
task: t1 "Скрининг" user in hr
task: t2 "Тест код" user in it
end: e "Финал" in it
s -> t1 -> t2 -> e"""
        compile_res = compile_dsl(dsl)
        self.assertTrue(compile_res.get('valid'))
        xml = compile_res.get('xml', '')

        decompiled = decompile_bpmn_xml(xml)
        self.assertIn('pool: p1 "Компания"', decompiled)
        self.assertIn('lane: hr "HR" in p1', decompiled)
        self.assertIn('lane: it "IT" in p1', decompiled)
        self.assertIn('in hr', decompiled)
        self.assertIn('in it', decompiled)

    def test_bidirectional_roundtrip(self):
        original_dsl = """process "Roundtrip Test"
pool: p "Компания"
lane: sales "Продажи" in p
lane: legal "Юристы" in p
start: s "Заявка" in sales
task: t_draft "Подготовка договора" user in sales
task: t_check "Экспертиза" user in legal
gateway: g "Согласовано?" exclusive in legal
task: t_fix "Исправить замечания" user in sales
end: e_ok "Подписан" in sales
s -> t_draft -> t_check -> g
g --[Да]--> e_ok
g --[На доработку]--> t_fix
t_fix -> t_check"""
        # Step 1: DSL -> XML
        c1 = compile_dsl(original_dsl)
        self.assertTrue(c1.get('valid'))

        # Step 2: XML -> DSL (Decompile)
        decompiled_dsl = decompile_bpmn_xml(c1['xml'])
        self.assertIn('process "Roundtrip Test"', decompiled_dsl)

        # Step 3: Decompiled DSL -> XML (Re-compile)
        c2 = compile_dsl(decompiled_dsl)
        self.assertTrue(c2.get('valid'), f"Re-compilation failed: {c2.get('error')}")
        self.assertEqual(c1.get('node_count'), c2.get('node_count'))
        self.assertEqual(c1.get('flow_count'), c2.get('flow_count'))
