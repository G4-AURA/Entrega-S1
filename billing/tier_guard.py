from dataclasses import dataclass
from functools import wraps
import calendar
import unicodedata

from django.http import JsonResponse
from django.utils import timezone

from rutas.models import Guia, Ruta
from tours.models import SesionTour, TuristaSesion

from .models import FeatureAccessSetting, Subscription, TierUsageEvent


ALLOWED_MOODS_FREEMIUM_ORDERED = (
    Ruta.Mood.HISTORIA,
    Ruta.Mood.NATURALEZA,
    Ruta.Mood.RELIGIOSO_Y_ESPIRITUAL,
    Ruta.Mood.ARQUITECTURA_Y_DISEÑO,
)
ALLOWED_MOODS_FREEMIUM = set(ALLOWED_MOODS_FREEMIUM_ORDERED)

_MOOD_ALIAS_MAP = {
    'historia': Ruta.Mood.HISTORIA,
    'gastronomia': Ruta.Mood.GASTRONOMIA,
    'naturaleza': Ruta.Mood.NATURALEZA,
    'misterio y leyendas': Ruta.Mood.MISTERIO_Y_LEYENDAS,
    'misterio-leyendas': Ruta.Mood.MISTERIO_Y_LEYENDAS,
    'local': Ruta.Mood.LOCAL,
    'cine y series': Ruta.Mood.CINE_Y_SERIES,
    'cine-series': Ruta.Mood.CINE_Y_SERIES,
    'religioso y espiritual': Ruta.Mood.RELIGIOSO_Y_ESPIRITUAL,
    'religioso-espiritual': Ruta.Mood.RELIGIOSO_Y_ESPIRITUAL,
    'arquitectura y diseño': Ruta.Mood.ARQUITECTURA_Y_DISEÑO,
    'arquitectura y diseno': Ruta.Mood.ARQUITECTURA_Y_DISEÑO,
    'arquitectura-diseno': Ruta.Mood.ARQUITECTURA_Y_DISEÑO,
    'ocio/cultural': Ruta.Mood.OCIO_CULTURAL,
    'ocio cultural': Ruta.Mood.OCIO_CULTURAL,
    'ocio-cultural': Ruta.Mood.OCIO_CULTURAL,
}


