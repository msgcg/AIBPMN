import os
import re
import base64
from pathlib import Path
from django.conf import settings
from architect.models import KnowledgeBaseFile

# Blacklist of forbidden extensions (executables, scripts, binary archives)
FORBIDDEN_EXTENSIONS = {
    # Executables & scripts
    '.exe', '.dll', '.so', '.dylib', '.bat', '.cmd', '.sh', '.bash',
    '.py', '.pyc', '.pyd', '.vbs', '.js', '.jar', '.bin', '.msi', '.com',
    '.apk', '.app', '.sys', '.scr', '.pif', '.reg',
    # Binary archives
    '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.iso', '.dmg'
}

MAX_FILE_SIZE = getattr(settings, 'MAX_KB_UPLOAD_SIZE', 10 * 1024 * 1024)  # 10 MB

def get_kb_templates_dir() -> Path:
    kb_dir = getattr(settings, 'KNOWLEDGE_BASE_DIR', None)
    if not kb_dir:
        kb_dir = settings.BASE_DIR / 'knowledge_base'
    kb_dir.mkdir(parents=True, exist_ok=True)
    return kb_dir

def sanitize_filename(name: str) -> str:
    clean = re.sub(r'[^a-zA-Z0-9_\u0400-\u04FF\.\-]', '_', name.strip())
    clean = re.sub(r'_+', '_', clean)
    return clean or "knowledge_note.md"

def seed_user_knowledge_base(user=None):
    """
    Seeds initial knowledge base files from disk templates into DB for a given user.
    """
    if not user or not user.is_authenticated:
        return []

    templates_dir = get_kb_templates_dir()
    seeded = []
    for f in sorted(templates_dir.glob('*.*')):
        if f.suffix.lower() in ['.md', '.markdown', '.txt']:
            try:
                content = f.read_text(encoding='utf-8')
                kb_file, created = KnowledgeBaseFile.objects.get_or_create(
                    user=user,
                    name=f.name,
                    defaults={
                        'file_type': 'text/markdown',
                    }
                )
                kb_file.set_text_content(content)
                kb_file.save()
                seeded.append(kb_file)
            except Exception as e:
                print(f"Error seeding KB template {f.name}: {e}")
    return seeded

def list_kb_files(user=None):
    """
    Lists knowledge base files for the user from database.
    Unauthenticated guests have no persistent files in DB.
    """
    if user and user.is_authenticated:
        qs = KnowledgeBaseFile.objects.filter(user=user)
        if not qs.exists():
            seed_user_knowledge_base(user)
            qs = KnowledgeBaseFile.objects.filter(user=user)
        return [f.to_dict() for f in qs]
    return []

def read_kb_file(filename: str, user=None) -> str:
    """
    Reads a knowledge base file content for the user from DB,
    or falls back to disk templates for guests.
    """
    safe_name = Path(filename).name
    if user and user.is_authenticated:
        f = KnowledgeBaseFile.objects.filter(user=user, name=safe_name).first()
        if f:
            return f.get_text_content()

    # Fallback to reading disk template if exists
    template_file = get_kb_templates_dir() / safe_name
    if template_file.exists() and template_file.is_file():
        return template_file.read_text(encoding='utf-8')

    raise FileNotFoundError(f"Файл «{safe_name}» не найден в базе знаний")

def write_kb_file(filename: str, content: str, user=None):
    """
    Creates or updates a knowledge base file for the user, storing Base64 in DB.
    """
    safe_name = sanitize_filename(Path(filename).name)
    suffix = Path(safe_name).suffix.lower()

    if suffix in FORBIDDEN_EXTENSIONS:
        raise ValueError(f"Файлы формата {suffix} запрещены (архивы и исполняемые файлы не поддерживаются).")

    # Format conversion to markdown if text-based
    if suffix in ['.txt', '.csv', '.json', '.xml', '.yaml', '.yml']:
        base_name = Path(safe_name).stem
        if suffix == '.txt':
            safe_name = f"{base_name}.md"
            if not content.startswith('#'):
                content = f"# {base_name}\n\n{content}"
        elif suffix == '.json':
            safe_name = f"{base_name}.md"
            content = f"# Данные: {base_name}\n\n```json\n{content}\n```"
        elif suffix == '.xml':
            safe_name = f"{base_name}.md"
            content = f"# Структура: {base_name}\n\n```xml\n{content}\n```"
        elif suffix == '.csv':
            safe_name = f"{base_name}.md"
            content = f"# Таблица: {base_name}\n\n```csv\n{content}\n```"

    if not safe_name.endswith('.md'):
        safe_name += '.md'

    if not user or not user.is_authenticated:
        raise PermissionError("Для сохранения файлов в базе знаний необходимо войти в систему.")

    kb_file, _ = KnowledgeBaseFile.objects.get_or_create(
        user=user,
        name=safe_name,
        defaults={'file_type': 'text/markdown'}
    )
    kb_file.set_text_content(content)
    kb_file.save()

    return {'name': kb_file.name, 'size': kb_file.file_size}

