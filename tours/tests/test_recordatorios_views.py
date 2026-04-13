import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from rutas.models import AuthUser, Guia, Ruta
from tours.models import RecordatorioSesion, SesionTour, Turista, TuristaSesion


class RecordatoriosViewsTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.guia_user = User.objects.create_user(username='guia_recordatorios', password='pass123')
        self.auth_guia = AuthUser.objects.create(user=self.guia_user)
        self.guia = Guia.objects.create(
            user=self.auth_guia,
            tipo_suscripcion=Guia.Suscripcion.PREMIUM,
        )

        self.ruta = Ruta.objects.create(
            titulo='Ruta Recordatorios',
            descripcion='Desc',
            duracion_horas=2.0,
            num_personas=20,
            mood=['Historia'],
            guia=self.guia,
        )

        self.sesion = SesionTour.objects.create(
            codigo_acceso='RECAD1',
            estado=SesionTour.EN_CURSO,
            fecha_inicio=timezone.now(),
            ruta=self.ruta,
        )

    def _activar_turista_en_cliente(self, alias='Turista X'):
        turista = Turista.objects.create(alias=alias)
        TuristaSesion.objects.create(turista=turista, sesion_tour=self.sesion, activo=True)
        session = self.client.session
        session['turista_id'] = turista.id
        session.save()
        return turista

    def test_guia_premium_crea_recordatorio(self):
        self.client.force_login(self.guia_user)
        url = reverse('tours:recordatorios_sesion', args=[self.sesion.id])

        payload = {
            'mensaje': 'Nos reunimos en la puerta principal.',
            'hora_objetivo': (timezone.now() + timedelta(minutes=30)).isoformat(),
            'avisar_minutos_antes': 10,
            'meetup_lat': 37.3891,
            'meetup_lng': -5.9845,
            'etiqueta_quedada': 'Puerta principal',
        }
        response = self.client.post(url, data=json.dumps(payload), content_type='application/json')

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(RecordatorioSesion.objects.filter(sesion_tour=self.sesion).count(), 1)

    def test_guia_freemium_puede_crear_recordatorio_con_ubicacion(self):
        self.guia.tipo_suscripcion = Guia.Suscripcion.FREEMIUM
        self.guia.save(update_fields=['tipo_suscripcion'])

        self.client.force_login(self.guia_user)
        url = reverse('tours:recordatorios_sesion', args=[self.sesion.id])
        payload = {
            'mensaje': 'Recordatorio permitido en freemium',
            'hora_objetivo': (timezone.now() + timedelta(minutes=25)).isoformat(),
            'avisar_minutos_antes': 10,
            'meetup_lat': 37.3891,
            'meetup_lng': -5.9845,
            'etiqueta_quedada': 'Freemium meetup',
        }

        response = self.client.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 201)

    def test_turista_lista_recordatorios(self):
        self._activar_turista_en_cliente()
        RecordatorioSesion.objects.create(
            sesion_tour=self.sesion,
            creado_por=self.guia_user,
            mensaje='Recordatorio en lista',
            hora_objetivo=timezone.now() + timedelta(minutes=20),
            avisar_minutos_antes=10,
        )

        url = reverse('tours:recordatorios_sesion', args=[self.sesion.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['recordatorios'][0]['mensaje'], 'Recordatorio en lista')

    def test_alertas_turista_se_entregan_una_sola_vez(self):
        self._activar_turista_en_cliente(alias='Turista alerta')
        RecordatorioSesion.objects.create(
            sesion_tour=self.sesion,
            creado_por=self.guia_user,
            mensaje='Alerta inmediata',
            hora_objetivo=timezone.now() + timedelta(minutes=1),
            avisar_minutos_antes=5,
        )

        url = reverse('tours:alertas_recordatorios', args=[self.sesion.id])

        first = self.client.get(url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()['total'], 1)

        second = self.client.get(url)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()['total'], 0)
