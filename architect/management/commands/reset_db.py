from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.admin.models import LogEntry
from django.contrib.sessions.models import Session
from architect.models import Project, Diagram, ChatMessage, KnowledgeBaseFile
from architect.backends import ensure_default_admin, DEFAULT_ADMIN_USERNAME


class Command(BaseCommand):
    help = "Очищает БД от отладочных данных и оставляет только чистого пользователя/администратора max (Admin2026!Bpmn)."

    def handle(self, *args, **options):
        UserModel = get_user_model()

        # Удаляем все проекты, диаграммы, сообщения, файлы БЗ, сессии и логи админки
        ChatMessage.objects.all().delete()
        Diagram.objects.all().delete()
        Project.objects.all().delete()
        KnowledgeBaseFile.objects.all().delete()
        Session.objects.all().delete()
        LogEntry.objects.all().delete()

        # Удаляем всех остальных пользователей кроме max
        UserModel.objects.exclude(username__iexact=DEFAULT_ADMIN_USERNAME).delete()

        # Гарантируем наличие чистого пользователя max с паролем Admin2026!Bpmn и правами администратора
        admin_user = ensure_default_admin(reset_password=True)
        if admin_user:
            admin_user.last_login = None
            admin_user.save(update_fields=['last_login'])

        self.stdout.write(
            self.style.SUCCESS(
                f"БД очищена. Оставлен только чистый пользователь/админ '{DEFAULT_ADMIN_USERNAME}' (пароль: Admin2026!Bpmn)."
            )
        )
