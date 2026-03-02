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


from .models import SESION_TOUR, TURISTA, UBICACION_VIVO, TURISTASESION, MENSAJE_CHAT

def _is_authenticated(request):
	return request.user.is_authenticated



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
    
    es_turista = hasattr(request.user, 'turista') and request.user.turista in sesion.turistas.all()
    es_guia = False
    try:
        if sesion.ruta.guia.user.user == request.user:
            es_guia = True
    except AttributeError:
        pass

    if not es_turista and not es_guia:
        return redirect('tours:pantalla_unirse')
    
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
        'paradas': paradas,
        'paradas_json': paradas_json,
        'is_anonymous': False,
        'es_guia': es_guia,  # <--- Añadir esto
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
@require_http_methods(["GET"])
def crear_sesion(request):
	"""
	Crear una nueva SESION_TOUR para la ruta indicada por el parametro id.
	"""
	ruta_id = request.GET.get('ruta_id')
	if not ruta_id:
		return JsonResponse({'error': 'Parámetro ruta_id requerido.'}, status=400)

	try:
		from rutas.models import Ruta
		ruta = Ruta.objects.get(id=ruta_id)
	except Exception:
		return JsonResponse({'error': 'Ruta no encontrada.'}, status=404)
	
	es_guia = False
	try:
		if hasattr(ruta, 'guia') and ruta.guia and hasattr(ruta.guia, 'user') and hasattr(ruta.guia.user, 'user'):
			es_guia = (ruta.guia.user.user == request.user)
	except Exception:
		es_guia = False

	if not es_guia:
		return JsonResponse({'error': 'No autorizado para crear sesión para esta ruta.'}, status=403)

	try:
		codigo = _generate_unique_access_code()
		sesion = SESION_TOUR.objects.create(
			codigo_acceso=codigo,
			estado='en_curso',
			fecha_inicio=timezone.now(),
			ruta=ruta
		)

		from django.urls import reverse
		return redirect(reverse('tours:guia_sesion', args=[sesion.id]))

	except Exception as e:
		return JsonResponse({'error': f'Error creando sesión: {str(e)}'}, status=500)


@login_required
def guia_sesion(request, sesion_id):
	"""
	Panel para el guía que creó la sesión.
	"""
	sesion = get_object_or_404(SESION_TOUR, id=sesion_id)

	es_guia = False
	try:
		if hasattr(sesion.ruta, 'guia') and sesion.ruta.guia and hasattr(sesion.ruta.guia, 'user') and hasattr(sesion.ruta.guia.user, 'user'):
			es_guia = (sesion.ruta.guia.user.user == request.user)
	except Exception:
		es_guia = False

	if not es_guia:
		return JsonResponse({'error': 'No autorizado para ver esta página.'}, status=403)

	return render(request, 'tours/guia_sesion.html', {'sesion': sesion})


@login_required
@require_POST
def regenerar_codigo(request, sesion_id):
	"""
	Genera un nuevo codigo_acceso único para la sesión.
	"""
	try:
		sesion = SESION_TOUR.objects.get(id=sesion_id)
	except SESION_TOUR.DoesNotExist:
		return JsonResponse({'error': 'Sesión no encontrada.'}, status=404)

	es_guia = False
	try:
		if hasattr(sesion.ruta, 'guia') and sesion.ruta.guia and hasattr(sesion.ruta.guia, 'user') and hasattr(sesion.ruta.guia.user, 'user'):
			es_guia = (sesion.ruta.guia.user.user == request.user)
	except Exception:
		es_guia = False

	if not es_guia:
		return JsonResponse({'error': 'No autorizado.'}, status=403)

	nuevo_codigo = _generate_unique_access_code()
	sesion.codigo_acceso = nuevo_codigo
	sesion.save(update_fields=['codigo_acceso'])

	return JsonResponse({'codigo_acceso': nuevo_codigo}, status=200)


