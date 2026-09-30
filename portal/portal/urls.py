from django.contrib import admin
from django.urls import path, include
from player.views import serve_media

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('users/', include('users.urls')),
    path('media/<path:path>', serve_media, name='serve_media'),
    path('', include('player.urls')),
]
