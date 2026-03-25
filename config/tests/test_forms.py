from django.test import TestCase
from django.contrib.auth.models import User

from config.forms import RegistroUsuarioForm


class RegistroUsuarioFormTest(TestCase):

    def get_valid_data(self):
        return {
            'username': 'testuser',
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        }

    def test_formulario_valido_es_valido(self):
        form = RegistroUsuarioForm(data=self.get_valid_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_guardar_crea_usuario_con_campos_correctos(self):
        form = RegistroUsuarioForm(data=self.get_valid_data())
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertIsNotNone(user.pk)
        self.assertEqual(user.first_name, 'Test')
        self.assertEqual(user.last_name, 'User')
        self.assertEqual(user.email, 'test@example.com')

    def test_email_es_obligatorio(self):
        data = self.get_valid_data()
        data['email'] = ''
        form = RegistroUsuarioForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_formato_email_invalido(self):
        data = self.get_valid_data()
        data['email'] = 'not-an-email'
        form = RegistroUsuarioForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_email_duplicado_lanza_error_de_validacion(self):
        User.objects.create_user(
            username='existing', email='test@example.com', password='pass123'
        )
        data = self.get_valid_data()
        form = RegistroUsuarioForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_email_duplicado_sin_distinguir_mayusculas(self):
        User.objects.create_user(
            username='existing', email='test@example.com', password='pass123'
        )
        data = self.get_valid_data()
        data['email'] = 'TEST@EXAMPLE.COM'
        form = RegistroUsuarioForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_email_se_normaliza_a_minusculas(self):
        data = self.get_valid_data()
        data['email'] = 'Test@Example.COM'
        form = RegistroUsuarioForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['email'], 'test@example.com')

    def test_clean_email_elimina_espacios(self):
        data = self.get_valid_data()
        data['email'] = '  clean@example.com  '
        form = RegistroUsuarioForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['email'], 'clean@example.com')

    def test_nombre_es_obligatorio(self):
        data = self.get_valid_data()
        data['first_name'] = ''
        form = RegistroUsuarioForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('first_name', form.errors)

    def test_apellidos_son_obligatorios(self):
        data = self.get_valid_data()
        data['last_name'] = ''
        form = RegistroUsuarioForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('last_name', form.errors)

    def test_contrasenas_no_coinciden(self):
        data = self.get_valid_data()
        data['password2'] = 'DifferentPass456!'
        form = RegistroUsuarioForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('password2', form.errors)
