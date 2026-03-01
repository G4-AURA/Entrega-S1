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
from django.urls import include, path
from django.contrib.auth import views as auth_views
from config import views
from tours import views as tours_views
from django.views.generic import TemplateView



urlpatterns = [
    path('admin/', admin.site.urls),
    # Ruta temporal para probar el mapa en la página de inicio
    path('', TemplateView.as_view(template_name='mapa.html'), name='home'),
    # URLs de la app de creación de rutas
    path('crear-ruta/', include('creacion.urls')),
    path('api/ubicacion/', tours_views.registrar_ubicacion, name='api_ubicacion'),
    path('tours/', include('tours.urls')),
    path('', views.home_router, name='home'),
    path('', include('rutas.urls')),
    path('personalizacion/', TemplateView.as_view(template_name='creacion/personalizacion.html'), name='personalizacion'),
    
    # URLs de autenticación
    path('accounts/login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
]
