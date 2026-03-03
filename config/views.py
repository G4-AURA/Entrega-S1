from django.conf import settings
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required

from django.shortcuts import render, redirect
from django.contrib.auth import login
from rutas.models import AuthUser, Guia
from .forms import RegistroUsuarioForm 

@login_required
def home_router(request):
    """
    Vista principal '/' que redirige a los usuarios según su rol.
    """
    # 1. Si el usuario no ha iniciado sesión, lo mandamos al login
    if not request.user.is_authenticated:
        return redirect('login')

    # 2. Comprobamos si el usuario tiene el perfil de 'turista' (relación directa)
    if hasattr(request.user, 'turista'):
        # Es turista: lo mandamos a su panel de Mis Tours
        return redirect('tours:pantalla_unirse')
    
    # 3. Si es guía o cualquier otro usuario (superusuario, etc.)
    # le mostramos el mapa principal (home de guías)

    context = {
        'MAPBOX_ACCESS_TOKEN': getattr(settings, 'MAPBOX_ACCESS_TOKEN', '')
    }
    return render(request, 'mapa.html', context)

def registro(request):
    # Si el usuario ya está logueado, se le manda a la home directamente
    if request.user.is_authenticated:
        return redirect('catalogo')

    if request.method == 'POST':
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            auth_user, _ = AuthUser.objects.get_or_create(user=user)
            
            tipo = 'guia'
            if tipo == 'guia':
                Guia.objects.create(user=auth_user)
            else:
                # TODO: implementar la creación de la cuenta de turista
                pass 
    
            login(request, user)

            return redirect('catalogo')
    else:
        form = RegistroUsuarioForm()
        
    return render(request, 'registration/registro.html', {'form': form})