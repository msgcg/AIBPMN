import os
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.management import call_command
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError


DEFAULT_ADMIN_USERNAME = os.getenv('DJANGO_ADMIN_USERNAME', 'max')
DEFAULT_ADMIN_PASSWORD = os.getenv('DJANGO_ADMIN_PASSWORD', 'Admin2026!Bpmn')
DEFAULT_ADMIN_EMAIL = os.getenv('DJANGO_ADMIN_EMAIL', 'admin@aibpmn.local')

_bootstrapped_in_process = False


def ensure_default_admin(reset_password=False):
    """
    Гарантирует наличие в БД пользователя-администратора (и обычного пользователя) max
    с паролем Admin2026!Bpmn. Если таблицы еще не созданы — автоматически выполняет миграции.
    """
    try:
        table_names = connection.introspection.table_names()
        if 'auth_user' not in table_names:
            call_command('migrate', interactive=False, verbosity=0)
            table_names = connection.introspection.table_names()
            if 'auth_user' not in table_names:
                return None

        UserModel = get_user_model()
        user = UserModel._default_manager.filter(username__iexact=DEFAULT_ADMIN_USERNAME).first()
        if user is None:
            user = UserModel._default_manager.create_superuser(
                username=DEFAULT_ADMIN_USERNAME,
                email=DEFAULT_ADMIN_EMAIL,
                password=DEFAULT_ADMIN_PASSWORD,
            )
            return user

        changed = False
        if user.username != DEFAULT_ADMIN_USERNAME:
            user.username = DEFAULT_ADMIN_USERNAME
            changed = True
        if not user.is_staff:
            user.is_staff = True
            changed = True
        if not user.is_superuser:
            user.is_superuser = True
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if reset_password or not user.has_usable_password():
            if not user.check_password(DEFAULT_ADMIN_PASSWORD):
                user.set_password(DEFAULT_ADMIN_PASSWORD)
                changed = True

        if changed:
            user.save()
        return user
    except (OperationalError, ProgrammingError):
        return None
    except Exception:
        return None


class AutoBootstrapAdminMiddleware:
    """
    Однократно при первом HTTP-запросе проверяет наличие таблиц БД и дефолтного
    администратора `max`, автоматически создавая его, если БД новая или пустая.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        global _bootstrapped_in_process
        if not _bootstrapped_in_process or request.path.startswith('/admin'):
            ensure_default_admin(reset_password=False)
            _bootstrapped_in_process = True
        return self.get_response(request)


class AdminAutoCreateBackend(ModelBackend):
    """
    Кастомный бэкенд аутентификации:
    1. Автоматически создает/восстанавливает администратора `max` при входе в `/admin/` или `/`,
       даже если БД была пересоздана или пользователь был удален/изменен при отладке.
    2. Поддерживает регистронезависимый поиск логина (например, `max` и `Max`).
    3. Допускает случайные пробелы по краям пароля при копировании из документации.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or password is None:
            return None

        clean_username = username.strip()
        clean_password = password.strip()

        if clean_username.lower() == DEFAULT_ADMIN_USERNAME.lower():
            is_default_pwd = (password == DEFAULT_ADMIN_PASSWORD or clean_password == DEFAULT_ADMIN_PASSWORD)
            ensure_default_admin(reset_password=is_default_pwd)

        user = UserModel._default_manager.filter(username__iexact=clean_username).first()
        if user is None:
            UserModel().set_password(password)
            return None

        password_ok = user.check_password(password)
        if not password_ok and clean_password != password:
            password_ok = user.check_password(clean_password)

        if password_ok and self.user_can_authenticate(user):
            return user
        return None

