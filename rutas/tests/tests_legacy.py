from unittest.mock import Mock, patch

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.urls import reverse
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError

from rutas import services as rutas_services
from rutas.models import AuthUser, Curiosidad, Guia, Ruta, Parada
from rutas.services import ServicioCuriosidadesIA


class AuthUserModelTest(TestCase):
    """Tests para el modelo AuthUser"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.auth_user = AuthUser.objects.create(user=self.user)
    
    def test_auth_user_creation(self):
        """Test que AuthUser se crea correctamente"""
        self.assertEqual(self.auth_user.user.username, 'testuser')
        self.assertEqual(str(self.auth_user), 'testuser')
    
    def test_auth_user_one_to_one_relationship(self):
        """Test que la relación OneToOne funciona correctamente"""
        retrieved_auth_user = AuthUser.objects.get(user=self.user)
        self.assertEqual(retrieved_auth_user, self.auth_user)


class GuiaModelTest(TestCase):
    """Tests para el modelo Guia"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='guiauser',
            email='guia@example.com',
            password='testpass123'
        )
        self.auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(
            user=self.auth_user,
            tipo_suscripcion=Guia.Suscripcion.PREMIUM
        )
    
    def test_guia_creation(self):
        """Test que Guia se crea correctamente"""
        self.assertEqual(self.guia.tipo_suscripcion, 'Premium')
        self.assertEqual(self.guia.user.user.username, 'guiauser')
    
    def test_guia_default_subscription(self):
        """Test que la suscripción por defecto es Freemium"""
        # Crear un nuevo usuario para evitar conflicto con el OneToOne
        user2 = User.objects.create_user(
            username='guiauser2',
            email='guia2@example.com',
            password='testpass123'
        )
        auth_user2 = AuthUser.objects.create(user=user2)
        guia_free = Guia.objects.create(user=auth_user2)
        self.assertEqual(guia_free.tipo_suscripcion, 'Freemium')
    
    def test_guia_subscription_choices(self):
        """Test que solo se pueden usar tipos de suscripción válidos"""
        # Crear un nuevo usuario para evitar conflicto con el OneToOne
        user3 = User.objects.create_user(
            username='guiauser3',
            email='guia3@example.com',
            password='testpass123'
        )
        auth_user3 = AuthUser.objects.create(user=user3)
        
        # Test 1: Valor válido pasa la validación
        guia_valido = Guia(user=auth_user3, tipo_suscripcion='Freemium')
        try:
            guia_valido.full_clean()  # Debe pasar sin error
            guia_valido.save()
        except ValidationError:
            self.fail("Guia con suscripción válida no debería lanzar ValidationError")
        
        # Test 2: Valor inválido lanza ValidationError
        user4 = User.objects.create_user(
            username='guiauser4',
            email='guia4@example.com',
            password='testpass123'
        )
        auth_user4 = AuthUser.objects.create(user=user4)
        guia_invalido = Guia(user=auth_user4, tipo_suscripcion='InvalidChoice')
        
        with self.assertRaises(ValidationError) as context:
            guia_invalido.full_clean()
        
        # Verificar que el error es específicamente del campo tipo_suscripcion
        self.assertIn('tipo_suscripcion', context.exception.message_dict)
    
    def test_guia_str_representation(self):
        """Test la representación en string de Guia"""
        expected = f"guiauser (Premium)"
        self.assertEqual(str(self.guia), expected)


