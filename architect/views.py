import os
import re
import json
import datetime
import urllib.parse
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.http import JsonResponse, HttpResponse, HttpResponseNotFound
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from .models import Project, Diagram, ChatMessage, KnowledgeBaseFile, UserGigaChatCredential
from .services.gigachat_client import GigaChatService, GigaChatAuthError
from .services.compiler_service import compile_dsl, decompile_bpmn_xml
from .services.knowledge_base import (
    list_kb_files,
    read_kb_file,
    write_kb_file,
    delete_kb_file,
    process_uploaded_kb_file,
    compose_system_prompt,
    seed_user_knowledge_base
)
from .services.process_analyzer import (
    parse_dsl_structure,
    analyze_process_metrics,
    generate_validation_report,
    generate_proactive_questions,
    extract_traceability,
)

GIGACHAT_COOKIE_KEY = 'aibpmn_gigachat_key'
GIGACHAT_COOKIE_SCOPE = 'aibpmn_gigachat_scope'
GIGACHAT_COOKIE_MAX_AGE = 60 * 60 * 24 * 90  # 90 дней


def normalize_gigachat_key(raw_key: str) -> str:
    val = (raw_key or '').strip().strip('"').strip("'")
    if val.lower().startswith('basic '):
        val = val[6:].strip()
    return val


def mask_gigachat_key(key: str) -> str:
    val = (key or '').strip()
    if not val:
        return ''
    if len(val) <= 12:
        return '*' * len(val)
    return f"{val[:6]}...{val[-4:]}"


def resolve_request_gigachat_credentials(request, data=None) -> tuple[str, str, str]:
    """
    Определяет ключ авторизации и Scope для текущего запроса:
    - Для авторизованного пользователя: берет из БД (UserGigaChatCredential). Если в БД пусто, но есть гостевая cookie, переносит в БД.
    - Для гостя: берет из cookie браузера (aibpmn_gigachat_key).
    Возвращает кортеж: (auth_key, scope, storage_mode), где storage_mode in ('db', 'cookie').
    """
    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    default_scope = getattr(settings, 'GIGACHAT_DEFAULT_SCOPE', 'GIGACHAT_API_PERS')

    explicit_key = normalize_gigachat_key((data or {}).get('gigachat_auth_key', '') or '')
    explicit_scope = ((data or {}).get('gigachat_scope', '') or '').strip()

    raw_cookie_key = request.COOKIES.get(GIGACHAT_COOKIE_KEY, '') if hasattr(request, 'COOKIES') else ''
    raw_cookie_scope = request.COOKIES.get(GIGACHAT_COOKIE_SCOPE, '') if hasattr(request, 'COOKIES') else ''
    cookie_key = normalize_gigachat_key(urllib.parse.unquote(raw_cookie_key or ''))
    cookie_scope = urllib.parse.unquote(raw_cookie_scope or '').strip() or default_scope

    if user:
        cred = UserGigaChatCredential.objects.filter(user=user).first()
        if explicit_key:
            scope_val = explicit_scope or (cred.scope if cred else default_scope)
            cred, _ = UserGigaChatCredential.objects.update_or_create(
                user=user,
                defaults={'auth_key': explicit_key, 'scope': scope_val}
            )
            return cred.auth_key.strip(), cred.scope, 'db'

        if cred and cred.auth_key.strip():
            return cred.auth_key.strip(), (cred.scope or default_scope), 'db'

        if cookie_key:
            cred, _ = UserGigaChatCredential.objects.update_or_create(
                user=user,
                defaults={'auth_key': cookie_key, 'scope': cookie_scope}
            )
            return cred.auth_key.strip(), cred.scope, 'db'

        return '', default_scope, 'db'

    key_val = explicit_key or cookie_key
    scope_val = explicit_scope or cookie_scope or default_scope
    return key_val, scope_val, 'cookie'


INITIAL_DEMO_DSL = """process "Согласование командировки"

pool: p_corp "Организация"
lane: l_employee "Сотрудник" in p_corp
lane: l_manager "Руководитель отдела" in p_corp
lane: l_fin "Бухгалтерия и финансы" in p_corp

start: s_req "Подать заявку на командировку" in l_employee
task: t_check "Проверить лимит бюджета" service in l_manager
gateway: g_budget "В рамках бюджета?" exclusive in l_manager

task: t_review "Согласование руководителем" user in l_manager
gateway: g_manager "Решение руководителя" exclusive in l_manager
task: t_rework "Доработать параметры поездки" user in l_employee

task: t_booking "Бронирование билетов и выплата суточных" service in l_fin

end: e_approved "Командировка согласована" in l_fin
end: e_rejected "Заявка отклонена" in l_manager

s_req -> t_check -> g_budget
g_budget --[В лимите]--> t_review -> g_manager
g_budget --[Превышен]--> e_rejected

g_manager --[Одобрено]--> t_booking -> e_approved
g_manager --[На доработку]--> t_rework
t_rework -> t_review
g_manager --[Отклонено]--> e_rejected"""


def validate_username_and_password(username, password, password_confirm=None, is_registration=True):
    """
    Validates username and password according to strict rules:
    - Username: English letters, digits, and . _ - only (3-30 chars, at least one letter).
    - Password: English characters only (ASCII), length >= 8.
    - Password complexity: >=1 uppercase (A-Z), >=1 lowercase (a-z), >=1 digit (0-9), >=1 special char.
    - Password must NOT equal username, and must NOT contain username.
    """
    if not username or not username.strip():
        return False, "Логин не может быть пустым."
    username = username.strip()

    if not re.match(r'^[a-zA-Z0-9_.-]+$', username):
        return False, "Логин может содержать только английские буквы, цифры и знаки _ . - (без пробелов и кириллицы)."

    if not re.search(r'[a-zA-Z]', username):
        return False, "Логин должен содержать хотя бы одну английскую букву."

    if len(username) < 3 or len(username) > 30:
        return False, "Длина логина должна быть от 3 до 30 символов."

    if is_registration:
        if User.objects.filter(username__iexact=username).exists():
            return False, "Пользователь с таким логином уже существует."

    if not password:
        return False, "Пароль не может быть пустым."

    if not re.match(r'^[a-zA-Z0-9!@#$%^&*()_+\-=\[\]{}|;:\'",./<>?~` ]+$', password):
        return False, "Пароль должен состоять только из английских символов, цифр и спецсимволов."

    if len(password) < 8:
        return False, "Длина пароля должна быть не менее 8 символов."

    if not re.search(r'[A-Z]', password):
        return False, "Пароль должен содержать хотя бы одну заглавную английскую букву (A-Z)."

    if not re.search(r'[a-z]', password):
        return False, "Пароль должен содержать хотя бы одну строчную английскую букву (a-z)."

    if not re.search(r'[0-9]', password):
        return False, "Пароль должен содержать хотя бы одну цифру (0-9)."

    if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:\'",./<>?~` ]', password):
        return False, "Пароль должен содержать хотя бы один специальный символ (!@#$%^&* и др.)."

    if password.lower() == username.lower():
        return False, "Пароль не должен совпадать с логином."

    if username.lower() in password.lower():
        return False, "Пароль не должен содержать в себе логин."

    if is_registration and password_confirm is not None:
        if password != password_confirm:
            return False, "Введенные пароли не совпадают."

    return True, ""


def create_default_project_for_user(user=None, project_name="Основной проект"):
    """
    Creates an initial starter project and diagram for a user or guest.
    """
    project = Project.objects.create(
        user=user,
        name=project_name,
        description="Проект по умолчанию для моделирования бизнес-процессов"
    )
    compile_res = compile_dsl(INITIAL_DEMO_DSL)
    diagram = Diagram.objects.create(
        project=project,
        name="Согласование командировки",
        description="Пример процесса согласования командировки и выплаты суточных",
        dsl_code=INITIAL_DEMO_DSL,
        bpmn_xml=compile_res.get('xml', '')
    )
    ChatMessage.objects.create(
        diagram=diagram,
        role="assistant",
        content="Добро пожаловать в Архитектор BPMN-диаграмм! Я готов построить любую схему процесса по вашему описанию.",
        dsl_code=INITIAL_DEMO_DSL,
        explanation="В демонстрационном процессе показаны: стартовое событие, проверка лимитов, двухуровневое согласование, параллельное оформление билетов и начисление суточных, а также разделение исходов."
    )
    return project, diagram


