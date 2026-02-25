import json
import secrets
import string

from django.contrib.gis.geos import Point
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required

from .models import SESION_TOUR, TURISTA, UBICACION_VIVO


def _is_authenticated(request):
	return request.user.is_authenticated


def _generate_unique_access_code(length=6):
	alphabet = string.ascii_uppercase + string.digits
	while True:
		code = ''.join(secrets.choice(alphabet) for _ in range(length))
		if not SESION_TOUR.objects.filter(codigo_acceso=code).exists():
			return code

@login_required
def pantalla_unirse_tour(request):

	try:
		# 1. Buscamos el perfil de turista del usuario logueado
		turista = TURISTA.objects.get(user=request.user)
		
		# 2. Buscamos todas las sesiones en las que este turista esté incluido
		# Las ordenamos para que las más recientes salgan primero
		mis_tours = SESION_TOUR.objects.filter(turistas=turista).order_by('-fecha_inicio')
		
	except TURISTA.DoesNotExist:
		turista = None
		mis_tours = []

	# Le pasamos los datos reales a la plantilla HTML
	context = {
		'turista': turista,
		'mis_tours': mis_tours
	}
	
	return render(request, 'inicio_turista.html', context)

@login_required
def mapa_turista(request, sesion_id):
    """
    Vista inmersiva del mapa para un turista dentro de una sesión específica.
    """
    # 1. Buscamos la sesión por su ID. Si no existe, devuelve un error 404 seguro.
    sesion = get_object_or_404(SESION_TOUR, id=sesion_id)
    
    # 2. Seguridad extra: Comprobamos que este turista realmente pertenece a esta sesión
    if not hasattr(request.user, 'turista') or request.user.turista not in sesion.turistas.all():
        return redirect('tours:pantalla_unirse') # Si intenta colarse, lo devolvemos a su panel
    
    # 3. Preparamos los datos para enviarlos al HTML
    context = {
        'sesion': sesion,
        #'ruta': sesion.ruta,
    }
    
    return render(request, 'turista_mapa.html', context)

@require_POST
def iniciar_tour(request, sesion_id):
	if not _is_authenticated(request):
		return JsonResponse({'error': 'Autenticación requerida.'}, status=401)

	try:
		sesion = SESION_TOUR.objects.get(id=sesion_id)
	except SESION_TOUR.DoesNotExist:
		return JsonResponse({'error': 'Sesión no encontrada.'}, status=404)

	if sesion.estado == 'finalizado':
		return JsonResponse({'error': 'No se puede iniciar una sesión finalizada.'}, status=400)

	sesion.estado = 'en_curso'
	sesion.fecha_inicio = timezone.now()
	sesion.codigo_acceso = _generate_unique_access_code()
	sesion.save(update_fields=['estado', 'fecha_inicio', 'codigo_acceso'])

	return JsonResponse(
		{
			'message': 'Tour iniciado correctamente.',
			'sesion_id': sesion.id,
			'estado': sesion.estado,
			'codigo_acceso': sesion.codigo_acceso,
		},
		status=200,
	)


@require_POST
def unirse_tour(request):
	if not _is_authenticated(request):
		return JsonResponse({'error': 'Autenticación requerida.'}, status=401)

	try:
		body = json.loads(request.body or '{}')
	except json.JSONDecodeError:
		return JsonResponse({'error': 'JSON inválido.'}, status=400)

	codigo_acceso = body.get('codigo_acceso') or request.POST.get('codigo_acceso')
	if not codigo_acceso:
		return JsonResponse({'error': 'El campo codigo_acceso es obligatorio.'}, status=400)

	try:
		turista = TURISTA.objects.get(user=request.user)
	except TURISTA.DoesNotExist:
		return JsonResponse({'error': 'El usuario autenticado no tiene perfil de turista.'}, status=403)

	try:
		sesion = SESION_TOUR.objects.get(codigo_acceso=codigo_acceso)
	except SESION_TOUR.DoesNotExist:
		return JsonResponse({'error': 'Código de acceso inválido.'}, status=404)

	sesion.turistas.add(turista)

	return JsonResponse(
		{
			'message': 'Te has unido al tour correctamente.',
			'sesion_id': sesion.id,
			'codigo_acceso': sesion.codigo_acceso,
		},
		status=200,
	)


@require_POST
def registrar_ubicacion(request):
	if not _is_authenticated(request):
		return JsonResponse({'error': 'Autenticación requerida.'}, status=401)

	try:
		body = json.loads(request.body or '{}')
	except json.JSONDecodeError:
		return JsonResponse({'error': 'JSON inválido.'}, status=400)

	latitud = body.get('latitud')
	longitud = body.get('longitud')
	sesion_id = body.get('sesion_id')

	if latitud is None or longitud is None or sesion_id is None:
		return JsonResponse(
			{'error': 'Los campos sesion_id, latitud y longitud son obligatorios.'},
			status=400,
		)

	try:
		latitud = float(latitud)
		longitud = float(longitud)
	except (TypeError, ValueError):
		return JsonResponse({'error': 'Latitud/longitud deben ser numéricas.'}, status=400)

	if not (-90 <= latitud <= 90) or not (-180 <= longitud <= 180):
		return JsonResponse({'error': 'Coordenadas fuera de rango válido.'}, status=400)

	try:
		sesion = SESION_TOUR.objects.get(id=sesion_id)
	except SESION_TOUR.DoesNotExist:
		return JsonResponse({'error': 'Sesión no encontrada.'}, status=404)

	ubicacion = UBICACION_VIVO.objects.create(
		coordenadas=Point(longitud, latitud, srid=4326),
		timestamp=timezone.now(),
		sesion_tour=sesion,
		usuario=request.user,
	)

	return JsonResponse(
		{
			'message': 'Ubicación registrada correctamente.',
			'ubicacion_id': ubicacion.id,
			'sesion_id': sesion.id,
			'latitud': latitud,
			'longitud': longitud,
			'timestamp': ubicacion.timestamp.isoformat(),
		},
		status=201,
	)


