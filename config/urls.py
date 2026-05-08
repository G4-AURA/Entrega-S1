"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.urls import include, path, re_path
from config import views
from tours import views as tours_views
from django.views.generic import TemplateView
from django.views.static import serve
from .views import registro


def favicon_redirect(request):
    static_url = str(settings.STATIC_URL or '/static/')
    if not static_url.endswith('/'):
        static_url = f'{static_url}/'
    if not static_url.startswith(('http://', 'https://', '/')):
        static_url = f'/{static_url}'
    return redirect(f'{static_url}img/logo_aura.png', permanent=True)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('favicon.ico', favicon_redirect),

    # Ruta temporal para probar el mapa en la página de inicio
    # path('', TemplateView.as_view(template_name='mapa.html'), name='home'),
    # URLs de la app de creación de rutas
    path('crear-ruta/', include('creacion.urls')),
    path('api/ubicacion/', tours_views.registrar_ubicacion, name='api_ubicacion'),
    path('tours/', include('tours.urls')),
    path('billing/', include('billing.urls')),
    path('', include('rutas.urls')),
    path('personalizacion/', TemplateView.as_view(template_name='creacion/personalizacion.html'), name='personalizacion'),
    path("allowList/", include("allowList.urls")),
    
    path('accounts/login/', views.SuperuserAwareLoginView.as_view(), name='login'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('registro/', registro, name='registro'),
    path('terminos-de-uso/', TemplateView.as_view(template_name='terminos_y_condiciones.html'), name='terminos_uso'),

# Home router - debe ir al final para que no intercepte otras rutas
    path('', views.home_router, name='home'),
]

# Serve media files whenever local filesystem storage is active.
# `static()` only works with DEBUG=True, so in production-like environments
# we explicitly add a media route when GCS is not configured.
if getattr(settings, "USE_GCS_MEDIA", False):
    pass
elif settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    media_prefix = str(settings.MEDIA_URL).lstrip("/")
    urlpatterns += [
        re_path(
            rf"^{media_prefix}(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        )
    ]
