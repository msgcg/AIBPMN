import os

# Automatically select settings module based on DJANGO_ENV or DJANGO_DEBUG
env = os.getenv('DJANGO_ENV', '').lower()
debug_flag = os.getenv('DJANGO_DEBUG', 'True').lower()

if env in ('prod', 'production') or debug_flag in ('false', '0', 'no'):
    from .prod import *
else:
    from .dev import *

