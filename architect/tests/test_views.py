import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from architect.models import Project, Diagram, ChatMessage
from architect.services.knowledge_base import delete_kb_file

class ArchitectViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="Password123!")
        self.client = Client()
        self.client.force_login(self.user)
        self.guest_client = Client()

        self.project = Project.objects.create(user=self.user, name="Тестовый проект", description="Описание")
        self.diagram = Diagram.objects.create(
            project=self.project,
            name="Тестовая диаграмма",
            dsl_code='process "Тест"\nstart: s "Начало"\nend: e "Конец"\ns -> e'
        )
        self.msg1 = ChatMessage.objects.create(
            diagram=self.diagram,
            role="user",
            content="Создай процесс"
        )
        self.msg2 = ChatMessage.objects.create(
            diagram=self.diagram,
            role="assistant",
            content="Процесс готов",
            dsl_code=self.diagram.dsl_code
        )

    def test_index_view_authenticated(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "BPMN Architect")
        self.assertContains(resp, "testuser")

    def test_index_view_guest_ephemeral(self):
        resp = self.guest_client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "BPMN Architect")
        self.assertContains(resp, "Без сохранения")
        # Ensure zero unauthenticated projects in DB
        self.assertEqual(Project.objects.filter(user__isnull=True).count(), 0)

    def test_guest_rejections_require_auth(self):
        # Create project rejected
        resp_p = self.guest_client.post(
            '/api/projects/',
            data=json.dumps({'name': 'Гостевой проект'}),
            content_type='application/json'
        )
        self.assertEqual(resp_p.status_code, 401)
        self.assertTrue(resp_p.json().get('auth_required'))

        # Create diagram rejected
        resp_d = self.guest_client.post(
            '/api/diagrams/',
            data=json.dumps({'name': 'Гостевая схема'}),
            content_type='application/json'
        )
        self.assertEqual(resp_d.status_code, 401)
        self.assertTrue(resp_d.json().get('auth_required'))

        # KB upload rejected
        test_file = SimpleUploadedFile("doc.txt", b"text", content_type="text/plain")
        resp_kb = self.guest_client.post('/api/kb/upload/', {'file': test_file})
        self.assertEqual(resp_kb.status_code, 401)
        self.assertTrue(resp_kb.json().get('auth_required'))

    def test_guest_generate_in_memory_no_db_persistence(self):
        from unittest.mock import patch
        with patch('architect.services.gigachat_client.GigaChatService.generate_diagram') as mock_gen:
            mock_gen.return_value = {
                'success': True,
                'has_dsl': True,
                'dsl_code': 'process "Гость"\nstart: s "С"\nend: e "К"\ns -> e',
                'explanation': 'Построено в памяти',
                'bpmn_xml': '<xml></xml>',
                'attempts': 1
            }
            initial_diags = Diagram.objects.count()
            initial_msgs = ChatMessage.objects.count()

            resp = self.guest_client.post(
                '/api/generate/',
                data=json.dumps({'prompt': 'Построй процесс согласования'}),
                content_type='application/json'
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data['success'])
            self.assertTrue(data.get('guest_mode'))
            self.assertEqual(data['diagram']['id'], 0)
            # Verify ZERO records were written to SQLite!
            self.assertEqual(Diagram.objects.count(), initial_diags)
            self.assertEqual(ChatMessage.objects.count(), initial_msgs)

    def test_projects_api(self):
        # List
        resp = self.client.get('/api/projects/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['projects']), 1)

        # Create
        resp = self.client.post(
            '/api/projects/',
            data=json.dumps({'name': 'Второй проект', 'description': 'Новый'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Project.objects.filter(user=self.user).count(), 2)

    def test_diagrams_api(self):
        resp = self.client.get(f'/api/diagrams/?project_id={self.project.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['diagrams']), 1)

    def test_delete_single_message(self):
        resp = self.client.delete(
            f'/api/diagrams/{self.diagram.id}/messages/',
            data=json.dumps({'message_id': self.msg1.id}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.diagram.messages.count(), 1)

    def test_delete_bulk_messages(self):
        msg3 = ChatMessage.objects.create(
            diagram=self.diagram,
            role="user",
            content="Сообщение 3"
        )
        resp = self.client.delete(
            f'/api/diagrams/{self.diagram.id}/messages/',
            data=json.dumps({'message_ids': [self.msg1.id, msg3.id]}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ChatMessage.objects.filter(id=self.msg1.id).exists())
        self.assertFalse(ChatMessage.objects.filter(id=msg3.id).exists())
        self.assertTrue(ChatMessage.objects.filter(id=self.msg2.id).exists())

    def test_clear_all_messages(self):
        resp = self.client.delete(
            f'/api/diagrams/{self.diagram.id}/messages/',
            data=json.dumps({'clear_all': True}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.diagram.messages.count(), 0)

    def test_api_compile(self):
        resp = self.client.post(
            '/api/compile/',
            data=json.dumps({'dsl_code': 'process "A"\nstart: s "S"\nend: e "E"\ns -> e'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['valid'])

    def test_project_create_creates_diagram_and_chat(self):
        resp = self.client.post(
            '/api/projects/',
            data=json.dumps({'name': 'Проект с автогенерацией'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        proj_id = data['project']['id']
        proj = Project.objects.get(id=proj_id)
        # Verify diagram was automatically created
        self.assertEqual(proj.diagrams.count(), 1)
        diag = proj.diagrams.first()
        self.assertEqual(diag.name, "Новый процесс")
        # Verify initial greeting message was created
        self.assertEqual(diag.messages.count(), 1)
        msg = diag.messages.first()
        self.assertEqual(msg.role, 'assistant')
        self.assertIn("успешно создан", msg.content)

    def test_api_kb_upload_success(self):
        txt_content = b"Some test guidelines for BPMN"
        test_file = SimpleUploadedFile("custom_policy.txt", txt_content, content_type="text/plain")
        resp = self.client.post('/api/kb/upload/', {'file': test_file})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['file']['name'], 'custom_policy.md')
        # Clean up
        delete_kb_file('custom_policy.md', user=self.user)

    def test_api_kb_upload_forbidden_extension(self):
        exe_file = SimpleUploadedFile("malware.exe", b"binary content", content_type="application/octet-stream")
        resp = self.client.post('/api/kb/upload/', {'file': exe_file})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn("запрещены", data['error'])

    def test_api_refine_persists_user_dsl(self):
        from unittest.mock import patch
        new_dsl = 'process "Пользовательские правки"\nstart: s "Старт"\ntask: t1 "Моя задача"\nend: e "Конец"\ns -> t1 -> e'
        with patch('architect.services.gigachat_client.GigaChatService.refine_diagram') as mock_refine:
            mock_refine.return_value = {
                'success': True,
                'dsl_code': new_dsl,
                'explanation': 'Доработка учтена',
                'bpmn_xml': '<xml></xml>',
                'node_count': 3,
                'flow_count': 2,
                'attempts': 1
            }
            resp = self.client.post(
                '/api/refine/',
                data=json.dumps({
                    'diagram_id': self.diagram.id,
                    'instruction': 'Добавь задачу',
                    'current_dsl': new_dsl
                }),
                content_type='application/json'
            )
            self.assertEqual(resp.status_code, 200)
            # Verify diagram in database was updated with user's dsl
            self.diagram.refresh_from_db()
            self.assertIn('Моя задача', self.diagram.dsl_code)
            mock_refine.assert_called_once()
            call_kwargs = mock_refine.call_args[1]
            self.assertEqual(call_kwargs['current_dsl'], new_dsl)

    def test_api_refine_consultative_qa_does_not_overwrite_diagram(self):
        from unittest.mock import patch
        original_dsl = self.diagram.dsl_code
        explanation_text = "В вашей схеме 2 узла: Начало и Конец. Связь прямая."
        with patch('architect.services.gigachat_client.GigaChatService.refine_diagram') as mock_refine:
            mock_refine.return_value = {
                'success': True,
                'has_dsl': False,
                'dsl_code': None,
                'explanation': explanation_text,
                'content': explanation_text,
                'bpmn_xml': None,
                'attempts': 1
            }
            resp = self.client.post(
                '/api/refine/',
                data=json.dumps({
                    'diagram_id': self.diagram.id,
                    'instruction': 'Объясни, как работает этот процесс'
                }),
                content_type='application/json'
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data['success'])
            self.assertFalse(data['has_dsl'])
            self.assertIsNone(data['dsl_code'])
            self.assertEqual(data['assistant_message']['content'], explanation_text)
            # Verify diagram DSL code remained untouched in database
            self.diagram.refresh_from_db()
            self.assertEqual(self.diagram.dsl_code, original_dsl)

    def test_api_generate_with_attached_md_file_and_prompt(self):
        from unittest.mock import patch
        md_content = b"# Process Rules\n1. Check balance\n2. Transfer funds"
        uploaded_file = SimpleUploadedFile("rules.md", md_content, content_type="text/markdown")

        with patch('architect.services.gigachat_client.GigaChatService.generate_diagram') as mock_gen:
            mock_gen.return_value = {
                'success': True,
                'has_dsl': True,
                'dsl_code': 'process "Rules"\nstart: s "Начало"\nend: e "Конец"\ns -> e',
                'explanation': 'Построено по правилам',
                'bpmn_xml': '<xml></xml>',
                'attempts': 1
            }
            resp = self.client.post('/api/generate/', {
                'project_id': self.project.id,
                'prompt': 'Построй процесс по правилам',
                'attached_file': uploaded_file
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data['success'])

            mock_gen.assert_called_once()
            called_prompt = mock_gen.call_args[1]['prompt']
            self.assertIn('Построй процесс по правилам', called_prompt)
            self.assertIn('📎 **Прикрепленный документ: `rules.md`**', called_prompt)
            self.assertIn('# Process Rules', called_prompt)

            # Check message in DB
            last_msg = ChatMessage.objects.filter(role='user').last()
            self.assertIn('Построй процесс по правилам', last_msg.content)
            self.assertIn('rules.md', last_msg.content)

    def test_api_generate_with_attached_md_file_only_empty_prompt(self):
        from unittest.mock import patch
        md_content = b"# Only document content"
        uploaded_file = SimpleUploadedFile("doc.md", md_content, content_type="text/markdown")

        with patch('architect.services.gigachat_client.GigaChatService.generate_diagram') as mock_gen:
            mock_gen.return_value = {
                'success': True,
                'has_dsl': True,
                'dsl_code': 'process "Doc"\nstart: s "Начало"\nend: e "Конец"\ns -> e',
                'explanation': 'Построено только по документу',
                'bpmn_xml': '<xml></xml>',
                'attempts': 1
            }
            resp = self.client.post('/api/generate/', {
                'project_id': self.project.id,
                'prompt': '   ',
                'attached_file': uploaded_file
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data['success'])

            mock_gen.assert_called_once()
            called_prompt = mock_gen.call_args[1]['prompt']
            self.assertIn('Построй процесс на основе прикрепленного документа', called_prompt)
            self.assertIn('# Only document content', called_prompt)

    def test_api_generate_with_invalid_file_extension_rejected(self):
        invalid_file = SimpleUploadedFile("script.py", b"print('hello')", content_type="text/x-python")
        resp = self.client.post('/api/generate/', {
            'project_id': self.project.id,
            'prompt': 'Построй процесс',
            'attached_file': invalid_file
        })
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn('Недопустимый формат файла', data['error'])
        self.assertIn('.md', data['error'])

    def test_api_generate_with_oversized_file_rejected(self):
        # 2MB + 10 bytes
        large_bytes = b'a' * (2 * 1024 * 1024 + 10)
        large_file = SimpleUploadedFile("huge.md", large_bytes, content_type="text/markdown")
        resp = self.client.post('/api/generate/', {
            'project_id': self.project.id,
            'prompt': 'Построй процесс',
            'attached_file': large_file
        })
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn('превышает допустимый лимит', data['error'])

    def test_api_generate_with_binary_content_rejected(self):
        binary_data = b'text\x00binary'
        bin_file = SimpleUploadedFile("fake.md", binary_data, content_type="text/markdown")
        resp = self.client.post('/api/generate/', {
            'project_id': self.project.id,
            'prompt': 'Построй процесс',
            'attached_file': bin_file
        })
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn('бинарные данные', data['error'])

    def test_api_refine_with_attached_md_file(self):
        from unittest.mock import patch
        md_content = b"# Extra Requirements\nAdd security gateway."
        uploaded_file = SimpleUploadedFile("extra.md", md_content, content_type="text/markdown")

        with patch('architect.services.gigachat_client.GigaChatService.refine_diagram') as mock_refine:
            mock_refine.return_value = {
                'success': True,
                'has_dsl': True,
                'dsl_code': 'process "Refined"\nstart: s "Начало"\nend: e "Конец"\ns -> e',
                'explanation': 'Добавлена проверка',
                'bpmn_xml': '<xml></xml>',
                'attempts': 1
            }
            resp = self.client.post('/api/refine/', {
                'diagram_id': self.diagram.id,
                'instruction': 'Дополни схему',
                'attached_file': uploaded_file
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data['success'])

            mock_refine.assert_called_once()
            called_instruction = mock_refine.call_args[1]['instruction']
            self.assertIn('Дополни схему', called_instruction)
            self.assertIn('📎 **Прикрепленный документ: `extra.md`**', called_instruction)
            self.assertIn('# Extra Requirements', called_instruction)





