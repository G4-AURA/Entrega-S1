from types import SimpleNamespace
from datetime import timezone as dt_timezone

from django.test import SimpleTestCase
from django.utils import timezone

from rutas.models import Guia, Ruta

from billing.tier_guard import (
    TierRuleViolation,
    apply_payload_tier_rules,
    ensure_chat_mode_allowed,
    ensure_route_stop_count_allowed,
    ensure_moods_allowed,
    ensure_premium_for_quedada,
    get_usage_cycle_window,
    tier_guard,
    tier_error_response,
)


class TierGuardServiceTest(SimpleTestCase):
    def test_apply_payload_tier_rules_ignora_deseos_en_freemium(self):
        guia = SimpleNamespace(tipo_suscripcion=Guia.Suscripcion.FREEMIUM)
        payload, warnings = apply_payload_tier_rules(
            guia,
            {'ciudad': 'Sevilla', 'deseos': ['menos cuestas']},
        )

        self.assertEqual(payload.get('deseos'), [])
        self.assertTrue(warnings)
        self.assertEqual(warnings[0]['code'], 'TIER_PLAN_REQUIRED')

    def test_apply_payload_tier_rules_no_modifica_deseos_en_premium(self):
        guia = SimpleNamespace(tipo_suscripcion=Guia.Suscripcion.PREMIUM)
        payload, warnings = apply_payload_tier_rules(
            guia,
            {'ciudad': 'Sevilla', 'deseos': ['menos cuestas']},
        )

        self.assertEqual(payload.get('deseos'), ['menos cuestas'])
        self.assertEqual(warnings, [])

    def test_ensure_moods_allowed_bloquea_mood_premium_en_freemium(self):
        guia = SimpleNamespace(tipo_suscripcion=Guia.Suscripcion.FREEMIUM)

        with self.assertRaises(TierRuleViolation) as ctx:
            ensure_moods_allowed(guia, [Ruta.Mood.GASTRONOMIA])

        self.assertEqual(ctx.exception.code, 'TIER_FORBIDDEN')
        self.assertEqual(ctx.exception.http_status, 403)

    def test_ensure_moods_allowed_permite_slug_historia_en_freemium(self):
        guia = SimpleNamespace(tipo_suscripcion=Guia.Suscripcion.FREEMIUM)
        ensure_moods_allowed(guia, ['historia'])

    def test_ensure_chat_mode_allowed_bloquea_separado_en_freemium(self):
        sesion = SimpleNamespace(
            ruta=SimpleNamespace(
                guia=SimpleNamespace(tipo_suscripcion=Guia.Suscripcion.FREEMIUM),
            )
        )

        with self.assertRaises(TierRuleViolation) as ctx:
            ensure_chat_mode_allowed(sesion, 'separado')

        self.assertEqual(ctx.exception.code, 'TIER_FORBIDDEN')
        self.assertEqual(ctx.exception.http_status, 403)

    def test_ensure_chat_mode_allowed_permite_separado_en_premium(self):
        sesion = SimpleNamespace(
            ruta=SimpleNamespace(
                guia=SimpleNamespace(tipo_suscripcion=Guia.Suscripcion.PREMIUM),
            )
        )
        ensure_chat_mode_allowed(sesion, 'separado')

    def test_ensure_premium_for_quedada_bloquea_freemium(self):
        sesion = SimpleNamespace(
            ruta=SimpleNamespace(
                guia=SimpleNamespace(tipo_suscripcion=Guia.Suscripcion.FREEMIUM),
            )
        )
        with self.assertRaises(TierRuleViolation) as ctx:
            ensure_premium_for_quedada(sesion)
        self.assertEqual(ctx.exception.code, 'TIER_FORBIDDEN')

    def test_ensure_premium_for_quedada_permite_premium(self):
        sesion = SimpleNamespace(
            ruta=SimpleNamespace(
                guia=SimpleNamespace(tipo_suscripcion=Guia.Suscripcion.PREMIUM),
            )
        )
        ensure_premium_for_quedada(sesion)

    def test_ensure_route_stop_count_allowed_bloquea_exceso_freemium(self):
        guia = SimpleNamespace(tipo_suscripcion=Guia.Suscripcion.FREEMIUM)
        with self.assertRaises(TierRuleViolation) as ctx:
            ensure_route_stop_count_allowed(guia, 6)
        self.assertEqual(ctx.exception.code, 'TIER_LIMIT_REACHED')

    def test_tier_error_response_formato(self):
        error = TierRuleViolation(
            code='TIER_LIMIT_REACHED',
            message='Límite alcanzado.',
            http_status=429,
        )
        response = tier_error_response(error)

        self.assertEqual(response.status_code, 429)
        self.assertIn('"code": "TIER_LIMIT_REACHED"', response.content.decode('utf-8'))

    def test_decorador_tier_guard_bloquea_si_regla_falla(self):
        def _check(*_args, **_kwargs):
            raise TierRuleViolation(
                code='TIER_FORBIDDEN',
                message='Solo Premium.',
                http_status=403,
            )

        @tier_guard(_check)
        def _view(*_args, **_kwargs):
            return None

        response = _view(None)
        self.assertEqual(response.status_code, 403)

    def test_usage_cycle_window_freemium_anclado_a_date_joined(self):
        joined_at = timezone.datetime(2026, 3, 17, 15, 30, tzinfo=dt_timezone.utc)
        now = timezone.datetime(2026, 4, 20, 10, 0, tzinfo=dt_timezone.utc)
        guia = SimpleNamespace(
            tipo_suscripcion=Guia.Suscripcion.FREEMIUM,
            user=SimpleNamespace(user=SimpleNamespace(date_joined=joined_at)),
        )

        cycle_start, cycle_end, anchor = get_usage_cycle_window(guia, now=now)

        self.assertEqual(anchor, joined_at)
        self.assertEqual(cycle_start, timezone.datetime(2026, 4, 17, 15, 30, tzinfo=dt_timezone.utc))
        self.assertEqual(cycle_end, timezone.datetime(2026, 5, 17, 15, 30, tzinfo=dt_timezone.utc))