def index_view(request):
    """
    Main single-page IDE view.
    Ensures user-specific projects and diagrams are served.
    Unauthenticated guests work in an ephemeral in-memory environment without DB writes.
    """
    user = request.user if request.user.is_authenticated else None

    # For guests: clean up any legacy unassociated DB records and return ephemeral demo
    if not user:
        Project.objects.filter(user__isnull=True).delete()
        KnowledgeBaseFile.objects.filter(user__isnull=True).delete()

        demo_diagram = {
            'id': 0,
            'name': 'Согласование командировки',
            'description': 'Пример процесса согласования командировки и выплаты суточных',
            'dsl_code': INITIAL_DEMO_DSL,
            'bpmn_xml': '',
            'svg_preview': '',
            'created_at': '',
            'updated_at': '',
            'project_id': 0,
        }
        demo_project = {
            'id': 0,
            'name': 'Демонстрационный проект',
            'description': 'Гостевой режим (без сохранения в базе данных)',
            'created_at': '',
            'updated_at': '',
            'diagrams': [demo_diagram]
        }
        initial_greeting = {
            'id': 0,
            'role': 'assistant',
            'content': 'Добро пожаловать в Архитектор BPMN-диаграмм! Вы работаете в гостевом режиме (без сохранения истории и базы знаний). Для сохранения проектов и создания файлов зарегистрируйтесь или войдите.',
            'dsl_code': INITIAL_DEMO_DSL,
            'explanation': 'В демонстрационном процессе показаны: стартовое событие, проверка лимитов, двухуровневое согласование, параллельное оформление билетов и начисление суточных.',
            'created_at': '',
            'is_error': False
        }
        auth_key, scope, storage_mode = resolve_request_gigachat_credentials(request)
        model_name = getattr(settings, 'GIGACHAT_MODEL', 'GigaChat-3-Ultra')
        status_info = {
            'ok': bool(auth_key),
            'key_configured': bool(auth_key),
            'key_required': not bool(auth_key),
            'storage_mode': storage_mode,
            'scope': scope,
            'masked_key': mask_gigachat_key(auth_key),
            'model': model_name,
            'message': f'Модель {model_name} готова' if auth_key else 'Настройте ключ GigaChat API'
        }
        context = {
            'current_project': demo_project,
            'current_diagram': demo_diagram,
            'projects': [demo_project],
            'status_info': status_info,
            'has_gigachat_key': bool(auth_key),
            'gigachat_scope': scope,
            'gigachat_masked_key': mask_gigachat_key(auth_key),
            'kb_files': [],
            'user': request.user,
            'initial_messages': [initial_greeting],
        }
        return render(request, 'architect/index.html', context)

    project_id = request.GET.get('project')
    diagram_id = request.GET.get('diagram')

    # Resolve project for authenticated user
    project = None
    if project_id:
        try:
            project = Project.objects.filter(user=user, id=int(project_id)).first()
        except (ValueError, TypeError):
            project = None

    if not project:
        project = Project.objects.filter(user=user).first()

    if not project:
        project, _ = create_default_project_for_user(user=user, project_name="Основной проект")

    # Resolve diagram
    diagram = None
    if diagram_id:
        try:
            diagram = project.diagrams.filter(id=int(diagram_id)).first()
        except (ValueError, TypeError):
            diagram = None

    if not diagram:
        diagram = project.diagrams.first()

    if not diagram:
        compile_res = compile_dsl(INITIAL_DEMO_DSL)
        diagram = Diagram.objects.create(
            project=project,
            name="Согласование командировки",
            description="Пример процесса согласования командировки и выплаты суточных",
            dsl_code=INITIAL_DEMO_DSL,
            bpmn_xml=compile_res.get('xml', '')
        )
        ChatMessage.objects.create(
            diagram=diagram,
            role="assistant",
            content="Добро пожаловать в Архитектор BPMN-диаграмм! Я готов построить любую схему процесса по вашему описанию.",
            dsl_code=INITIAL_DEMO_DSL,
            explanation="В демонстрационном процессе показаны: стартовое событие, проверка лимитов, двухуровневое согласование, параллельное оформление билетов и начисление суточных, а также разделение исходов."
        )

    # Build full project tree
    projects = []
    for p in Project.objects.filter(user=user).prefetch_related('diagrams').all():
        p_dict = p.to_dict()
        p_dict['diagrams'] = [d.to_dict() for d in p.diagrams.all()]
        projects.append(p_dict)

    auth_key, scope, storage_mode = resolve_request_gigachat_credentials(request)
    model_name = getattr(settings, 'GIGACHAT_MODEL', 'GigaChat-3-Ultra')
    status_info = {
        'ok': bool(auth_key),
        'key_configured': bool(auth_key),
        'key_required': not bool(auth_key),
        'storage_mode': storage_mode,
        'scope': scope,
        'masked_key': mask_gigachat_key(auth_key),
        'model': model_name,
        'message': f'Модель {model_name} готова' if auth_key else 'Настройте ключ GigaChat API'
    }
    kb_files = list_kb_files(user=user)
    initial_messages = [m.to_dict() for m in diagram.messages.order_by('created_at')]

    context = {
        'current_project': project,
        'current_diagram': diagram,
        'projects': projects,
        'status_info': status_info,
        'has_gigachat_key': bool(auth_key),
        'gigachat_scope': scope,
        'gigachat_masked_key': mask_gigachat_key(auth_key),
        'kb_files': kb_files,
        'user': request.user,
        'initial_messages': initial_messages,
    }
    return render(request, 'architect/index.html', context)


# ─── GigaChat Status & Interactive Key API ─────────────────────────────────

def api_status(request):
    user = request.user if request.user.is_authenticated else None
    auth_key, scope, storage_mode = resolve_request_gigachat_credentials(request)
    status = GigaChatService.check_status(auth_key=auth_key, scope=scope, user=user)
    status['storage_mode'] = storage_mode
    status['masked_key'] = mask_gigachat_key(auth_key)
    return JsonResponse(status)


