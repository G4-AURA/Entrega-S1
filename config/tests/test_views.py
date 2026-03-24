from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from config.views import SuperuserAwareLoginView, home_router, registro


class SuperuserAwareLoginViewTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

    def _make_view(self, user, next_url=None):
        request = self.factory.get('/accounts/login/')
        request.user = user
        view = SuperuserAwareLoginView()
        view.request = request
        view.get_redirect_url = MagicMock(return_value=next_url)
        return view

    def test_superusuario_con_next_no_admin_usa_ese_next(self):
        user = MagicMock(is_superuser=True)
        view = self._make_view(user, next_url='/tours/')
        self.assertEqual(view.get_success_url(), '/tours/')

    def test_superusuario_con_next_admin_redirige_a_allowlist(self):
        user = MagicMock(is_superuser=True)
        view = self._make_view(user, next_url='/admin/')
        result = str(view.get_success_url())
        self.assertIn('allow', result.lower())

    def test_superusuario_sin_next_redirige_a_allowlist(self):
        user = MagicMock(is_superuser=True)
        view = self._make_view(user, next_url=None)
        result = str(view.get_success_url())
        self.assertIn('allow', result.lower())

    def test_usuario_normal_con_next_usa_ese_next(self):
        user = MagicMock(is_superuser=False)
        view = self._make_view(user, next_url='/catalogo/')
        self.assertEqual(view.get_success_url(), '/catalogo/')

    def test_usuario_normal_sin_next_usa_url_por_defecto(self):
        user = MagicMock(is_superuser=False)
        view = self._make_view(user, next_url=None)
        result = view.get_success_url()
        self.assertIsNotNone(result)


@override_settings(MAPBOX_ACCESS_TOKEN='test-token')
class HomeRouterViewTest(TestCase):

    def test_anonimo_muestra_landing(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'landing.html')

    def test_superusuario_redirige_a_panel_allowlist(self):
        User.objects.create_superuser(
            username='admin', password='admin123', email='admin@test.com'
        )
        self.client.login(username='admin', password='admin123')
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('allow', response['Location'].lower())

    def test_guia_redirige_al_catalogo(self):
        from rutas.models import AuthUser, Guia

        user = User.objects.create_user(username='guia1', password='pass123')
        auth_user = AuthUser.objects.create(user=user)
        Guia.objects.create(user=auth_user)

        self.client.login(username='guia1', password='pass123')
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/catalogo/', response['Location'])

    def test_usuario_autenticado_sin_guia_redirige_al_catalogo(self):
        User.objects.create_user(username='plain', password='pass123')
        self.client.login(username='plain', password='pass123')
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/catalogo/', response['Location'])

    def test_usuario_con_auth_profile_sin_guia_usa_fallback(self):
        from rutas.models import AuthUser

        user = User.objects.create_user(username='noguia', password='pass123')
        AuthUser.objects.create(user=user)
        self.client.login(username='noguia', password='pass123')
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/catalogo/', response['Location'])


@override_settings(MAPBOX_ACCESS_TOKEN='test-token')
class RegistroViewTest(TestCase):

    def get_valid_data(self):
        return {
            'username': 'newguia',
            'email': 'newguia@example.com',
            'first_name': 'Nuevo',
            'last_name': 'Guia',
            'password1': 'SuperSecure123!',
            'password2': 'SuperSecure123!',
        }

    def test_usuario_autenticado_redirigido_al_catalogo(self):
        User.objects.create_user(username='existing', password='pass123')
        self.client.login(username='existing', password='pass123')
        response = self.client.get(reverse('registro'))
        self.assertRedirects(
            response, reverse('catalogo'), fetch_redirect_response=False
        )

    def test_get_registro_muestra_formulario(self):
        response = self.client.get(reverse('registro'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'registration/registro.html')
        self.assertIn('form', response.context)

    def test_post_datos_validos_crea_usuario_auth_y_guia(self):
        from rutas.models import AuthUser, Guia

        response = self.client.post(reverse('registro'), self.get_valid_data())
        self.assertRedirects(
            response, reverse('catalogo'), fetch_redirect_response=False
        )
        self.assertTrue(User.objects.filter(username='newguia').exists())
        user = User.objects.get(username='newguia')
        self.assertTrue(AuthUser.objects.filter(user=user).exists())
        auth_user = AuthUser.objects.get(user=user)
        self.assertTrue(Guia.objects.filter(user=auth_user).exists())

    def test_post_datos_invalidos_muestra_formulario_de_nuevo(self):
        response = self.client.post(reverse('registro'), {'username': ''})
        self.assertEqual(response.status_code, 200)
        self.assertIn('form', response.context)
