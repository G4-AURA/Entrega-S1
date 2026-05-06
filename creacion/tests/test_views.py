import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from creacion import services
from rutas.models import AuthUser, Guia, Ruta
from tours.models import TURISTA


def _crear_guia_para_usuario(user, tipo_suscripcion=Guia.Suscripcion.FREEMIUM):
    auth_profile, _ = AuthUser.objects.get_or_create(user=user)
    guia, _ = Guia.objects.get_or_create(
        user=auth_profile,
        defaults={'tipo_suscripcion': tipo_suscripcion},
    )
    if guia.tipo_suscripcion != tipo_suscripcion:
        guia.tipo_suscripcion = tipo_suscripcion
        guia.save(update_fields=['tipo_suscripcion'])
    return guia


class GenerarRutaIAViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('creacion:generar_ruta_ia')
        self.payload = {
            'ciudad': 'Sevilla',
            'duracion': 3,
            'personas': 6,
            'exigencia': 'media',
            'mood': ['historia'],
        }

    def test_rechaza_usuario_no_autenticado(self):
        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['status'], 'ERROR')

    def test_rechaza_usuario_turista(self):
        turista_user = User.objects.create_user(username='turista', password='1234')
        TURISTA.objects.create(user=turista_user, alias='T1')
        self.client.force_login(turista_user)

        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['status'], 'ERROR')

    @patch('creacion.views._guardar_ruta_ia_en_bd')
    @patch('creacion.views._obtener_guia_para_usuario')
    @patch('creacion.views.consultar_langgraph')
    def test_delega_en_servicios_y_retorna_200(self, mock_consultar, mock_get_guia, mock_guardar):
        user = User.objects.create_user(username='guia', password='1234')
        self.client.force_login(user)

        mock_consultar.return_value = {'paradas': [{'nombre': 'A', 'coordenadas': [37.38, -5.99]}]}
        mock_get_guia.return_value = _crear_guia_para_usuario(user)
        mock_guardar.return_value = SimpleNamespace(id=99)

        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 200)
        mock_consultar.assert_called_once_with({
            'ciudad': 'Sevilla',
            'duracion': 3.0,
            'personas': 6,
            'exigencia': Ruta.Exigencia.MEDIA,
            'mood': [Ruta.Mood.HISTORIA],
            'deseos': [],
            'restricciones': [],
            'metadata': {},
        })
        mock_get_guia.assert_called_once_with(user)
        mock_guardar.assert_called_once()

        data = response.json()
        self.assertTrue(data.get('sesion_generacion_id'))
        self.assertEqual(data.get('checkpoint_actual'), 'ruta_guardada')

    @patch('creacion.views.consultar_langgraph')
    def test_devuelve_400_si_faltan_campos(self, mock_consultar):
        user = User.objects.create_user(username='guia_campos', password='1234')
        self.client.force_login(user)

        incompleto = {'ciudad': 'Sevilla'}
        response = self.client.post(self.url, data=json.dumps(incompleto), content_type='application/json')

        self.assertEqual(response.status_code, 400)
        mock_consultar.assert_not_called()

    @patch('creacion.views.consultar_langgraph')
    def test_devuelve_error_de_mood_en_errores_cuando_no_hay_etiquetas(self, mock_consultar):
        user = User.objects.create_user(username='guia_sin_mood', password='1234')
        self.client.force_login(user)

        sin_etiquetas = {
            'ciudad': 'Sevilla',
            'duracion': 2,
            'personas': 4,
            'exigencia': 'media',
            'mood': [],
        }
        response = self.client.post(self.url, data=json.dumps(sin_etiquetas), content_type='application/json')

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data.get('status'), 'ERROR')
        self.assertIn('errores', data)
        self.assertIn('mood', data.get('errores', {}))
        self.assertIn('etiqueta temática', data['errores']['mood'])
        mock_consultar.assert_not_called()

    @patch('creacion.views._obtener_guia_para_usuario')
    @patch('creacion.views.consultar_langgraph', side_effect=ValueError('datos inválidos'))
    def test_error_validacion_retorna_400(self, _mock_consultar, mock_get_guia):
        user = User.objects.create_user(username='guia_error', password='1234')
        self.client.force_login(user)
        mock_get_guia.return_value = _crear_guia_para_usuario(user)

        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Error en los datos', response.json()['mensaje'])

    @patch('creacion.views._obtener_guia_para_usuario')
    @patch(
        'creacion.views.consultar_langgraph',
        side_effect=services.ErrorValidacionRuta(
            'Esta ciudad no está contemplada en esta version de la aplicacion'
        ),
    )
    def test_ciudad_no_contemplada_retorna_mensaje_de_producto(self, mock_consultar, mock_get_guia):
        user = User.objects.create_user(username='guia_ciudad_no_contemplada', password='1234')
        self.client.force_login(user)
        mock_get_guia.return_value = _crear_guia_para_usuario(user)

        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()['mensaje'],
            'Esta ciudad no está contemplada en esta version de la aplicacion',
        )
        mock_consultar.assert_called_once()

    @patch('creacion.views._obtener_guia_para_usuario')
    @patch('creacion.views.consultar_langgraph', side_effect=services.ErrorIntegracionIA('fallo mapbox/osm'))
    def test_error_integracion_ia_retorna_502(self, _mock_consultar, mock_get_guia):
        user = User.objects.create_user(username='guia_ia_fail', password='1234')
        self.client.force_login(user)
        mock_get_guia.return_value = _crear_guia_para_usuario(user)

        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['status'], 'ERROR')

    @patch(
        'creacion.views.services.avanzar_checkpoint_sesion_generacion',
        side_effect=services.ErrorSesionGeneracionExpirada(
            'La sesión de generación ha expirado. Vuelve a iniciar la generación de la ruta.'
        ),
    )
    @patch('creacion.views.consultar_langgraph')
    def test_sesion_generacion_expirada_retorna_410(self, mock_consultar, _mock_checkpoint):
        user = User.objects.create_user(username='guia_sesion_expirada', password='1234')
        self.client.force_login(user)
        mock_consultar.return_value = {'paradas': [{'nombre': 'A', 'coordenadas': [37.38, -5.99]}]}

        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.json()['status'], 'ERROR')
        self.assertIn('expirado', response.json()['mensaje'].lower())


class GuardarRutaManualViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('creacion:guardar_ruta_manual')
        self.payload = {
            'titulo': 'Ruta Manual Centro',
            'descripcion': 'Ruta creada a mano',
            'duracion_horas': 2.5,
            'num_personas': 12,
            'nivel_exigencia': 'Media',
            'mood': ['Historia'],
            'paradas': [
                {'nombre': 'Parada 1', 'lat': 37.38, 'lon': -5.99},
                {'nombre': 'Parada 2', 'lat': 37.39, 'lon': -6.00},
            ],
        }

    def test_guardar_manual_retorna_401_sin_login(self):
        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 401)

    def test_guardar_manual_retorna_403_para_turista(self):
        turista_user = User.objects.create_user(username='turista_manual', password='1234')
        TURISTA.objects.create(user=turista_user, alias='TM')
        self.client.force_login(turista_user)

        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 403)

    @patch('creacion.views._obtener_guia_para_usuario')
    def test_guardar_manual_delega_perfil_guia_y_crea_ruta(self, mock_get_guia):
        user = User.objects.create_user(username='guia_manual', password='1234')
        self.client.force_login(user)
        auth_profile = AuthUser.objects.create(user=user)
        mock_get_guia.return_value = Guia.objects.create(user=auth_profile)

        response = self.client.post(self.url, data=json.dumps(self.payload), content_type='application/json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Ruta.objects.count(), 1)
        mock_get_guia.assert_called_once_with(user)

    def test_guardar_manual_datos_invalidos_retorna_400(self):
        user = User.objects.create_user(username='guia_manual_bad', password='1234')
        self.client.force_login(user)

        invalid_payload = {'titulo': 'Ruta Inválida', 'duracion_horas': 'no-num'}
        response = self.client.post(self.url, data=json.dumps(invalid_payload), content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'ERROR')

    def test_guardar_manual_rechaza_formulario_vacio(self):
        user = User.objects.create_user(username='guia_manual_empty', password='1234')
        self.client.force_login(user)

        empty_payload = {
            'titulo': '',
            'descripcion': '',
            'duracion_horas': '',
            'num_personas': '',
            'nivel_exigencia': '',
            'mood': [],
            'paradas': [],
        }
        response = self.client.post(self.url, data=json.dumps(empty_payload), content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'ERROR')

    def test_guardar_manual_rechaza_valores_numericos_muy_grandes(self):
        user = User.objects.create_user(username='guia_manual_grande', password='1234')
        self.client.force_login(user)

        huge_payload = {
            'titulo': 'Ruta extrema',
            'descripcion': 'Prueba de límites',
            'duracion_horas': '1e309',
            'num_personas': '10',
            'nivel_exigencia': 'Media',
            'mood': ['Historia'],
            'paradas': [
                {'nombre': 'Parada 1', 'lat': 37.38, 'lon': -5.99},
                {'nombre': 'Parada 2', 'lat': 37.39, 'lon': -6.00},
            ],
        }
        response = self.client.post(self.url, data=json.dumps(huge_payload), content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'ERROR')

    def test_guardar_manual_rechaza_parada_sin_nombre(self):
        user = User.objects.create_user(username='guia_manual_sin_nombre', password='1234')
        self.client.force_login(user)
        payload = {
            **self.payload,
            'paradas': [
                {'nombre': '   ', 'lat': 37.38, 'lon': -5.99},
                {'nombre': 'Parada 2', 'lat': 37.39, 'lon': -6.00},
            ],
        }

        response = self.client.post(self.url, data=json.dumps(payload), content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'ERROR')
        self.assertEqual(
            response.json()['errores']['parada_1'],
            'El nombre de la parada 1 es obligatorio.',
        )
        self.assertEqual(Ruta.objects.count(), 0)

    def test_guardar_manual_rechaza_nombre_parada_mayor_a_50_caracteres(self):
        user = User.objects.create_user(username='guia_manual_nombre_largo', password='1234')
        self.client.force_login(user)
        payload = {
            **self.payload,
            'paradas': [
                {'nombre': 'A' * 51, 'lat': 37.38, 'lon': -5.99},
                {'nombre': 'Parada 2', 'lat': 37.39, 'lon': -6.00},
            ],
        }

        response = self.client.post(self.url, data=json.dumps(payload), content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'ERROR')
        self.assertEqual(
            response.json()['errores']['parada_1'],
            'El nombre de la parada 1 no puede superar los 50 caracteres.',
        )
        self.assertEqual(Ruta.objects.count(), 0)


class GenerarParadasIAViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='guia_paradas', password='1234')
        auth_profile = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=auth_profile)
        self.ruta = Ruta.objects.create(
            titulo='Sevilla Cultural',
            descripcion='Ruta base',
            duracion_horas=2,
            num_personas=8,
            nivel_exigencia=Ruta.Exigencia.MEDIA,
            mood=[Ruta.Mood.HISTORIA],
            es_generada_ia=False,
            guia=self.guia,
        )
        self.url = reverse('creacion:generar_paradas_ia', kwargs={'ruta_id': self.ruta.id})

    def test_requiere_autenticacion(self):
        response = self.client.post(self.url, data='{}', content_type='application/json')

        self.assertEqual(response.status_code, 401)

    @patch('creacion.views.services.generar_candidatos_paradas_ia')
    def test_retorna_candidatos_cuando_servicio_responde_ok(self, mock_generar):
        self.client.force_login(self.user)
        self.ruta.es_generada_ia = True
        self.ruta.save(update_fields=['es_generada_ia'])
        mock_generar.return_value = {'ruta_id': self.ruta.id, 'candidatos': [{'nombre': 'Archivo'}]}

        response = self.client.post(self.url, data=json.dumps({'cantidad': 2}), content_type='application/json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'OK')
        mock_generar.assert_called_once()

    @patch('creacion.views.services.generar_candidatos_paradas_ia')
    def test_retorna_400_si_cantidad_no_es_numerica(self, mock_generar):
        self.client.force_login(self.user)
        self.ruta.es_generada_ia = True
        self.ruta.save(update_fields=['es_generada_ia'])

        response = self.client.post(self.url, data=json.dumps({'cantidad': 'abc'}), content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'ERROR')
        self.assertIn('cantidad', response.json()['mensaje'])
        mock_generar.assert_not_called()
        
    @patch('creacion.views.services.generar_candidatos_paradas_ia', side_effect=services.ErrorIntegracionIA('sin convergencia'))
    def test_retorna_200_con_candidatos_vacios_si_falla_integracion_ia(self, _mock_generar):
        self.client.force_login(self.user)
        self.ruta.es_generada_ia = True
        self.ruta.save(update_fields=['es_generada_ia'])
        response = self.client.post(self.url, data=json.dumps({'cantidad': 3}), content_type='application/json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'OK')
        self.assertEqual(response.json()['datos']['candidatos'], [])

    @patch('creacion.views.services.generar_candidatos_paradas_ia')
    def test_retorna_400_si_la_ruta_no_es_generada_con_ia(self, mock_generar):
        self.client.force_login(self.user)

        response = self.client.post(self.url, data=json.dumps({'cantidad': 3}), content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'ERROR')
        self.assertIn('solo están disponibles', response.json()['mensaje'])
        mock_generar.assert_not_called()


class SesionGeneracionIAViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='guia_sesion_ia', password='1234')
        self.client.force_login(self.user)

    @patch('creacion.views.consultar_langgraph')
    @patch('creacion.views._obtener_guia_para_usuario')
    @patch('creacion.views._guardar_ruta_ia_en_bd')
    def test_obtener_y_actualizar_checkpoint_de_sesion(self, mock_guardar, mock_guia, mock_consultar):
        mock_consultar.return_value = {'paradas': [{'nombre': 'A', 'coordenadas': [37.38, -5.99]}]}
        mock_guia.return_value = _crear_guia_para_usuario(self.user)
        mock_guardar.return_value = SimpleNamespace(id=7)

        payload = {
            'ciudad': 'Sevilla',
            'duracion': 2,
            'personas': 4,
            'exigencia': 'media',
            'mood': ['historia'],
        }
        generar_response = self.client.post(
            reverse('creacion:generar_ruta_ia'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(generar_response.status_code, 200)

        session_id = generar_response.json()['sesion_generacion_id']

        get_response = self.client.get(
            reverse('creacion:obtener_sesion_generacion_ia', kwargs={'session_id': session_id})
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()['datos']['checkpoint_actual'], 'ruta_guardada')

        update_response = self.client.post(
            reverse('creacion:actualizar_checkpoint_sesion_generacion', kwargs={'session_id': session_id}),
            data=json.dumps(
                {
                    'checkpoint': 'feedback_usuario',
                    'parada_rechazada': {'nombre': 'A', 'coordenadas': [37.38, -5.99]},
                    'motivo_rechazo': 'Ya la conocía',
                    'restricciones': ['Evitar repeticiones'],
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(update_response.status_code, 200)
        datos_actualizados = update_response.json()['datos']
        self.assertEqual(datos_actualizados['checkpoint_actual'], 'feedback_usuario')
        self.assertEqual(len(datos_actualizados['paradas_rechazadas']), 1)
        self.assertIn('Evitar repeticiones', datos_actualizados['restricciones_usuario'])


class FlujoSeleccionParadasIATests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='guia_seleccion_ia', password='1234')
        self.client.force_login(self.user)

    @patch('creacion.views._guardar_ruta_ia_en_bd')
    @patch('creacion.views.consultar_langgraph')
    def test_generar_en_modo_seleccion_devuelve_propuesta_sin_guardar(self, mock_consultar, mock_guardar):
        mock_consultar.return_value = {
            'descripcion': 'Ruta propuesta',
            'paradas': [
                {'nombre': 'Parada A', 'coordenadas': [37.38, -5.99]},
                {'nombre': 'Parada B', 'coordenadas': [37.39, -6.00]},
            ],
        }

        response = self.client.post(
            reverse('creacion:generar_ruta_ia'),
            data=json.dumps(
                {
                    'ciudad': 'Sevilla',
                    'duracion': 2,
                    'personas': 4,
                    'exigencia': 'media',
                    'mood': ['historia'],
                    'modo_seleccion': True,
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['checkpoint_actual'], 'ruta_generada')
        self.assertTrue(data.get('sesion_generacion_id'))
        self.assertEqual(len(data.get('datos_ruta', {}).get('paradas', [])), 2)
        self.assertNotIn('ruta_id', data)
        mock_guardar.assert_not_called()

    @patch('creacion.views._guardar_ruta_ia_en_bd')
    @patch('creacion.views._obtener_guia_para_usuario')
    @patch('creacion.views.consultar_langgraph')
    def test_confirmar_seleccion_guarda_ruta_y_checkpoint_final(
        self,
        mock_consultar,
        mock_get_guia,
        mock_guardar,
    ):
        mock_consultar.return_value = {
            'descripcion': 'Ruta propuesta',
            'paradas': [
                {'nombre': 'Parada A', 'coordenadas': [37.38, -5.99]},
                {'nombre': 'Parada B', 'coordenadas': [37.39, -6.00]},
            ],
        }
        mock_get_guia.return_value = _crear_guia_para_usuario(self.user)
        mock_guardar.return_value = SimpleNamespace(id=123)

        generar = self.client.post(
            reverse('creacion:generar_ruta_ia'),
            data=json.dumps(
                {
                    'ciudad': 'Sevilla',
                    'duracion': 2,
                    'personas': 4,
                    'exigencia': 'media',
                    'mood': ['historia'],
                    'modo_seleccion': True,
                    'restricciones': ['Evitar escaleras'],
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(generar.status_code, 200)
        sesion_id = generar.json()['sesion_generacion_id']

        confirmar = self.client.post(
            reverse('creacion:confirmar_ruta_ia'),
            data=json.dumps(
                {
                    'sesion_generacion_id': sesion_id,
                    'seleccion_indices': [1],
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(confirmar.status_code, 200)
        data = confirmar.json()
        self.assertEqual(data['ruta_id'], 123)
        self.assertEqual(data['checkpoint_actual'], 'ruta_guardada')
        self.assertEqual(len(data['datos_ruta']['checkpoint_contexto']['paradas_rechazadas']), 1)
        self.assertIn('Evitar escaleras', data['datos_ruta']['checkpoint_contexto']['restricciones_usuario'])
        mock_guardar.assert_called_once()

    @patch('creacion.views.services.generar_paradas_adicionales_sesion')
    @patch('creacion.views.consultar_langgraph')
    def test_generar_paradas_adicionales_actualiza_propuestas_en_sesion(self, mock_consultar, mock_generar_adicionales):
        mock_consultar.return_value = {
            'descripcion': 'Ruta propuesta',
            'paradas': [
                {'nombre': 'Parada A', 'coordenadas': [37.38, -5.99]},
                {'nombre': 'Parada B', 'coordenadas': [37.39, -6.00]},
            ],
        }
        mock_generar_adicionales.return_value = [
            {
                'id_sugerencia': 1,
                'nombre': 'Parada C',
                'coordenadas': [37.40, -6.01],
                'categoria': 'historia',
                'nivel_confianza': 0.82,
                'justificacion': 'Complementa el recorrido',
            }
        ]

        generar = self.client.post(
            reverse('creacion:generar_ruta_ia'),
            data=json.dumps(
                {
                    'ciudad': 'Sevilla',
                    'duracion': 2,
                    'personas': 4,
                    'exigencia': 'media',
                    'mood': ['historia'],
                    'modo_seleccion': True,
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(generar.status_code, 200)
        sesion_id = generar.json()['sesion_generacion_id']

        adicionales = self.client.post(
            reverse('creacion:generar_paradas_adicionales_ia'),
            data=json.dumps(
                {
                    'sesion_generacion_id': sesion_id,
                    'cantidad': 2,
                    'sugerencias': 'Añade una parada con sombra',
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(adicionales.status_code, 200)
        data = adicionales.json()
        self.assertEqual(data['checkpoint_actual'], 'paradas_adicionales_generadas')
        self.assertEqual(len(data['datos']['paradas_propuestas']), 3)
        self.assertEqual(data['datos']['paradas_propuestas'][-1]['nombre'], 'Parada C')
