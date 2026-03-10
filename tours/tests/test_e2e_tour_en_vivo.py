import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from rutas.models import AuthUser, Guia, Ruta
from tours.models import SESION_TOUR, TURISTA, TuristaSesion


class TourEnVivoEndToEndTests(TestCase):
    def setUp(self):
        self.guia_user = User.objects.create_user(username='e2e_guia', password='1234')
        auth_guia = AuthUser.objects.create(user=self.guia_user)
        guia = Guia.objects.create(user=auth_guia)

        self.ruta = Ruta.objects.create(
            titulo='Ruta E2E Vivo',
            descripcion='Prueba de tour en vivo',
            duracion_horas=1.5,
            num_personas=15,
            mood=['Cultura'],
            guia=guia,
        )

        self.guia_client = Client()
        self.guia_client.force_login(self.guia_user)

        self.turista1_client = Client()
        self.turista2_client = Client()

    def test_flujo_tour_en_vivo_desde_guia_y_turistas(self):
        create_response = self.guia_client.get(
            reverse('tours:crear_sesion') + f'?ruta_id={self.ruta.id}'
        )
        self.assertEqual(create_response.status_code, 302)

        sesion = SESION_TOUR.objects.get(ruta=self.ruta)
        self.assertEqual(sesion.estado, SESION_TOUR.PENDIENTE)

        iniciar_response = self.guia_client.post(
            reverse('tours:iniciar_tour', args=[sesion.id])
        )
        self.assertEqual(iniciar_response.status_code, 200)

        sesion.refresh_from_db()
        self.assertEqual(sesion.estado, SESION_TOUR.EN_CURSO)
        self.assertTrue(sesion.codigo_acceso)
        self.assertTrue(sesion.token)

        codigo_acceso = sesion.codigo_acceso
        token = str(sesion.token)

        join_code_response = self.turista1_client.get(
            reverse('tours:join_tour_by_code', args=[codigo_acceso])
        )
        self.assertEqual(join_code_response.status_code, 302)

        self.assertIn('/live/', join_code_response['Location'])

        join_tour_response = self.turista1_client.post(
            reverse('tours:join_tour', args=[token]),
            data={'alias': 'turista1'},
        )
        self.assertEqual(join_tour_response.status_code, 302)

        mapa_response_t1 = self.turista1_client.get(
            reverse('tours:mapa_turista_anonimo', args=[token])
        )
        self.assertEqual(mapa_response_t1.status_code, 200)

        join_tour_response_2 = self.turista2_client.post(
            reverse('tours:join_tour', args=[token]),
            data={'alias': 'turista2'},
        )
        self.assertEqual(join_tour_response_2.status_code, 302)

        mapa_response_t2 = self.turista2_client.get(
            reverse('tours:mapa_turista_anonimo', args=[token])
        )
        self.assertEqual(mapa_response_t2.status_code, 200)

        participants_response = self.guia_client.get(
            reverse('tours:participantes_sesion', args=[sesion.id])
        )
        self.assertEqual(participants_response.status_code, 200)

        participantes = participants_response.json().get('participantes', [])
        self.assertEqual(len(participantes), 2)
        self.assertTrue(any(p['alias'] == 'turista1' for p in participantes))
        self.assertTrue(any(p['alias'] == 'turista2' for p in participantes))

        ubicacion_response = self.guia_client.post(
            reverse('tours:registrar_ubicacion'),
            data=json.dumps({'sesion_id': sesion.id, 'latitud': 40.418, 'longitud': -3.702}),
            content_type='application/json',
        )
        self.assertEqual(ubicacion_response.status_code, 201)

        ubicacion_tourista1 = self.turista1_client.get(
            reverse('tours:ubicacion_guia', args=[sesion.id])
        )
        self.assertEqual(ubicacion_tourista1.status_code, 200)
        self.assertTrue(ubicacion_tourista1.json().get('available'))

        guia_chat = self.guia_client.post(
            reverse('tours:enviar_mensaje', args=[sesion.id]),
            data=json.dumps({'texto': 'Comenzamos el tour'}),
            content_type='application/json',
        )
        self.assertEqual(guia_chat.status_code, 201)

        turista_chat = self.turista1_client.post(
            reverse('tours:enviar_mensaje', args=[sesion.id]),
            data=json.dumps({'texto': 'Hola guía, aquí estoy'}),
            content_type='application/json',
        )
        self.assertEqual(turista_chat.status_code, 201)

        mensajes_response = self.turista2_client.get(
            reverse('tours:obtener_mensajes', args=[sesion.id])
        )
        self.assertEqual(mensajes_response.status_code, 200)

        mensajes = mensajes_response.json().get('mensajes', [])
        self.assertEqual(len(mensajes), 2)
        self.assertTrue(any(msg['texto'] == 'Comenzamos el tour' for msg in mensajes))
        self.assertTrue(any(msg['texto'] == 'Hola guía, aquí estoy' for msg in mensajes))

        cerrar_response = self.guia_client.post(
            reverse('tours:cerrar_acceso', args=[sesion.id])
        )
        self.assertEqual(cerrar_response.status_code, 200)

        sesion.refresh_from_db()
        self.assertEqual(sesion.estado, SESION_TOUR.FINALIZADO)

        self.assertEqual(
            TuristaSesion.objects.filter(sesion_tour=sesion, activo=True).count(),
            0,
        )

        mapa_finalizado = self.turista1_client.get(
            reverse('tours:mapa_turista_anonimo', args=[token])
        )
        self.assertIn(mapa_finalizado.status_code, (403, 409, 410))

        self.assertEqual(TURISTA.objects.filter(alias__in=['turista1', 'turista2']).count(), 2)
