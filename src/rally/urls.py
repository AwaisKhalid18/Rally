"""Root URL conf. Every route is a Platform route (AGENTS.md §11.4)."""
from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

urlpatterns = [
    path("", include("rally.core.web.urls")),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