@csrf_exempt
def api_gigachat_key(request):
    """
    Управление авторизационными данными Сбер GigaChat API:
    - GET: возвращает статус наличия ключа, маску, scope и режим хранения ('db' для пользователей, 'cookie' для гостей)
    - POST: сохраняет ключ (в БД для авторизованного пользователя, либо в cookie для гостя)
    - DELETE: удаляет сохраненный ключ из БД и/или cookie
    """
    user = request.user if request.user.is_authenticated else None
    default_scope = getattr(settings, 'GIGACHAT_DEFAULT_SCOPE', 'GIGACHAT_API_PERS')

    if request.method == 'GET':
        auth_key, scope, storage_mode = resolve_request_gigachat_credentials(request)
        return JsonResponse({
            'success': True,
            'has_key': bool(auth_key),
            'masked_key': mask_gigachat_key(auth_key),
            'scope': scope,
            'storage': storage_mode,
            'storage_mode': storage_mode,
        })

    elif request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8')) if request.body else {}
        except Exception:
            return JsonResponse({'success': False, 'error': 'Некорректный формат JSON'}, status=400)

        auth_key = normalize_gigachat_key(data.get('auth_key', ''))
        scope = (data.get('scope') or default_scope).strip()
        if scope not in ('GIGACHAT_API_PERS', 'GIGACHAT_API_B2B', 'GIGACHAT_API_CORP'):
            scope = default_scope

        if not auth_key:
            return JsonResponse({
                'success': False,
                'error': 'Введите авторизационный ключ GigaChat (Authorization Key в формате Base64).'
            }, status=400)

        if data.get('verify'):
            try:
                GigaChatService.get_token(auth_key=auth_key, scope=scope, user=user)
            except GigaChatAuthError as auth_err:
                return JsonResponse({'success': False, 'error': str(auth_err)}, status=400)

        masked = mask_gigachat_key(auth_key)

        if user:
            UserGigaChatCredential.objects.update_or_create(
                user=user,
                defaults={'auth_key': auth_key, 'scope': scope}
            )
            return JsonResponse({
                'success': True,
                'has_key': True,
                'masked_key': masked,
                'scope': scope,
                'storage': 'db',
                'storage_mode': 'db',
                'message': 'Ключ GigaChat сохранен в вашей учетной записи (базе данных).'
            })
        else:
            resp = JsonResponse({
                'success': True,
                'has_key': True,
                'masked_key': masked,
                'scope': scope,
                'storage': 'cookie',
                'storage_mode': 'cookie',
                'message': 'Ключ GigaChat сохранен в cookie браузера (гостевой режим).'
            })
            resp.set_cookie(
                GIGACHAT_COOKIE_KEY,
                urllib.parse.quote(auth_key, safe=''),
                max_age=GIGACHAT_COOKIE_MAX_AGE,
                samesite='Lax',
                path='/'
            )
            resp.set_cookie(
                GIGACHAT_COOKIE_SCOPE,
                urllib.parse.quote(scope, safe=''),
                max_age=GIGACHAT_COOKIE_MAX_AGE,
                samesite='Lax',
                path='/'
            )
            return resp

    elif request.method == 'DELETE':
        if user:
            UserGigaChatCredential.objects.filter(user=user).delete()
        storage_mode = 'db' if user else 'cookie'
        resp = JsonResponse({
            'success': True,
            'has_key': False,
            'masked_key': '',
            'scope': default_scope,
            'storage_mode': storage_mode,
            'message': 'Ключ авторизации GigaChat удален.'
        })
        resp.delete_cookie(GIGACHAT_COOKIE_KEY, path='/')
        resp.delete_cookie(GIGACHAT_COOKIE_SCOPE, path='/')
        return resp

    return JsonResponse({'error': 'Метод не поддерживается'}, status=405)


# ─── Projects API ─────────────────────────────────────────────────────────

@csrf_exempt
def api_projects(request):
    user = request.user if request.user.is_authenticated else None
    if request.method == 'GET':
        if not user:
            demo_diag = {
                'id': 0,
                'name': 'Согласование командировки',
                'description': 'Пример процесса согласования командировки',
                'dsl_code': INITIAL_DEMO_DSL,
                'bpmn_xml': '',
                'svg_preview': '',
                'project_id': 0
            }
            demo_proj = {
                'id': 0,
                'name': 'Демонстрационный проект',
                'description': 'Гостевой режим',
                'diagrams': [demo_diag]
            }
            return JsonResponse({'projects': [demo_proj]})

        projects = []
        for p in Project.objects.filter(user=user).prefetch_related('diagrams').all():
            p_dict = p.to_dict()
            p_dict['diagrams'] = [d.to_dict() for d in p.diagrams.all()]
            projects.append(p_dict)
        return JsonResponse({'projects': projects})

    elif request.method == 'POST':
        if not user:
            return JsonResponse({
                'success': False,
                'error': 'В гостевом режиме создание проектов недоступно. Зарегистрируйтесь или войдите.',
                'auth_required': True
            }, status=401)
        try:
            data = json.loads(request.body.decode('utf-8'))
            name = data.get('name', '').strip() or 'Новый проект'
            description = data.get('description', '').strip()
            p = Project.objects.create(user=user, name=name, description=description)

            # Auto-create initial diagram and initial greeting chat for this project
            init_dsl = f'process "{name}"\n\nstart: s "Начало"\nend: e "Завершение"\n\ns -> e'
            comp_res = compile_dsl(init_dsl)
            d = Diagram.objects.create(
                project=p,
                name="Новый процесс",
                description=f"Основной процесс проекта «{name}»",
                dsl_code=init_dsl,
                bpmn_xml=comp_res.get('xml', '')
            )
            ChatMessage.objects.create(
                diagram=d,
                role="assistant",
                content=f"Проект «{name}» успешно создан! Опишите бизнес-процесс, и я построю BPMN-диаграмму.",
                dsl_code=init_dsl,
                explanation="Создана базовая схема. Введите описание логики или шагов процесса в поле ниже."
            )

            p_dict = p.to_dict()
            p_dict['diagrams'] = [d.to_dict()]
            return JsonResponse({'success': True, 'project': p_dict, 'diagram': d.to_dict()})
        except Exception as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    return JsonResponse({'error': 'Метод не поддерживается'}, status=405)


@csrf_exempt
def api_project_detail(request, project_id):
    user = request.user if request.user.is_authenticated else None
    if project_id == 0:
        if request.method == 'GET':
            demo_diag = {
                'id': 0,
                'name': 'Согласование командировки',
                'description': 'Пример процесса согласования командировки',
                'dsl_code': INITIAL_DEMO_DSL,
                'bpmn_xml': '',
                'svg_preview': '',
                'project_id': 0
            }
            demo_proj = {
                'id': 0,
                'name': 'Демонстрационный проект',
                'description': 'Гостевой режим',
                'diagrams': [demo_diag]
            }
            return JsonResponse({'project': demo_proj})
        return JsonResponse({'success': False, 'error': 'В гостевом режиме проекты не изменяются.', 'auth_required': True}, status=401)

    if not user:
        return JsonResponse({'error': 'Требуется авторизация', 'auth_required': True}, status=401)

    project = get_object_or_404(Project, id=project_id, user=user)

    if request.method == 'GET':
        diagrams = [d.to_dict() for d in project.diagrams.all()]
        data = project.to_dict()
        data['diagrams'] = diagrams
        return JsonResponse({'project': data})

    elif request.method in ['PUT', 'POST']:
        try:
            data = json.loads(request.body.decode('utf-8'))
            if 'name' in data:
                project.name = data['name'].strip()
            if 'description' in data:
                project.description = data['description'].strip()
            project.save()
            return JsonResponse({'success': True, 'project': project.to_dict()})
        except Exception as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    elif request.method == 'DELETE':
        project.delete()
        return JsonResponse({'success': True, 'deleted_id': project_id})

    return JsonResponse({'error': 'Метод не поддерживается'}, status=405)


# ─── Diagrams API ──────────────────────────────────────────────────────────

@csrf_exempt
def api_diagrams(request):
    user = request.user if request.user.is_authenticated else None
    if request.method == 'GET':
        if not user:
            demo_diag = {
                'id': 0,
                'name': 'Согласование командировки',
                'description': 'Пример процесса согласования командировки',
                'dsl_code': INITIAL_DEMO_DSL,
                'bpmn_xml': '',
                'svg_preview': '',
                'project_id': 0
            }
            return JsonResponse({'diagrams': [demo_diag]})

        project_id = request.GET.get('project_id')
        if project_id:
            diagrams = Diagram.objects.filter(project__user=user, project_id=project_id)
        else:
            diagrams = Diagram.objects.filter(project__user=user)
        return JsonResponse({'diagrams': [d.to_dict() for d in diagrams]})

    elif request.method == 'POST':
        if not user:
            return JsonResponse({
                'success': False,
                'error': 'В гостевом режиме сохранение схем недоступно. Зарегистрируйтесь или войдите.',
                'auth_required': True
            }, status=401)
        try:
            data = json.loads(request.body.decode('utf-8'))
            project_id = data.get('project_id')
            if not project_id:
                project = Project.objects.filter(user=user).first()
                if not project:
                    project, _ = create_default_project_for_user(user=user)
            else:
                project = get_object_or_404(Project, id=project_id, user=user)

            name = data.get('name', '').strip() or 'Новая диаграмма'
            description = data.get('description', '').strip()
            dsl_code = data.get('dsl_code', '').strip() or f'process "{name}"\n\nstart: s "Начало"\nend: e "Конец"\n\ns -> e'
            compile_res = compile_dsl(dsl_code)
            bpmn_xml = compile_res.get('xml', '')

            d = Diagram.objects.create(
                project=project,
                name=name,
                description=description,
                dsl_code=dsl_code,
                bpmn_xml=bpmn_xml
            )
            ChatMessage.objects.create(
                diagram=d,
                role="assistant",
                content=f"Создана новая схема «{name}». Опишите процесс или начните редактировать код.",
                dsl_code=dsl_code
            )
            return JsonResponse({'success': True, 'diagram': d.to_dict()})
        except Exception as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    return JsonResponse({'error': 'Метод не поддерживается'}, status=405)


