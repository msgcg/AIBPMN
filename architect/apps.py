from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _on_post_migrate(sender, **kwargs):
    from .backends import ensure_default_admin
    ensure_default_admin(reset_password=False)


class ArchitectConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'architect'
    verbose_name = 'BPMN Архитектор'

    def ready(self):
        post_migrate.connect(_on_post_migrate, sender=self)

