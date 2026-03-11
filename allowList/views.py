"""
allowlist/views.py

Vistas del panel de administración de la Allowlist de POIs.
Acceso restringido a superusuarios mediante el decorador @superuser_required.

Endpoints:
  GET  /allowlist/                        → panel principal (listado)
  GET  /allowlist/buscar-osm/             → módulo de curación asistida
  POST /allowlist/api/buscar-osm/         → ejecuta búsqueda Overpass
  POST /allowlist/api/importar-osm/       → importa selección desde OSM
  GET  /allowlist/nuevo/                  → módulo de creación manual
  POST /allowlist/api/crear-manual/       → crea POI manual
  POST /allowlist/api/eliminar/<id>/      → elimina POI
  GET  /allowlist/api/listar/             → listado JSON paginado
"""
import json
import logging
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import services
from .models import CategoriaOSM, POI

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Guardia: solo superusuarios
# ─────────────────────────────────────────────────────────────────────────────

def superuser_required(view_func):
    """Decorador que exige que el usuario sea superusuario autenticado."""
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            return JsonResponse(
                {'status': 'ERROR', 'mensaje': 'Acceso restringido a administradores.'},
                status=403,
            )
        return view_func(request, *args, **kwargs)
    return _wrapped


def superuser_required_html(view_func):
    """Versión del guardia que redirige a login para vistas HTML."""
    from django.contrib.auth.views import redirect_to_login
    from django.shortcuts import redirect

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_superuser:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden('Acceso denegado: área exclusiva para administradores.')
        return view_func(request, *args, **kwargs)
    return _wrapped


# ─────────────────────────────────────────────────────────────────────────────
# Vistas HTML
# ─────────────────────────────────────────────────────────────────────────────

@superuser_required_html
@require_GET
def panel_allowlist(request):
    """Panel principal: listado de POIs con filtros y paginación."""
    context = {
        'categorias': CategoriaOSM.choices,
        'fuentes':    POI.Fuente.choices,
        'total_pois': POI.objects.count(),
        'total_osm':  POI.objects.filter(fuente=POI.Fuente.OSM).count(),
        'total_manual': POI.objects.filter(fuente=POI.Fuente.MANUAL).count(),
    }
    return render(request, 'allowlist/panel.html', context)


@superuser_required_html
@require_GET
def vista_buscar_osm(request):
    """Módulo de curación asistida: formulario + resultados OSM."""
    context = {
        'categorias': CategoriaOSM.choices,
    }
    return render(request, 'allowlist/buscar_osm.html', context)


@superuser_required_html
@require_GET
def vista_crear_manual(request):
    """Módulo de alta manual: formulario de creación individual."""
    context = {
        'categorias': CategoriaOSM.choices,
    }
    return render(request, 'allowlist/crear_manual.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# API JSON
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
@superuser_required
def api_buscar_osm(request):
    """
    POST /allowlist/api/buscar-osm/
    Body JSON: { ciudad, categorias: [...], radio_km }
    Response:  { status, resultados: [...], total }
    """
    try:
        datos = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'JSON inválido.'}, status=400)

    ciudad     = str(datos.get('ciudad') or '').strip()
    categorias = datos.get('categorias') or []
    pais       = str(datos.get('pais') or '').strip()

    if not isinstance(categorias, list):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'categorias debe ser una lista.'}, status=400)

    try:
        resultados = services.buscar_pois_osm(ciudad, categorias, pais=pais)
    except services.ErrorValidacionPOI as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=400)
    except services.ErrorIntegracionOSM as exc:
        logger.warning('Error Overpass API: %s', exc)
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=502)

    return JsonResponse({
        'status':     'OK',
        'resultados': resultados,
        'total':      len(resultados),
    })


@csrf_exempt
@require_POST
@superuser_required
def api_importar_osm(request):
    """
    POST /allowlist/api/importar-osm/
    Body JSON: { ciudad, elementos: [{osm_id, osm_type, nombre, lat, lon, categoria}, ...] }
    Response:  { status, creados, ya_existian, errores }
    """
    try:
        datos = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'JSON inválido.'}, status=400)

    ciudad    = str(datos.get('ciudad') or '').strip()
    elementos = datos.get('elementos') or []

    if not isinstance(elementos, list) or not elementos:
        return JsonResponse({'status': 'ERROR', 'mensaje': 'Debes seleccionar al menos un elemento.'}, status=400)

    try:
        resultado = services.importar_pois_desde_osm(elementos, ciudad)
    except services.ErrorValidacionPOI as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=400)
    except services.ErrorPersistenciaPOI as exc:
        logger.exception('Error de persistencia al importar POIs OSM')
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=500)

    partes = []
    if resultado['creados']:
        partes.append(f"{resultado['creados']} POI(s) importados correctamente")
    if resultado['ya_existian']:
        partes.append(f"{resultado['ya_existian']} ya existían en la base de datos")
    if resultado['errores']:
        partes.append(f"{resultado['errores']} no pudieron procesarse")

    return JsonResponse({
        'status':  'OK',
        'mensaje': '. '.join(partes) + '.' if partes else 'Sin cambios.',
        **resultado,
    })


@csrf_exempt
@require_POST
@superuser_required
def api_crear_manual(request):
    """
    POST /allowlist/api/crear-manual/
    Body JSON: { nombre, lat, lon, categoria, ciudad?, direccion? }
    Response:  { status, mensaje, poi_id }
    """
    try:
        datos = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'status': 'ERROR', 'mensaje': 'JSON inválido.'}, status=400)

    try:
        poi = services.crear_poi_manual(
            nombre    = datos.get('nombre'),
            lat       = datos.get('lat'),
            lon       = datos.get('lon'),
            categoria = datos.get('categoria'),
            ciudad    = datos.get('ciudad', ''),
            direccion = datos.get('direccion', '')
        )
    except services.ErrorValidacionPOI as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=400)
    except services.ErrorPersistenciaPOI as exc:
        logger.exception('Error de persistencia al crear POI manual')
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=500)

    return JsonResponse({
        'status':  'OK',
        'mensaje': f'POI "{poi.nombre}" creado correctamente.',
        'poi_id':  poi.id,
    }, status=201)


@require_GET
@superuser_required
def api_listar_pois(request):
    """
    GET /allowlist/api/listar/
    Params: ciudad, categoria, fuente, page, limit, solo_activos
    Response: { status, results, total, page, total_pages }
    """
    ciudad      = request.GET.get('ciudad', '')
    categoria   = request.GET.get('categoria', '')
    fuente      = request.GET.get('fuente', '')

    try:
        page  = max(1, int(request.GET.get('page', 1)))
        limit = min(50, max(1, int(request.GET.get('limit', 20))))
    except (TypeError, ValueError):
        page, limit = 1, 20

    datos = services.listar_pois(
        ciudad=ciudad,
        categoria=categoria,
        fuente=fuente,
        page=page,
        limit=limit,
    )
    return JsonResponse({'status': 'OK', **datos})


@csrf_exempt
@require_POST
@superuser_required
def api_eliminar_poi(request, poi_id):
    """
    POST /allowlist/api/eliminar/<poi_id>/
    Response: { status, mensaje }
    """
    try:
        services.eliminar_poi(poi_id)
    except services.ErrorValidacionPOI as exc:
        return JsonResponse({'status': 'ERROR', 'mensaje': str(exc)}, status=404)

    return JsonResponse({'status': 'OK', 'mensaje': 'POI eliminado correctamente.'})