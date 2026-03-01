import json
import secrets
import string
from datetime import datetime

from django.contrib.gis.geos import Point
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required

from .models import SESION_TOUR, TURISTA, UBICACION_VIVO, MENSAJE_CHAT


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


@require_POST
def enviar_mensaje(request, sesion_id):
	"""
	Endpoint REST para enviar un mensaje en la sesión de tour.
	
	Parámetros POST:
	- texto: El contenido del mensaje (obligatorio)
	
	Respuesta:
	- message_id: ID del mensaje creado
	- remitente: Usuario que envía el mensaje
	- texto: Contenido del mensaje
	- momento: Timestamp del mensaje
	"""
	if not _is_authenticated(request):
		return JsonResponse({'error': 'Autenticación requerida.'}, status=401)

	try:
		body = json.loads(request.body or '{}')
	except json.JSONDecodeError:
		return JsonResponse({'error': 'JSON inválido.'}, status=400)

	texto = body.get('texto', '').strip()
	if not texto:
		return JsonResponse({'error': 'El campo texto es obligatorio y no puede estar vacío.'}, status=400)

	try:
		sesion = SESION_TOUR.objects.get(id=sesion_id)
	except SESION_TOUR.DoesNotExist:
		return JsonResponse({'error': 'Sesión no encontrada.'}, status=404)

	# Validar que el usuario pertenece a la sesión (como guía o turista)
	es_turista = hasattr(request.user, 'turista') and request.user.turista in sesion.turistas.all()
	# Para permitir que el guía también envíe, verificamos si es el propietario de la ruta
	es_guia = False
	if not (es_turista or es_guia):
		return JsonResponse({'error': 'No tienes permiso para enviar mensajes en esta sesión.'}, status=403)
	# o simplemente permitimos que cualquier usuario autenticado envíe en una sesión activa
	
	if sesion.estado != 'en_curso':
		return JsonResponse({'error': 'La sesión debe estar en curso para enviar mensajes.'}, status=400)

	try:
		mensaje = MENSAJE_CHAT.objects.create(
			sesion_tour=sesion,
			remitente=request.user,
			texto=texto
		)

		return JsonResponse(
			{
				'message': 'Mensaje enviado correctamente.',
				'message_id': mensaje.id,
				'remitente': mensaje.remitente.username,
				'texto': mensaje.texto,
				'momento': mensaje.momento.isoformat(),
				'sesion_id': sesion.id,
			},
			status=201,
		)
	except Exception as e:
		return JsonResponse({'error': f'Error al crear el mensaje: {str(e)}'}, status=500)


@require_http_methods(["GET"])
def obtener_mensajes(request, sesion_id):
	"""
	Endpoint REST para obtener mensajes de una sesión (polling).
	
	Parámetros GET:
	- desde: Timestamp ISO para obtener solo mensajes posteriores (opcional)
	- limite: Número máximo de mensajes a devolver (default: 50, máximo: 500)
	
	Respuesta:
	- mensajes: Lista de mensajes con remitente, texto, momento e ID
	- total: Cantidad total de mensajes en la sesión
	"""
	if not _is_authenticated(request):
		return JsonResponse({'error': 'Autenticación requerida.'}, status=401)

	try:
		sesion = SESION_TOUR.objects.select_related('ruta').prefetch_related('turistas').get(id=sesion_id)
	except SESION_TOUR.DoesNotExist:
		return JsonResponse({'error': 'Sesión no encontrada.'}, status=404)

	# Validar que el usuario pertenece a la sesión con una sola consulta
	turistas = [t.user_id for t in sesion.turistas.all()]
	es_turista = request.user.id in turistas
	# Determinar si el usuario es el guía de la ruta de la sesión
	es_guia = False
	if hasattr(sesion.ruta, 'guia'):
		guia = sesion.ruta.guia
		# Navegar hasta el usuario de Django asociado al guía, si existe
		if hasattr(guia, 'user') and hasattr(guia.user, 'user'):
			es_guia = guia.user.user == request.user
	if not (es_turista or es_guia):
		return JsonResponse({'error': 'No tienes permiso para ver los mensajes de esta sesión.'}, status=403)	
	# Obtener parámetros opcionales
	desde = request.GET.get('desde')
	
	# Validar y obtener límite con default de 50 y máximo de 500
	try:
		limite = int(request.GET.get('limite', 50))
		limite = min(max(limite, 1), 500)
	except (ValueError, TypeError):
		limite = 50
	
	mensajes_query = MENSAJE_CHAT.objects.filter(sesion_tour=sesion).order_by('momento')
	
	# Obtener total antes de aplicar el filtro
	total_mensajes = mensajes_query.count()
	
	if desde:
		try:
			# Limpiar el formato de la fecha
			# Convertir +00:00 a Z y luego a +00:00 para fromisoformat
			desde_str = desde.strip()
			
			# fromisoformat de Python no acepta Z, necesita +00:00
			if desde_str.endswith('Z'):
				desde_str = desde_str[:-1] + '+00:00'
			
			# Parsear la fecha
			desde_datetime = datetime.fromisoformat(desde_str)
			
			# Hacer timezone-aware si es naive
			if desde_datetime.tzinfo is None:
				desde_datetime = timezone.make_aware(desde_datetime)
			
			mensajes_query = mensajes_query.filter(momento__gt=desde_datetime)
		except Exception:
			# Si hay error parseando, simplemente no filtrar por fecha
			pass

	mensajes = mensajes_query.values(
		'id',
		'remitente__username',
		'texto',
		'momento'
	)[:limite]

	mensajes_list = list(mensajes)
	return JsonResponse(
		{
			'mensajes': mensajes_list,
			'total': total_mensajes,
			'sesion_id': sesion.id,
		},
		status=200,
	)
