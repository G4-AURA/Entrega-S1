import math
from django.test import TestCase
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.core.paginator import Page
from unittest.mock import patch, Mock
from rutas.models import AuthUser, Guia, Ruta, Parada
from rutas.services import (
    obtener_datos_catalogo_paginado,
    actualizar_titulo_ruta,
    actualizar_descripcion_ruta,
    actualizar_duracion_ruta,
    actualizar_personas_ruta,
    actualizar_exigencia_ruta,
    _validar_coordenadas,
    editar_parada,
    añadir_parada,
    reordenar_paradas,
    eliminar_parada_y_reordenar,
    actualizar_moods,
    eliminar_ruta
)

class RutasServicesValidationTest(TestCase):
    def setUp(self):
        # Setup base
        self.user = User.objects.create_user(username='guia_test', password='password')
        self.auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=self.auth_user)
        self.ruta = Ruta.objects.create(
            titulo="Ruta Original",
            duracion_horas=2.0,
            num_personas=5,
            guia=self.guia
        )
        self.parada1 = Parada.objects.create(
            orden=1, nombre="P1", coordenadas=Point(0, 0), ruta=self.ruta
        )
        self.parada2 = Parada.objects.create(
            orden=2, nombre="P2", coordenadas=Point(1, 1), ruta=self.ruta
        )

    # 1. Catálogo Paginado y Filtros
    def test_catalogo_paginado_tipo_ia(self):
        self.ruta.es_generada_ia = True
        self.ruta.save()
        res = obtener_datos_catalogo_paginado(self.user, 10, 1, 'ia')
        self.assertEqual(res['total_items'], 1)

    def test_catalogo_paginado_tipo_manual(self):
        res = obtener_datos_catalogo_paginado(self.user, 10, 1, 'manual')
        self.assertEqual(res['total_items'], 1)

    def test_catalogo_paginado_page_not_an_integer(self):
        res = obtener_datos_catalogo_paginado(self.user, 10, 'invalid', None)
        self.assertEqual(res['current_page'], 1)

    def test_catalogo_paginado_empty_page(self):
        res = obtener_datos_catalogo_paginado(self.user, 1, 999, None)
        # Debería devolver la última página (página 1)
        self.assertEqual(res['current_page'], 1)

    # 2. Actualizar Título
    def test_actualizar_titulo_vacio(self):
        with self.assertRaisesMessage(ValueError, "El título no puede estar vacío"):
            actualizar_titulo_ruta(self.ruta, "   ")

    def test_actualizar_titulo_demasiado_largo(self):
        with self.assertRaisesMessage(ValueError, "El título no puede superar los 255 caracteres"):
            actualizar_titulo_ruta(self.ruta, "A" * 256)

    def test_actualizar_titulo_correcto(self):
        actualizar_titulo_ruta(self.ruta, "Nuevo Titulo")
        self.assertEqual(self.ruta.titulo, "Nuevo Titulo")

    # 3. Actualizar Descripción
    def test_actualizar_descripcion_demasiado_larga(self):
        with self.assertRaisesMessage(ValueError, "La descripción no puede superar los 150 caracteres."):
            actualizar_descripcion_ruta(self.ruta, "A" * 151)

    # 4. Actualizar Duración
    def test_actualizar_duracion_invalida(self):
        with self.assertRaisesMessage(ValueError, "Valores numéricos inválidos (duración)"):
            actualizar_duracion_ruta(self.ruta, "cinco")

    def test_actualizar_duracion_infinite(self):
        with self.assertRaisesMessage(ValueError, "Valores numéricos inválidos (duración)"):
            actualizar_duracion_ruta(self.ruta, "nan")

    def test_actualizar_duracion_fuera_rango(self):
        # Mínimo es 0.5, Máximo es 24.0
        with self.assertRaisesMessage(ValueError, "Valores numéricos inválidos (duración)"):
            actualizar_duracion_ruta(self.ruta, "0.4")
        with self.assertRaisesMessage(ValueError, "Valores numéricos inválidos (duración)"):
            actualizar_duracion_ruta(self.ruta, "25.0")

    def test_actualizar_duracion_legacy_unchanged_permitida(self):
        self.ruta.duracion_horas = 1.2
        self.ruta.save(update_fields=["duracion_horas"])

        # No debe fallar si se reenvía el mismo valor legacy.
        actualizar_duracion_ruta(self.ruta, "1.2")
        self.ruta.refresh_from_db()
        self.assertAlmostEqual(self.ruta.duracion_horas, 1.2, places=6)

    def test_actualizar_duracion_legacy_changed_no_permitida(self):
        self.ruta.duracion_horas = 1.2
        self.ruta.save(update_fields=["duracion_horas"])

        # Cambiar a un valor nuevo que no es múltiplo de 0.5 debe seguir fallando.
        with self.assertRaisesMessage(ValueError, "Valores numéricos inválidos (duración)"):
            actualizar_duracion_ruta(self.ruta, "1.3")

    # 5. Actualizar Personas
    def test_actualizar_personas_invalido(self):
        with self.assertRaisesMessage(ValueError, "Valores numéricos inválidos (número de personas)"):
            actualizar_personas_ruta(self.ruta, "cinco")

    def test_actualizar_personas_fuera_rango(self):
        # Min 1, Max 50
        with self.assertRaisesMessage(ValueError, "Valores numéricos inválidos (número de personas)"):
            actualizar_personas_ruta(self.ruta, "0")
        with self.assertRaisesMessage(ValueError, "Valores numéricos inválidos (número de personas)"):
            actualizar_personas_ruta(self.ruta, "51")

    # 6. Actualizar Exigencia
    def test_actualizar_exigencia_invalida(self):
        with self.assertRaisesMessage(ValueError, "Valor inválido (nivel de exigencia)"):
            actualizar_exigencia_ruta(self.ruta, "Extrema")

    # 7. Coordenadas
    def test_validar_coordenadas_invalido_texto(self):
        with self.assertRaisesMessage(ValueError, "Coordenadas inválidas"):
            _validar_coordenadas("lat", "lon")

    def test_validar_coordenadas_infinite(self):
        with self.assertRaisesMessage(ValueError, "Coordenadas inválidas"):
            _validar_coordenadas("nan", "0")

    def test_validar_coordenadas_fuera_rango_lat(self):
        with self.assertRaisesMessage(ValueError, "Coordenadas inválidas"):
            _validar_coordenadas("91", "0")

    def test_validar_coordenadas_fuera_rango_lon(self):
        with self.assertRaisesMessage(ValueError, "Coordenadas inválidas"):
            _validar_coordenadas("0", "181")

    # 8. Editar Parada
    def test_editar_parada_nombre_vacio(self):
        with self.assertRaisesMessage(ValueError, "El nombre no puede estar vacío"):
            editar_parada(self.parada1, " ", "0", "0")

    def test_editar_parada_nombre_largo(self):
        with self.assertRaisesMessage(ValueError, "El nombre de la parada no puede superar los 255 caracteres"):
            editar_parada(self.parada1, "A" * 256, "0", "0")

    # 9. Añadir Parada
    def test_añadir_parada_nombre_vacio(self):
        with self.assertRaisesMessage(ValueError, "El nombre no puede estar vacío"):
            añadir_parada(self.ruta, " ", "0", "0")

    def test_añadir_parada_nombre_largo(self):
        with self.assertRaisesMessage(ValueError, "El nombre de la parada no puede superar los 255 caracteres"):
            añadir_parada(self.ruta, "A" * 256, "0", "0")

    # 10. Reordenar y Eliminar
    def test_reordenar_paradas(self):
        reordenar_paradas(self.ruta, [self.parada2.id, self.parada1.id])
        self.parada1.refresh_from_db()
        self.parada2.refresh_from_db()
        self.assertEqual(self.parada2.orden, 1)
        self.assertEqual(self.parada1.orden, 2)

    def test_eliminar_parada_y_reordenar(self):
        eliminar_parada_y_reordenar(self.ruta, self.parada1)
        self.parada2.refresh_from_db()
        self.assertEqual(self.parada2.orden, 1)
        self.assertEqual(Parada.objects.filter(ruta=self.ruta).count(), 1)

    # 11. Eliminar Ruta
    def test_eliminar_ruta(self):
        ruta_id = self.ruta.id
        eliminar_ruta(self.ruta)
        self.assertFalse(Ruta.objects.filter(id=ruta_id).exists())

    # 12. Actualizar Moods
    def test_actualizar_moods_invalidos_ignoran(self):
        # Moods válidos: Historia, Gastronómia...
        actualizar_moods(self.ruta, ["Historia", "Invalido"])
        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.mood, ["Historia"])

    def test_catalogo_paginado_guia_exception_handling(self):
        """Prueba que si falla el acceso al guía (ej. AttributeError en proxy), el bucle continúa."""
        from unittest.mock import PropertyMock
        with patch.object(Ruta, 'guia', new_callable=PropertyMock) as mock_guia:
             mock_guia.side_effect = Exception("Fallo acceso guía")
             res = obtener_datos_catalogo_paginado(self.user, 10, 1, None)
             # El listado debe salir procesando los datos comunes sin petar
             self.assertEqual(res['total_items'], 1)

    @patch('rutas.services.requests.get')
    def test_buscar_wikimedia_missing_imageinfo(self, mock_get):
        """Wikimedia devuelve páginas pero ninguna tiene 'imageinfo'."""
        from rutas.services import ServicioCuriosidadesIA
        mock_response = Mock()
        mock_response.json.return_value = {
            "query": {
                "pages": {
                    "123": {"title": "Sin_Info.jpg"} # sin 'imageinfo'
                }
            }
        }
        mock_get.return_value = mock_response
        servicio = ServicioCuriosidadesIA()
        res = servicio._buscar_wikimedia("giralda")
        self.assertIsNone(res)