@csrf_exempt
def api_diagram_detail(request, diagram_id):
    user = request.user if request.user.is_authenticated else None
    if diagram_id == 0:
        if request.method == 'GET':
            demo_msg = {
                'id': 0,
                'role': 'assistant',
                'content': 'Добро пожаловать в Архитектор BPMN-диаграмм! Вы работаете в гостевом режиме (без сохранения истории и базы знаний). Для сохранения проектов и создания файлов зарегистрируйтесь или войдите.',
                'dsl_code': INITIAL_DEMO_DSL,
                'explanation': 'В демонстрационном процессе показаны: стартовое событие, проверка лимитов, двухуровневое согласование, параллельное оформление билетов и начисление суточных.',
                'created_at': '',
                'is_error': False
            }
            demo_diag = {
                'id': 0,
                'name': 'Согласование командировки',
                'description': 'Пример процесса согласования командировки',
                'dsl_code': INITIAL_DEMO_DSL,
                'bpmn_xml': '',
                'svg_preview': '',
                'project_id': 0,
                'messages': [demo_msg]
            }
            return JsonResponse({'diagram': demo_diag})
        return JsonResponse({'success': False, 'error': 'В гостевом режиме изменение диаграмм не сохраняется в БД.', 'auth_required': True}, status=401)

    if not user:
        return JsonResponse({'error': 'Требуется авторизация', 'auth_required': True}, status=401)

    diagram = get_object_or_404(Diagram, id=diagram_id, project__user=user)

    if request.method == 'GET':
        messages = [m.to_dict() for m in diagram.messages.all()]
        data = diagram.to_dict()
        data['messages'] = messages
        return JsonResponse({'diagram': data})

    elif request.method in ['PUT', 'POST']:
        try:
            data = json.loads(request.body.decode('utf-8'))
            if 'name' in data:
                diagram.name = data['name'].strip()
            if 'description' in data:
                diagram.description = data['description'].strip()
            if 'dsl_code' in data and data['dsl_code'].strip():
                diagram.dsl_code = data['dsl_code']
                compile_res = compile_dsl(diagram.dsl_code)
                if compile_res.get('valid') and compile_res.get('xml'):
                    diagram.bpmn_xml = compile_res['xml']
            elif 'bpmn_xml' in data and data['bpmn_xml'].strip():
                diagram.bpmn_xml = data['bpmn_xml']
                decompiled_dsl = decompile_bpmn_xml(diagram.bpmn_xml)
                if decompiled_dsl and not decompiled_dsl.startswith('# Ошибка'):
                    diagram.dsl_code = decompiled_dsl
            if 'bpmn_xml' in data and data['bpmn_xml'].strip():
                diagram.bpmn_xml = data['bpmn_xml']
            if 'svg_preview' in data:
                diagram.svg_preview = data['svg_preview']
            diagram.save()
            return JsonResponse({'success': True, 'diagram': diagram.to_dict()})
        except Exception as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    elif request.method == 'DELETE':
        diagram.delete()
        return JsonResponse({'success': True, 'deleted_id': diagram_id})

    return JsonResponse({'error': 'Метод не поддерживается'}, status=405)


# ─── Chat Messages API (Single, Bulk, Clear All) ──────────────────────────

@csrf_exempt
def api_messages(request, diagram_id):
    user = request.user if request.user.is_authenticated else None
    if diagram_id == 0:
        if request.method == 'GET':
            demo_msg = {
                'id': 0,
                'role': 'assistant',
                'content': 'Добро пожаловать в Архитектор BPMN-диаграмм! Вы работаете в гостевом режиме (без сохранения истории и базы знаний). Для сохранения проектов и создания файлов зарегистрируйтесь или войдите.',
                'dsl_code': INITIAL_DEMO_DSL,
                'explanation': 'В демонстрационном процессе показаны: стартовое событие, проверка лимитов, двухуровневое согласование, параллельное оформление билетов и начисление суточных.',
                'created_at': '',
                'is_error': False
            }
            return JsonResponse({'messages': [demo_msg]})
        elif request.method == 'DELETE':
            return JsonResponse({'success': True, 'cleared_count': 0})
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)

    if not user:
        return JsonResponse({'error': 'Требуется авторизация', 'auth_required': True}, status=401)

    diagram = get_object_or_404(Diagram, id=diagram_id, project__user=user)

    if request.method == 'GET':
        messages = [m.to_dict() for m in diagram.messages.all()]
        return JsonResponse({'messages': messages})

    elif request.method == 'DELETE':
        try:
            body = request.body.decode('utf-8')
            data = json.loads(body) if body else {}

            if data.get('clear_all'):
                count = diagram.messages.count()
                diagram.messages.all().delete()
                return JsonResponse({'success': True, 'cleared_count': count})

            message_ids = data.get('message_ids', [])
            if message_ids:
                deleted, _ = diagram.messages.filter(id__in=message_ids).delete()
                return JsonResponse({'success': True, 'deleted_count': deleted})

            message_id = data.get('message_id')
            if message_id:
                diagram.messages.filter(id=message_id).delete()
                return JsonResponse({'success': True, 'deleted_id': message_id})

            return JsonResponse({'success': False, 'error': 'Не указаны идентификаторы сообщений для удаления'}, status=400)
        except Exception as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    return JsonResponse({'error': 'Метод не поддерживается'}, status=405)


# ─── Generation & Refinement API ──────────────────────────────────────────

MAX_UPLOAD_DOC_SIZE = 10 * 1024 * 1024  # 10 МБ лимит для документов
MAX_MD_FILE_SIZE = MAX_UPLOAD_DOC_SIZE
ALLOWED_DOC_EXTENSIONS = ('.md', '.markdown', '.txt', '.docx', '.pdf')
ALLOWED_MD_EXTENSIONS = ALLOWED_DOC_EXTENSIONS


def extract_text_from_docx(raw_bytes: bytes, file_name: str) -> str:
    """Извлекает текст из DOCX документа, включая параграфы и таблицы."""
    import io
    # 1. Try python-docx
    try:
        import docx
        doc = docx.Document(io.BytesIO(raw_bytes))
        parts = []
        for p in doc.paragraphs:
            t = p.text.strip()
            if t:
                parts.append(t)
        for tbl in doc.tables:
            for row in tbl.rows:
                row_text = ' | '.join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    parts.append(row_text)
        text = '\n'.join(parts).strip()
        if text:
            return text
    except Exception:
        pass

    # 2. Fallback using built-in zipfile and xml parsing
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
            xml_content = z.read('word/document.xml')
            tree = ET.fromstring(xml_content)
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            paragraphs = []
            for p in tree.iterfind('.//w:p', ns):
                texts = [node.text for node in p.iterfind('.//w:t', ns) if node.text]
                if texts:
                    paragraphs.append(''.join(texts))
            text = '\n'.join(paragraphs).strip()
            if text:
                return text
    except Exception as exc:
        raise ValueError(f"Не удалось извлечь текст из DOCX «{file_name}»: {exc}")

    raise ValueError(f"Документ DOCX «{file_name}» не содержит текстовых данных.")


