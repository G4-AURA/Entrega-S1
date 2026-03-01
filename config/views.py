

from django.conf import settings
from django.shortcuts import redirect, render


def home_router(request):
    """
    Vista principal '/' que redirige a los usuarios según su rol.
    """
    # 1. Si el usuario no ha iniciado sesión, lo mandamos al login
    if not request.user.is_authenticated:
        return redirect('login')

    # 2. Comprobamos si el usuario tiene el perfil de 'turista'
    if hasattr(request.user, 'turista'):
        # Es turista: lo mandamos a su panel de Mis Tours
        return redirect('tours:pantalla_unirse')
    
    # 3. Si el usuario tiene el perfil de 'guia'
    if hasattr(request.user, 'guia'):
        # Es guía: lo mandamos a la selección de tipo de ruta (su home)
        return redirect('creacion:seleccion_tipo_ruta')
    
    # 4. Si no es ni turista ni guía (superusuario u otro rol)
    # le mostramos el mapa principal
    context = {
        'MAPBOX_ACCESS_TOKEN': getattr(settings, 'MAPBOX_ACCESS_TOKEN', '')
    }
    return render(request, 'mapa.html', context)