def _canonical_text_key(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
    compact = ascii_text.replace('_', ' ').replace('-', ' ')
    return ' '.join(compact.lower().strip().split())


def _normalize_mood_or_none(raw_mood: str) -> str | None:
    key = _canonical_text_key(raw_mood)
    if not key:
        return None

    if key in _MOOD_ALIAS_MAP:
        return _MOOD_ALIAS_MAP[key]

    for value, _label in Ruta.Mood.choices:
        if _canonical_text_key(value) == key:
            return value
    return None


def normalize_mood_values(selected_moods: list[str]) -> tuple[set[str], list[str]]:
    normalized_values = set()
    unknown_values = []
    for raw in selected_moods or []:
        if not str(raw or '').strip():
            continue
        normalized = _normalize_mood_or_none(raw)
        if normalized is None:
            unknown_values.append(str(raw))
            continue
        normalized_values.add(normalized)
    return normalized_values, unknown_values

TIER_LIMITS = {
    Guia.Suscripcion.FREEMIUM: {
        'manual_routes_simultaneous': 1,
        'ia_routes_simultaneous': 1,
        'ai_generations_per_month': 3,
        'ai_stop_replacements_per_month': 9,
        'ai_stop_replacements_per_route': 3,
        'max_stops_per_route': 5,
        'session_capacity': 15,
        'max_active_sessions_per_route': 1,
        'curiosity_routes': 3,
    },
    Guia.Suscripcion.PREMIUM: {
        'manual_routes_simultaneous': 10,
        'ia_routes_simultaneous': 10,
        'ai_generations_per_month': 10,
        'ai_stop_replacements_per_month': 30,
        'ai_stop_replacements_per_route': None,
        'max_stops_per_route': 15,
        'session_capacity': 50,
        'max_active_sessions_per_route': None,
        'curiosity_routes': None,
    },
}

FEATURE_ACCESS_DEFINITIONS = (
    {
        'key': 'ai_route_generation',
        'name': 'Generacion de rutas con IA',
        'description': (
            'Controla si el guia puede usar la opcion "Generar con IA" '
            'y ejecutar la generacion.'
        ),
        'default_freemium': True,
        'default_premium': True,
    },
    {
        'key': 'ai_stop_replacement',
        'name': 'Sustitucion con IA de paradas',
        'description': (
            'Permite sustituir una parada de una ruta generada con IA '
            'por otra propuesta por IA.'
        ),
        'default_freemium': True,
        'default_premium': True,
    },
    {
        'key': 'chat_mode_separate',
        'name': 'Chat por separado',
        'description': (
            'El chat grupal sigue disponible siempre. '
            'Este toggle controla el chat privado por turista.'
        ),
        'default_freemium': False,
        'default_premium': True,
    },
    {
        'key': 'scheduled_meetup',
        'name': 'Quedada programada con notificacion',
        'description': 'Controla la funcionalidad de quedada programada para sesiones.',
        'default_freemium': False,
        'default_premium': True,
    },
    {
        'key': 'tourist_proximity_curiosity',
        'name': 'Curiosidad automatica por proximidad',
        'description': (
            'Si esta activa, el turista recibe curiosidades automaticamente '
            'al acercarse a una parada (sin accion manual del guia).'
        ),
        'default_freemium': True,
        'default_premium': True,
    },
    {
        'key': 'payload_wishes',
        'name': 'Campo de deseos con IA',
        'description': (
            'Permite usar el campo "deseos" en la personalizacion '
            'de la generacion con IA.'
        ),
        'default_freemium': False,
        'default_premium': True,
    },
)

FEATURE_ACCESS_DEFAULTS = {
    item['key']: (
        bool(item['default_freemium']),
        bool(item['default_premium']),
    )
    for item in FEATURE_ACCESS_DEFINITIONS
}

FEATURE_ACCESS_NAMES = {
    item['key']: item['name']
    for item in FEATURE_ACCESS_DEFINITIONS
}


@dataclass
class TierRuleViolation(Exception):
    code: str
    message: str
    http_status: int = 403


def tier_error_response(error: TierRuleViolation) -> JsonResponse:
    return JsonResponse(
        {
            'status': 'ERROR',
            'code': error.code,
            'mensaje': error.message,
        },
        status=error.http_status,
    )


def tier_guard(check_fn):
    def decorator(view_fn):
        @wraps(view_fn)
        def wrapped(*args, **kwargs):
            try:
                check_fn(*args, **kwargs)
            except TierRuleViolation as exc:
                return tier_error_response(exc)
            return view_fn(*args, **kwargs)

        return wrapped

    return decorator


def get_feature_access_definitions() -> tuple[dict, ...]:
    return FEATURE_ACCESS_DEFINITIONS


def _coerce_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or '').strip().lower()
    if text in {'1', 'true', 'on', 'yes', 'si'}:
        return True
    if text in {'0', 'false', 'off', 'no'}:
        return False
    return bool(default)


def get_feature_access_rows() -> list[dict]:
    stored_rows: dict[str, dict] = {}
    try:
        keys = [item['key'] for item in FEATURE_ACCESS_DEFINITIONS]
        stored_rows = {
            row['key']: row
            for row in FeatureAccessSetting.objects.filter(key__in=keys).values(
                'key',
                'enabled_freemium',
                'enabled_premium',
            )
        }
    except Exception:
        stored_rows = {}

    rows = []
    for definition in FEATURE_ACCESS_DEFINITIONS:
        default_freemium, default_premium = FEATURE_ACCESS_DEFAULTS[definition['key']]
        stored = stored_rows.get(definition['key']) or {}
        rows.append(
            {
                **definition,
                'enabled_freemium': _coerce_bool(
                    stored.get('enabled_freemium'),
                    default_freemium,
                ),
                'enabled_premium': _coerce_bool(
                    stored.get('enabled_premium'),
                    default_premium,
                ),
            }
        )
    return rows