def extract_text_from_pdf(raw_bytes: bytes, file_name: str) -> str:
    """Извлекает текстовый слой из PDF файла."""
    import io
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        if len(reader.pages) == 0:
            raise ValueError(f"PDF документ «{file_name}» не содержит страниц.")
        parts = []
        for idx, page in enumerate(reader.pages):
            txt = page.extract_text() or ''
            txt = txt.strip()
            if txt:
                parts.append(txt)
        text = '\n\n'.join(parts).strip()
        if not text:
            raise ValueError(
                f"PDF документ «{file_name}» не содержит распознаваемого текстового слоя "
                f"(возможно, документ является отсканированным изображением). "
                f"Пожалуйста, используйте текстовый PDF, DOCX или Markdown."
            )
        return text
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Ошибка чтения PDF файла «{file_name}»: {exc}")


def validate_and_extract_md_file(uploaded_file):
    """
    Проверяет загруженный файл:
    - Расширение .md, .markdown, .txt, .docx, .pdf
    - Размер <= MAX_UPLOAD_DOC_SIZE (10 МБ) и > 0 байт
    - Извлекает текстовое содержимое
    Возвращает кортеж: (is_valid, file_name, text_content, error_message)
    """
    if not uploaded_file:
        return True, "", "", None

    file_name = getattr(uploaded_file, 'name', '') or 'document.txt'
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in ALLOWED_DOC_EXTENSIONS:
        allowed_str = ', '.join(ALLOWED_DOC_EXTENSIONS)
        return False, file_name, "", (
            f"Недопустимый формат файла «{file_name}». "
            f"Разрешены документы форматов: {allowed_str}."
        )

    file_size = getattr(uploaded_file, 'size', 0)
    # 2 МБ лимит для текстовых файлов (md, txt), 10 МБ лимит для офисных документов (docx, pdf)
    max_allowed_size = 2 * 1024 * 1024 if ext in ('.md', '.markdown', '.txt') else MAX_UPLOAD_DOC_SIZE
    if file_size > max_allowed_size:
        max_mb = max_allowed_size // (1024 * 1024)
        return False, file_name, "", (
            f"Размер файла «{file_name}» ({round(file_size / 1024, 1)} КБ) "
            f"превышает допустимый лимит {max_mb} МБ."
        )

    try:
        raw_bytes = uploaded_file.read()
    except Exception as exc:
        return False, file_name, "", f"Ошибка чтения файла «{file_name}»: {exc}"

    if not raw_bytes or len(raw_bytes.strip()) == 0:
        return False, file_name, "", f"Прикрепленный файл «{file_name}» пуст."

    # DOCX extraction
    if ext == '.docx':
        try:
            content = extract_text_from_docx(raw_bytes, file_name)
            return True, file_name, content, None
        except Exception as exc:
            return False, file_name, "", str(exc)

    # PDF extraction
    if ext == '.pdf':
        try:
            content = extract_text_from_pdf(raw_bytes, file_name)
            return True, file_name, content, None
        except Exception as exc:
            return False, file_name, "", str(exc)

    # Plaintext / Markdown / TXT: must not contain binary null bytes
    if b'\x00' in raw_bytes:
        return False, file_name, "", (
            f"Файл «{file_name}» содержит бинарные данные. "
            f"Ожидается текстовый документ в формате Markdown или TXT."
        )

    text_content = None
    for encoding in ('utf-8', 'utf-8-sig', 'windows-1251', 'cp1251'):
        try:
            text_content = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if text_content is None:
        return False, file_name, "", (
            f"Не удалось распознать кодировку текстового файла «{file_name}». "
            f"Пожалуйста, сохраните файл в кодировке UTF-8."
        )

    text_content = text_content.replace('\r\n', '\n').strip()
    if not text_content:
        return False, file_name, "", f"Текстовое содержимое файла «{file_name}» пусто."

    return True, file_name, text_content, None


def merge_prompt_with_md(prompt: str, file_name: str, file_content: str) -> str:
    """
    Объединяет пользовательский текст промпта и прикрепленный документ (MD, TXT, DOCX, PDF).
    """
    prompt = (prompt or '').strip()
    file_content = (file_content or '').strip()
    if not file_content:
        return prompt

    separator = f"\n\n---\n📎 **Прикрепленный документ: `{file_name}`**\n\n```text\n{file_content}\n```"
    if prompt:
        return f"{prompt}{separator}"
    else:
        return f"Построй процесс на основе прикрепленного документа `{file_name}`:{separator}"


def extract_request_payload(request):
    """
    Универсально извлекает словарь параметров и загруженный файл
    как из multipart/form-data, так и из application/json.
    """
    content_type = request.headers.get('Content-Type', '') or request.META.get('CONTENT_TYPE', '')
    if 'multipart/form-data' in content_type:
        data = request.POST.dict()
        uploaded_file = request.FILES.get('attached_file') or request.FILES.get('file')
        if 'history' in data and isinstance(data['history'], str):
            try:
                data['history'] = json.loads(data['history'])
            except Exception:
                data['history'] = []
    else:
        try:
            data = json.loads(request.body.decode('utf-8')) if request.body else {}
        except Exception:
            data = {}
        uploaded_file = None

    return data, uploaded_file


