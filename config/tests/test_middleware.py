import json

from django.http import JsonResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings

from config.middleware import ApiErrorMiddleware


class ApiErrorMiddlewareUnitTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_normaliza_error_json_y_agrega_request_id(self):
        middleware = ApiErrorMiddleware(
            lambda request: JsonResponse(
                {
                    'status': 'ERROR',
                    'mensaje': 'Falló la validación',
                    'code': 'CUSTOM_ERROR',
                    'extra': 'valor',
                },
                status=400,
            )
        )

        request = self.factory.get('/billing/create-checkout-session/')
        response = middleware(request)
        body = json.loads(response.content.decode('utf-8'))

        self.assertEqual(response.status_code, 400)
        self.assertIn('X-Request-ID', response)
        self.assertEqual(body['request_id'], response['X-Request-ID'])
        self.assertEqual(body['error'], 'Falló la validación')
        self.assertEqual(body['code'], 'CUSTOM_ERROR')
        self.assertEqual(body['mensaje'], 'Falló la validación')
        self.assertEqual(body['extra'], 'valor')
        self.assertEqual(body['status'], 'ERROR')

    def test_reutiliza_request_id_inyectado_por_el_cliente(self):
        middleware = ApiErrorMiddleware(lambda request: JsonResponse({'error': 'Falló'}, status=403))

        request = self.factory.get(
            '/billing/create-checkout-session/',
            HTTP_X_REQUEST_ID='client-123',
        )
        response = middleware(request)
        body = json.loads(response.content.decode('utf-8'))

        self.assertEqual(response['X-Request-ID'], 'client-123')
        self.assertEqual(body['request_id'], 'client-123')
        self.assertEqual(body['error'], 'Falló')

    def test_convierte_excepcion_no_controlada_en_json(self):
        middleware = ApiErrorMiddleware(lambda request: None)
        request = self.factory.post(
            '/billing/create-checkout-session/',
            content_type='application/json',
            HTTP_ACCEPT='application/json',
        )

        response = middleware.process_exception(request, RuntimeError('boom'))
        body = json.loads(response.content.decode('utf-8'))

        self.assertEqual(response.status_code, 500)
        self.assertEqual(body['code'], 'INTERNAL_SERVER_ERROR')
        self.assertIn('error', body)
        self.assertIn('request_id', body)
        self.assertEqual(response['X-Request-ID'], body['request_id'])


@override_settings(STRIPE_ENABLED=False)
class ApiErrorMiddlewareIntegrationTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_respuesta_de_api_real_incluye_request_id(self):
        response = self.client.post(
            '/billing/create-checkout-session/',
            data='{}',
            content_type='application/json',
            HTTP_ACCEPT='application/json',
        )

        body = response.json()

        self.assertEqual(response.status_code, 401)
        self.assertIn('X-Request-ID', response)
        self.assertEqual(body['request_id'], response['X-Request-ID'])
        self.assertEqual(body['error'], 'Debes iniciar sesión para acceder al checkout.')

    def test_endpoint_creacion_sin_autenticacion_incluye_request_id(self):
        '''Verifica que endpoint de creacion también normaliza con request_id.'''
        response = self.client.post(
            '/crear-ruta/api/rutas/123/paradas-ia/',
            data='{}',
            content_type='application/json',
            HTTP_ACCEPT='application/json',
        )

        body = response.json()

        self.assertEqual(response.status_code, 401)
        self.assertIn('X-Request-ID', response)
        self.assertEqual(body['request_id'], response['X-Request-ID'])
        self.assertIn('error', body)

    def test_endpoint_allowlist_sin_permisos_incluye_request_id(self):
        '''Verifica que endpoint de allowList también normaliza con request_id (no superuser).'''
        from django.contrib.auth.models import User
        # Crear usuario no superusuario
        user = User.objects.create_user(username='user_no_super', password='pass123')
        self.client.login(username='user_no_super', password='pass123')
        
        response = self.client.post(
            '/allowList/api/buscar-osm/',
            data='{}',
            content_type='application/json',
            HTTP_ACCEPT='application/json',
        )

        # No es superusuario, así que devuelve 403 con JsonResponse de middlewear
        self.assertEqual(response.status_code, 403)
        self.assertIn('X-Request-ID', response)
        body = response.json()
        self.assertEqual(body['request_id'], response['X-Request-ID'])
        self.assertIn('error', body)

    def test_cliente_puede_inyectar_request_id_y_se_propaga(self):
        '''Verifica que cliente puede enviar X-Request-ID y se devuelve integro.'''
        custom_id = 'req-client-123-abc'
        response = self.client.post(
            '/billing/create-checkout-session/',
            data='{}',
            content_type='application/json',
            HTTP_ACCEPT='application/json',
            HTTP_X_REQUEST_ID=custom_id,
        )

        body = response.json()

        self.assertEqual(response['X-Request-ID'], custom_id)
        self.assertEqual(body['request_id'], custom_id)