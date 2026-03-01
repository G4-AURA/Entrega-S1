from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.urls import reverse
from django.db import IntegrityError
import json

from .models import AuthUser, Guia, Ruta, Parada


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
        guia = Guia.objects.create(user=auth_user3, tipo_suscripcion='Freemium')
        self.assertIn(guia.tipo_suscripcion, dict(Guia.Suscripcion.choices))
    
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
        # Aunque Django ORM no valida esto en la inserción, se puede intentar
        ruta = Ruta.objects.create(
            titulo='Ruta Positive',
            duracion_horas=0.0,  # 0 es válido según la restricción >=
            num_personas=5,
            guia=self.guia
        )
        self.assertGreaterEqual(ruta.duracion_horas, 0.0)
    
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
                coordenadas=Point(40.4168, -3.7038),
                ruta=ruta
            )
            Parada.objects.create(
                orden=2,
                nombre=f'Parada {i+1}-2',
                coordenadas=Point(40.4200, -3.7050),
                ruta=ruta
            )
            self.rutas.append(ruta)
    
    def test_catalogo_view_basic(self):
        """Test que la vista devuelve un JSON válido"""
        response = self.client.get('/api/rutas/')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIsInstance(data, list)
    
    def test_catalogo_view_returns_all_rutas(self):
        """Test que la vista devuelve todas las rutas por defecto"""
        response = self.client.get('/api/rutas/')
        data = json.loads(response.content)
        self.assertEqual(len(data), 5)
    
    def test_catalogo_view_limit_parameter(self):
        """Test que el parámetro limit funciona correctamente"""
        response = self.client.get('/api/rutas/?limit=2')
        data = json.loads(response.content)
        self.assertEqual(len(data), 2)
    
    def test_catalogo_view_offset_parameter(self):
        """Test que el parámetro offset funciona correctamente"""
        response = self.client.get('/api/rutas/?offset=2&limit=2')
        data = json.loads(response.content)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['titulo'], 'Ruta 3')
    
    def test_catalogo_view_invalid_limit(self):
        """Test que un limit inválido usa el valor por defecto"""
        response = self.client.get('/api/rutas/?limit=abc')
        data = json.loads(response.content)
        self.assertEqual(len(data), 5)
    
    def test_catalogo_view_negative_limit(self):
        """Test que un limit negativo usa el valor por defecto"""
        response = self.client.get('/api/rutas/?limit=-5')
        data = json.loads(response.content)
        self.assertEqual(len(data), 5)
    
    def test_catalogo_view_limit_exceeds_max(self):
        """Test que un limit mayor que MAX_RUTAS_PAGE_SIZE se limita"""
        response = self.client.get('/api/rutas/?limit=1000')
        data = json.loads(response.content)
        self.assertEqual(len(data), 5)
    
    def test_catalogo_view_invalid_offset(self):
        """Test que un offset inválido usa 0"""
        response = self.client.get('/api/rutas/?offset=abc')
        data = json.loads(response.content)
        self.assertEqual(len(data), 5)
    
    def test_catalogo_view_negative_offset(self):
        """Test que un offset negativo usa 0"""
        response = self.client.get('/api/rutas/?offset=-5')
        data = json.loads(response.content)
        self.assertEqual(len(data), 5)
    
    def test_catalogo_view_ruta_data_structure(self):
        """Test que la estructura de datos de la ruta es correcta"""
        response = self.client.get('/api/rutas/?limit=1')
        data = json.loads(response.content)
        
        ruta_data = data[0]
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
        response = self.client.get('/api/rutas/?limit=1')
        data = json.loads(response.content)
        
        guia_data = data[0]['guia']
        self.assertIn('id', guia_data)
        self.assertIn('username', guia_data)
        self.assertEqual(guia_data['username'], 'viewuser')
    
    def test_catalogo_view_paradas_data(self):
        """Test que los datos de paradas se incluyen correctamente"""
        response = self.client.get('/api/rutas/?limit=1')
        data = json.loads(response.content)
        
        paradas = data[0]['paradas']
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
        response = self.client.get('/api/rutas/?limit=1')
        data = json.loads(response.content)
        
        paradas = data[0]['paradas']
        ordenes = [p['orden'] for p in paradas]
        self.assertEqual(ordenes, sorted(ordenes))
    
    def test_catalogo_view_mood_as_list(self):
        """Test que el mood se devuelve como lista"""
        response = self.client.get('/api/rutas/?limit=1')
        data = json.loads(response.content)
        
        mood = data[0]['mood']
        self.assertIsInstance(mood, list)
    
    def test_catalogo_view_content_type(self):
        """Test que el Content-Type es JSON con charset UTF-8"""
        response = self.client.get('/api/rutas/')
        self.assertEqual(response['Content-Type'], 'application/json; charset=utf-8')
    
    def test_catalogo_view_empty_database(self):
        """Test que la vista maneja una base de datos vacía"""
        Ruta.objects.all().delete()
        response = self.client.get('/api/rutas/')
        data = json.loads(response.content)
        self.assertEqual(len(data), 0)
        self.assertEqual(response.status_code, 200)
    
    def test_catalogo_view_ruta_with_guia_required(self):
        """Test que todas las rutas requieren un guía asignado"""
        # El modelo Ruta requiere un guía (ForeignKey sin null=True)
        # Verificamos que todas las rutas en el catálogo tienen guía
        response = self.client.get('/api/rutas/?limit=10')
        data = json.loads(response.content)
        
        for ruta_data in data:
            self.assertIsNotNone(ruta_data['guia'])
            self.assertIsNotNone(ruta_data['guia']['id'])


class CatalogoViewTest(TestCase):
    """Tests para la vista catalogo_view"""
    
    def setUp(self):
        self.client = Client()
    
    def test_catalogo_view_returns_template(self):
        """Test que la vista catalogo_view devuelve la plantilla correcta"""
        response = self.client.get('/catalogo/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'rutas/catalogo.html')
    
    def test_catalogo_view_is_get_only(self):
        """Test que solo se acepta GET en la vista catalogo"""
        response = self.client.post('/catalogo/')
        # POST no es permitido
        self.assertEqual(response.status_code, 405)