def process_uploaded_kb_file(uploaded_file, user=None):
    """
    Validates uploaded file against size and blacklist, stores as Base64 in DB.
    """
    if not user or not user.is_authenticated:
        raise PermissionError("Для загрузки файлов в базу знаний необходимо войти в систему.")

    raw_name = uploaded_file.name
    suffix = Path(raw_name).suffix.lower()

    if suffix in FORBIDDEN_EXTENSIONS:
        raise ValueError(f"Файлы формата «{suffix}» запрещены для загрузки (архивы и исполняемые файлы не поддерживаются).")

    raw_bytes = uploaded_file.read()
    if len(raw_bytes) > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)
        raise ValueError(f"Размер файла превышает допустимый лимит ({max_mb} МБ).")

    # Try decode text
    text_content = None
    for enc in ['utf-8', 'utf-8-sig', 'windows-1251', 'cp866']:
        try:
            text_content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if text_content is not None:
        return write_kb_file(raw_name, text_content, user=user)
    else:
        # Binary file that is not in the blacklist (e.g. specialized documents)
        safe_name = sanitize_filename(Path(raw_name).name)
        kb_file, _ = KnowledgeBaseFile.objects.get_or_create(
            user=user,
            name=safe_name,
            defaults={'file_type': suffix or 'application/octet-stream'}
        )
        kb_file.set_binary_content(raw_bytes)
        kb_file.save()
        return {'name': kb_file.name, 'size': kb_file.file_size}

def delete_kb_file(filename: str, user=None) -> bool:
    """
    Deletes a knowledge base file for the user from DB.
    """
    if not user or not user.is_authenticated:
        raise PermissionError("Для удаления файлов из базы знаний необходимо войти в систему.")

    safe_name = Path(filename).name
    deleted, _ = KnowledgeBaseFile.objects.filter(user=user, name=safe_name).delete()
    return deleted > 0

def compose_system_prompt(user=None) -> str:
    """
    Composes GigaChat system prompt incorporating documents from user's DB knowledge base,
    or disk templates for guest users (without writing to DB).
    """
    sections = []
    sections.append(
        "Ты — Главный Архитектор бизнес-процессов и эксперт по нотации BPMN 2.0. "
        "Твоя задача: анализировать текстовые описания процессов от пользователя и формировать безупречные, "
        "логически полные и синтаксически валидные диаграммы на декларативном языке моделирования BPMN-as-Code (DSL).\n"
        "Сгенерированный тобой код сразу же компилируется компилятором в графическую BPMN 2.0 XML диаграмму."
    )

    if user and user.is_authenticated:
        kb_files = KnowledgeBaseFile.objects.filter(user=user)
        if not kb_files.exists():
            seed_user_knowledge_base(user)
            kb_files = KnowledgeBaseFile.objects.filter(user=user)
        for f in kb_files:
            content = f.get_text_content().strip()
            if content:
                sections.append(f"\n--- БАЗА ЗНАНИЙ: {f.name} ---\n{content}")
    else:
        # Guests: read directly from disk templates without writing to database
        templates_dir = get_kb_templates_dir()
        for f in sorted(templates_dir.glob('*.*')):
            if f.suffix.lower() in ['.md', '.markdown', '.txt']:
                try:
                    content = f.read_text(encoding='utf-8').strip()
                    if content:
                        sections.append(f"\n--- БАЗА ЗНАНИЙ: {f.name} ---\n{content}")
                except Exception:
                    pass

    sections.append(
        "\n--- ПРАВИЛА ВЗАИМОДЕЙСТВИЯ И ОТВЕТОВ АРХИТЕКТОРА ---\n"
        "Определяй намерение пользователя (Intent) по контексту его сообщения:\n\n"
        "1. МОДИФИКАЦИЯ ИЛИ СОЗДАНИЕ СХЕМЫ:\n"
        "   Если пользователь просит построить процесс, добавить, удалить, изменить шаги, перестроить развилки или оптимизировать схему:\n"
        "   - ОБЯЗАТЕЛЬНО предоставь обновленный полный блок DSL-кода процесса, заключенный в тройные обратные кавычки с тегом ```bac:\n"
        "     ```bac\n"
        "     process \"Имя процесса\"\n"
        "     start: ...\n"
        "     task: ...\n"
        "     end: ...\n"
        "     ...\n"
        "     ```\n"
        "   - DSL код ДОЛЖЕН БЫТЬ 100% синтаксически валидным:\n"
        "     * Начинаться с `process \"Название\"`\n"
        "     * Все ID узлов уникальны, латиница snake_case\n"
        "     * Все лейблы в двойных кавычках\n"
        "     * КРИТИЧЕСКИ ВАЖНО: Все узлы, используемые в потоках ->, ОБЯЗАНЫ быть предварительно объявлены строками выше (например: `task: id \"Название\"`). Никогда не указывай в потоках стрелок идентификаторы, которые не были объявлены!\n"
        "     * Все объявленные узлы соединены потоками `->`\n"
        "     * Для развилок `gateway: id \"Вопрос?\" exclusive` исходящие стрелки ДОЛЖНЫ иметь условия: `id --[Да]--> ...` и `id --[Нет]--> ...`\n"
        "     * Если используется `gateway ... parallel`, потоки ОБЯЗАНЫ сходиться в парный `gateway ... parallel`\n"
        "   - Сопроводи код кратким емким архитектурным пояснением внесенных изменений.\n\n"
        "2. ВОПРОСЫ, КОНСУЛЬТАЦИИ И АНАЛИЗ ПО СХЕМЕ:\n"
        "   Если пользователь задает вопрос о схеме (например: «Кто согласует договор?», «Объясни назначение шлюза», «Сколько шагов в процессе?», «Какие есть риски?», «Поясни нотацию»):\n"
        "   - Дай развернутый, понятный и экспертный ответ на естественном языке с красивым форматированием (маркированные списки, жирный текст).\n"
        "   - В этом случае блок кода ```bac НЕ НУЖЕН и НЕ ТРЕБУЕТСЯ! Не возвращай блок кода, если пользователь не просил менять схему."
    )

    return "\n\n".join(sections)
