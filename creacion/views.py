from django.shortcuts import render


def seleccion_tipo_ruta(request):
    """Vista para la selección del tipo de ruta (Manual o IA)"""
    return render(request, 'seleccion_tipo_ruta.html')


def creacion_manual(request):
    """Vista para la creación manual de rutas"""
    return render(request, 'creacion_manual.html')
