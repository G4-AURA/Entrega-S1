from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from rutas.models import Guia

from billing.models import FeatureAccessSetting
from billing.tier_guard import (
    apply_payload_tier_rules,
    ensure_premium_for_quedada,
    is_feature_enabled_for_tier,
    update_feature_access,
)


class FeatureAccessPanelViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='admin_feature',
            email='admin_feature@example.com',
            password='admin_feature_123',
        )
        self.normal_user = User.objects.create_user(
            username='normal_feature',
            email='normal_feature@example.com',
            password='normal_feature_123',
        )

    def test_panel_redirige_anonimo(self):
        response = self.client.get(reverse('billing:feature_access_panel'))
        self.assertEqual(response.status_code, 302)

    def test_panel_requiere_superusuario(self):
        self.client.force_login(self.normal_user)
        response = self.client.get(reverse('billing:feature_access_panel'))
        self.assertEqual(response.status_code, 403)

    def test_panel_es_accesible_para_superusuario(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('billing:feature_access_panel'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Panel de funcionalidades por plan')
        self.assertContains(response, 'Generacion de rutas con IA')
        self.assertContains(response, 'Sustitucion con IA de paradas')
        self.assertContains(response, 'Chat por separado')
        self.assertContains(response, 'Quedada programada con notificacion')
        self.assertContains(response, 'Curiosidad automatica por proximidad')
        self.assertContains(response, 'Campo de deseos con IA')
        self.assertNotContains(response, 'Gestion de paradas por ruta')
        self.assertNotContains(response, 'Curiosidades en rutas')

    def test_actualiza_disponibilidad_desde_panel(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse('billing:feature_access_update'),
            data={'key': 'chat_mode_separate', 'tier': 'freemium', 'enabled': '1'},
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('?updated=chat_mode_separate&tier=freemium', response['Location'])

        setting = FeatureAccessSetting.objects.get(key='chat_mode_separate')
        self.assertTrue(setting.enabled_freemium)
        self.assertTrue(setting.enabled_premium)

    def test_actualizar_clave_invalida_muestra_error(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse('billing:feature_access_update'),
            data={'key': 'clave_inexistente', 'tier': 'freemium', 'enabled': '1'},
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('?error=', response['Location'])


class FeatureAccessTierGuardIntegrationTest(TestCase):
    def test_toggle_independiente_no_modifica_el_otro_plan(self):
        FeatureAccessSetting.objects.create(
            key='chat_mode_separate',
            enabled_freemium=False,
            enabled_premium=True,
        )

        update_feature_access('chat_mode_separate', 'freemium', True)

        setting = FeatureAccessSetting.objects.get(key='chat_mode_separate')
        self.assertTrue(setting.enabled_freemium)
        self.assertTrue(setting.enabled_premium)

    def test_puede_quedar_desactivado_para_ambos_planes(self):
        update_feature_access('chat_mode_separate', 'freemium', False)
        update_feature_access('chat_mode_separate', 'premium', False)

        self.assertFalse(is_feature_enabled_for_tier('chat_mode_separate', Guia.Suscripcion.FREEMIUM))
        self.assertFalse(is_feature_enabled_for_tier('chat_mode_separate', Guia.Suscripcion.PREMIUM))

    def test_quedada_permite_freemium_si_toggle_freemium_esta_activo(self):
        FeatureAccessSetting.objects.create(
            key='scheduled_meetup',
            enabled_freemium=True,
            enabled_premium=False,
        )
        sesion = SimpleNamespace(
            ruta=SimpleNamespace(
                guia=SimpleNamespace(tipo_suscripcion=Guia.Suscripcion.FREEMIUM),
            )
        )

        ensure_premium_for_quedada(sesion)

    def test_payload_wishes_permite_freemium_si_toggle_freemium_esta_activo(self):
        FeatureAccessSetting.objects.create(
            key='payload_wishes',
            enabled_freemium=True,
            enabled_premium=False,
        )
        guia = SimpleNamespace(tipo_suscripcion=Guia.Suscripcion.FREEMIUM)

        payload, warnings = apply_payload_tier_rules(
            guia,
            {'ciudad': 'Sevilla', 'deseos': ['sin cuestas']},
        )

        self.assertEqual(payload['deseos'], ['sin cuestas'])
        self.assertEqual(warnings, [])
