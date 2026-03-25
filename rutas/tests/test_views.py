from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from rutas.models import AuthUser, Guia, Ruta, Parada, Curiosidad
from unittest.mock import patch, Mock

class RutasViewsTest(TestCase):
    def setUp(self):
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
            'num_personas': '18',
            'nivel_exigencia': 'Alta'
        })
        self.assertRedirects(response, f"{url}?meta_updated=1")
        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.num_personas, 18)
        self.assertEqual(self.ruta.nivel_exigencia, 'Alta')

    def test_ruta_detalle_post_stop_add_success(self):
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'stop_add',
            'nombre': 'Parada 2',
            'lat': '10.0',
            'lon': '10.0'
        })
        self.assertRedirects(response, f"{url}?stop_added=1")
        self.assertEqual(self.ruta.paradas.count(), 2)

    def test_ruta_detalle_post_stop_edit_success(self):
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'stop_edit',
            'parada_id': self.parada.id,
            'nombre': 'Parada Editada',
            'lat': '5.0',
            'lon': '5.0'
        })
        self.assertRedirects(response, f"{url}?stop_updated=1")

    def test_ruta_detalle_post_stop_delete_success(self):
        url = reverse('ruta-detalle', args=[self.ruta.id])
        response = self.client.post(url, {
            'form_type': 'stop_delete',
            'parada_id': self.parada.id
        })
        self.assertRedirects(response, f"{url}?stop_deleted=1")

    def test_ruta_detalle_post_stop_reorder_success(self):
        parada2 = Parada.objects.create(orden=2, nombre="P2", coordenadas=Point(1, 1), ruta=self.ruta)
        url = reverse('ruta-detalle', args=[self.ruta.id])
        # Enviar orden invertido: [2, 1]
        response = self.client.post(url, {
            'form_type': 'stop_reorder',
            'stop_order': f"{parada2.id},{self.parada.id}"
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
