"""config/views.py"""
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from rutas.models import AuthUser, Guia
from .forms import RegistroUsuarioForm


class SuperuserAwareLoginView(LoginView):
    """
    Evita redirigir a /admin tras login de superusuario.
    Si el `next` apunta al admin, lo sustituye por el panel allowlist.
    """

    template_name = 'registration/login.html'

    def get_success_url(self):
        next_url = self.get_redirect_url()
        user = self.request.user

        if user.is_superuser:
            if next_url and not str(next_url).startswith('/admin'):
                return next_url
            return reverse_lazy('allowlist:panel')

        return next_url or super().get_success_url()


def home_router(request):
    """
    Redirige a los usuarios autenticados según su rol.
    Si no están autenticados, muestra la landing page inicial.
    """
    if request.user.is_authenticated:
        user = request.user

        # 1. Si es Superusuario -> Panel de allowlist
        if user.is_superuser:
            return redirect("allowlist:panel")

        # 2. Si es Guía -> Al catálogo
        if hasattr(user, 'auth_profile') and hasattr(user.auth_profile, 'guia'):
            return redirect("catalogo")

        # 3. Fallback de seguridad
        return redirect("catalogo")

    # Si NO está autenticado, renderizamos la nueva pantalla inicial
    return render(request, "landing.html")


def registro(request):
    """Registro exclusivo para guías."""
    if request.user.is_authenticated:
        return redirect("catalogo")

    if request.method == "POST":
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_user, _ = AuthUser.objects.get_or_create(user=user)
            Guia.objects.create(user=auth_user)
            login(request, user)
            return redirect("catalogo")
    else:
        form = RegistroUsuarioForm()

    return render(request, "registration/registro.html", {"form": form})