class RutaModelTest(TestCase):
    """Tests para el modelo Ruta"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='rutauser',
            email='ruta@example.com',
            password='testpass123'
        )
        self.auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=self.auth_user)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Test',
            descripcion='Descripción de prueba',
            duracion_horas=2.5,
            num_personas=10,
            nivel_exigencia=Ruta.Exigencia.MEDIA,
            mood=['Historia', 'Gastronomía'],
            es_generada_ia=False,
            guia=self.guia
        )
    
    def test_ruta_creation(self):
        """Test que Ruta se crea correctamente"""
        self.assertEqual(self.ruta.titulo, 'Ruta Test')
        self.assertEqual(self.ruta.duracion_horas, 2.5)
        self.assertEqual(self.ruta.num_personas, 10)
        self.assertEqual(self.ruta.nivel_exigencia, 'Media')
        self.assertFalse(self.ruta.es_generada_ia)
    
    def test_ruta_default_values(self):
        """Test que los valores por defecto se asignan correctamente"""
        ruta = Ruta.objects.create(
            titulo='Ruta Default',
            duracion_horas=1.0,
            num_personas=5,
            guia=self.guia
        )
        self.assertEqual(ruta.nivel_exigencia, 'Media')
        self.assertFalse(ruta.es_generada_ia)
        self.assertEqual(ruta.mood, [])
    
    def test_ruta_mood_array_field(self):
        """Test que el campo mood funciona como un array"""
        ruta = Ruta.objects.create(
            titulo='Ruta Mood',
            duracion_horas=1.0,
            num_personas=5,
            mood=['Historia', 'Misterio y Leyendas', 'Cine y Series'],
            guia=self.guia
        )
        self.assertEqual(len(ruta.mood), 3)
        self.assertIn('Historia', ruta.mood)
    
    def test_ruta_all_exigencia_levels(self):
        """Test que todos los niveles de exigencia son válidos"""
        for level, _ in Ruta.Exigencia.choices:
            ruta = Ruta.objects.create(
                titulo=f'Ruta {level}',
                duracion_horas=1.0,
                num_personas=5,
                nivel_exigencia=level,
                guia=self.guia
            )
            self.assertEqual(ruta.nivel_exigencia, level)
    
    def test_ruta_all_mood_choices(self):
        """Test que todos los moods disponibles son válidos"""
        moods = [choice[0] for choice in Ruta.Mood.choices]
        ruta = Ruta.objects.create(
            titulo='Ruta All Moods',
            duracion_horas=1.0,
            num_personas=5,
            mood=moods[:3],
            guia=self.guia
        )
        self.assertEqual(len(ruta.mood), 3)
    
    def test_ruta_duracion_positive_constraint(self):
        """Test que la restricción CHECK para duracion_horas positiva funciona"""
        # Valor válido (borde): 0.0 debe permitirse
        ruta_valida = Ruta.objects.create(
            titulo='Ruta Positive',
            duracion_horas=0.0,
            num_personas=5,
            guia=self.guia
        )
        self.assertEqual(ruta_valida.duracion_horas, 0.0)

        # Valor inválido: negativo debe violar la CheckConstraint en BD
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Ruta.objects.create(
                    titulo='Ruta Negative',
                    duracion_horas=-1.0,
                    num_personas=5,
                    guia=self.guia
                )
    
    def test_ruta_str_representation(self):
        """Test la representación en string de Ruta"""
        self.assertEqual(str(self.ruta), 'Ruta Test')
    
    def test_ruta_ia_generated_flag(self):
        """Test que el flag es_generada_ia se asigna correctamente"""
        ruta_ia = Ruta.objects.create(
            titulo='Ruta IA',
            duracion_horas=1.0,
            num_personas=5,
            es_generada_ia=True,
            guia=self.guia
        )
        self.assertTrue(ruta_ia.es_generada_ia)


class ParadaModelTest(TestCase):
    """Tests para el modelo Parada"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='paradauser',
            email='parada@example.com',
            password='testpass123'
        )
        self.auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=self.auth_user)
        self.ruta = Ruta.objects.create(
            titulo='Ruta con Paradas',
            duracion_horas=2.0,
            num_personas=10,
            guia=self.guia
        )
        self.parada = Parada.objects.create(
            orden=1,
            nombre='Primera Parada',
            coordenadas=Point(-3.7038, 40.4168),  # Madrid (longitud, latitud)
            ruta=self.ruta
        )
    
    def test_parada_creation(self):
        """Test que Parada se crea correctamente"""
        self.assertEqual(self.parada.orden, 1)
        self.assertEqual(self.parada.nombre, 'Primera Parada')
        self.assertEqual(self.parada.coordenadas.x, -3.7038)
        self.assertEqual(self.parada.coordenadas.y, 40.4168)
    
    def test_parada_ordering(self):
        """Test que las paradas se ordenan por orden"""
        Parada.objects.create(
            orden=3,
            nombre='Tercera Parada',
            coordenadas=Point(-3.7038, 40.4168),  # longitud, latitud
            ruta=self.ruta
        )
        Parada.objects.create(
            orden=2,
            nombre='Segunda Parada',
            coordenadas=Point(-3.7050, 40.4200),  # longitud, latitud
            ruta=self.ruta
        )
        
        paradas = Parada.objects.filter(ruta=self.ruta)
        self.assertEqual([p.orden for p in paradas], [1, 2, 3])
    
    def test_parada_str_representation(self):
        """Test la representación en string de Parada"""
        expected = "Primera Parada (Orden: 1)"
        self.assertEqual(str(self.parada), expected)
    
    def test_parada_multiple_for_same_ruta(self):
        """Test que una ruta puede tener múltiples paradas"""
        parada2 = Parada.objects.create(
            orden=2,
            nombre='Segunda Parada',
            coordenadas=Point(-3.7050, 40.4200),  # longitud, latitud
            ruta=self.ruta
        )
        self.assertEqual(self.ruta.paradas.count(), 2)
        self.assertIn(parada2, self.ruta.paradas.all())
    
    def test_parada_cascade_delete(self):
        """Test que las paradas se eliminan cuando se elimina la ruta"""
        parada_id = self.parada.id
        self.ruta.delete()
        with self.assertRaises(Parada.DoesNotExist):
            Parada.objects.get(id=parada_id)