def update_feature_access(key: str, tier: str, enabled) -> dict:
    key_clean = str(key or '').strip()
    if key_clean not in FEATURE_ACCESS_DEFAULTS:
        raise ValueError('La funcionalidad indicada no existe.')

    tier_clean = str(tier or '').strip().lower()
    if tier_clean not in {'freemium', 'premium'}:
        raise ValueError('El plan indicado no existe.')

    default_freemium, default_premium = FEATURE_ACCESS_DEFAULTS[key_clean]
    current_enabled_freemium, current_enabled_premium = _enabled_flags_for_feature_key(
        key_clean
    )

    enabled_bool = _coerce_bool(enabled, True)
    next_enabled_freemium = (
        enabled_bool if tier_clean == 'freemium' else current_enabled_freemium
    )
    next_enabled_premium = (
        enabled_bool if tier_clean == 'premium' else current_enabled_premium
    )

    FeatureAccessSetting.objects.update_or_create(
        key=key_clean,
        defaults={
            'enabled_freemium': _coerce_bool(next_enabled_freemium, default_freemium),
            'enabled_premium': _coerce_bool(next_enabled_premium, default_premium),
        },
    )
    return {
        'enabled_freemium': _coerce_bool(next_enabled_freemium, default_freemium),
        'enabled_premium': _coerce_bool(next_enabled_premium, default_premium),
    }


def _enabled_flags_for_feature_key(feature_key: str) -> tuple[bool, bool]:
    default_freemium, default_premium = FEATURE_ACCESS_DEFAULTS.get(
        feature_key,
        (True, True),
    )
    try:
        row = (
            FeatureAccessSetting.objects.filter(key=feature_key).values(
                'enabled_freemium',
                'enabled_premium',
            )
            .first()
        )
    except Exception:
        row = None
    if not row:
        return default_freemium, default_premium
    return (
        _coerce_bool(row.get('enabled_freemium'), default_freemium),
        _coerce_bool(row.get('enabled_premium'), default_premium),
    )


def _is_feature_enabled_for_tier(feature_key: str, tier: str) -> bool:
    enabled_freemium, enabled_premium = _enabled_flags_for_feature_key(feature_key)
    if tier == Guia.Suscripcion.FREEMIUM:
        return enabled_freemium
    if tier == Guia.Suscripcion.PREMIUM:
        return enabled_premium
    if str(tier or '').strip().lower() == 'freemium':
        return enabled_freemium
    if str(tier or '').strip().lower() == 'premium':
        return enabled_premium
    return False


def is_feature_enabled_for_tier(feature_key: str, tier: str) -> bool:
    return _is_feature_enabled_for_tier(feature_key, tier)


def _tier_to_human_text(tier: str) -> str:
    if tier == Guia.Suscripcion.FREEMIUM:
        return 'Freemium'
    if tier == Guia.Suscripcion.PREMIUM:
        return 'Premium'
    return 'este plan'


def is_feature_enabled_for_guia(guia: Guia, feature_key: str) -> bool:
    return _is_feature_enabled_for_tier(feature_key, _tier_of(guia))


def ensure_feature_enabled_for_guia(guia: Guia, feature_key: str):
    current_tier = _tier_of(guia)
    if is_feature_enabled_for_guia(guia, feature_key):
        return

    feature_name = FEATURE_ACCESS_NAMES.get(feature_key, feature_key)
    raise TierRuleViolation(
        code='TIER_FORBIDDEN',
        message=(
            f'La funcionalidad "{feature_name}" no esta habilitada '
            f'para {_tier_to_human_text(current_tier)}.'
        ),
        http_status=403,
    )


def is_feature_enabled_for_plan(feature_key: str, plan: str) -> bool:
    plan_clean = str(plan or '').strip()
    if plan_clean == Guia.Suscripcion.FREEMIUM:
        return _is_feature_enabled_for_tier(feature_key, Guia.Suscripcion.FREEMIUM)
    if plan_clean == Guia.Suscripcion.PREMIUM:
        return _is_feature_enabled_for_tier(feature_key, Guia.Suscripcion.PREMIUM)
    return False