@login_required
@require_POST
def cerrar_acceso(request, sesion_id):
	"""
	Cierra el acceso a la sesión.
	"""
	try:
		sesion = SESION_TOUR.objects.get(id=sesion_id)
	except SESION_TOUR.DoesNotExist:
		return JsonResponse({'error': 'Sesión no encontrada.'}, status=404)

	es_guia = False
	try:
		if hasattr(sesion.ruta, 'guia') and sesion.ruta.guia and hasattr(sesion.ruta.guia, 'user') and hasattr(sesion.ruta.guia.user, 'user'):
			es_guia = (sesion.ruta.guia.user.user == request.user)
	except Exception:
		es_guia = False

	if not es_guia:
		return JsonResponse({'error': 'No autorizado.'}, status=403)

	sesion.estado = 'finalizado'
	sesion.save(update_fields=['estado'])

	try:
		TURISTASESION.objects.filter(sesion_tour=sesion, activo=True).update(activo=False)
	except Exception:
		pass

	return JsonResponse({'status': 'cerrado'}, status=200)


@login_required
def participantes_sesion(request, sesion_id):
	"""
	Devuelve la lista de turistas activos en la sesión.
	"""
	try:
		sesion = SESION_TOUR.objects.get(id=sesion_id)
	except SESION_TOUR.DoesNotExist:
		return JsonResponse({'error': 'Sesión no encontrada.'}, status=404)

	es_guia = False
	try:
		if hasattr(sesion.ruta, 'guia') and sesion.ruta.guia and hasattr(sesion.ruta.guia, 'user') and hasattr(sesion.ruta.guia.user, 'user'):
			es_guia = (sesion.ruta.guia.user.user == request.user)
	except Exception:
		es_guia = False

	if not es_guia:
		return JsonResponse({'error': 'No autorizado.'}, status=403)

	participantes_qs = TURISTASESION.objects.filter(sesion_tour=sesion, activo=True).select_related('turista')
	participantes = []
	for ts in participantes_qs:
		participantes.append({
			'id': ts.turista.id,
			'alias': ts.turista.alias,
			'fecha_union': ts.fecha_union.isoformat(),
		})

	return JsonResponse({'participantes': participantes}, status=200)


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

	# Validar que la sesión esté activa (en curso)
	if sesion.estado != 'en_curso':
		return JsonResponse({'error': 'La sesión no está activa.'}, status=400)

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

	# Verificar que el usuario es el guía de la ruta o un turista unido a la sesión
	es_guia = False
	es_turista = False

	# Verificar si es el guía
	try:
		if sesion.ruta.guia.user.user == request.user:
			es_guia = True
	except AttributeError:
		pass

	# Verificar si es un turista registrado en esta sesión
	if not es_guia:
		if hasattr(request.user, 'turista'):
			es_turista = sesion.turistas.filter(id=request.user.turista.id).exists()

	# Si no es ni guía ni turista, denegamos el acceso
	if not es_guia and not es_turista:
		return JsonResponse(
			{'error': 'No tienes permiso para registrar ubicaciones en esta sesión.'},
			status=403,
		)

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

@login_required
def obtener_ubicacion_guia(request, sesion_id):
    """
    Devuelve la última ubicación registrada del guía de la sesión.
    """
    sesion = get_object_or_404(SESION_TOUR, id=sesion_id)
    
    # Identificamos al usuario que es el guía de la ruta
    try:
        guia_user = sesion.ruta.guia.user.user
    except AttributeError:
        return JsonResponse({'error': 'No se pudo identificar al guía de esta ruta.'}, status=404)

    # Obtenemos su ubicación más reciente en esta sesión específica
    ultima_ubi = UBICACION_VIVO.objects.filter(
        sesion_tour=sesion,
        usuario=guia_user
    ).order_by('-timestamp').first()

    if ultima_ubi and ultima_ubi.coordenadas:
        return JsonResponse({
            'lat': ultima_ubi.coordenadas.y,
            'lng': ultima_ubi.coordenadas.x,
            'timestamp': ultima_ubi.timestamp.isoformat()
        })
    
    return JsonResponse({'error': 'El guía aún no ha compartido su ubicación.'}, status=404)

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
		'paradas': paradas,
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

