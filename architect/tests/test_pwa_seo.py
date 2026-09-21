import json
import tempfile
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.management import call_command
from django.contrib import admin
from architect.models import Project, Diagram, ChatMessage, KnowledgeBaseFile

class PwaAndSeoTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_robots_txt(self):
        resp = self.client.get('/robots.txt')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/plain', resp.headers['Content-Type'])
        content = resp.content.decode('utf-8')
        self.assertIn('User-agent: *', content)
        self.assertIn('Allow: /', content)
        self.assertIn('Disallow: /api/', content)
        self.assertIn('Disallow: /admin/', content)
        self.assertIn('Sitemap:', content)
        self.assertIn('/sitemap.xml', content)

    def test_sitemap_xml(self):
        resp = self.client.get('/sitemap.xml')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('application/xml', resp.headers['Content-Type'])
        content = resp.content.decode('utf-8')
        self.assertIn('http://www.sitemaps.org/schemas/sitemap/0.9', content)
        self.assertIn('<loc>', content)
        self.assertIn('<priority>1.0</priority>', content)

    def test_service_worker_security_and_headers(self):
        resp = self.client.get('/sw.js')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('application/javascript', resp.headers['Content-Type'])
        self.assertEqual(resp.headers.get('Service-Worker-Allowed'), '/')
        content = resp.content.decode('utf-8')

        # Verify critical user constraint: NO path routing / route worker in SW, CSRF safe
        self.assertIn("request.method !== 'GET'", content)
        self.assertIn("request.mode === 'navigate'", content)
        self.assertIn("url.pathname.startsWith('/api/')", content)

    def test_manifest_json(self):
        resp = self.client.get('/manifest.json')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode('utf-8'))
        self.assertEqual(data.get('name'), 'AIBPMN Architect')
        self.assertEqual(data.get('short_name'), 'AIBPMN')
        self.assertEqual(data.get('display'), 'standalone')
        self.assertTrue(len(data.get('icons', [])) >= 2)

    def test_favicon_ico(self):
        resp = self.client.get('/favicon.ico')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get('Content-Type'), 'image/x-icon')
        self.assertTrue(len(resp.content) > 0)

    def test_generate_seo_command(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            call_command('generate_seo', domain='https://example.com', outdir=tmp_dir)
            import os
            self.assertTrue(os.path.exists(os.path.join(tmp_dir, 'robots.txt')))
            self.assertTrue(os.path.exists(os.path.join(tmp_dir, 'sitemap.xml')))
            with open(os.path.join(tmp_dir, 'robots.txt'), 'r', encoding='utf-8') as f:
                self.assertIn('https://example.com/sitemap.xml', f.read())

    def test_admin_site_models_registered(self):
        self.assertIn(Project, admin.site._registry)
        self.assertIn(Diagram, admin.site._registry)
        self.assertIn(ChatMessage, admin.site._registry)
        self.assertIn(KnowledgeBaseFile, admin.site._registry)
        self.assertEqual(admin.site.site_header, "AIBPMN Architect — Панель управления")

    def test_root_user_max_created(self):
        # Verify root user max exists with superuser privileges
        max_user = User.objects.filter(username='max').first()
        self.assertIsNotNone(max_user)
        self.assertTrue(max_user.is_staff)
        self.assertTrue(max_user.is_superuser)
        self.assertTrue(max_user.check_password('Admin2026!Bpmn'))