def _add_months_preserving_day(dt, months: int):
    total_month = (dt.month - 1) + int(months)
    year = dt.year + (total_month // 12)
    month = (total_month % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, last_day)
    return dt.replace(year=year, month=month, day=day)


def _current_cycle_start(anchor, now):
    if anchor > now:
        return now

    months_diff = (now.year - anchor.year) * 12 + (now.month - anchor.month)
    candidate = _add_months_preserving_day(anchor, months_diff)

    while candidate > now and months_diff > 0:
        months_diff -= 1
        candidate = _add_months_preserving_day(anchor, months_diff)

    while True:
        following = _add_months_preserving_day(candidate, 1)
        if following <= now:
            candidate = following
            continue
        return candidate


def _account_creation_anchor(guia: Guia):
    try:
        date_joined = guia.user.user.date_joined
        if date_joined is not None:
            return date_joined
    except Exception:
        pass
    return timezone.now()


def _premium_success_anchor(guia: Guia):
    subscription = (
        Subscription.objects.filter(
            guia=guia,
            tier=Guia.Suscripcion.PREMIUM,
            status__in=[
                Subscription.Status.ACTIVE,
                Subscription.Status.TRIALING,
                Subscription.Status.PAST_DUE,
            ],
            stripe_subscription_id__isnull=False,
        )
        .exclude(stripe_subscription_id='')
        .order_by('-updated_at', '-id')
        .first()
    )
    if subscription is None:
        return None
    return subscription.current_period_start or subscription.created_at


def get_usage_cycle_window(guia: Guia, now=None):
    current_now = now or timezone.now()
    tier = _tier_of(guia)

    if tier == Guia.Suscripcion.PREMIUM:
        anchor = _premium_success_anchor(guia) or _account_creation_anchor(guia)
    else:
        anchor = _account_creation_anchor(guia)

    cycle_start = _current_cycle_start(anchor, current_now)
    cycle_end = _add_months_preserving_day(cycle_start, 1)
    return cycle_start, cycle_end, anchor


def _tier_of(guia: Guia) -> str:
    tier = getattr(guia, 'tipo_suscripcion', Guia.Suscripcion.FREEMIUM)
    if tier not in TIER_LIMITS:
        return Guia.Suscripcion.FREEMIUM
    return tier


def _limit_for(guia: Guia, key: str):
    return TIER_LIMITS[_tier_of(guia)][key]


def get_allowed_moods_for_guia(guia: Guia | None) -> list[str]:
    if guia is None:
        return [value for value, _label in Ruta.Mood.choices]
    if _tier_of(guia) == Guia.Suscripcion.FREEMIUM:
        return list(ALLOWED_MOODS_FREEMIUM_ORDERED)
    return [value for value, _label in Ruta.Mood.choices]


def get_session_capacity_limit(guia: Guia | None) -> int:
    if guia is None:
        return TIER_LIMITS[Guia.Suscripcion.PREMIUM]['session_capacity']
    return int(_limit_for(guia, 'session_capacity'))


def get_max_stops_per_route_limit(guia: Guia | None) -> int:
    if guia is None:
        return TIER_LIMITS[Guia.Suscripcion.PREMIUM]['max_stops_per_route']
    return int(_limit_for(guia, 'max_stops_per_route'))


def apply_payload_tier_rules(guia: Guia, payload: dict) -> tuple[dict, list[dict]]:
    if not isinstance(payload, dict):
        return payload, []

    warnings = []
    if not is_feature_enabled_for_guia(guia, 'payload_wishes') and payload.get('deseos'):
        payload = dict(payload)
        payload['deseos'] = []
        warnings.append(
            {
                'code': 'TIER_PLAN_REQUIRED',
                'mensaje': (
                    'El campo deseos no esta habilitado para tu plan actual y se ha ignorado.'
                ),
            }
        )
    return payload, warnings


def ensure_routes_quota_available(guia: Guia):
    limit = _limit_for(guia, 'manual_routes_simultaneous') + _limit_for(guia, 'ia_routes_simultaneous')
    current = Ruta.objects.filter(guia=guia).count()
    if current >= limit:
        raise TierRuleViolation(
            code='TIER_LIMIT_REACHED',
            message=(
                f'Has alcanzado el límite de rutas simultáneas de tu plan ({limit}). '
                'Elimina una ruta o mejora a Premium.'
            ),
            http_status=429,
        )


def ensure_manual_routes_quota_available(guia: Guia):
    limit = _limit_for(guia, 'manual_routes_simultaneous')
    current = Ruta.objects.filter(
        guia=guia,
        es_generada_ia=False,
    ).count()
    if current >= limit:
        raise TierRuleViolation(
            code='TIER_LIMIT_REACHED',
            message=(
                f'Has alcanzado el límite de rutas manuales simultáneas ({limit}) '
                'de tu plan.'
            ),
            http_status=429,
        )


def ensure_ia_routes_quota_available(guia: Guia):
    limit = _limit_for(guia, 'ia_routes_simultaneous')
    current = Ruta.objects.filter(
        guia=guia,
        es_generada_ia=True,
    ).count()
    if current >= limit:
        raise TierRuleViolation(
            code='TIER_LIMIT_REACHED',
            message=(
                f'Has alcanzado el límite de rutas IA simultáneas ({limit}) '
                'de tu plan.'
            ),
            http_status=429,
        )


def ensure_route_stop_count_allowed(guia: Guia, stops_count: int):
    limit = _limit_for(guia, 'max_stops_per_route')
    if int(stops_count or 0) > limit:
        raise TierRuleViolation(
            code='TIER_LIMIT_REACHED',
            message=(
                f'El máximo de paradas por ruta en tu plan es {limit}.'
            ),
            http_status=429,
        )


def clamp_generated_stops_to_tier(guia: Guia, stops: list[dict] | None) -> tuple[list[dict], dict | None]:
    current_stops = list(stops) if isinstance(stops, list) else []
    limit = _limit_for(guia, 'max_stops_per_route')
    if len(current_stops) <= limit:
        return current_stops, None

    return current_stops[:limit], {
        'code': 'TIER_LIMIT_APPLIED',
        'mensaje': (
            f'Tu plan permite hasta {limit} paradas por ruta. '
            f'Se han conservado únicamente las primeras {limit} paradas.'
        ),
    }


def _monthly_usage_count(guia: Guia, action: str) -> int:
    cycle_start, cycle_end, _anchor = get_usage_cycle_window(guia)
    return TierUsageEvent.objects.filter(
        guia=guia,
        action=action,
        created_at__gte=cycle_start,
        created_at__lt=cycle_end,
    ).count()


def ensure_ai_generation_allowed(guia: Guia):
    ensure_feature_enabled_for_guia(guia, 'ai_route_generation')
    ensure_ia_routes_quota_available(guia)
    monthly_limit = _limit_for(guia, 'ai_generations_per_month')
    monthly_used = _monthly_usage_count(guia, TierUsageEvent.Action.IA_ROUTE_GENERATION)
    if monthly_used >= monthly_limit:
        raise TierRuleViolation(
            code='TIER_LIMIT_REACHED',
            message=(
                f'Has alcanzado el límite mensual de generaciones IA ({monthly_limit}) '
                'de tu plan actual.'
            ),
            http_status=429,
        )


def ensure_ai_route_confirmation_allowed(guia: Guia):
    ensure_feature_enabled_for_guia(guia, 'ai_route_generation')
    ensure_ia_routes_quota_available(guia)


def ensure_ai_stop_replacement_allowed(guia: Guia, ruta: Ruta):
    ensure_feature_enabled_for_guia(guia, 'ai_stop_replacement')
    monthly_limit = _limit_for(guia, 'ai_stop_replacements_per_month')
    monthly_used = _monthly_usage_count(guia, TierUsageEvent.Action.IA_STOP_REPLACEMENT)
    if monthly_used >= monthly_limit:
        raise TierRuleViolation(
            code='TIER_LIMIT_REACHED',
            message=(
                f'Has alcanzado el límite mensual de sustituciones IA ({monthly_limit}) '
                'de tu plan actual.'
            ),
            http_status=429,
        )

    per_route_limit = _limit_for(guia, 'ai_stop_replacements_per_route')
    if per_route_limit is None:
        return

    per_route_used = TierUsageEvent.objects.filter(
        guia=guia,
        ruta=ruta,
        action=TierUsageEvent.Action.IA_STOP_REPLACEMENT,
    ).count()
    if per_route_used >= per_route_limit:
        raise TierRuleViolation(
            code='TIER_LIMIT_REACHED',
            message=(
                f'Has alcanzado el límite por ruta de sustituciones IA ({per_route_limit}) '
                'en tu plan Freemium.'
            ),
            http_status=429,
        )


def record_ai_generation_usage(guia: Guia):
    TierUsageEvent.objects.create(
        guia=guia,
        action=TierUsageEvent.Action.IA_ROUTE_GENERATION,
    )


def record_ai_stop_replacement_usage(guia: Guia, ruta: Ruta):
    TierUsageEvent.objects.create(
        guia=guia,
        ruta=ruta,
        action=TierUsageEvent.Action.IA_STOP_REPLACEMENT,
    )


def ensure_route_people_count_allowed(guia: Guia, people_count: int):
    limit = _limit_for(guia, 'session_capacity')
    try:
        people_count_int = int(people_count)
    except (TypeError, ValueError):
        return

    if people_count_int > limit:
        raise TierRuleViolation(
            code='TIER_CAPACITY_REACHED',
            message=f'El máximo de turistas por sesión en tu plan es {limit}.',
            http_status=429,
        )


def ensure_route_stop_add_allowed(ruta: Ruta):
    limit = _limit_for(ruta.guia, 'max_stops_per_route')
    current = ruta.paradas.count()
    if current >= limit:
        raise TierRuleViolation(
            code='TIER_LIMIT_REACHED',
            message=(
                f'Has alcanzado el límite de paradas por ruta ({limit}) para tu plan.'
            ),
            http_status=429,
        )


def ensure_moods_allowed(guia: Guia, selected_moods: list[str]):
    if _tier_of(guia) != Guia.Suscripcion.FREEMIUM:
        return

    requested, unknown = normalize_mood_values(selected_moods)
    forbidden = sorted(requested - ALLOWED_MOODS_FREEMIUM)
    if forbidden or unknown:
        raise TierRuleViolation(
            code='TIER_FORBIDDEN',
            message=(
                'Las etiquetas seleccionadas incluyen opciones no permitidas para tu plan. '
                'En Freemium solo están permitidas: Historia, Naturaleza, '
                'Religioso y Espiritual, Arquitectura y Diseño.'
            ),
            http_status=403,
        )


def ensure_session_creation_allowed(ruta: Ruta):
    max_active = _limit_for(ruta.guia, 'max_active_sessions_per_route')
    if max_active is None:
        return

    active_count = SesionTour.objects.filter(
        ruta=ruta,
        estado__in=[SesionTour.PENDIENTE, SesionTour.EN_CURSO],
    ).count()
    if active_count >= max_active:
        raise TierRuleViolation(
            code='TIER_LIMIT_REACHED',
            message=(
                'Tu plan Freemium permite una sesión activa por ruta. '
                'Cierra la sesión actual o mejora a Premium.'
            ),
            http_status=429,
        )


def ensure_session_capacity_available(sesion: SesionTour):
    limit = _limit_for(sesion.ruta.guia, 'session_capacity')
    active_tourists = TuristaSesion.objects.filter(
        sesion_tour=sesion,
        activo=True,
    ).count()
    if active_tourists >= limit:
        raise TierRuleViolation(
            code='TIER_CAPACITY_REACHED',
            message=(
                f'La sesión alcanzó su capacidad máxima ({limit} turistas) para este plan.'
            ),
            http_status=429,
        )


def ensure_chat_mode_allowed(sesion: SesionTour, mode: str):
    mode_clean = str(mode or '').strip().lower()
    if mode_clean in ('', 'comun', 'común', 'common'):
        return
    if mode_clean in ('separado', 'separate'):
        ensure_feature_enabled_for_guia(sesion.ruta.guia, 'chat_mode_separate')
        return
    raise TierRuleViolation(
        code='TIER_FORBIDDEN',
        message='Modo de chat no soportado.',
        http_status=400,
    )


def ensure_curiosity_route_allowed(ruta: Ruta):
    max_routes = _limit_for(ruta.guia, 'curiosity_routes')
    if max_routes is None:
        return

    routes_with_curiosity = Ruta.objects.filter(
        guia=ruta.guia,
        paradas__curiosidad__isnull=False,
    ).distinct()

    if routes_with_curiosity.filter(id=ruta.id).exists():
        return

    if routes_with_curiosity.count() >= max_routes:
        raise TierRuleViolation(
            code='TIER_LIMIT_REACHED',
            message=(
                'Has alcanzado el límite de rutas con curiosidades en Freemium '
                f'({max_routes} rutas).'
            ),
            http_status=429,
        )


def ensure_premium_for_quedada(sesion: SesionTour):
    ensure_feature_enabled_for_guia(sesion.ruta.guia, 'scheduled_meetup')
