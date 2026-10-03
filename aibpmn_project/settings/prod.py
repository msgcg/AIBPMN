import os
from .base import *

# Production Configuration
DEBUG = False
ENVIRONMENT = 'production'

# Secret Key from environment
env_secret = os.getenv('DJANGO_SECRET_KEY')
if not env_secret or env_secret == 'django-insecure-aibpmn-architecture-suite-2026-key':
    # Warn in production if using default insecure key
    import warnings
    warnings.warn("Using default or empty DJANGO_SECRET_KEY in production! Please set a strong random key in .env.")
SECRET_KEY = env_secret or SECRET_KEY

# Allowed Hosts from environment (comma-separated: e.g. "example.com,www.example.com")
allowed_hosts_str = os.getenv('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost,0.0.0.0')
ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_str.split(',') if h.strip()]

# CSRF Trusted Origins
csrf_origins_str = os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '')
if csrf_origins_str:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in csrf_origins_str.split(',') if o.strip()]

# Production Database (SQLite by default, or configurable via DATABASE_URL)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Production Security & Cookie Settings (False by default so local HTTP /admin/ login works unless HTTPS is enabled)
SESSION_COOKIE_SECURE = os.getenv('DJANGO_COOKIE_SECURE', 'False').lower() == 'true'
CSRF_COOKIE_SECURE = os.getenv('DJANGO_COOKIE_SECURE', 'False').lower() == 'true'
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # Allows JS CSRF extraction if needed

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

SECURE_SSL_REDIRECT = os.getenv('DJANGO_SECURE_SSL_REDIRECT', 'False').lower() == 'true'
if SECURE_SSL_REDIRECT:
    SECURE_HSTS_SECONDS = int(os.getenv('DJANGO_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Production Logging
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': str(LOGS_DIR / 'django.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
}

