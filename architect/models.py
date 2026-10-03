import base64
from django.db import models
from django.contrib.auth.models import User

class Project(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='projects', verbose_name='Пользователь')
    name = models.CharField('Название проекта', max_length=255)
    description = models.TextField('Описание проекта', blank=True, default='')
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлен', auto_now=True)

    class Meta:
        verbose_name = 'Проект'
        verbose_name_plural = 'Проекты'
        ordering = ['-updated_at']

    def __str__(self):
        return self.name

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'description': self.description,
            'diagrams_count': self.diagrams.count(),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M'),
        }


class KnowledgeBaseFile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='kb_files', verbose_name='Пользователь')
    name = models.CharField('Имя файла', max_length=255)
    file_type = models.CharField('Формат/расширение', max_length=100, default='text/markdown')
    content_base64 = models.TextField('Содержимое Base64', blank=True, default='')
    file_size = models.IntegerField('Размер в байтах', default=0)
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлен', auto_now=True)

    class Meta:
        verbose_name = 'Файл базы знаний'
        verbose_name_plural = 'Файлы базы знаний'
        ordering = ['-updated_at']

    def __str__(self):
        u_name = self.user.username if self.user else 'общий'
        return f"[{u_name}] {self.name}"

    def get_text_content(self) -> str:
        if not self.content_base64:
            return ""
        try:
            raw_bytes = base64.b64decode(self.content_base64.encode('ascii'))
            for enc in ['utf-8', 'utf-8-sig', 'windows-1251', 'cp866']:
                try:
                    return raw_bytes.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw_bytes.decode('utf-8', errors='replace')
        except Exception:
            return ""

    def set_text_content(self, text: str):
        raw_bytes = text.encode('utf-8')
        self.content_base64 = base64.b64encode(raw_bytes).decode('ascii')
        self.file_size = len(raw_bytes)

    def set_binary_content(self, raw_bytes: bytes):
        self.content_base64 = base64.b64encode(raw_bytes).decode('ascii')
        self.file_size = len(raw_bytes)

    def get_binary_content(self) -> bytes:
        if not self.content_base64:
            return b""
        return base64.b64decode(self.content_base64.encode('ascii'))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'size': self.file_size,
            'file_type': self.file_type,
            'modified': self.updated_at.strftime('%Y-%m-%d %H:%M'),
        }


class Diagram(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='diagrams', verbose_name='Проект')
    name = models.CharField('Название диаграммы', max_length=255)
    description = models.TextField('Исходное описание процесса', blank=True, default='')
    dsl_code = models.TextField('Код BPMN-as-Code (DSL)', blank=True, default='')
    bpmn_xml = models.TextField('BPMN 2.0 XML', blank=True, default='')
    svg_preview = models.TextField('SVG миниатюра', blank=True, default='')
    created_at = models.DateTimeField('Создана', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлена', auto_now=True)

    class Meta:
        verbose_name = 'Диаграмма'
        verbose_name_plural = 'Диаграммы'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.project.name} / {self.name}"

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'project_name': self.project.name,
            'name': self.name,
            'description': self.description,
            'dsl_code': self.dsl_code,
            'bpmn_xml': self.bpmn_xml,
            'messages_count': self.messages.count(),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M'),
        }


class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ('user', 'Пользователь'),
        ('assistant', 'GigaChat Архитектор'),
        ('system', 'Системное сообщение'),
    ]

    diagram = models.ForeignKey(Diagram, on_delete=models.CASCADE, related_name='messages', verbose_name='Диаграмма')
    role = models.CharField('Роль', max_length=20, choices=ROLE_CHOICES)
    content = models.TextField('Текст сообщения')
    dsl_code = models.TextField('Сгенерированный DSL код', blank=True, default='')
    explanation = models.TextField('Архитектурное пояснение', blank=True, default='')
    is_error = models.BooleanField('Ошибка генерации', default=False)
    created_at = models.DateTimeField('Время отправки', auto_now_add=True)

    class Meta:
        verbose_name = 'Сообщение чата'
        verbose_name_plural = 'Сообщения чата'
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.role}] {self.content[:40]}"

    def to_dict(self):
        return {
            'id': self.id,
            'diagram_id': self.diagram_id,
            'role': self.role,
            'content': self.content,
            'dsl_code': self.dsl_code,
            'explanation': self.explanation,
            'is_error': self.is_error,
            'created_at': self.created_at.strftime('%H:%M:%S'),
        }


class UserGigaChatCredential(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='gigachat_credential',
        verbose_name='Пользователь'
    )
    auth_key = models.TextField('Авторизационный ключ GigaChat (Base64)', blank=True, default='')
    scope = models.CharField('Scope API', max_length=64, default='GIGACHAT_API_PERS')
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)

    class Meta:
        verbose_name = 'Ключ GigaChat пользователя'
        verbose_name_plural = 'Ключи GigaChat пользователей'
        ordering = ['-updated_at']

    def __str__(self):
        return f"GigaChat Key [{self.user.username}]"

    def masked_key(self) -> str:
        val = (self.auth_key or '').strip()
        if not val:
            return ''
        if len(val) <= 12:
            return '*' * len(val)
        return f"{val[:6]}...{val[-4:]}"