@csrf_exempt
def api_generate(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Только POST запрос'}, status=405)

    try:
        data, uploaded_file = extract_request_payload(request)

        # Верификация прикрепленного файла
        if uploaded_file:
            is_valid, f_name, f_content, err_msg = validate_and_extract_md_file(uploaded_file)
            if not is_valid:
                return JsonResponse({'success': False, 'error': err_msg}, status=400)
            attached_doc = {
                'name': f_name,
                'size': getattr(uploaded_file, 'size', len(f_content.encode('utf-8'))),
                'content': f_content
            }
        else:
            f_name, f_content = "", ""
            attached_doc = None

        raw_prompt = data.get('prompt', '').strip()
        prompt = merge_prompt_with_md(raw_prompt, f_name, f_content)

        if not prompt:
            return JsonResponse({'success': False, 'error': 'Описание процесса или прикрепленный файл не могут быть пустыми'}, status=400)

        user = request.user if request.user.is_authenticated else None
        auth_key, scope, storage_mode = resolve_request_gigachat_credentials(request, data)
        current_dsl = data.get('current_dsl', '').strip()
        history = data.get('history', [])
        if isinstance(history, str):
            try:
                history = json.loads(history)
            except Exception:
                history = []

        if not user:
            # Guest mode: compute completely in-memory, ZERO database rows written
            if current_dsl and ('task:' in current_dsl or 'gateway:' in current_dsl or '->' in current_dsl):
                result = GigaChatService.refine_diagram(
                    current_dsl=current_dsl,
                    instruction=prompt,
                    history=history,
                    max_retries=5,
                    user=None,
                    auth_key=auth_key,
                    scope=scope
                )
            else:
                result = GigaChatService.generate_diagram(
                    prompt=prompt,
                    history=history,
                    max_retries=5,
                    user=None,
                    auth_key=auth_key,
                    scope=scope
                )

            has_dsl = result.get('has_dsl', True)
            dsl_code = result.get('dsl_code', '')
            explanation = result.get('explanation', '')
            bpmn_xml = result.get('bpmn_xml', '')
            success = result.get('success', False)
            error = result.get('error')

            title = "Процесс"
            if dsl_code and 'process "' in dsl_code:
                try:
                    title = dsl_code.split('process "')[1].split('"')[0]
                except Exception:
                    pass
            elif len(prompt) < 40:
                title = prompt.split('.')[0]

            if not has_dsl:
                content_text = explanation or result.get('content', '') or "Ответ на ваш вопрос:"
            elif success:
                content_text = explanation if explanation else f"Построен процесс «{title}»."
            else:
                content_text = f"Ошибка: {error}"

            demo_diag = {
                'id': 0,
                'name': title,
                'description': prompt,
                'dsl_code': dsl_code or "",
                'bpmn_xml': bpmn_xml or "",
                'svg_preview': "",
                'project_id': 0
            }
            user_msg = {
                'id': 0,
                'role': 'user',
                'content': prompt,
                'dsl_code': '',
                'explanation': '',
                'is_error': False,
                'created_at': ''
            }
            assistant_msg = {
                'id': 0,
                'role': 'assistant',
                'content': content_text,
                'dsl_code': dsl_code if has_dsl else "",
                'explanation': explanation,
                'is_error': not success,
                'created_at': ''
            }
            return JsonResponse({
                'success': success,
                'has_dsl': has_dsl,
                'diagram': demo_diag,
                'dsl_code': dsl_code if has_dsl else None,
                'bpmn_xml': bpmn_xml,
                'explanation': explanation,
                'user_message': user_msg,
                'assistant_message': assistant_msg,
                'attached_doc': attached_doc,
                'guest_mode': True,
                'attempts': result.get('attempts', 1),
                'validation_report': result.get('validation_report'),
                'proactive_questions': result.get('proactive_questions', []),
                'traceability': result.get('traceability', []),
                'error': error
            })

        # Authenticated user workflow
        project_id = data.get('project_id')
        diagram_id = data.get('diagram_id')
        try:
            project_id = int(project_id) if project_id not in (None, '', '0') else None
        except (ValueError, TypeError):
            project_id = None
        try:
            diagram_id = int(diagram_id) if diagram_id not in (None, '', '0') else None
        except (ValueError, TypeError):
            diagram_id = None

        project = Project.objects.filter(user=user, id=project_id).first() if project_id else Project.objects.filter(user=user).first()
        if not project:
            project, _ = create_default_project_for_user(user=user, project_name="Основной проект")

        diagram = Diagram.objects.filter(id=diagram_id, project__user=user).first() if diagram_id else None

        # Build chat history for context
        auth_history = []
        if diagram:
            for msg in diagram.messages.order_by('-created_at')[:6]:
                auth_history.insert(0, {'role': msg.role, 'content': msg.content})

        if not current_dsl and diagram and diagram.dsl_code:
            current_dsl = diagram.dsl_code.strip()

        # If user already modified or populated diagram with tasks/flows, refine it rather than wiping it out
        if current_dsl and ('task:' in current_dsl or 'gateway:' in current_dsl or '->' in current_dsl):
            if diagram:
                diagram.dsl_code = current_dsl
                diagram.save(update_fields=['dsl_code'])
            result = GigaChatService.refine_diagram(
                current_dsl=current_dsl,
                instruction=prompt,
                history=auth_history,
                max_retries=5,
                user=user,
                auth_key=auth_key,
                scope=scope
            )
        else:
            result = GigaChatService.generate_diagram(
                prompt=prompt,
                history=auth_history,
                max_retries=5,
                user=user,
                auth_key=auth_key,
                scope=scope
            )

        has_dsl = result.get('has_dsl', True)
        dsl_code = result.get('dsl_code', '')
        explanation = result.get('explanation', '')
        bpmn_xml = result.get('bpmn_xml', '')
        success = result.get('success', False)
        error = result.get('error')

        title = "Процесс"
        if dsl_code and 'process "' in dsl_code:
            try:
                title = dsl_code.split('process "')[1].split('"')[0]
            except Exception:
                pass
        elif len(prompt) < 40:
            title = prompt.split('.')[0]

        if not diagram:
            diagram = Diagram.objects.create(
                project=project,
                name=title,
                description=prompt,
                dsl_code=dsl_code or "",
                bpmn_xml=bpmn_xml or ""
            )
        elif has_dsl and dsl_code:
            diagram.dsl_code = dsl_code
            diagram.bpmn_xml = bpmn_xml
            if title != "Процесс" and (diagram.name.startswith("Новый") or diagram.name.startswith("Новая")):
                diagram.name = title
            diagram.save()

        user_msg = ChatMessage.objects.create(
            diagram=diagram,
            role='user',
            content=prompt
        )

        if not has_dsl:
            content_text = explanation or result.get('content', '') or "Ответ на ваш вопрос:"
            stored_dsl = ""
            stored_exp = ""
        elif success:
            content_text = explanation if explanation else f"Построен процесс «{title}»."
            stored_dsl = dsl_code
            stored_exp = explanation
        else:
            content_text = f"Ошибка: {error}"
            stored_dsl = dsl_code
            stored_exp = explanation

        assistant_msg = ChatMessage.objects.create(
            diagram=diagram,
            role='assistant',
            content=content_text,
            dsl_code=stored_dsl,
            explanation=stored_exp,
            is_error=not success
        )

        return JsonResponse({
            'success': success,
            'has_dsl': has_dsl,
            'diagram': diagram.to_dict(),
            'dsl_code': dsl_code if has_dsl else None,
            'bpmn_xml': bpmn_xml,
            'explanation': explanation,
            'user_message': user_msg.to_dict(),
            'assistant_message': assistant_msg.to_dict(),
            'attached_doc': attached_doc,
            'attempts': result.get('attempts', 1),
            'validation_report': result.get('validation_report'),
            'proactive_questions': result.get('proactive_questions', []),
            'traceability': result.get('traceability', []),
            'error': error
        })

    except GigaChatAuthError as auth_err:
        storage_mode = 'db' if request.user.is_authenticated else 'cookie'
        return JsonResponse({
            'success': False,
            'gigachat_key_required': True,
            'storage_mode': storage_mode,
            'error': str(auth_err)
        }, status=401)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@csrf_exempt
def api_refine(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Только POST запрос'}, status=405)

    try:
        data, uploaded_file = extract_request_payload(request)

        # Верификация прикрепленного файла
        if uploaded_file:
            is_valid, f_name, f_content, err_msg = validate_and_extract_md_file(uploaded_file)
            if not is_valid:
                return JsonResponse({'success': False, 'error': err_msg}, status=400)
            attached_doc = {
                'name': f_name,
                'size': getattr(uploaded_file, 'size', len(f_content.encode('utf-8'))),
                'content': f_content
            }
        else:
            f_name, f_content = "", ""
            attached_doc = None

        diagram_id = data.get('diagram_id')
        try:
            diagram_id = int(diagram_id) if diagram_id not in (None, '', '0') else 0
        except (ValueError, TypeError):
            diagram_id = 0

        raw_instruction = data.get('instruction', '').strip()
        instruction = merge_prompt_with_md(raw_instruction, f_name, f_content)
        current_dsl = data.get('current_dsl', '').strip()

        if not instruction:
            return JsonResponse({'success': False, 'error': 'Инструкция по доработке или прикрепленный файл не могут быть пустыми'}, status=400)

        user = request.user if request.user.is_authenticated else None
        auth_key, scope, storage_mode = resolve_request_gigachat_credentials(request, data)

        if not user or diagram_id == 0:
            # Guest mode refine: in-memory calculation without writing to DB
            result = GigaChatService.refine_diagram(
                current_dsl=current_dsl or INITIAL_DEMO_DSL,
                instruction=instruction,
                history=data.get('history', []),
                max_retries=5,
                user=None,
                auth_key=auth_key,
                scope=scope
            )
            has_dsl = result.get('has_dsl', True)
            dsl_code = result.get('dsl_code')
            explanation = result.get('explanation', '')
            bpmn_xml = result.get('bpmn_xml')
            success = result.get('success', False)
            error = result.get('error')

            if not has_dsl:
                content_text = explanation or result.get('content', '') or "Ответ на ваш вопрос:"
            elif success:
                content_text = explanation if explanation else "Схема обновлена в соответствии с вашими указаниями."
            else:
                content_text = f"Не удалось применить изменения: {error}"

            demo_diag = {
                'id': 0,
                'name': "Процесс",
                'description': instruction,
                'dsl_code': dsl_code or current_dsl or INITIAL_DEMO_DSL,
                'bpmn_xml': bpmn_xml or "",
                'svg_preview': "",
                'project_id': 0
            }
            user_msg = {
                'id': 0,
                'role': 'user',
                'content': instruction,
                'dsl_code': '',
                'explanation': '',
                'is_error': False,
                'created_at': ''
            }
            assistant_msg = {
                'id': 0,
                'role': 'assistant',
                'content': content_text,
                'dsl_code': dsl_code if has_dsl else "",
                'explanation': explanation,
                'is_error': not success,
                'created_at': ''
            }
            return JsonResponse({
                'success': success,
                'has_dsl': has_dsl,
                'diagram': demo_diag,
                'dsl_code': dsl_code if has_dsl else None,
                'bpmn_xml': bpmn_xml,
                'explanation': explanation,
                'user_message': user_msg,
                'assistant_message': assistant_msg,
                'attached_doc': attached_doc,
                'guest_mode': True,
                'validation_report': result.get('validation_report'),
                'proactive_questions': result.get('proactive_questions', []),
                'traceability': result.get('traceability', []),
                'error': error
            })

        # Authenticated user
        diagram = get_object_or_404(Diagram, id=diagram_id, project__user=user)
        if current_dsl:
            diagram.dsl_code = current_dsl
            diagram.save(update_fields=['dsl_code'])
        else:
            current_dsl = diagram.dsl_code

        history = []
        for msg in diagram.messages.order_by('-created_at')[:4]:
            history.insert(0, {'role': msg.role, 'content': msg.content})

        result = GigaChatService.refine_diagram(
            current_dsl=current_dsl,
            instruction=instruction,
            history=history,
            max_retries=5,
            user=user,
            auth_key=auth_key,
            scope=scope
        )

        has_dsl = result.get('has_dsl', True)
        dsl_code = result.get('dsl_code')
        explanation = result.get('explanation', '')
        bpmn_xml = result.get('bpmn_xml')
        success = result.get('success', False)
        error = result.get('error')

        if success and has_dsl and dsl_code:
            diagram.dsl_code = dsl_code
            if bpmn_xml:
                diagram.bpmn_xml = bpmn_xml
            diagram.save()

        user_msg = ChatMessage.objects.create(
            diagram=diagram,
            role='user',
            content=instruction
        )

        if not has_dsl:
            content_text = explanation or result.get('content', '') or "Ответ на ваш вопрос:"
            stored_dsl = ""
            stored_exp = ""
        elif success:
            content_text = explanation if explanation else "Схема обновлена в соответствии с вашими указаниями."
            stored_dsl = dsl_code or ""
            stored_exp = explanation or ""
        else:
            content_text = f"Не удалось применить изменения: {error}"
            stored_dsl = dsl_code or ""
            stored_exp = explanation or ""

        assistant_msg = ChatMessage.objects.create(
            diagram=diagram,
            role='assistant',
            content=content_text,
            dsl_code=stored_dsl,
            explanation=stored_exp,
            is_error=not success
        )

        return JsonResponse({
            'success': success,
            'has_dsl': has_dsl,
            'diagram': diagram.to_dict(),
            'dsl_code': dsl_code if has_dsl else None,
            'bpmn_xml': diagram.bpmn_xml,
            'explanation': explanation,
            'user_message': user_msg.to_dict(),
            'assistant_message': assistant_msg.to_dict(),
            'attached_doc': attached_doc,
            'validation_report': result.get('validation_report'),
            'proactive_questions': result.get('proactive_questions', []),
            'traceability': result.get('traceability', []),
            'error': error
        })

    except GigaChatAuthError as auth_err:
        storage_mode = 'db' if request.user.is_authenticated else 'cookie'
        return JsonResponse({
            'success': False,
            'gigachat_key_required': True,
            'storage_mode': storage_mode,
            'error': str(auth_err)
        }, status=401)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


# ─── Knowledge Base Management API (Validation & Upload) ───────────────────

@csrf_exempt
def api_kb_files_list(request):
    user = request.user if request.user.is_authenticated else None
    if request.method == 'GET':
        return JsonResponse({'files': list_kb_files(user=user)})

    elif request.method == 'POST':
        if not user:
            return JsonResponse({
                'success': False,
                'error': 'В гостевом режиме добавление файлов в базу знаний недоступно. Зарегистрируйтесь или войдите.',
                'auth_required': True
            }, status=401)
        try:
            data = json.loads(request.body.decode('utf-8'))
            name = data.get('name', '').strip()
            content = data.get('content', '')
            if not name:
                return JsonResponse({'success': False, 'error': 'Имя файла обязательно'}, status=400)
            res = write_kb_file(name, content, user=user)
            return JsonResponse({'success': True, 'file': res})
        except ValueError as val_err:
            return JsonResponse({'success': False, 'error': str(val_err)}, status=400)
        except Exception as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    return JsonResponse({'error': 'Метод не поддерживается'}, status=405)


@csrf_exempt
def api_kb_file_detail(request, filename):
    user = request.user if request.user.is_authenticated else None
    if request.method == 'GET':
        try:
            content = read_kb_file(filename, user=user)
            return JsonResponse({'success': True, 'name': filename, 'content': content})
        except Exception as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=404)

    elif request.method in ['POST', 'PUT']:
        if not user:
            return JsonResponse({
                'success': False,
                'error': 'В гостевом режиме изменение базы знаний недоступно. Зарегистрируйтесь или войдите.',
                'auth_required': True
            }, status=401)
        try:
            data = json.loads(request.body.decode('utf-8'))
            content = data.get('content', '')
            write_kb_file(filename, content, user=user)
            return JsonResponse({'success': True, 'name': filename})
        except ValueError as val_err:
            return JsonResponse({'success': False, 'error': str(val_err)}, status=400)
        except Exception as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    elif request.method == 'DELETE':
        if not user:
            return JsonResponse({
                'success': False,
                'error': 'В гостевом режиме удаление файлов базы знаний недоступно. Зарегистрируйтесь или войдите.',
                'auth_required': True
            }, status=401)
        try:
            deleted = delete_kb_file(filename, user=user)
            return JsonResponse({'success': deleted, 'name': filename})
        except Exception as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    return JsonResponse({'error': 'Метод не поддерживается'}, status=405)


@csrf_exempt
def api_kb_upload(request):
    user = request.user if request.user.is_authenticated else None
    if request.method != 'POST':
        return JsonResponse({'error': 'Только POST запрос'}, status=405)

    if not user:
        return JsonResponse({
            'success': False,
            'error': 'В гостевом режиме загрузка файлов в базу знаний недоступна. Зарегистрируйтесь или войдите.',
            'auth_required': True
        }, status=401)

    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return JsonResponse({'success': False, 'error': 'Файл не прикреплен'}, status=400)

    try:
        res = process_uploaded_kb_file(uploaded_file, user=user)
        return JsonResponse({'success': True, 'file': res})
    except ValueError as val_err:
        return JsonResponse({'success': False, 'error': str(val_err)}, status=400)
    except Exception as exc:
        return JsonResponse({'success': False, 'error': f"Ошибка обработки файла: {exc}"}, status=400)


# ─── Compilation API ───────────────────────────────────────────────────────

@csrf_exempt
def api_compile(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Только POST запрос'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8'))
        dsl_code = data.get('dsl_code', '')
        result = compile_dsl(dsl_code)
        return JsonResponse(result)
    except Exception as exc:
        return JsonResponse({'valid': False, 'error': str(exc)}, status=400)


