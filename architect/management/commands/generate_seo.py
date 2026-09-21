import os
import datetime
from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    help = "Автогенерация статических файлов robots.txt и sitemap.xml для поисковых систем."

    def add_arguments(self, parser):
        parser.add_argument(
            '--domain',
            type=str,
            default='https://aibpmn.ru',
            help='Базовый домен сайта с протоколом (например: https://aibpmn.ru)'
        )
        parser.add_argument(
            '--outdir',
            type=str,
            default=None,
            help='Целевая папка для сохранения файлов (по умолчанию: корень static_collected или static)'
        )

    def handle(self, *args, **options):
        domain = options['domain'].rstrip('/')
        outdir = options['outdir']
        
        if not outdir:
            outdir = getattr(settings, 'STATIC_ROOT', None) or os.path.join(settings.BASE_DIR, 'architect', 'static')
        
        os.makedirs(outdir, exist_ok=True)
        today_str = datetime.date.today().isoformat()

        # 1. Генерация robots.txt
        robots_content = (
            "User-agent: *\n"
            "Allow: /\n"
            "Disallow: /api/\n"
            "Disallow: /admin/\n"
            "\n"
            f"Sitemap: {domain}/sitemap.xml\n"
        )
        robots_path = os.path.join(outdir, 'robots.txt')
        with open(robots_path, 'w', encoding='utf-8') as f:
            f.write(robots_content)
        self.stdout.write(self.style.SUCCESS(f"[OK] Сгенерирован {robots_path}"))

        # 2. Генерация sitemap.xml
        sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{domain}/</loc>
    <lastmod>{today_str}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>{domain}/terms/</loc>
    <lastmod>{today_str}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.5</priority>
  </url>
  <url>
    <loc>{domain}/privacy/</loc>
    <lastmod>{today_str}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.5</priority>
  </url>
  <url>
    <loc>{domain}/robots.txt</loc>
    <lastmod>{today_str}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.3</priority>
  </url>
</urlset>"""
        sitemap_path = os.path.join(outdir, 'sitemap.xml')
        with open(sitemap_path, 'w', encoding='utf-8') as f:
            f.write(sitemap_content)
        self.stdout.write(self.style.SUCCESS(f"[OK] Сгенерирован {sitemap_path}"))
        self.stdout.write(self.style.SUCCESS(f"SEO-файлы успешно созданы для домена {domain}"))

