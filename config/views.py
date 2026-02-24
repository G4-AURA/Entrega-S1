

from django.conf import settings
from django.shortcuts import redirect, render


def home_router(request):
    """
    Vista principal '/' que redirige a los usuarios según su rol.
    """
    # 1. Si el usuario no ha iniciado sesión, lo mandamos al login 
    # (temporalmente usamos el login del admin de Django para que puedas probar)
    if not request.user.is_authenticated:
        return redirect('/admin/login/?next=/')

    # 2. Comprobamos si el usuario tiene el perfil de 'turista'
    if hasattr(request.user, 'turista'):
        # Es turista: lo mandamos a su panel de Mis Tours
        return redirect('tours:pantalla_unirse')
    
    # 3. Si no es turista (es decir, es un Guía o el Superusuario) 
    # le mostramos el mapa principal del guía
    context = {
        'MAPBOX_ACCESS_TOKEN': getattr(settings, 'MAPBOX_ACCESS_TOKEN', '')
    }
    return render(request, 'mapa.html', context)