class RutasCatalogoViewTest(TestCase):
    """Tests para la vista rutas_catalogo"""
    
    def setUp(self):
        self.client = Client()
        self.catalogo_api_url = reverse('rutas-catalogo')
        self.user = User.objects.create_user(
            username='viewuser',
            email='view@example.com',
            password='testpass123'
        )
        self.auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=self.auth_user)
        
        # Crear rutas de prueba
        self.rutas = []
        for i in range(5):
            ruta = Ruta.objects.create(
                titulo=f'Ruta {i+1}',
                descripcion=f'Descripción {i+1}',
                duracion_horas=1.5 + i,
                num_personas=5 + i,
                mood=['Historia'] if i % 2 == 0 else ['Gastronomía'],
                guia=self.guia
            )
            # Agregar paradas a cada ruta
            Parada.objects.create(
                orden=1,
                nombre=f'Parada {i+1}-1',
                coordenadas=Point(-3.7038, 40.4168),
                ruta=ruta
            )
            Parada.objects.create(
                orden=2,
                nombre=f'Parada {i+1}-2',
                coordenadas=Point(-3.7050, 40.4200),
                ruta=ruta
            )
            self.rutas.append(ruta)
        self.client.force_login(self.user)
    
    def test_catalogo_view_basic(self):
        """Test que la vista devuelve un JSON válido"""
        response = self.client.get(self.catalogo_api_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data.get('results'), list)
    
    def test_catalogo_view_returns_all_rutas(self):
        """Test que la vista devuelve las rutas por defecto (limit 3)"""
        response = self.client.get(self.catalogo_api_url)
        data = response.json()
        self.assertEqual(len(data.get('results', [])), 3)
    
    def test_catalogo_view_limit_parameter(self):
        """Test que el parámetro limit funciona correctamente"""
        response = self.client.get(self.catalogo_api_url, {'limit': 2})
        data = response.json()
        self.assertEqual(len(data.get('results', [])), 2)
    
    def test_catalogo_view_page_parameter(self):
        """Test que el parámetro page funciona correctamente"""
        response = self.client.get(self.catalogo_api_url, {'page': 2, 'limit': 2})
        data = response.json()
        self.assertEqual(len(data.get('results', [])), 2)
        self.assertEqual(data.get('results', [])[0]['titulo'], 'Ruta 3')
    
    def test_catalogo_view_invalid_limit(self):
        """Test que un limit inválido usa el valor por defecto (3)"""
        response = self.client.get(self.catalogo_api_url, {'limit': 'abc'})
        data = response.json()
        self.assertEqual(len(data.get('results', [])), 3)
    
    def test_catalogo_view_negative_limit(self):
        """Test que un limit negativo usa el valor por defecto (3)"""
        response = self.client.get(self.catalogo_api_url, {'limit': -5})
        data = response.json()
        self.assertEqual(len(data.get('results', [])), 3)
    
    def test_catalogo_view_limit_exceeds_max(self):
        """Test que un limit mayor que MAX_RUTAS_PAGE_SIZE se limita"""
        response = self.client.get(self.catalogo_api_url, {'limit': 1000})
        data = response.json()
        self.assertLessEqual(len(data.get('results', [])), 9) # MAX_RUTAS_PAGE_SIZE
    
    def test_catalogo_view_invalid_page(self):
        """Test que una page inválida usa 1"""
        response = self.client.get(self.catalogo_api_url, {'page': 'abc'})
        data = response.json()
        self.assertEqual(len(data.get('results', [])), 3)
    
    def test_catalogo_view_negative_page(self):
        """Test que una page negativa usa 1"""
        response = self.client.get(self.catalogo_api_url, {'page': -5})
        data = response.json()
        self.assertEqual(len(data.get('results', [])), 3)
    
    def test_catalogo_view_ruta_data_structure(self):
        """Test que la estructura de datos de la ruta es correcta"""
        response = self.client.get(self.catalogo_api_url, {'limit': 1})
        data = response.json()
        
        ruta_data = data.get('results', [])[0]
        self.assertIn('id', ruta_data)
        self.assertIn('titulo', ruta_data)
        self.assertIn('descripcion', ruta_data)
        self.assertIn('duracion_horas', ruta_data)
        self.assertIn('num_personas', ruta_data)
        self.assertIn('nivel_exigencia', ruta_data)
        self.assertIn('mood', ruta_data)
        self.assertIn('es_generada_ia', ruta_data)
        self.assertIn('guia', ruta_data)
        self.assertIn('paradas', ruta_data)
    
    def test_catalogo_view_guia_info(self):
        """Test que la información del guía se incluye correctamente"""
        response = self.client.get(self.catalogo_api_url, {'limit': 1})
        data = response.json()
        
        guia_data = data.get('results', [])[0]['guia']
        self.assertIn('id', guia_data)
        self.assertIn('username', guia_data)
        self.assertEqual(guia_data['username'], 'viewuser')
    
    def test_catalogo_view_paradas_data(self):
        """Test que los datos de paradas se incluyen correctamente"""
        response = self.client.get(self.catalogo_api_url, {'limit': 1})
        data = response.json()
        
        paradas = data.get('results', [])[0]['paradas']
        self.assertEqual(len(paradas), 2)
        
        for parada in paradas:
            self.assertIn('id', parada)
            self.assertIn('orden', parada)
            self.assertIn('nombre', parada)
            self.assertIn('coordenadas', parada)
            
            if parada['coordenadas']:
                self.assertIn('lat', parada['coordenadas'])
                self.assertIn('lng', parada['coordenadas'])
    
    def test_catalogo_view_paradas_ordered(self):
        """Test que las paradas están ordenadas por orden"""
        response = self.client.get(self.catalogo_api_url, {'limit': 1})
        data = response.json()
        
        paradas = data.get('results', [])[0]['paradas']
        ordenes = [p['orden'] for p in paradas]
        self.assertEqual(ordenes, sorted(ordenes))
    
    def test_catalogo_view_mood_as_list(self):
        """Test que el mood se devuelve como lista"""
        response = self.client.get(self.catalogo_api_url, {'limit': 1})
        data = response.json()
        
        mood = data.get('results', [])[0]['mood']
        self.assertIsInstance(mood, list)
    
    def test_catalogo_view_content_type(self):
        """Test que el Content-Type es JSON con charset UTF-8"""
        response = self.client.get(self.catalogo_api_url)
        self.assertEqual(response['Content-Type'], 'application/json; charset=utf-8')
    
    def test_catalogo_view_empty_database(self):
        """Test que la vista maneja una base de datos vacía"""
        Ruta.objects.all().delete()
        response = self.client.get(self.catalogo_api_url)
        data = response.json()
        self.assertEqual(len(data.get('results', [])), 0)
        self.assertEqual(response.status_code, 200)
    
    def test_catalogo_view_ruta_requires_guia_at_model_level(self):
        """Test que no se puede crear una ruta sin guía (FK NOT NULL)"""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Ruta.objects.create(
                    titulo='Ruta Sin Guia',
                    descripcion='Debe fallar por FK obligatoria',
                    duracion_horas=1.0,
                    num_personas=5,
                    mood=['Historia'],
                    guia=None
                )


