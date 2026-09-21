from django.test import TestCase, Client
from django.urls import reverse
from django.core.management import call_command
import tempfile
import os


class LegalPagesTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_terms_page(self):
        response = self.client.get('/terms/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'architect/terms.html')
        content = response.content.decode('utf-8')
        self.assertIn('Условия использования', content)
        self.assertIn('GPLv3', content)
        self.assertIn('GigaChat', content)
        self.assertIn('КАК ЕСТЬ', content)
        self.assertIn('Вернуться в редактор', content)

    def test_privacy_page(self):
        response = self.client.get('/privacy/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'architect/privacy.html')
        content = response.content.decode('utf-8')
        self.assertIn('Политика конфиденциальности', content)
        self.assertIn('sessionid', content)
        self.assertIn('csrftoken', content)
        self.assertIn('152-ФЗ', content)
        self.assertIn('Base64', content)
        self.assertIn('Вернуться в редактор', content)

    def test_links_present_on_index_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        # Sidebar footer links
        self.assertIn('sidebar-footer', content)
        self.assertIn('href="/terms/"', content)
        self.assertIn('href="/privacy/"', content)
        # Cookie banner links
        self.assertIn('cookie-legal-link', content)

    def test_sitemap_includes_legal_pages(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('/terms/</loc>', content)
        self.assertIn('/privacy/</loc>', content)

    def test_generate_seo_command_includes_legal_pages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            call_command('generate_seo', domain='https://aibpmn.example.com', outdir=tmpdir)
            sitemap_path = os.path.join(tmpdir, 'sitemap.xml')
            self.assertTrue(os.path.exists(sitemap_path))
            with open(sitemap_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn('https://aibpmn.example.com/terms/', content)
            self.assertIn('https://aibpmn.example.com/privacy/', content)

