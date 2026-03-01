import json
import secrets
import string

from django.contrib.gis.geos import Point
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required

from .models import SESION_TOUR, TURISTA, UBICACION_VIVO, TURISTASESION


def _generate_unique_access_code(length=6):
	alphabet = string.ascii_uppercase + string.digits
	while True:
		code = ''.join(secrets.choice(alphabet) for _ in range(length))
		if not SESION_TOUR.objects.filter(codigo_acceso=code).exists():
			return code

# =============================================================================
# VISTAS PARA TURISTAS REGISTRADOS (requieren login)
# =============================================================================

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
    
    # 3. Obtener paradas de la ruta
    paradas = sesion.ruta.paradas.all()
    paradas_json = json.dumps([{
        'id': p.id,
        'nombre': p.nombre,
        'orden': p.orden,
        'lat': p.coordenadas.y if p.coordenadas else None,
        'lng': p.coordenadas.x if p.coordenadas else None,
        'es_actual': sesion.parada_actual_id == p.id if sesion.parada_actual_id else False
    } for p in paradas])
    
    # 4. Preparamos los datos para enviarlos al HTML
    context = {
        'sesion': sesion,
        'paradas_json': paradas_json,
        'is_anonymous': False,
    }
    
    return render(request, 'turista_mapa.html', context)


# =============================================================================
# VISTAS PARA GUÍAS (requieren login)
# =============================================================================

@login_required
@require_POST
def iniciar_tour(request, sesion_id):
	"""
	Vista para que un GUÍA inicie un tour.
	"""
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


@login_required
@require_POST
def unirse_tour(request):
	"""
	Vista para que un turista REGISTRADO se una a un tour mediante código de acceso.
	"""
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


@login_required
@require_POST
def registrar_ubicacion(request):
	"""
	Vista para registrar la ubicación de un usuario (GUÍA o TURISTA registrado).
	"""
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


# =============================================================================
# VISTAS PARA TURISTAS ANÓNIMOS (solo requieren token/cookie)
# =============================================================================

def join_tour(request, token):
	"""
	Vista para unirse a un tour mediante token único sin necesidad de registro.
	GET: Muestra formulario para ingresar alias
	POST: Crea turista anónimo y lo vincula a la sesión
	"""
	# Buscar la sesión por token
	try:
		sesion = SESION_TOUR.objects.get(token=token)
	except SESION_TOUR.DoesNotExist:
		return render(request, 'tours/join_error.html', {
			'error': 'Token inválido o sesión no encontrada.'
		}, status=404)
	
	# Si la sesión ya finalizó, no permitir unirse
	if sesion.estado == 'finalizado':
		return render(request, 'tours/join_error.html', {
			'error': 'Esta sesión ya ha finalizado.'
		}, status=400)
	
	# Verificar si el usuario ya tiene cookie y está en esta sesión
	turista_id_cookie = request.session.get('turista_id')
	if turista_id_cookie and request.method == 'GET':
		try:
			turista = TURISTA.objects.get(id=turista_id_cookie)
			if TURISTASESION.objects.filter(turista=turista, sesion_tour=sesion, activo=True).exists():
				# Ya está en la sesión, redirigir al mapa directamente
				return redirect('tours:mapa_turista_anonimo', token=token)
		except TURISTA.DoesNotExist:
			pass
	
	if request.method == 'POST':
		alias = request.POST.get('alias', '').strip()
		
		if not alias:
			return render(request, 'tours/join_tour.html', {
				'sesion': sesion,
				'error': 'El alias es obligatorio.'
			})
		
		# Verificar si el usuario ya tiene una cookie de turista
		turista_id_cookie = request.session.get('turista_id')
		
		# Buscar si ya existe un turista ACTIVO con ese alias en esta sesión
		turista_sesion_existente = TURISTASESION.objects.filter(
			sesion_tour=sesion, 
			turista__alias=alias,
			activo=True  # Solo buscar activos
		).first()
		
		if turista_sesion_existente:
			# Caso 1: Es el mismo turista volviendo (tiene la cookie correcta)
			if turista_id_cookie and turista_sesion_existente.turista.id == turista_id_cookie:
				turista = turista_sesion_existente.turista
			# Caso 2: El alias está siendo usado activamente pero el usuario no tiene cookie
			# Esto puede pasar si cerró el navegador o limpió cookies
			# Desactivamos la sesión anterior como "abandonada" y permitimos continuar
			elif not turista_id_cookie:
				turista_sesion_existente.activo = False
				turista_sesion_existente.save()
				
				# Crear nuevo turista con el mismo alias
				turista = TURISTA.objects.create(
					alias=alias,
					user=None
				)
				TURISTASESION.objects.create(
					turista=turista,
					sesion_tour=sesion,
					activo=True
				)
			# Caso 3: El alias está siendo usado por OTRO usuario con cookie diferente
			else:
				return render(request, 'tours/join_tour.html', {
					'sesion': sesion,
					'error': f'El alias "{alias}" ya está en uso en este tour. Por favor elige otro nombre.'
				})
		else:
			# No hay nadie activo con ese alias, crear nuevo o reutilizar inactivo
			turista_inactivo = TURISTASESION.objects.filter(
				sesion_tour=sesion,
				turista__alias=alias,
				activo=False
			).first()
			
			if turista_inactivo and not turista_id_cookie:
				# Reutilizar el turista inactivo
				turista_inactivo.activo = True
				turista_inactivo.save()
				turista = turista_inactivo.turista
			else:
				# Crear nuevo turista
				turista = TURISTA.objects.create(
					alias=alias,
					user=None
				)
				TURISTASESION.objects.create(
					turista=turista,
					sesion_tour=sesion,
					activo=True
				)
		
		# Guardar el ID del turista en la sesión (cookie)
		request.session['turista_id'] = turista.id
		request.session['turista_alias'] = turista.alias
		
		# Redirigir al mapa del tour
		return redirect('tours:mapa_turista_anonimo', token=token)
	
	# GET: Mostrar formulario
	return render(request, 'tours/join_tour.html', {
		'sesion': sesion
	})