class CatalogoViewTest(TestCase):
    """Tests para la vista catalogo_view"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='viewuser2',
            password='testpass123'
        )
        self.auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=self.auth_user)
        self.client.force_login(self.user)
        self.catalogo_url = reverse('catalogo')
    
    def test_catalogo_view_returns_template(self):
        """Test que la vista catalogo_view devuelve la plantilla correcta"""
        response = self.client.get(self.catalogo_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'rutas/catalogo.html')
    
    def test_catalogo_view_is_get_only(self):
        """Test que solo se acepta GET en la vista catalogo"""
        response = self.client.post(self.catalogo_url)
        # POST no es permitido
        self.assertEqual(response.status_code, 405)


class ServicioCuriosidadesIACacheTest(TestCase):
    """Tests de almacenamiento, cacheo y errores de curiosidades IA por parada."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='curiosidadesuser',
            email='curiosidades@example.com',
            password='testpass123'
        )
        self.auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=self.auth_user)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Curiosidades',
            duracion_horas=2.0,
            num_personas=10,
            guia=self.guia,
            mood=['Historia', 'Arquitectura']
        )
        self.parada = Parada.objects.create(
            orden=1,
            nombre='Catedral de Sevilla',
            coordenadas=Point(-5.9927, 37.3861),
            ruta=self.ruta,
        )

    @patch('rutas.services.requests.get')
    @patch('rutas.services.genai.Client')
    def test_primera_solicitud_genera_y_guarda_curiosidad(self, mock_client_class, mock_requests_get):
        """Camino feliz completo: Gemini genera bien y Wikimedia devuelve imagen."""
        mock_client = mock_client_class.return_value
        mock_client.models.generate_content.return_value = Mock(
            text='{"titulo":"La Giralda y su secreto","texto":"La Giralda fue minarete antes de ser campanario cristiano.","tipo":"Historia","busqueda_imagen":"seville giralda tower"}'
        )

        mock_response = Mock()
        mock_response.json.return_value = {
            "query": {
                "pages": {
                    "123": {
                        "title": "Giralda.jpg",
                        "imageinfo": [{"url": "http://ejemplo.com/giralda.jpg"}]
                    }
                }
            }
        }
        mock_response.raise_for_status = Mock()
        mock_requests_get.return_value = mock_response

        with self.settings(GEMINI_API_KEY='test-key'):
            servicio = ServicioCuriosidadesIA()
            resultado = servicio.generar_curiosidad(self.parada, ciudad='Sevilla')

        self.assertEqual(Curiosidad.objects.filter(parada=self.parada).count(), 1)
        curiosidad = Curiosidad.objects.get(parada=self.parada)
        self.assertEqual(curiosidad.ciudad, 'Sevilla')
        self.assertEqual(curiosidad.titulo, 'La Giralda y su secreto')
        self.assertEqual(curiosidad.texto, 'La Giralda fue minarete antes de ser campanario cristiano.')
        self.assertEqual(curiosidad.imagen_url, 'http://ejemplo.com/giralda.jpg')
        self.assertEqual(resultado['titulo'], 'La Giralda y su secreto')
        
        mock_client.models.generate_content.assert_called_once()
        mock_requests_get.assert_called_once()

    @patch('rutas.services.requests.get')
    @patch('rutas.services.genai.Client')
    def test_segunda_solicitud_reutiliza_cache_sin_ia(self, mock_client_class, mock_requests_get):
        """Camino feliz: la segunda solicitud tira de base de datos."""
        mock_client = mock_client_class.return_value
        mock_client.models.generate_content.return_value = Mock(
            text='{"titulo":"Murallas y leyendas","texto":"La muralla medieval protegía la ciudad.","tipo":"Historia","busqueda_imagen":""}'
        )

        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_requests_get.return_value = mock_response

        with self.settings(GEMINI_API_KEY='test-key'):
            servicio = ServicioCuriosidadesIA()
            primera = servicio.generar_curiosidad(self.parada, ciudad='Sevilla')
            segunda = servicio.generar_curiosidad(self.parada, ciudad='Sevilla')

        self.assertEqual(Curiosidad.objects.filter(parada=self.parada).count(), 1)
        self.assertEqual(primera['titulo'], segunda['titulo'])
        self.assertEqual(primera['texto'], segunda['texto'])
        mock_client.models.generate_content.assert_called_once()

    @patch('rutas.services.requests.get')
    @patch('rutas.services.genai.Client')
    def test_generacion_usa_temas_de_la_ruta_en_el_prompt(self, mock_client_class, mock_requests_get):
        """Camino feliz: verifica que el prompt contiene los temas (moods) de la ruta."""
        mock_client = mock_client_class.return_value
        mock_client.models.generate_content.return_value = Mock(
            text='{"titulo":"Test","texto":"Test text","tipo":"Historia","busqueda_imagen":""}'
        )
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_requests_get.return_value = mock_response

        with self.settings(GEMINI_API_KEY='test-key'):
            servicio = ServicioCuriosidadesIA()
            servicio.generar_curiosidad(self.parada, ciudad='Sevilla')

        args, kwargs = mock_client.models.generate_content.call_args
        prompt = kwargs.get('contents') or args[0]
        self.assertIn('Historia', prompt)
        self.assertIn('Arquitectura', prompt)

    @patch('rutas.services.genai.Client')
    def test_ia_devuelve_json_invalido(self, mock_client_class):
        """Caso infeliz: IA devuelve JSON deformado."""
        mock_client = mock_client_class.return_value
        mock_client.models.generate_content.return_value = Mock(
            text='{"titulo": "Falta cerrar comillas...'
        )

        with self.settings(GEMINI_API_KEY='test-key'):
            servicio = ServicioCuriosidadesIA()
            with self.assertRaisesMessage(ValueError, "Error de formato: La IA no devolvió un JSON válido."):
                servicio.generar_curiosidad(self.parada, ciudad='Sevilla')

    @patch('rutas.services.genai.Client')
    def test_ia_devuelve_json_sin_texto(self, mock_client_class):
        """Caso infeliz: IA devuelve JSON pero olvida el atributo fundamental (texto)."""
        mock_client = mock_client_class.return_value
        mock_client.models.generate_content.return_value = Mock(
            text='{"titulo": "Falta el texto", "tipo": "Historia"}'
        )

        with self.settings(GEMINI_API_KEY='test-key'):
            servicio = ServicioCuriosidadesIA()
            with self.assertRaisesMessage(ValueError, "Error de formato: La IA devolvió una curiosidad sin texto."):
                servicio.generar_curiosidad(self.parada, ciudad='Sevilla')

    @patch('rutas.services.genai.Client')
    def test_ia_lanza_excepcion_api(self, mock_client_class):
        """Caso infeliz: Problema de red con Gemini o API key inválida."""
        mock_client = mock_client_class.return_value
        mock_client.models.generate_content.side_effect = Exception("API Caída")

        with self.settings(GEMINI_API_KEY='test-key'):
            servicio = ServicioCuriosidadesIA()
            with self.assertRaisesMessage(Exception, "API Caída"):
                servicio.generar_curiosidad(self.parada, ciudad='Sevilla')

    @patch('rutas.services.requests.get')
    @patch('rutas.services.genai.Client')
    def test_ia_tipo_invalido_usa_default(self, mock_client_class, mock_requests_get):
        """Caso borde: IA inventa un 'tipo'. El sistema hace fallback al por defecto."""
        mock_client = mock_client_class.return_value
        mock_client.models.generate_content.return_value = Mock(
            text='{"titulo":"Test","texto":"Test","tipo":"Inventado_Loco","busqueda_imagen":""}'
        )
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_requests_get.return_value = mock_response

        with self.settings(GEMINI_API_KEY='test-key'):
            servicio = ServicioCuriosidadesIA()
            resultado = servicio.generar_curiosidad(self.parada, ciudad='Sevilla')

        self.assertEqual(resultado['tipo'], Curiosidad.TipoCuriosidad.DATO_CURIOSO)
        curiosidad = Curiosidad.objects.get(parada=self.parada)
        self.assertEqual(curiosidad.tipo, Curiosidad.TipoCuriosidad.DATO_CURIOSO)

    @patch('rutas.services.requests.get')
    @patch('rutas.services.genai.Client')
    def test_busqueda_imagen_falla_no_rompe_generacion(self, mock_client_class, mock_requests_get):
        """Caso borde: Falla Wikimedia pero la curiosidad text-only sobrevive."""
        mock_client = mock_client_class.return_value
        mock_client.models.generate_content.return_value = Mock(
            text='{"titulo":"Test fail","texto":"Text fail","tipo":"Historia","busqueda_imagen":"tower"}'
        )
        import requests
        mock_requests_get.side_effect = requests.RequestException("Timeout")

        with self.settings(GEMINI_API_KEY='test-key'):
            servicio = ServicioCuriosidadesIA()
            resultado = servicio.generar_curiosidad(self.parada, ciudad='Sevilla')

        self.assertEqual(resultado['titulo'], 'Test fail')
        self.assertIsNone(resultado.get('imagen_url'))
        curiosidad = Curiosidad.objects.get(parada=self.parada)
        self.assertIsNone(curiosidad.imagen_url)

    @patch('rutas.services.requests.get')
    @patch('rutas.services.genai.Client')
    def test_normalizacion_payload_trunca_titulos_largos(self, mock_client_class, mock_requests_get):
        """Caso borde: título exageradamente largo es truncado para caber en BD."""
        titulo_largo = "A" * 300
        mock_client = mock_client_class.return_value
        mock_client.models.generate_content.return_value = Mock(
            text=f'{{"titulo":"{titulo_largo}","texto":"Texto válido","tipo":"Historia","busqueda_imagen":""}}'
        )
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_requests_get.return_value = mock_response

        with self.settings(GEMINI_API_KEY='test-key'):
            servicio = ServicioCuriosidadesIA()
            resultado = servicio.generar_curiosidad(self.parada, ciudad='Sevilla')

        self.assertEqual(len(resultado['titulo']), 255)
        self.assertTrue(resultado['titulo'].startswith("A" * 200))


