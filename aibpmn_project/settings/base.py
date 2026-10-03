import os
from pathlib import Path
from dotenv import load_dotenv

# BASE_DIR points to repository root (settings -> aibpmn_project -> repo root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load .env from project root if it exists
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-aibpmn-architecture-suite-2026-key')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'architect',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'architect.backends.AutoBootstrapAdminMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'architect.backends.AdminAutoCreateBackend',
]

ROOT_URLCONF = 'aibpmn_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'aibpmn_project.wsgi.application'
ASGI_APPLICATION = 'aibpmn_project.asgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'architect' / 'static',
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Knowledge Base directory and limits
KNOWLEDGE_BASE_DIR = BASE_DIR / 'knowledge_base'
MAX_KB_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB

# GigaChat settings
GIGACHAT_AUTH_KEY = os.getenv('GIGACHAT_AUTH_KEY', '')
GIGACHAT_SCOPE = os.getenv('GIGACHAT_SCOPE', 'GIGACHAT_API_PERS')
GIGACHAT_CLIENT_ID = os.getenv('GIGACHAT_CLIENT_ID', '')
GIGACHAT_CLIENT_SECRET = os.getenv('GIGACHAT_CLIENT_SECRET', '')
GIGACHAT_MODEL = os.getenv('GIGACHAT_MODEL', 'GigaChat-3-Ultra')

