from django.test import TestCase
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point, LineString
from rutas.models import AuthUser, Guia, Ruta, Parada, Curiosidad
from rutas.admin import RutaAdmin
from django.contrib import admin

class RutasModelsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='test_user', password='password')
        self.auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=self.auth_user, tipo_suscripcion=Guia.Suscripcion.PREMIUM)
        
        self.ruta = Ruta.objects.create(
            titulo="Ruta de Prueba",
            duracion_horas=2.5,
            num_personas=10,
            guia=self.guia,
            mood=["Historia", "Naturaleza"]
        )
        
        self.parada = Parada.objects.create(
            orden=1,
            nombre="Parada 1",
            coordenadas=Point(1.0, 2.0, srid=4326),
            ruta=self.ruta
        )

        self.curiosidad = Curiosidad.objects.create(
            parada=self.parada,
            ciudad="Sevilla",
            titulo="Curiosidad 1",
            texto="Un texto interesante."
        )

    def test_strings_representation(self):
        """Prueba de los métodos __str__ de los modelos."""
        self.assertEqual(str(self.auth_user), "test_user")
        self.assertEqual(str(self.guia), "test_user (Premium)")
        self.assertEqual(str(self.ruta), "Ruta de Prueba")
        self.assertEqual(str(self.parada), "Parada 1 (Orden: 1)")
        self.assertEqual(str(self.curiosidad), "Curiosidad 1 (Parada 1)")

    def test_ruta_properties_calculated(self):
        """Prueba de las propiedades calculadas en el modelo Ruta con datos."""
        self.ruta.distancia_total_m = 1500.0
        self.ruta.duracion_total_s = 3600
        # LineString requiere al menos 2 puntos
        self.ruta.geometria_ruta = LineString((0, 0), (1, 1), srid=4326)
        
        self.assertEqual(self.ruta.distancia_total_km, "1.5")
        self.assertEqual(self.ruta.duracion_total_min, 60)
        # Lat, Lon invertidos (Leaflet)
        self.assertEqual(self.ruta.geometria_ruta_coords, [[0.0, 0.0], [1.0, 1.0]])

    def test_ruta_properties_calculated_empty(self):
        """Prueba de las propiedades calculadas en el modelo Ruta sin datos (Null)."""
        self.ruta.distancia_total_m = None
        self.ruta.duracion_total_s = None
        self.ruta.geometria_ruta = None
        
        self.assertIsNone(self.ruta.distancia_total_km)
        self.assertIsNone(self.ruta.duracion_total_min)
        self.assertIsNone(self.ruta.geometria_ruta_coords)

    def test_parada_properties_calculated(self):
        """Prueba de propiedades calculadas en el modelo Parada."""
        self.parada.duracion_siguiente_s = 120
        self.assertEqual(self.parada.duracion_siguiente_min, 2)

    def test_parada_properties_calculated_empty(self):
        self.parada.duracion_siguiente_s = None
        self.assertIsNone(self.parada.duracion_siguiente_min)


class RutasAdminTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin_tester', password='password')
        self.auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=self.auth_user)
        self.ruta_admin = RutaAdmin(Ruta, admin.site)

    def test_mood_display_with_items(self):
        """Comprueba mood_display cuando hay moods en la lista."""
        ruta = Ruta(titulo="Ruta Test", guia=self.guia, mood=["Historia", "Naturaleza"])
        display = self.ruta_admin.mood_display(ruta)
        self.assertEqual(display, "Historia, Naturaleza")

    def test_mood_display_empty(self):
        """Comprueba mood_display cuando la lista de moods está vacía."""
        ruta = Ruta(titulo="Ruta Test", guia=self.guia, mood=[])
        display = self.ruta_admin.mood_display(ruta)
        self.assertEqual(display, "")
        
    def test_mood_display_none(self):
        """Comprueba mood_display cuando el mood es None."""
        ruta = Ruta(titulo="Ruta Test", guia=self.guia, mood=None)
        display = self.ruta_admin.mood_display(ruta)
        self.assertEqual(display, "")