class ObtenerOGenerarCuriosidadTest(TestCase):
    """Tests para la orquestación superior (helper) de servicios."""
    def setUp(self):
        self.user = User.objects.create_user(
            username='curiosidadesuser2',
            email='curiosidades2@example.com',
            password='testpass123'
        )
        self.auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=self.auth_user)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Func',
            duracion_horas=2.0,
            num_personas=10,
            guia=self.guia,
        )
        self.parada = Parada.objects.create(
            orden=1,
            nombre='Giralda',
            coordenadas=Point(-5.9927, 37.3861),
            ruta=self.ruta,
        )

    @patch('rutas.services.ServicioCuriosidadesIA._generar_curiosidad_ia')
    @patch('rutas.services.ServicioCuriosidadesIA._guardar_curiosidad_en_cache')
    def test_obtener_o_generar_llama_servicio_cuando_no_existe(self, mock_guardar, mock_generar):
        from rutas.services import obtener_o_generar_curiosidad_parada
        
        datos_simulados = {
            'titulo': 'Generado', 
            'texto': 'Texto', 
            'tipo': Curiosidad.TipoCuriosidad.HISTORIA,
            'imagen_url': 'url.jpg'
        }
        mock_generar.return_value = datos_simulados
        
        curiosidad_mock = Curiosidad(
            parada=self.parada, ciudad='Sevilla', titulo='Generado', texto='Texto', tipo='Historia'
        )
        mock_guardar.return_value = curiosidad_mock

        curiosidad, generada = obtener_o_generar_curiosidad_parada(self.parada, 'Sevilla')

        self.assertTrue(generada)
        self.assertEqual(curiosidad.titulo, 'Generado')
        mock_generar.assert_called_once_with(parada=self.parada, ciudad='Sevilla')
        mock_guardar.assert_called_once_with(parada=self.parada, ciudad='Sevilla', datos_curiosidad=datos_simulados)

    def test_obtener_o_generar_devuelve_existente_sin_llamar_ia(self):
        from rutas.services import obtener_o_generar_curiosidad_parada
        Curiosidad.objects.create(
            parada=self.parada,
            ciudad='Sevilla',
            titulo='Existente',
            texto='Texto',
            tipo=Curiosidad.TipoCuriosidad.HISTORIA
        )

        with patch('rutas.services.ServicioCuriosidadesIA._generar_curiosidad_ia') as mock_generar:
            curiosidad, generada = obtener_o_generar_curiosidad_parada(self.parada, 'Sevilla')
            
        self.assertFalse(generada)
        self.assertEqual(curiosidad.titulo, 'Existente')
        mock_generar.assert_not_called()



class CuriosidadParadaApiTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='curiosidaduser',
            email='curiosidad@example.com',
            password='testpass123'
        )
        self.auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=self.auth_user)
        self.ruta = Ruta.objects.create(
            titulo='Ruta Curiosidad',
            duracion_horas=2.0,
            num_personas=10,
            guia=self.guia,
        )
        self.parada = Parada.objects.create(
            orden=1,
            nombre='Catedral',
            coordenadas=Point(-5.992, 37.388),
            ruta=self.ruta,
        )
        self.url = reverse('parada-curiosidad', args=[self.parada.id])

    def test_devuelve_curiosidad_existente_sin_generar_via_ia(self):
        # ...setup...
        curiosidad = Curiosidad.objects.create(
            parada=self.parada,
            ciudad='Sevilla',
            titulo='Título existente',
            texto='Texto existente',
            tipo=Curiosidad.TipoCuriosidad.HISTORIA,
        )
        self.client.force_login(self.user)

        with patch('rutas.services.ServicioCuriosidadesIA._generar_curiosidad_ia') as mock_ia:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertFalse(data['generada'])
        self.assertEqual(data['curiosidad']['titulo'], 'Título existente')
        mock_ia.assert_not_called()

    def test_genera_y_persiste_curiosidad_si_no_existe(self):
        self.client.force_login(self.user)
        
        from django.utils import timezone
        # Simular la curiosidad guardada en BD que devolvería el helper
        mock_curiosidad = Curiosidad(
            id=999,
            parada=self.parada,
            ciudad='Sevilla',
            titulo='Sevilla bajo tus pies',
            texto='Un dato histórico breve para turistas.',
            tipo=Curiosidad.TipoCuriosidad.EVENTO,
            imagen_url=None,
            fecha_generacion=timezone.now()
        )

        with patch(
            'rutas.services.obtener_o_generar_curiosidad_parada',
            return_value=(mock_curiosidad, True),
        ) as mock_ia:
            response = self.client.get(f'{self.url}?ciudad=Sevilla')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(data['generada'])
        self.assertEqual(data['curiosidad']['titulo'], 'Sevilla bajo tus pies')
        mock_ia.assert_called_once()


class RutaDetalleMetaValidationViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='meta_view_user',
            email='meta_view@example.com',
            password='testpass123'
        )
        self.auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(
            user=self.auth_user,
            tipo_suscripcion=Guia.Suscripcion.PREMIUM,
        )
        self.ruta = Ruta.objects.create(
            titulo='Ruta Meta',
            descripcion='Ruta para validar edición meta',
            duracion_horas=2.0,
            num_personas=10,
            nivel_exigencia=Ruta.Exigencia.MEDIA,
            guia=self.guia,
        )
        self.url = reverse('ruta-detalle', kwargs={'ruta_id': self.ruta.id})
        self.client.force_login(self.user)

    def test_rechaza_duracion_extremadamente_grande_en_edicion_meta(self):
        response = self.client.post(
            self.url,
            data={
                'form_type': 'meta',
                'duracion_horas': '1e309',
                'num_personas': '10',
                'nivel_exigencia': Ruta.Exigencia.MEDIA,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('meta_error=1', response.url)

        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.duracion_horas, 2.0)
        self.assertEqual(self.ruta.num_personas, 10)

    def test_rechaza_asistentes_extremadamente_grandes_en_edicion_meta(self):
        response = self.client.post(
            self.url,
            data={
                'form_type': 'meta',
                'duracion_horas': '2',
                'num_personas': '99999999999999999999999999999999999999999999',
                'nivel_exigencia': Ruta.Exigencia.MEDIA,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('meta_error=1', response.url)

        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.duracion_horas, 2.0)
        self.assertEqual(self.ruta.num_personas, 10)

    def test_acepta_valores_validos_en_edicion_meta(self):
        response = self.client.post(
            self.url,
            data={
                'form_type': 'meta',
                'duracion_horas': '3.5',
                'num_personas': '25',
                'nivel_exigencia': Ruta.Exigencia.ALTA,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('meta_updated=1', response.url)

        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.duracion_horas, 3.5)
        self.assertEqual(self.ruta.num_personas, 25)
        self.assertEqual(self.ruta.nivel_exigencia, Ruta.Exigencia.ALTA)


class RutaEdicionValidacionesServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='edicion_user',
            email='edicion@example.com',
            password='testpass123'
        )
        self.auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=self.auth_user)
        self.ruta = Ruta.objects.create(
            titulo='Ruta edición',
            descripcion='Ruta para validar edición',
            duracion_horas=2.0,
            num_personas=10,
            guia=self.guia,
        )

    def test_actualizar_duracion_rechaza_nan_infinity_y_muy_grande(self):
        for raw in ['nan', 'inf', '1e309', '9999999999999999999999999999999']:
            with self.assertRaises(ValueError):
                rutas_services.actualizar_duracion_ruta(self.ruta, raw)

    def test_actualizar_personas_rechaza_muy_grande_y_fuera_rango(self):
        for raw in ['9999999999999999999999999999999', '0', '-1']:
            with self.assertRaises(ValueError):
                rutas_services.actualizar_personas_ruta(self.ruta, raw)

    def test_actualizar_duracion_y_personas_acepta_valores_validos(self):
        rutas_services.actualizar_duracion_ruta(self.ruta, '3.5')
        rutas_services.actualizar_personas_ruta(self.ruta, '25')
        self.ruta.refresh_from_db()

        self.assertEqual(self.ruta.duracion_horas, 3.5)
        self.assertEqual(self.ruta.num_personas, 25)