@csrf_exempt
def api_analyze_dsl(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Только POST запрос'}, status=405)
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        dsl_code = data.get('dsl_code', '').strip()
        source_text = data.get('source_text', '').strip()
        structure = parse_dsl_structure(dsl_code)
        metrics = analyze_process_metrics(structure)
        report = generate_validation_report(structure)
        questions = generate_proactive_questions(structure, source_text=source_text)
        traceability = extract_traceability(dsl_code, source_text=source_text)
        return JsonResponse({
            'success': True,
            'metrics': metrics,
            'validation_report': report,
            'proactive_questions': questions,
            'traceability': traceability,
        })
    except Exception as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


# ─── Authentication API (Register, Login, Logout, Status) ─────────────────

@csrf_exempt
def api_register(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Только POST запрос'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
        username = data.get('username', '').strip()
        password = data.get('password', '')
        password_confirm = data.get('password_confirm', '')

        is_valid, err_msg = validate_username_and_password(
            username=username,
            password=password,
            password_confirm=password_confirm,
            is_registration=True
        )
        if not is_valid:
            return JsonResponse({'success': False, 'error': err_msg}, status=400)

        user = User.objects.create_user(username=username, password=password)
        seed_user_knowledge_base(user)
        project, diag = create_default_project_for_user(user=user, project_name="Основной проект")
        login(request, user)
        resolve_request_gigachat_credentials(request, data)

        return JsonResponse({
            'success': True,
            'user': {'id': user.id, 'username': user.username},
            'redirect': f'/?project={project.id}&diagram={diag.id}'
        })
    except Exception as exc:
        return JsonResponse({'success': False, 'error': f"Ошибка регистрации: {exc}"}, status=400)


@csrf_exempt
def api_login(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Только POST запрос'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return JsonResponse({'success': False, 'error': 'Введите логин и пароль.'}, status=400)

        user = authenticate(request, username=username, password=password)
        if user is None:
            return JsonResponse({'success': False, 'error': 'Неверный логин или пароль.'}, status=400)

        login(request, user)
        resolve_request_gigachat_credentials(request, data)
        p = Project.objects.filter(user=user).first()
        d = p.diagrams.first() if p else None
        redirect_url = f"/?project={p.id}&diagram={d.id}" if (p and d) else "/"

        return JsonResponse({
            'success': True,
            'user': {'id': user.id, 'username': user.username},
            'redirect': redirect_url
        })
    except Exception as exc:
        return JsonResponse({'success': False, 'error': f"Ошибка входа: {exc}"}, status=400)


@csrf_exempt
def api_logout(request):
    logout(request)
    return JsonResponse({'success': True, 'redirect': '/'})


def api_auth_me(request):
    is_auth = request.user.is_authenticated
    return JsonResponse({
        'authenticated': is_auth,
        'username': request.user.username if is_auth else None,
        'id': request.user.id if is_auth else None
    })


@csrf_exempt
def api_change_password(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Требуется авторизация.'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'error': 'Только POST запрос'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
        old_password = data.get('old_password', '')
        new_password = data.get('new_password', '')
        new_password_confirm = data.get('new_password_confirm', '')

        if not old_password or not new_password:
            return JsonResponse({'success': False, 'error': 'Заполните все обязательные поля.'}, status=400)

        if not request.user.check_password(old_password):
            return JsonResponse({'success': False, 'error': 'Неверный текущий пароль.'}, status=400)

        is_valid, err_msg = validate_username_and_password(
            username=request.user.username,
            password=new_password,
            password_confirm=new_password_confirm,
            is_registration=False
        )
        if not is_valid:
            return JsonResponse({'success': False, 'error': err_msg}, status=400)

        if new_password_confirm is not None and new_password != new_password_confirm:
            return JsonResponse({'success': False, 'error': 'Введенные пароли не совпадают.'}, status=400)

        if old_password == new_password:
            return JsonResponse({'success': False, 'error': 'Новый пароль должен отличаться от старого.'}, status=400)

        request.user.set_password(new_password)
        request.user.save()
        update_session_auth_hash(request, request.user)

        return JsonResponse({'success': True, 'message': 'Пароль успешно изменен.'})
    except Exception as exc:
        return JsonResponse({'success': False, 'error': f"Ошибка смены пароля: {exc}"}, status=400)


@csrf_exempt
def api_delete_account(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Требуется авторизация.'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'error': 'Только POST запрос'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
        password = data.get('password', '')

        if not password:
            return JsonResponse({'success': False, 'error': 'Введите пароль для подтверждения удаления.'}, status=400)

        if not request.user.check_password(password):
            return JsonResponse({'success': False, 'error': 'Неверный пароль.'}, status=400)

        user = request.user
        logout(request)
        user.delete()

        return JsonResponse({'success': True, 'redirect': '/'})
    except Exception as exc:
        return JsonResponse({'success': False, 'error': f"Ошибка удаления аккаунта: {exc}"}, status=400)


# ─── SEO, PWA and Root Static Views ────────────────────────────────────────

def robots_txt_view(request):
    """
    Динамическая автогенерация robots.txt с актуальным протоколом, хостом и ссылкой на sitemap.xml.
    """
    host = request.get_host()
    scheme = 'https' if request.is_secure() else 'http'
    sitemap_url = f"{scheme}://{host}/sitemap.xml"
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /admin/\n"
        "\n"
        f"Sitemap: {sitemap_url}\n"
    )
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


def sitemap_xml_view(request):
    """
    Динамическая автогенерация sitemap.xml по спецификации Sitemaps 0.9.
    """
    host = request.get_host()
    scheme = 'https' if request.is_secure() else 'http'
    base_url = f"{scheme}://{host}"
    today_str = datetime.date.today().isoformat()

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{base_url}/</loc>
    <lastmod>{today_str}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>{base_url}/terms/</loc>
    <lastmod>{today_str}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.5</priority>
  </url>
  <url>
    <loc>{base_url}/privacy/</loc>
    <lastmod>{today_str}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.5</priority>
  </url>
  <url>
    <loc>{base_url}/robots.txt</loc>
    <lastmod>{today_str}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.3</priority>
  </url>
</urlset>"""
    return HttpResponse(xml_content, content_type="application/xml; charset=utf-8")


def service_worker_view(request):
    """
    Отдача sw.js из корня сайта с заголовком Service-Worker-Allowed: /.
    """
    sw_path = os.path.join(settings.BASE_DIR, 'architect', 'static', 'architect', 'sw.js')
    if not os.path.exists(sw_path):
        return HttpResponseNotFound("Service Worker not found")
    with open(sw_path, 'r', encoding='utf-8') as f:
        content = f.read()
    response = HttpResponse(content, content_type="application/javascript; charset=utf-8")
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


def manifest_view(request):
    """
    Отдача PWA manifest.json по прямому адресу /manifest.json.
    """
    manifest_path = os.path.join(settings.BASE_DIR, 'architect', 'static', 'architect', 'manifest.json')
    if not os.path.exists(manifest_path):
        return HttpResponseNotFound("Manifest not found")
    with open(manifest_path, 'r', encoding='utf-8') as f:
        content = f.read()
    response = HttpResponse(content, content_type="application/manifest+json; charset=utf-8")
    response['Cache-Control'] = 'public, max-age=86400'
    return response


def favicon_ico_view(request):
    """
    Отдача favicon.ico по прямому корневому адресу /favicon.ico.
    """
    ico_path = os.path.join(settings.BASE_DIR, 'architect', 'static', 'architect', 'icons', 'favicon.ico')
    if not os.path.exists(ico_path):
        return HttpResponseNotFound("Favicon not found")
    with open(ico_path, 'rb') as f:
        content = f.read()
    response = HttpResponse(content, content_type="image/x-icon")
    response['Cache-Control'] = 'public, max-age=604800'
    return response


def terms_view(request):
    """
    Отображение страницы Условий использования (Terms of Use).
    """
    return render(request, 'architect/terms.html')


def privacy_view(request):
    """
    Отображение страницы Политики конфиденциальности (Privacy Policy).
    """
    return render(request, 'architect/privacy.html')


