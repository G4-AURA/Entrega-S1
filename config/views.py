"""config/views.py"""
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from rutas.models import AuthUser, Guia
from .forms import RegistroUsuarioForm


@login_required
def home_router(request):
    """
    Redirige a los usuarios autenticados según su rol.
    Turistas ya no tienen cuenta — cualquier usuario logueado es un guía
    (o superusuario), por lo que todos van al catálogo.
    """
    return redirect("catalogo")


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