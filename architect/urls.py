from django.urls import path
from . import views

urlpatterns = [
    # Main IDE View
    path('', views.index_view, name='index'),

    # Status API
    path('api/status/', views.api_status, name='api_status'),

    # Projects
    path('api/projects/', views.api_projects, name='api_projects'),
    path('api/projects/<int:project_id>/', views.api_project_detail, name='api_project_detail'),

    # Diagrams
    path('api/diagrams/', views.api_diagrams, name='api_diagrams'),
    path('api/diagrams/<int:diagram_id>/', views.api_diagram_detail, name='api_diagram_detail'),

    # Messages (History, Single delete, Bulk delete, Clear)
    path('api/diagrams/<int:diagram_id>/messages/', views.api_messages, name='api_messages'),

    # GigaChat Generation & Refinement
    path('api/generate/', views.api_generate, name='api_generate'),
    path('api/refine/', views.api_refine, name='api_refine'),

    # Knowledge Base
    path('api/kb/', views.api_kb_files_list, name='api_kb_files_list'),
    path('api/kb/upload/', views.api_kb_upload, name='api_kb_upload'),
    path('api/kb/<str:filename>/', views.api_kb_file_detail, name='api_kb_file_detail'),

    # DSL Compilation / Validation
    path('api/compile/', views.api_compile, name='api_compile'),

    # Authentication & Profile API
    path('api/auth/register/', views.api_register, name='api_register'),
    path('api/auth/login/', views.api_login, name='api_login'),
    path('api/auth/logout/', views.api_logout, name='api_logout'),
    path('api/auth/me/', views.api_auth_me, name='api_auth_me'),
    path('api/auth/change-password/', views.api_change_password, name='api_change_password'),
    path('api/auth/delete-account/', views.api_delete_account, name='api_delete_account'),

    # SEO & PWA Root Endpoints
    path('robots.txt', views.robots_txt_view, name='robots_txt'),
    path('sitemap.xml', views.sitemap_xml_view, name='sitemap_xml'),
    path('sw.js', views.service_worker_view, name='service_worker'),
    path('manifest.json', views.manifest_view, name='manifest'),
    path('favicon.ico', views.favicon_ico_view, name='favicon_ico'),

    # Legal pages
    path('terms/', views.terms_view, name='terms'),
    path('privacy/', views.privacy_view, name='privacy'),
]