def mapa_turista_anonimo(request, token):
	"""
	Vista del mapa para turistas anónimos (sin cuenta de usuario).
	"""
	# Buscar la sesión por token
	try:
		sesion = SESION_TOUR.objects.get(token=token)
	except SESION_TOUR.DoesNotExist:
		return render(request, 'tours/join_error.html', {
			'error': 'Token inválido o sesión no encontrada.'
		}, status=404)
	
	# Verificar que el turista esté en la sesión (mediante cookie)
	turista_id = request.session.get('turista_id')
	if not turista_id:
		return redirect('tours:join_tour', token=token)
	
	try:
		turista = TURISTA.objects.get(id=turista_id)
		# Verificar que el turista esté efectivamente vinculado a esta sesión
		if not TURISTASESION.objects.filter(turista=turista, sesion_tour=sesion).exists():
			return redirect('tours:join_tour', token=token)
	except TURISTA.DoesNotExist:
		return redirect('tours:join_tour', token=token)
	
	# Obtener paradas de la ruta
	paradas = sesion.ruta.paradas.all()
	paradas_json = json.dumps([{
		'id': p.id,
		'nombre': p.nombre,
		'orden': p.orden,
		'lat': p.coordenadas.y if p.coordenadas else None,
		'lng': p.coordenadas.x if p.coordenadas else None,
		'es_actual': sesion.parada_actual_id == p.id if sesion.parada_actual_id else False
	} for p in paradas])
	
	context = {
		'sesion': sesion,
		'turista': turista,
		'is_anonymous': True,
		'paradas_json': paradas_json,
	}
	
	return render(request, 'turista_mapa.html', context)


def join_tour_by_code(request, codigo):
	"""
	Vista para unirse a un tour mediante código de acceso.
	Redirige al endpoint con token UUID.
	"""
	try:
		sesion = SESION_TOUR.objects.get(codigo_acceso=codigo.upper())
		# Redirigir al endpoint con token
		return redirect('tours:join_tour', token=sesion.token)
	except SESION_TOUR.DoesNotExist:
		return render(request, 'tours/join_error.html', {
			'error': f'Código de acceso "{codigo}" no encontrado. Verifica con tu guía.'
		}, status=404)