from unittest.mock import patch, Mock
from django.contrib.gis.geos import LineString
from rutas.graphhopper import GraphHopperError
from rutas.services import recalcular_ruta_graphhopper

class RutasServicesGraphHopperTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='guia_test2', password='password')
        self.auth_user = AuthUser.objects.create(user=self.user)
        self.guia = Guia.objects.create(user=self.auth_user)
        self.ruta = Ruta.objects.create(titulo="Ruta GH", duracion_horas=2, num_personas=5, guia=self.guia)
        self.parada1 = Parada.objects.create(orden=1, nombre="P1", coordenadas=Point(0, 0), ruta=self.ruta)
        self.parada2 = Parada.objects.create(orden=2, nombre="P2", coordenadas=Point(1, 1), ruta=self.ruta)



    @patch('rutas.graphhopper.calcular_ruta')
    def test_recalcular_ruta_graphhopper_error(self, mock_calc):
        mock_calc.side_effect = GraphHopperError("Simulado")
        res = recalcular_ruta_graphhopper(self.ruta)
        self.assertFalse(res)

    @patch('rutas.graphhopper.calcular_ruta')
    def test_recalcular_ruta_graphhopper_unexpected_error(self, mock_calc):
        mock_calc.side_effect = Exception("Inesperado")
        res = recalcular_ruta_graphhopper(self.ruta)
        self.assertFalse(res)

    def test_recalcular_ruta_graphhopper_less_than_two_paradas(self):
        self.parada2.delete() # Dejar solo 1
        res = recalcular_ruta_graphhopper(self.ruta)
        self.assertFalse(res)
        self.ruta.refresh_from_db()
        self.assertIsNone(self.ruta.distancia_total_m)
