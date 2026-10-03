from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('architect.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
else:
    static_doc_root = settings.STATIC_ROOT if settings.STATIC_ROOT.exists() else settings.STATICFILES_DIRS[0]
    urlpatterns += [
        re_path(r'^static/(?P<path>.*)$', serve, {'document_root': static_doc_root}),
    ]
