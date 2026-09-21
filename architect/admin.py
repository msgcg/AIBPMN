from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Project, Diagram, ChatMessage, KnowledgeBaseFile

# ─── Настройка заголовков панели управления ─────────────────────────────────
admin.site.site_header = "AIBPMN Architect — Панель управления"
admin.site.site_title = "AIBPMN Admin"
admin.site.index_title = "Управление платформой, проектами и базой знаний"


# ─── Inlines ───────────────────────────────────────────────────────────────

class DiagramInline(admin.TabularInline):
    model = Diagram
    extra = 0
    fields = ('name', 'diagram_link', 'messages_count_display', 'updated_at')
    readonly_fields = ('diagram_link', 'messages_count_display', 'updated_at')
    show_change_link = True

    def diagram_link(self, obj):
        if obj.id:
            url = reverse('admin:architect_diagram_change', args=[obj.id])
            return format_html('<a href="{}">Редактировать диаграмму</a>', url)
        return "-"
    diagram_link.short_description = "Переход"

    def messages_count_display(self, obj):
        return obj.messages.count()
    messages_count_display.short_description = "Сообщений чата"


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    fields = ('role_badge', 'content_preview', 'has_dsl', 'is_error', 'created_at')
    readonly_fields = ('role_badge', 'content_preview', 'has_dsl', 'is_error', 'created_at')
    can_delete = True

    def role_badge(self, obj):
        colors = {
            'user': '#3b82f6',
            'assistant': '#8b5cf6',
            'system': '#64748b'
        }
        color = colors.get(obj.role, '#64748b')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
            color, obj.get_role_display()
        )
    role_badge.short_description = "Роль"

    def content_preview(self, obj):
        return (obj.content[:80] + '...') if len(obj.content) > 80 else obj.content
    content_preview.short_description = "Сообщение"

    def has_dsl(self, obj):
        return bool(obj.dsl_code.strip())
    has_dsl.boolean = True
    has_dsl.short_description = "DSL код"


# ─── Model Admins ──────────────────────────────────────────────────────────

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'user_badge', 'diagrams_count_display', 'created_at', 'updated_at')
    list_filter = ('user', 'created_at', 'updated_at')
    search_fields = ('name', 'description', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [DiagramInline]
    ordering = ('-updated_at',)

    def user_badge(self, obj):
        if obj.user:
            return format_html(
                '<span style="background-color: #0284c7; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{}</span>',
                obj.user.username
            )
        return format_html('<span style="color: #94a3b8; font-style: italic;">Общий / Без владельца</span>')
    user_badge.short_description = "Владелец"

    def diagrams_count_display(self, obj):
        count = obj.diagrams.count()
        return format_html('<b>{}</b> диаграмм', count)
    diagrams_count_display.short_description = "Количество диаграмм"


@admin.register(Diagram)
class DiagramAdmin(admin.ModelAdmin):
    list_display = ('name', 'project_link', 'user_display', 'messages_count_display', 'has_bpmn_xml', 'updated_at')
    list_filter = ('project__user', 'created_at', 'updated_at')
    search_fields = ('name', 'description', 'dsl_code', 'project__name', 'project__user__username')
    readonly_fields = ('created_at', 'updated_at', 'xml_preview')
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'project', 'description')
        }),
        ('Код процесса (BPMN-as-Code)', {
            'fields': ('dsl_code',)
        }),
        ('Скомпилированный BPMN 2.0 XML', {
            'classes': ('collapse',),
            'fields': ('xml_preview', 'bpmn_xml')
        }),
        ('Системные даты', {
            'fields': ('created_at', 'updated_at')
        })
    )
    inlines = [ChatMessageInline]
    ordering = ('-updated_at',)

    def project_link(self, obj):
        url = reverse('admin:architect_project_change', args=[obj.project_id])
        return format_html('<a href="{}"><b>{}</b></a>', url, obj.project.name)
    project_link.short_description = "Проект"

    def user_display(self, obj):
        return obj.project.user.username if obj.project.user else "—"
    user_display.short_description = "Пользователь"

    def messages_count_display(self, obj):
        return obj.messages.count()
    messages_count_display.short_description = "Сообщений"

    def has_bpmn_xml(self, obj):
        return bool(obj.bpmn_xml.strip())
    has_bpmn_xml.boolean = True
    has_bpmn_xml.short_description = "BPMN XML"

    def xml_preview(self, obj):
        if not obj.bpmn_xml:
            return "XML отсутствует"
        preview = obj.bpmn_xml[:500] + ('...' if len(obj.bpmn_xml) > 500 else '')
        return format_html('<pre style="max-height: 200px; overflow-y: auto; background: #1e293b; color: #f8fafc; padding: 8px; border-radius: 4px;">{}</pre>', preview)
    xml_preview.short_description = "Предпросмотр XML"


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'diagram_link', 'role_badge', 'content_preview', 'has_dsl', 'is_error', 'created_at')
    list_filter = ('role', 'is_error', 'created_at')
    search_fields = ('content', 'dsl_code', 'explanation', 'diagram__name')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

    def diagram_link(self, obj):
        url = reverse('admin:architect_diagram_change', args=[obj.diagram_id])
        return format_html('<a href="{}">{}</a>', url, obj.diagram.name)
    diagram_link.short_description = "Диаграмма"

    def role_badge(self, obj):
        colors = {
            'user': '#2563eb',
            'assistant': '#7c3aed',
            'system': '#475569'
        }
        color = colors.get(obj.role, '#475569')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
            color, obj.get_role_display()
        )
    role_badge.short_description = "Роль"

    def content_preview(self, obj):
        return (obj.content[:100] + '...') if len(obj.content) > 100 else obj.content
    content_preview.short_description = "Текст сообщения"

    def has_dsl(self, obj):
        return bool(obj.dsl_code.strip())
    has_dsl.boolean = True
    has_dsl.short_description = "DSL код"


@admin.register(KnowledgeBaseFile)
class KnowledgeBaseFileAdmin(admin.ModelAdmin):
    list_display = ('name', 'user_badge', 'file_type', 'formatted_size', 'created_at', 'updated_at')
    list_filter = ('file_type', 'user', 'created_at')
    search_fields = ('name', 'user__username')
    readonly_fields = ('file_size', 'created_at', 'updated_at', 'text_preview')
    fieldsets = (
        ('Информация о файле', {
            'fields': ('name', 'user', 'file_type', 'file_size')
        }),
        ('Содержимое', {
            'fields': ('text_preview', 'content_base64')
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at')
        })
    )
    ordering = ('-updated_at',)

    def user_badge(self, obj):
        if obj.user:
            return format_html(
                '<span style="background-color: #059669; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{}</span>',
                obj.user.username
            )
        return format_html('<span style="color: #64748b; font-style: italic;">Системный / Общий</span>')
    user_badge.short_description = "Пользователь"

    def formatted_size(self, obj):
        size = obj.file_size
        if size < 1024:
            return f"{size} Б"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} КБ"
        return f"{size / (1024 * 1024):.2f} МБ"
    formatted_size.short_description = "Размер"

    def text_preview(self, obj):
        text = obj.get_text_content()
        if not text:
            return "Пустой или бинарный файл"
        preview = text[:800] + ('...' if len(text) > 800 else '')
        return format_html('<pre style="max-height: 250px; overflow-y: auto; background: #0f172a; color: #e2e8f0; padding: 10px; border-radius: 6px; font-family: monospace;">{}</pre>', preview)
    text_preview.short_description = "Текстовый предпросмотр"

