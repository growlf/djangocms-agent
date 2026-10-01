"""URL configuration for the default site: copy to ``__PROJECT_NAME__/urls.py`` (or merge).

Order matters: admindocs must come before admin/ or the admin catch-all swallows it, and the
cms.urls include must be last because it matches everything.

admindocs prefix: Django's own documented default is ``admin/doc/``; this site uses ``admin/docs/``
(the prefix the skill documents). Pick one and use it consistently.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/docs/', include('django.contrib.admindocs.urls')),
    path('admin/', admin.site.urls),
]
if settings.DEBUG:
    urlpatterns += [path('__debug__/', include('debug_toolbar.urls'))]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)  # dev-only media
urlpatterns += [path('', include('cms.urls'))]
