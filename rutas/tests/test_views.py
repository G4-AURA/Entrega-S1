import json
import shutil
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from rutas.models import AuthUser, Guia, Ruta, Parada, Curiosidad, RutaAuditoria
from billing.models import Subscription, TierUsageEvent
from unittest.mock import patch, Mock
from django.utils import timezone
from tours.models import SesionTour, Turista, TuristaSesion

class RutasViewsTest(TestCase):
    def setUp(self):
        self._tmp_media_root = tempfile.mkdtemp(prefix='test-media-')
        self._media_override = override_settings(MEDIA_ROOT=self._tmp_media_root)
        self._media_override.enable()

        self.client = Client()
        self.user = User.objects.create_user(username='guia_test', password='password')
        self.auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=self.auth_user)
        self.client.force_login(self.user)
        
        self.ruta = Ruta.objects.create(
            titulo="Ruta Original",
            duracion_horas=2.0,
            num_personas=5,
            guia=self.guia
        )
        self.parada = Parada.objects.create(
            orden=1, nombre="Parada 1", coordenadas=Point(0, 0), ruta=self.ruta
        )

    def tearDown(self):
        self._media_override.disable()
        shutil.rmtree(self._tmp_media_root, ignore_errors=True)

    # 1. Seguridad y Decoradores
    def test_es_guia_denegado_for_normal_user(self):
         """Un usuario sin perfil Guia recibe PermissionDenied (403)."""
         user2 = User.objects.create_user(username='normal_user', password='password')
         self.client.force_login(user2)
         response = self.client.get(reverse('catalogo'))
         self.assertEqual(response.status_code, 403)
         
    def test_es_guia_permitido_superuser(self):
         self.user.is_superuser = True
         self.user.save()
         # Debería cargar 200 en catalogo
         response = self.client.get(reverse('catalogo'))
         self.assertEqual(response.status_code, 200)

    # 2. Catálogo
    def test_rutas_catalogo_json(self):
        url = reverse('rutas-catalogo')
        response = self.client.get(url, {'limit': 2, 'page': 1})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['total_items'], 1)

    def test_catalogo_view_renders(self):
        response = self.client.get(reverse('catalogo'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'rutas/catalogo.html')

    def test_catalogo_view_muestra_estado_plan(self):
        response = self.client.get(reverse('catalogo'))
        self.assertContains(response, 'Plan actual')
        self.assertContains(response, self.guia.tipo_suscripcion)

    def test_navbar_dropdown_muestra_enlaces_perfil_y_plan(self):
        response = self.client.get(reverse('catalogo'))
        self.assertContains(response, reverse('perfil-editar'))
        self.assertContains(response, reverse('plan'))

    @override_settings(STRIPE_ENABLED=True)
    def test_plan_view_freemium_muestra_cta_upgrade(self):
        response = self.client.get(reverse('plan'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'rutas/plan.html')
        self.assertContains(response, 'Plan actual')
        self.assertContains(response, 'Pasar a Premium')

    def test_plan_view_freemium_muestra_consumos_reales(self):
        Parada.objects.create(
            orden=2,
            nombre="Parada 2",
            coordenadas=Point(1, 1),
            ruta=self.ruta,
        )

        sesion = SesionTour.objects.create(
            codigo_acceso='ABC123',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )
        turista_1 = Turista.objects.create(alias='T1')
        turista_2 = Turista.objects.create(alias='T2')
        TuristaSesion.objects.create(turista=turista_1, sesion_tour=sesion, activo=True)
        TuristaSesion.objects.create(turista=turista_2, sesion_tour=sesion, activo=True)

        TierUsageEvent.objects.create(
            guia=self.guia,
            action=TierUsageEvent.Action.IA_ROUTE_GENERATION,
        )
        TierUsageEvent.objects.create(
            guia=self.guia,
            ruta=self.ruta,
            action=TierUsageEvent.Action.IA_STOP_REPLACEMENT,
        )

        response = self.client.get(reverse('plan'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sesión más ocupada: 2/15 turistas')
        self.assertContains(response, 'Ruta con más paradas: 2/5')
        self.assertContains(response, 'Usadas en el ciclo actual: 1 de 3.')
        self.assertContains(response, 'Ciclo: 1/9. Ruta más usada: 1/3')
        self.assertContains(response, 'Inicio del ciclo:')
        self.assertNotContains(response, 'N/D')

    @override_settings(STRIPE_ENABLED=True)
    def test_plan_view_premium_no_muestra_cta_upgrade(self):
        self.guia.tipo_suscripcion = Guia.Suscripcion.PREMIUM
        self.guia.save(update_fields=['tipo_suscripcion'])

        response = self.client.get(reverse('plan'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ya estás en Premium')
        self.assertNotContains(response, 'id="btn-upgrade-plan"')

    @override_settings(STRIPE_ENABLED=True)
    def test_plan_view_premium_muestra_cta_downgrade_si_hay_suscripcion_activa(self):
        self.guia.tipo_suscripcion = Guia.Suscripcion.PREMIUM
        self.guia.save(update_fields=['tipo_suscripcion'])
        Subscription.objects.create(
            guia=self.guia,
            tier=Guia.Suscripcion.PREMIUM,
            status=Subscription.Status.ACTIVE,
            stripe_subscription_id='sub_test_123',
            current_period_end=timezone.now(),
        )

        response = self.client.get(reverse('plan'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Volver a Freemium al final del periodo')
        self.assertContains(response, 'Próxima renovación')

    @override_settings(STRIPE_ENABLED=True)
    def test_plan_view_prioriza_suscripcion_activa_frente_a_incomplete_reciente(self):
        self.guia.tipo_suscripcion = Guia.Suscripcion.PREMIUM
        self.guia.save(update_fields=['tipo_suscripcion'])

        renewal_dt = timezone.now() + timedelta(days=25)
        Subscription.objects.create(
            guia=self.guia,
            tier=Guia.Suscripcion.PREMIUM,
            status=Subscription.Status.ACTIVE,
            stripe_subscription_id='sub_active_123',
            current_period_end=renewal_dt,
        )
        Subscription.objects.create(
            guia=self.guia,
            tier=Guia.Suscripcion.PREMIUM,
            status=Subscription.Status.INCOMPLETE,
            stripe_subscription_id='',
            current_period_end=None,
        )

        response = self.client.get(reverse('plan'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Volver a Freemium al final del periodo')
        self.assertContains(
            response,
            timezone.localtime(renewal_dt).strftime('%d/%m/%Y %H:%M'),
        )

    @override_settings(STRIPE_ENABLED=True)
    def test_plan_view_oculta_datos_tecnicos_stripe(self):
        self.guia.tipo_suscripcion = Guia.Suscripcion.PREMIUM
        self.guia.save(update_fields=['tipo_suscripcion'])
        Subscription.objects.create(
            guia=self.guia,
            tier=Guia.Suscripcion.PREMIUM,
            status=Subscription.Status.ACTIVE,
            stripe_subscription_id='sub_secret_id_123',
            current_period_end=timezone.now(),
        )

        response = self.client.get(reverse('plan'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Suscripción Stripe')
        self.assertNotContains(response, 'sub_secret_id_123')

    @override_settings(STRIPE_ENABLED=True, STRIPE_SECRET_KEY='sk_test_123')
    @patch('rutas.views.fetch_subscription_snapshot')
    def test_plan_view_refresca_periodo_desde_stripe_si_falta(self, mock_fetch_subscription):
        self.guia.tipo_suscripcion = Guia.Suscripcion.PREMIUM
        self.guia.save(update_fields=['tipo_suscripcion'])
        Subscription.objects.create(
            guia=self.guia,
            tier=Guia.Suscripcion.PREMIUM,
            status=Subscription.Status.ACTIVE,
            stripe_subscription_id='sub_refresh_123',
            cancel_at_period_end=True,
            current_period_end=None,
        )
        mock_fetch_subscription.return_value = {
            'id': 'sub_refresh_123',
            'status': 'active',
            'cancel_at_period_end': True,
            'current_period_end': None,
            'cancel_at': 1777590764,
            'canceled_at': None,
        }

        response = self.client.get(reverse('plan'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fin del periodo actual')
        mock_fetch_subscription.assert_called_once()

    def test_editar_perfil_view_get(self):
        response = self.client.get(reverse('perfil-editar'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'rutas/perfil_editar.html')
        self.assertContains(response, 'Editar perfil')
        self.assertContains(response, self.user.username)

    def test_editar_perfil_view_post_actualiza_datos(self):
        url = reverse('perfil-editar')
        response = self.client.post(url, {
            'first_name': 'Max',
            'last_name': 'Corti',
            'email': 'max@example.com',
        })
        self.assertRedirects(response, f"{url}?updated=1")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Max')
        self.assertEqual(self.user.last_name, 'Corti')
        self.assertEqual(self.user.email, 'max@example.com')

    def test_editar_perfil_view_email_duplicado(self):
        user2 = User.objects.create_user(
            username='otro_usuario',
            password='password',
            email='existente@example.com',
        )
        AuthUser.objects.create(user=user2)
        Guia.objects.create(user=user2.auth_profile)

        response = self.client.post(reverse('perfil-editar'), {
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'existente@example.com',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ya existe una cuenta con este correo electrónico.')

    # 3. Eliminar Ruta
    def test_eliminar_ruta_view_success(self):
        url = reverse('ruta-eliminar', args=[self.ruta.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Ruta.objects.filter(id=self.ruta.id).exists())

    def test_eliminar_ruta_view_not_owner(self):
        # Otro guía
        user2 = User.objects.create_user(username='guia2', password='password')
        auth2 = AuthUser.objects.create(user=user2)
        Guia.objects.create(user=auth2)
        self.client.force_login(user2)
        
        url = reverse('ruta-eliminar', args=[self.ruta.id])
        # Intentar borrar ruta que no es suya -> 404 por query guia_user=request.user
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    # 4. Detalle y Edición (POSTs)
    def test_ruta_detalle_view_redirects_no_owner(self):
        user2 = User.objects.create_user(username='guia2', password='password')
        auth2 = AuthUser.objects.create(user=user2)
        Guia.objects.create(user=auth2)
        self.client.force_login(user2)
        
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403) # _render_ruta_no_autorizada

    def test_ruta_detalle_post_title_success(self):
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'title',
            'titulo': 'Nuevo Titulo',
            'descripcion': 'Nueva Descr'
        })
        self.assertRedirects(response, f"{url}?title_updated=1")
        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.titulo, "Nuevo Titulo")

    def test_ruta_detalle_post_title_error(self):
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'title',
            'titulo': '', # Inválido
            'descripcion': 'Nueva Descr'
        })
        self.assertRedirects(response, f"{url}?title_error=1")

    def test_ruta_detalle_post_meta_success(self):
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'meta',
            'duracion_horas': '3.0',
            'num_personas': '15',
            'nivel_exigencia': 'Alta'
        })
        self.assertRedirects(response, f"{url}?meta_updated=1")

    def test_ruta_detalle_post_meta_success_con_duracion_legacy_sin_cambiar(self):
        self.ruta.duracion_horas = 1.2
        self.ruta.save(update_fields=["duracion_horas"])

        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'meta',
            'duracion_horas': '1.2',
            'num_personas': '15',
            'nivel_exigencia': 'Alta'
        })
        self.assertRedirects(response, f"{url}?meta_updated=1")
        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.num_personas, 15)
        self.assertEqual(self.ruta.nivel_exigencia, 'Alta')

    def test_ruta_detalle_post_meta_bloquea_capacidad_freemium(self):
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'meta',
            'duracion_horas': '2.0',
            'num_personas': '16',
            'nivel_exigencia': 'Media'
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('tier_code=TIER_CAPACITY_REACHED', response.url)

    def test_ruta_detalle_post_stop_add_success(self):
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'stop_add',
            'nombre': 'Parada 2',
            'descripcion': 'Descripcion de la nueva parada',
            'lat': '10.0',
            'lon': '10.0'
        })
        self.assertRedirects(response, f"{url}?stop_added=1")
        self.assertEqual(self.ruta.paradas.count(), 2)
        parada_agregada = self.ruta.paradas.order_by('-orden').first()
        self.assertEqual(parada_agregada.descripcion, 'Descripcion de la nueva parada')

    def test_ruta_detalle_post_stop_edit_success(self):
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'stop_edit',
            'parada_id': self.parada.id,
            'nombre': 'Parada Editada',
            'descripcion': 'Descripcion editada manualmente',
            'lat': '5.0',
            'lon': '5.0'
        })
        self.assertRedirects(response, f"{url}?stop_updated=1")
        self.parada.refresh_from_db()
        self.assertEqual(self.parada.descripcion, 'Descripcion editada manualmente')

    def test_ruta_detalle_post_stop_delete_bloqueado_con_dos_paradas_minimas(self):
        Parada.objects.create(orden=2, nombre="Parada 2", coordenadas=Point(1, 1), ruta=self.ruta)
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'stop_delete',
            'parada_id': self.parada.id
        })
        self.assertRedirects(response, f"{url}?stop_error=1")
        self.assertEqual(self.ruta.paradas.count(), 2)

    def test_ruta_detalle_post_stop_delete_success_con_mas_de_dos_paradas(self):
        parada2 = Parada.objects.create(orden=2, nombre="Parada 2", coordenadas=Point(1, 1), ruta=self.ruta)
        parada3 = Parada.objects.create(orden=3, nombre="Parada 3", coordenadas=Point(2, 2), ruta=self.ruta)
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'stop_delete',
            'parada_id': parada3.id,
        })
        self.assertRedirects(response, f"{url}?stop_deleted=1")
        self.assertEqual(self.ruta.paradas.count(), 2)
        self.assertTrue(Parada.objects.filter(id=parada2.id).exists())
    
    def test_ruta_detalle_post_stop_reorder_success(self):
        parada2 = Parada.objects.create(orden=2, nombre="P2", coordenadas=Point(1, 1), ruta=self.ruta)
        url = reverse('ruta-detalle', args=[self.ruta.id])
        # Enviar orden invertido: [2, 1]
        response = self.client.post(url, {
            'form_type': 'stop_reorder',
            'stop_order': f"{parada2.id},{self.parada.id}"
        })
        self.assertRedirects(response, f"{url}?stop_reordered=1")

    def test_ruta_detalle_post_stop_reorder_sin_cambios_success(self):
        parada2 = Parada.objects.create(orden=2, nombre="P2", coordenadas=Point(1, 1), ruta=self.ruta)
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'stop_reorder',
            'stop_order': ''
        })
        self.assertRedirects(response, f"{url}?stop_reordered=1")

    def test_ruta_detalle_post_mood_success(self):
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'mood',
            'mood': ['Historia']
        })
        self.assertRedirects(response, f"{url}?mood_updated=1")

    def test_ruta_detalle_view_attribute_error_guia_redirects(self):
        """Si ruta.guia no tiene user o explota en el acceso, se le deniega el acceso."""
        from unittest.mock import PropertyMock
        # Forzar un AttributeError de NoneType al acceder a .user
        with patch.object(Ruta, 'guia', new_callable=PropertyMock) as mock_guia:
            mock_guia.return_value = None
            url = reverse('ruta-detalle', args=[self.ruta.id])
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)

    def test_ruta_detalle_post_unknown_form_type_redirects(self):
        """Si entra un form_type desconocido, hace fallback y redirige a la misma página."""
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'alien_form_type'
        })
        self.assertRedirects(response, url)

    @patch('rutas.services.reordenar_paradas')
    def test_ruta_detalle_post_stop_reorder_service_error_redirects(self, mock_reorder):
        """Si el servicio lanza ValueError al reordenar, la vista redirige con error."""
        parada2 = Parada.objects.create(orden=2, nombre="P2", coordenadas=Point(1, 1), ruta=self.ruta)
        url = reverse('ruta-detalle', args=[self.ruta.id])
        mock_reorder.side_effect = ValueError("Fallo service")
        
        response = self.client.post(url, {
            'form_type': 'stop_reorder',
            'stop_order': f"{self.parada.id},{parada2.id}" # IDs correctos para pasar el set check
        })
        self.assertRedirects(response, f"{url}?stop_error=1")

    def test_ruta_detalle_post_stop_edit_error(self):
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'stop_edit',
            'parada_id': self.parada.id,
            'nombre': 'Parada Editada',
            'lat': 'invalid_float', # Provocar ValueError
            'lon': '5.0'
        })
        self.assertRedirects(response, f"{url}?stop_error=1")

    def test_ruta_detalle_view_muestra_auditoria_de_cambios(self):
        self.ruta.es_generada_ia = True
        self.ruta.save(update_fields=["es_generada_ia"])
        RutaAuditoria.objects.create(
            ruta=self.ruta,
            parada=self.parada,
            parada_id_snapshot=self.parada.id,
            parada_nombre_snapshot=self.parada.nombre,
            parada_orden_snapshot=self.parada.orden,
            tipo_evento=RutaAuditoria.TipoEvento.PARADA_MODIFICADA,
            usuario=self.user,
            motivo='Corrección manual',
            detalles={'antes': {'nombre': self.parada.nombre}},
        )

        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Auditoría de cambios')
        self.assertContains(response, 'Parada modificada')
        self.assertContains(response, 'Corrección manual')

    def test_ruta_detalle_post_stop_add_error(self):
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'stop_add',
            'nombre': 'Parada',
            'lat': 'invalid_float',
            'lon': '10.0'
        })
        self.assertRedirects(response, f"{url}?stop_error=1")

    def test_ruta_detalle_post_stop_reorder_error_format(self):
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'stop_reorder',
            'stop_order': "letras,no,numeros"
        })
        self.assertRedirects(response, f"{url}?stop_error=1")

    def test_ruta_detalle_post_stop_reorder_error_mismatch(self):
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'stop_reorder',
            'stop_order': "9999" # ID no pertenece a ruta
        })
        self.assertRedirects(response, f"{url}?stop_error=1")

    def test_obtener_curiosidad_parada_api_superuser(self):
         self.user.is_superuser = True
         self.user.save()
         url = reverse('parada-curiosidad', args=[self.parada.id])
         curiosidad = Curiosidad.objects.create(
             parada=self.parada, ciudad="Sevilla", titulo="S", texto="T"
         )
         with patch('rutas.services.obtener_o_generar_curiosidad_parada') as mock_obtener:
              mock_obtener.return_value = (curiosidad, False)
              response = self.client.get(url)
         self.assertEqual(response.status_code, 200)

    # 5. APIs AJAX
    def test_recalcular_ruta_api_success(self):
        url = reverse('ruta-recalcular', args=[self.ruta.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)

    def test_recalcular_ruta_api_no_guia(self):
         user2 = User.objects.create_user(username='normal_user2', password='password')
         self.client.force_login(user2)
         url = reverse('ruta-recalcular', args=[self.ruta.id])
         response = self.client.post(url)
         self.assertEqual(response.status_code, 403) # No tienes permisos

    @patch('rutas.services.obtener_o_generar_curiosidad_parada')
    def test_obtener_curiosidad_parada_api_success(self, mock_obtener):
        curiosidad = Curiosidad.objects.create(
            parada=self.parada, ciudad="Sevilla", titulo="Curiosa", texto="Texto"
        )
        # Mock tuple response
        mock_obtener.return_value = (curiosidad, False)
        
        url = reverse('parada-curiosidad', args=[self.parada.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['curiosidad']['titulo'], "Curiosa")
        
    @patch('rutas.services.obtener_o_generar_curiosidad_parada')
    def test_obtener_curiosidad_parada_api_error(self, mock_obtener):
        mock_obtener.side_effect = Exception("Fallo")
        url = reverse('parada-curiosidad', args=[self.parada.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 502)

    @patch('rutas.services.generar_curiosidad_parada_preview')
    def test_obtener_curiosidad_parada_api_error_ia_unavailable(self, mock_preview):
        mock_preview.side_effect = RuntimeError(
            "503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand.'}}"
        )
        url = reverse('parada-curiosidad', args=[self.parada.id]) + '?preview=1'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data['status'], 'error')
        self.assertIn('IA no está disponible', data['mensaje'])
        self.assertNotIn('503 UNAVAILABLE', data['mensaje'])

    # 6. S3.1-09 Guardado manual de curiosidad
    def test_guardar_curiosidad_parada_api_post_persiste(self):
        url = reverse('parada-curiosidad-guardar', args=[self.parada.id])
        payload = {
            'texto': 'Curiosidad manual persistida',
            'tipo': 'Historia',
            'titulo': 'Titulo manual',
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(data['creada'])
        self.assertEqual(data['curiosidad']['texto'], payload['texto'])
        self.assertEqual(data['curiosidad']['tipo'], payload['tipo'])

        curiosidad = Curiosidad.objects.get(parada=self.parada)
        self.assertEqual(curiosidad.texto, payload['texto'])
        self.assertEqual(curiosidad.tipo, payload['tipo'])

    def test_guardar_curiosidad_parada_api_put_actualiza(self):
        curiosidad = Curiosidad.objects.create(
            parada=self.parada,
            ciudad='Sevilla',
            titulo='Titulo viejo',
            texto='Texto viejo',
            tipo='Arquitectura',
        )
        url = reverse('parada-curiosidad-guardar', args=[self.parada.id])
        payload = {
            'texto': 'Texto actualizado por PUT',
            'tipo': 'Evento',
            'titulo': 'Titulo actualizado',
        }
        response = self.client.put(
            url,
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertFalse(data['creada'])
        self.assertEqual(data['curiosidad']['id'], curiosidad.id)

        curiosidad.refresh_from_db()
        self.assertEqual(curiosidad.texto, payload['texto'])
        self.assertEqual(curiosidad.tipo, payload['tipo'])

    def test_guardar_curiosidad_parada_api_post_multipart_guarda_imagen_local(self):
        url = reverse('parada-curiosidad-guardar', args=[self.parada.id])
        image_file = SimpleUploadedFile(
            'curiosidad.png',
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR',
            content_type='image/png',
        )

        response = self.client.post(
            url,
            data={
                'texto': 'Curiosidad con imagen local',
                'tipo': 'Historia',
                'titulo': 'Titulo con imagen',
                'imagen_manual': image_file,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(data['curiosidad']['imagen_url'].startswith('/media/'))
        self.assertTrue(data['curiosidad']['manual_url'].startswith('/media/'))

        curiosidad = Curiosidad.objects.get(parada=self.parada)
        self.assertTrue(bool(curiosidad.imagen_manual))

    def test_obtener_curiosidad_parada_api_prioriza_imagen_manual(self):
        curiosidad = Curiosidad.objects.create(
            parada=self.parada,
            ciudad='Sevilla',
            titulo='Curiosa',
            texto='Texto',
            tipo='Historia',
            imagen_url='https://externa.example/curiosa.jpg',
        )
        curiosidad.imagen_manual.save(
            'manual.png',
            SimpleUploadedFile(
                'manual.png',
                b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR',
                content_type='image/png',
            ),
        )

        with patch('rutas.services.obtener_o_generar_curiosidad_parada') as mock_obtener:
            mock_obtener.return_value = (curiosidad, False)
            url = reverse('parada-curiosidad', args=[self.parada.id])
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['curiosidad']['imagen_url'].startswith('/media/'))
        self.assertTrue(data['curiosidad']['manual_url'].startswith('/media/'))

    def test_obtener_curiosidad_parada_api_preview_existente_prioriza_imagen_manual(self):
        curiosidad = Curiosidad.objects.create(
            parada=self.parada,
            ciudad='Sevilla',
            titulo='Curiosa preview',
            texto='Texto preview',
            tipo='Historia',
            imagen_url='https://externa.example/preview.jpg',
        )
        curiosidad.imagen_manual.save(
            'manual_preview.png',
            SimpleUploadedFile(
                'manual_preview.png',
                b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR',
                content_type='image/png',
            ),
        )

        url = reverse('parada-curiosidad', args=[self.parada.id])
        response = self.client.get(f'{url}?preview=1')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(data['persistida'])
        self.assertFalse(data['generada'])
        self.assertTrue(data['curiosidad']['imagen_url'].startswith('/media/'))
        self.assertTrue(data['curiosidad']['manual_url'].startswith('/media/'))

    def test_guardar_curiosidad_parada_api_freemium_bloquea_cuarta_ruta(self):
        for index in range(2, 5):
            ruta_extra = Ruta.objects.create(
                titulo=f'Ruta extra {index}',
                duracion_horas=2.0,
                num_personas=5,
                guia=self.guia,
            )
            parada_extra = Parada.objects.create(
                orden=1,
                nombre=f'Parada extra {index}',
                coordenadas=Point(index, index),
                ruta=ruta_extra,
            )
            if index < 4:
                Curiosidad.objects.create(
                    parada=parada_extra,
                    ciudad='Sevilla',
                    titulo=f'Curiosidad {index}',
                    texto='Texto previo',
                    tipo='Historia',
                )
            else:
                parada_cuarta = parada_extra

        Curiosidad.objects.create(
            parada=self.parada,
            ciudad='Sevilla',
            titulo='Curiosidad base',
            texto='Texto base',
            tipo='Historia',
        )

        url = reverse('parada-curiosidad-guardar', args=[parada_cuarta.id])
        response = self.client.post(
            url,
            data=json.dumps({'texto': 'No debería crear', 'tipo': 'Evento'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 429)
        data = response.json()
        self.assertEqual(data['status'], 'ERROR')
        self.assertEqual(data['code'], 'TIER_LIMIT_REACHED')
        self.assertFalse(Curiosidad.objects.filter(parada=parada_cuarta).exists())

    def test_guardar_curiosidad_parada_api_premium_sin_limite(self):
        self.guia.tipo_suscripcion = Guia.Suscripcion.PREMIUM
        self.guia.save(update_fields=['tipo_suscripcion'])

        for index in range(2, 6):
            ruta_extra = Ruta.objects.create(
                titulo=f'Ruta premium {index}',
                duracion_horas=2.0,
                num_personas=5,
                guia=self.guia,
            )
            parada_extra = Parada.objects.create(
                orden=1,
                nombre=f'Parada premium {index}',
                coordenadas=Point(index, index),
                ruta=ruta_extra,
            )
            if index < 5:
                Curiosidad.objects.create(
                    parada=parada_extra,
                    ciudad='Sevilla',
                    titulo=f'Curiosidad premium {index}',
                    texto='Texto previo',
                    tipo='Historia',
                )
            else:
                parada_objetivo = parada_extra

        url = reverse('parada-curiosidad-guardar', args=[parada_objetivo.id])
        response = self.client.post(
            url,
            data=json.dumps({'texto': 'Sí debería crear', 'tipo': 'Dato Curioso'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(data['creada'])
        self.assertTrue(Curiosidad.objects.filter(parada=parada_objetivo).exists())
