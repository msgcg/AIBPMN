from django.test import TestCase
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from architect.models import KnowledgeBaseFile
from architect.services.knowledge_base import (
    list_kb_files,
    read_kb_file,
    write_kb_file,
    delete_kb_file,
    process_uploaded_kb_file,
    compose_system_prompt
)

class KnowledgeBaseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="kb_tester", password="Password123!")

    def test_guest_and_user_list_files(self):
        # Guest gets empty list (no persistence)
        guest_files = list_kb_files()
        self.assertEqual(len(guest_files), 0)

        # Authenticated user gets seeded files
        user_files = list_kb_files(user=self.user)
        self.assertGreater(len(user_files), 0)
        first = user_files[0]['name']
        content = read_kb_file(first, user=self.user)
        self.assertTrue(len(content) > 0)

    def test_compose_system_prompt(self):
        # Both guest and user get valid prompt with knowledge base content
        prompt = compose_system_prompt()
        self.assertIn("Главный Архитектор бизнес-процессов", prompt)
        self.assertIn("BPMN-as-Code", prompt)
        self.assertIn("БАЗА ЗНАНИЙ:", prompt)

    def test_write_and_delete_file(self):
        test_filename = "99_temp_test.md"
        write_kb_file(test_filename, "# Test file content", user=self.user)
        content = read_kb_file(test_filename, user=self.user)
        self.assertEqual(content, "# Test file content")

        deleted = delete_kb_file(test_filename, user=self.user)
        self.assertTrue(deleted)
        with self.assertRaises(FileNotFoundError):
            read_kb_file(test_filename, user=self.user)

    def test_guest_write_rejected(self):
        with self.assertRaises(PermissionError):
            write_kb_file("unauth.md", "content", user=None)

    def test_user_isolation(self):
        user_a = User.objects.create_user(username="user_a", password="Password123!")
        user_b = User.objects.create_user(username="user_b", password="Password123!")

        write_kb_file("private_doc_a.md", "# User A Private Doc", user=user_a)
        write_kb_file("private_doc_b.md", "# User B Private Doc", user=user_b)

        files_a = [f['name'] for f in list_kb_files(user=user_a)]
        files_b = [f['name'] for f in list_kb_files(user=user_b)]

        self.assertIn("private_doc_a.md", files_a)
        self.assertNotIn("private_doc_b.md", files_a)

        self.assertIn("private_doc_b.md", files_b)
        self.assertNotIn("private_doc_a.md", files_b)

    def test_base64_db_storage(self):
        user = User.objects.create_user(username="db_user", password="Password123!")
        write_kb_file("encoded_note.md", "Secret information 12345", user=user)

        db_record = KnowledgeBaseFile.objects.get(user=user, name="encoded_note.md")
        self.assertTrue(len(db_record.content_base64) > 0)
        # Verify decoding matches original
        self.assertEqual(db_record.get_text_content(), "Secret information 12345")

    def test_upload_blacklist_rejects_archives_and_binaries(self):
        for bad_name in ["archive.zip", "data.rar", "backup.7z", "tool.exe", "script.bat"]:
            bad_file = SimpleUploadedFile(bad_name, b"dummy content", content_type="application/octet-stream")
            with self.assertRaises(ValueError) as ctx:
                process_uploaded_kb_file(bad_file, user=self.user)
            self.assertIn("запрещены", str(ctx.exception))

    def test_upload_size_limit(self):
        # 11MB file (exceeds 10MB limit)
        large_content = b"0" * (11 * 1024 * 1024)
        large_file = SimpleUploadedFile("huge.txt", large_content, content_type="text/plain")
        with self.assertRaises(ValueError) as ctx:
            process_uploaded_kb_file(large_file, user=self.user)
        self.assertIn("допустимый лимит", str(ctx.exception))


