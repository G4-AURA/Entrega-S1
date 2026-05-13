"""
allowList/tests.py

Suite completa de pruebas unitarias para el módulo AllowList.

Cubre:
  - Modelo POI: creación, propiedades, validaciones
  - Servicios: búsqueda OSM, importación, creación manual, listado, eliminación
  - Vistas (API JSON): todos los endpoints REST
  - Permisos: solo superusuarios pueden acceder
  - Casos límite y manejo de errores
"""
import json
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from allowList.models import CategoriaOSM, POI
from allowList import services
from allowList.management.commands.import_city_boundary import Command as ImportCityBoundaryCommand


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _crear_poi(
    nombre="Catedral de Sevilla",
    categoria=CategoriaOSM.MONUMENTO,
    ciudad="Sevilla",
    lat=37.386,
    lon=-5.992,
    fuente=POI.Fuente.MANUAL,
    osm_id=None,
):
    return POI.objects.create(
        nombre=nombre,
        categoria=categoria,
        ciudad=ciudad,
        coordenadas=Point(lon, lat, srid=4326),
        fuente=fuente,
        osm_id=osm_id,
    )


def _superuser():
    return User.objects.create_superuser(
        username="admin_test", password="admin123", email="admin@test.com"
    )


def _user_normal():
    return User.objects.create_user(username="normal_test", password="normal123")


class ImportCityBoundaryCommandUnitTest(SimpleTestCase):
    def test_extrae_varias_ciudades_desde_feature_collection(self):
        raw = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"nombre": "Málaga"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[-4.5, 36.7], [-4.4, 36.7], [-4.4, 36.8], [-4.5, 36.7]]],
                    },
                },
                {
                    "type": "Feature",
                    "properties": {"nombre": "Sevilla"},
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [[[[-6.0, 37.3], [-5.9, 37.3], [-5.9, 37.4], [-6.0, 37.3]]]],
                    },
                },
            ],
        }

        boundaries = ImportCityBoundaryCommand._extract_boundaries(raw)

        self.assertEqual([city for city, _geometry in boundaries], ["Málaga", "Sevilla"])

    def test_filtra_ciudad_con_acentos_en_feature_collection(self):
        raw = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"nombre": "Málaga"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[-4.5, 36.7], [-4.4, 36.7], [-4.4, 36.8], [-4.5, 36.7]]],
                    },
                },
                {
                    "type": "Feature",
                    "properties": {"nombre": "Sevilla"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[-6.0, 37.3], [-5.9, 37.3], [-5.9, 37.4], [-6.0, 37.3]]],
                    },
                },
            ],
        }

        boundaries = ImportCityBoundaryCommand._extract_boundaries(raw, ciudad="Malaga")

        self.assertEqual(len(boundaries), 1)
        self.assertEqual(boundaries[0][0], "Málaga")


# ─────────────────────────────────────────────────────────────────────────────
# Tests del modelo POI
# ─────────────────────────────────────────────────────────────────────────────

class POIModelTest(TestCase):
    """Tests sobre el modelo POI."""

    def test_creacion_poi_manual(self):
        """Un POI manual se crea con los campos correctos."""
        poi = _crear_poi(
            nombre="Plaza de España",
            categoria=CategoriaOSM.PLAZA,
            ciudad="Sevilla",
            lat=37.377,
            lon=-5.987,
        )

        self.assertEqual(poi.nombre, "Plaza de España")
        self.assertEqual(poi.categoria, "place=square")
        self.assertEqual(poi.ciudad, "Sevilla")
        self.assertEqual(poi.fuente, POI.Fuente.MANUAL)
        self.assertIsNone(poi.osm_id)
        self.assertIsNotNone(poi.id)

    def test_propiedades_lat_lon(self):
        """Las propiedades lat y lon devuelven los valores correctos."""
        poi = _crear_poi(lat=37.386, lon=-5.992)

        self.assertAlmostEqual(poi.lat, 37.386, places=3)
        self.assertAlmostEqual(poi.lon, -5.992, places=3)

    def test_str_representation(self):
        """La representación en string incluye nombre, categoría y ciudad."""
        poi = _crear_poi(nombre="Museo del Prado", ciudad="Madrid")
        str_repr = str(poi)

        self.assertIn("Museo del Prado", str_repr)
        self.assertIn("Madrid", str_repr)

    def test_str_sin_ciudad(self):
        """La representación en string maneja POI sin ciudad."""
        poi = POI.objects.create(
            nombre="Lugar sin ciudad",
            categoria=CategoriaOSM.OTRO,
            coordenadas=Point(-5.99, 37.38, srid=4326),
            fuente=POI.Fuente.MANUAL,
            ciudad="",
        )
        self.assertIn("sin ciudad", str(poi))

    def test_poi_osm_tiene_osm_id(self):
        """Un POI de origen OSM tiene osm_id y osm_type."""
        poi = _crear_poi(
            fuente=POI.Fuente.OSM,
            osm_id=123456789,
        )
        poi.osm_type = "node"
        poi.save()

        self.assertEqual(poi.osm_id, 123456789)
        self.assertEqual(poi.fuente, POI.Fuente.OSM)

    def test_osm_id_es_unico(self):
        """Dos POIs no pueden tener el mismo osm_id."""
        from django.db import IntegrityError, transaction

        _crear_poi(fuente=POI.Fuente.OSM, osm_id=111)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _crear_poi(fuente=POI.Fuente.OSM, osm_id=111)

    def test_orden_por_nombre(self):
        """El ordering por defecto del modelo es por nombre."""
        _crear_poi(nombre="Zaragoza")
        _crear_poi(nombre="Avila")
        _crear_poi(nombre="Madrid")

        nombres = list(POI.objects.values_list("nombre", flat=True))
        self.assertEqual(nombres, sorted(nombres))

    def test_categoria_choices_validos(self):
        """Todas las categorías de CategoriaOSM son válidas."""
        for valor, _ in CategoriaOSM.choices:
            poi = POI.objects.create(
                nombre=f"POI {valor}",
                categoria=valor,
                coordenadas=Point(-5.99, 37.38, srid=4326),
                fuente=POI.Fuente.MANUAL,
            )
            self.assertEqual(poi.categoria, valor)

    def test_get_categoria_display(self):
        """get_categoria_display devuelve la etiqueta legible."""
        poi = _crear_poi(categoria=CategoriaOSM.MUSEO)
        self.assertEqual(poi.get_categoria_display(), "Museo")

    def test_fuente_choices(self):
        """Los valores de Fuente son los esperados."""
        self.assertEqual(POI.Fuente.OSM, "osm")
        self.assertEqual(POI.Fuente.MANUAL, "manual")


# ─────────────────────────────────────────────────────────────────────────────
# Tests de services.crear_poi_manual
# ─────────────────────────────────────────────────────────────────────────────

class CrearPOIManualServiceTest(TestCase):
    """Tests del servicio de creación manual de POIs."""

    def test_crea_poi_correctamente(self):
        """El servicio crea un POI con todos los campos."""
        poi = services.crear_poi_manual(
            nombre="Alcázar de Sevilla",
            lat=37.383,
            lon=-5.990,
            categoria=CategoriaOSM.CASTILLO,
            ciudad="Sevilla",
            direccion="Patio de Banderas, s/n",
        )

        self.assertIsInstance(poi, POI)
        self.assertEqual(poi.nombre, "Alcázar de Sevilla")
        self.assertEqual(poi.ciudad, "Sevilla")
        self.assertEqual(poi.fuente, POI.Fuente.MANUAL)
        self.assertAlmostEqual(poi.lat, 37.383, places=3)
        self.assertAlmostEqual(poi.lon, -5.990, places=3)

    def test_crea_poi_sin_campos_opcionales(self):
        """El servicio funciona sin ciudad ni dirección."""
        poi = services.crear_poi_manual(
            nombre="Lugar sin ciudad",
            lat=40.0,
            lon=-3.0,
            categoria=CategoriaOSM.OTRO,
        )

        self.assertEqual(poi.ciudad, "")
        self.assertEqual(poi.direccion, "")

    def test_nombre_vacio_lanza_error(self):
        """Nombre vacío lanza ErrorValidacionPOI."""
        with self.assertRaises(services.ErrorValidacionPOI):
            services.crear_poi_manual(nombre="", lat=37.0, lon=-5.0, categoria=CategoriaOSM.OTRO)

    def test_nombre_solo_espacios_lanza_error(self):
        """Nombre con solo espacios lanza ErrorValidacionPOI."""
        with self.assertRaises(services.ErrorValidacionPOI):
            services.crear_poi_manual(nombre="   ", lat=37.0, lon=-5.0, categoria=CategoriaOSM.OTRO)

    def test_nombre_muy_largo_lanza_error(self):
        """Nombre de más de 255 caracteres lanza ErrorValidacionPOI."""
        with self.assertRaises(services.ErrorValidacionPOI):
            services.crear_poi_manual(
                nombre="A" * 256, lat=37.0, lon=-5.0, categoria=CategoriaOSM.OTRO
            )

    def test_categoria_invalida_lanza_error(self):
        """Categoría no reconocida lanza ErrorValidacionPOI."""
        with self.assertRaises(services.ErrorValidacionPOI):
            services.crear_poi_manual(
                nombre="Test", lat=37.0, lon=-5.0, categoria="categoria=invalida"
            )

    def test_coordenadas_no_numericas_lanzan_error(self):
        """Coordenadas no numéricas lanzan ErrorValidacionPOI."""
        with self.assertRaises(services.ErrorValidacionPOI):
            services.crear_poi_manual(
                nombre="Test", lat="no-es-numero", lon=-5.0, categoria=CategoriaOSM.OTRO
            )

    def test_latitud_fuera_de_rango_lanza_error(self):
        """Latitud fuera de [-90, 90] lanza ErrorValidacionPOI."""
        with self.assertRaises(services.ErrorValidacionPOI):
            services.crear_poi_manual(
                nombre="Test", lat=91.0, lon=-5.0, categoria=CategoriaOSM.OTRO
            )

    def test_longitud_fuera_de_rango_lanza_error(self):
        """Longitud fuera de [-180, 180] lanza ErrorValidacionPOI."""
        with self.assertRaises(services.ErrorValidacionPOI):
            services.crear_poi_manual(
                nombre="Test", lat=37.0, lon=181.0, categoria=CategoriaOSM.OTRO
            )

    def test_coordenadas_como_strings_se_convierten(self):
        """El servicio acepta coordenadas como strings numéricos."""
        poi = services.crear_poi_manual(
            nombre="Test Strings", lat="37.386", lon="-5.992", categoria=CategoriaOSM.OTRO
        )
        self.assertAlmostEqual(poi.lat, 37.386, places=3)

    def test_coordenadas_en_limite_validas(self):
        """Coordenadas en los bordes del rango son válidas."""
        poi_max = services.crear_poi_manual(
            nombre="Polo Sur", lat=-90.0, lon=-180.0, categoria=CategoriaOSM.OTRO
        )
        self.assertAlmostEqual(poi_max.lat, -90.0, places=1)


# ─────────────────────────────────────────────────────────────────────────────
# Tests de services.listar_pois
# ─────────────────────────────────────────────────────────────────────────────

class ListarPOIsServiceTest(TestCase):
    """Tests del servicio de listado de POIs."""

    def setUp(self):
        _crear_poi(nombre="Museo Reina Sofia", ciudad="Madrid", categoria=CategoriaOSM.MUSEO, fuente=POI.Fuente.OSM, osm_id=1)
        _crear_poi(nombre="Museo del Prado", ciudad="Madrid", categoria=CategoriaOSM.MUSEO, fuente=POI.Fuente.OSM, osm_id=2)
        _crear_poi(nombre="Catedral de Sevilla", ciudad="Sevilla", categoria=CategoriaOSM.MONUMENTO, fuente=POI.Fuente.MANUAL)
        _crear_poi(nombre="Parque del Retiro", ciudad="Madrid", categoria=CategoriaOSM.PARQUE, fuente=POI.Fuente.MANUAL)

    def test_lista_todos_sin_filtros(self):
        """Sin filtros devuelve todos los POIs paginados."""
        resultado = services.listar_pois()
        self.assertEqual(resultado["total"], 4)

    def test_filtra_por_ciudad(self):
        """El filtro por ciudad devuelve solo los de esa ciudad."""
        resultado = services.listar_pois(ciudad="Madrid")
        self.assertEqual(resultado["total"], 3)
        ciudades = {r["ciudad"] for r in resultado["results"]}
        self.assertEqual(ciudades, {"Madrid"})

    def test_filtra_por_ciudad_insensible_a_mayusculas(self):
        """El filtro de ciudad es insensible a mayúsculas."""
        resultado = services.listar_pois(ciudad="madrid")
        self.assertEqual(resultado["total"], 3)

    def test_filtra_por_categoria(self):
        """El filtro por categoría devuelve solo los de esa categoría."""
        resultado = services.listar_pois(categoria=CategoriaOSM.MUSEO)
        self.assertEqual(resultado["total"], 2)

    def test_filtra_por_fuente(self):
        """El filtro por fuente devuelve solo los de ese origen."""
        resultado = services.listar_pois(fuente=POI.Fuente.MANUAL)
        self.assertEqual(resultado["total"], 2)
        fuentes = {r["fuente"] for r in resultado["results"]}
        self.assertEqual(fuentes, {POI.Fuente.MANUAL})

    def test_paginacion_basica(self):
        """La paginación limita correctamente los resultados."""
        resultado = services.listar_pois(limit=2, page=1)
        self.assertEqual(len(resultado["results"]), 2)
        self.assertEqual(resultado["total"], 4)
        self.assertEqual(resultado["total_pages"], 2)

    def test_paginacion_segunda_pagina(self):
        """La segunda página devuelve los elementos correctos."""
        resultado = services.listar_pois(limit=2, page=2)
        self.assertEqual(len(resultado["results"]), 2)
        self.assertEqual(resultado["page"], 2)

    def test_sin_resultados_devuelve_estructura_correcta(self):
        """Sin resultados devuelve estructura válida con total=0."""
        resultado = services.listar_pois(ciudad="Tokio")
        self.assertEqual(resultado["total"], 0)
        self.assertEqual(resultado["results"], [])
        self.assertEqual(resultado["total_pages"], 1)

    def test_resultado_contiene_campos_requeridos(self):
        """Cada resultado contiene todos los campos esperados."""
        resultado = services.listar_pois(limit=1)
        item = resultado["results"][0]
        campos = ["id", "nombre", "categoria", "categoria_label", "lat", "lon", "ciudad", "fuente"]
        for campo in campos:
            self.assertIn(campo, item)

    def test_filtros_combinados(self):
        """Los filtros se pueden combinar."""
        resultado = services.listar_pois(ciudad="Madrid", categoria=CategoriaOSM.MUSEO)
        self.assertEqual(resultado["total"], 2)

    def test_listar_pois_para_mapa_no_pagina(self):
        """El mapa recibe todos los POIs filtrados, no solo una página."""
        resultado = services.listar_pois_para_mapa(ciudad="Madrid")
        self.assertEqual(len(resultado), 3)
        self.assertTrue(all("lat" in item and "lon" in item for item in resultado))


# ─────────────────────────────────────────────────────────────────────────────
# Tests de services.eliminar_poi
# ─────────────────────────────────────────────────────────────────────────────

class EliminarPOIServiceTest(TestCase):
    """Tests del servicio de eliminación de POIs."""

    def test_elimina_poi_existente(self):
        """Eliminar un POI existente lo borra de la BD."""
        poi = _crear_poi()
        poi_id = poi.id

        services.eliminar_poi(poi_id)

        self.assertFalse(POI.objects.filter(id=poi_id).exists())

    def test_eliminar_poi_inexistente_lanza_error(self):
        """Eliminar un POI que no existe lanza ErrorValidacionPOI."""
        with self.assertRaises(services.ErrorValidacionPOI):
            services.eliminar_poi(99999)

    def test_eliminar_reduce_conteo(self):
        """Eliminar un POI reduce el total en BD."""
        _crear_poi(nombre="POI 1")
        poi2 = _crear_poi(nombre="POI 2", osm_id=9999)
        total_antes = POI.objects.count()

        services.eliminar_poi(poi2.id)

        self.assertEqual(POI.objects.count(), total_antes - 1)


# ─────────────────────────────────────────────────────────────────────────────
# Tests de services.importar_pois_desde_osm
# ─────────────────────────────────────────────────────────────────────────────

class ImportarPOIsOSMServiceTest(TestCase):
    """Tests del servicio de importación de POIs desde OSM."""

    def _elemento_osm(self, osm_id, nombre, lat=37.386, lon=-5.992, categoria=CategoriaOSM.MONUMENTO):
        return {
            "osm_id": osm_id,
            "osm_type": "node",
            "nombre": nombre,
            "lat": lat,
            "lon": lon,
            "categoria": categoria,
        }

    def test_importa_elementos_correctamente(self):
        """Importar una lista válida crea los POIs en BD."""
        elementos = [
            self._elemento_osm(1001, "Giralda"),
            self._elemento_osm(1002, "Torre del Oro"),
        ]

        resultado = services.importar_pois_desde_osm(elementos, ciudad="Sevilla")

        self.assertEqual(resultado["creados"], 2)
        self.assertEqual(resultado["ya_existian"], 0)
        self.assertEqual(resultado["errores"], 0)
        self.assertEqual(POI.objects.count(), 2)

    def test_idempotente_no_duplica_por_osm_id(self):
        """Importar el mismo OSM ID dos veces no crea duplicados."""
        elemento = [self._elemento_osm(2001, "Real Alcazar")]

        services.importar_pois_desde_osm(elemento, ciudad="Sevilla")
        resultado = services.importar_pois_desde_osm(elemento, ciudad="Sevilla")

        self.assertEqual(resultado["ya_existian"], 1)
        self.assertEqual(resultado["creados"], 0)
        self.assertEqual(POI.objects.filter(osm_id=2001).count(), 1)

    def test_ciudad_asignada_correctamente(self):
        """Los POIs importados tienen la ciudad indicada."""
        elementos = [self._elemento_osm(3001, "Test Ciudad")]
        services.importar_pois_desde_osm(elementos, ciudad="Granada")

        poi = POI.objects.get(osm_id=3001)
        self.assertEqual(poi.ciudad, "Granada")

    def test_fuente_osm_asignada(self):
        """Los POIs importados tienen fuente=osm."""
        elementos = [self._elemento_osm(4001, "Test Fuente")]
        services.importar_pois_desde_osm(elementos, ciudad="Cordoba")

        poi = POI.objects.get(osm_id=4001)
        self.assertEqual(poi.fuente, POI.Fuente.OSM)

    def test_elemento_sin_nombre_cuenta_como_error(self):
        """Elemento sin nombre es ignorado y cuenta como error."""
        elementos = [{"osm_id": 5001, "osm_type": "node", "nombre": "", "lat": 37.0, "lon": -5.0}]
        resultado = services.importar_pois_desde_osm(elementos, ciudad="Sevilla")

        self.assertEqual(resultado["errores"], 1)
        self.assertEqual(resultado["creados"], 0)

    def test_lista_vacia_lanza_error(self):
        """Importar lista vacía lanza ErrorValidacionPOI."""
        with self.assertRaises(services.ErrorValidacionPOI):
            services.importar_pois_desde_osm([], ciudad="Sevilla")

    def test_mezcla_nuevos_y_existentes(self):
        """Importar mezcla de nuevos y ya existentes funciona correctamente."""
        servicios_inicial = [self._elemento_osm(6001, "El Nuevo")]
        services.importar_pois_desde_osm(servicios_inicial, ciudad="Sevilla")

        mezcla = [
            self._elemento_osm(6001, "El Nuevo"),
            self._elemento_osm(6002, "El Otro"),
        ]
        resultado = services.importar_pois_desde_osm(mezcla, ciudad="Sevilla")

        self.assertEqual(resultado["creados"], 1)
        self.assertEqual(resultado["ya_existian"], 1)


# ─────────────────────────────────────────────────────────────────────────────
# Tests de services.serializar_pois_para_ruta
# ─────────────────────────────────────────────────────────────────────────────

class SerializarPOIsParaRutaServiceTest(TestCase):
    """Tests de la serialización de POIs para el motor de rutas."""

    def setUp(self):
        _crear_poi(nombre="Museo", ciudad="Sevilla", categoria=CategoriaOSM.MUSEO)
        _crear_poi(nombre="Parque", ciudad="Sevilla", categoria=CategoriaOSM.PARQUE)
        _crear_poi(nombre="Bar", ciudad="Madrid", categoria=CategoriaOSM.BAR)

    def test_devuelve_pois_de_ciudad(self):
        """Solo devuelve POIs de la ciudad indicada."""
        resultado = services.serializar_pois_para_ruta(ciudad="Sevilla")
        self.assertEqual(len(resultado), 2)

    def test_estructura_del_resultado(self):
        """Cada elemento tiene las claves correctas."""
        resultado = services.serializar_pois_para_ruta(ciudad="Sevilla")
        for item in resultado:
            self.assertIn("nombre", item)
            self.assertIn("coords", item)
            self.assertIn("desc", item)
            self.assertIsInstance(item["coords"], list)
            self.assertEqual(len(item["coords"]), 2)

    def test_filtra_por_categorias(self):
        """El filtro por categorías reduce los resultados."""
        resultado = services.serializar_pois_para_ruta(
            ciudad="Sevilla", categorias=[CategoriaOSM.MUSEO]
        )
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["nombre"], "Museo")

    def test_ciudad_sin_pois_devuelve_lista_vacia(self):
        """Ciudad sin POIs devuelve lista vacía."""
        resultado = services.serializar_pois_para_ruta(ciudad="Tokio")
        self.assertEqual(resultado, [])


# ─────────────────────────────────────────────────────────────────────────────
# Tests de services.buscar_pois_osm (con mock de Overpass)
# ─────────────────────────────────────────────────────────────────────────────

class BuscarPOIsOSMServiceTest(TestCase):
    """Tests del servicio de búsqueda en OSM (con mock de Overpass API)."""

    def _respuesta_overpass_ok(self, elementos):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"elements": elementos}
        return mock_resp

    def _elemento_node(self, osm_id, nombre, lat=37.386, lon=-5.992, extra_tags=None):
        tags = {"name": nombre}
        if extra_tags:
            tags.update(extra_tags)
        return {"type": "node", "id": osm_id, "lat": lat, "lon": lon, "tags": tags}

    @patch("allowList.services.requests.post")
    def test_busqueda_basica_devuelve_resultados(self, mock_post):
        """Búsqueda básica devuelve lista de POIs."""
        mock_post.return_value = self._respuesta_overpass_ok([
            self._elemento_node(1, "Catedral", extra_tags={"tourism": "museum"}),
        ])

        resultado = services.buscar_pois_osm("Sevilla", [CategoriaOSM.MUSEO])

        self.assertIsInstance(resultado, list)
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["nombre"], "Catedral")

    @patch("allowList.services.requests.post")
    def test_elemento_sin_nombre_es_ignorado(self, mock_post):
        """Elementos sin nombre en tags se descartan."""
        mock_post.return_value = self._respuesta_overpass_ok([
            {"type": "node", "id": 99, "lat": 37.386, "lon": -5.992, "tags": {}},
        ])

        resultado = services.buscar_pois_osm("Sevilla", [CategoriaOSM.MUSEO])
        self.assertEqual(resultado, [])

    @patch("allowList.services.requests.post")
    def test_ya_importado_se_marca_correctamente(self, mock_post):
        """Elemento ya en la BD se marca como ya_importado=True."""
        _crear_poi(fuente=POI.Fuente.OSM, osm_id=777)
        mock_post.return_value = self._respuesta_overpass_ok([
            self._elemento_node(777, "El Ya Importado"),
        ])

        resultado = services.buscar_pois_osm("Sevilla", [CategoriaOSM.MUSEO])
        self.assertTrue(resultado[0]["ya_importado"])

    @patch("allowList.services.requests.post")
    def test_elemento_nuevo_no_marcado_como_importado(self, mock_post):
        """Elemento nuevo no se marca como ya_importado."""
        mock_post.return_value = self._respuesta_overpass_ok([
            self._elemento_node(888, "El Nuevo"),
        ])

        resultado = services.buscar_pois_osm("Sevilla", [CategoriaOSM.MUSEO])
        self.assertFalse(resultado[0]["ya_importado"])

    @patch("allowList.services.requests.post")
    def test_estructura_resultado(self, mock_post):
        """Cada resultado contiene los campos esperados."""
        mock_post.return_value = self._respuesta_overpass_ok([
            self._elemento_node(1, "Test", extra_tags={"historic": "monument"}),
        ])

        resultado = services.buscar_pois_osm("Sevilla", [CategoriaOSM.MONUMENTO])

        self.assertEqual(len(resultado), 1)
        item = resultado[0]
        for campo in ["osm_id", "osm_type", "nombre", "lat", "lon", "categoria", "ya_importado"]:
            self.assertIn(campo, item)

    @patch("allowList.services.requests.post")
    def test_timeout_lanza_error_integracion(self, mock_post):
        """Timeout de Overpass lanza ErrorIntegracionOSM."""
        import requests as req_lib
        mock_post.side_effect = req_lib.Timeout("timeout")

        with self.assertRaises(services.ErrorIntegracionOSM):
            services.buscar_pois_osm("Sevilla", [CategoriaOSM.MUSEO])

    @patch("allowList.services.requests.post")
    def test_error_http_lanza_error_integracion(self, mock_post):
        """Error HTTP de Overpass lanza ErrorIntegracionOSM."""
        import requests as req_lib
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_lib.HTTPError(response=MagicMock(status_code=500))
        mock_post.return_value = mock_resp

        with self.assertRaises(services.ErrorIntegracionOSM):
            services.buscar_pois_osm("Sevilla", [CategoriaOSM.MUSEO])

    def test_ciudad_vacia_lanza_error_validacion(self):
        """Ciudad vacía lanza ErrorValidacionPOI."""
        with self.assertRaises(services.ErrorValidacionPOI):
            services.buscar_pois_osm("", [CategoriaOSM.MUSEO])

    def test_sin_categorias_validas_lanza_error_validacion(self):
        """Sin categorías válidas (solo 'other') lanza ErrorValidacionPOI."""
        with self.assertRaises(services.ErrorValidacionPOI):
            services.buscar_pois_osm("Sevilla", [CategoriaOSM.OTRO])

    @patch("allowList.services.requests.post")
    def test_normalizacion_nombre_ciudad(self, mock_post):
        """El nombre de ciudad se normaliza antes de la búsqueda."""
        mock_post.return_value = self._respuesta_overpass_ok([])
        services.buscar_pois_osm("SEVILLA", [CategoriaOSM.MUSEO])

        call_args = mock_post.call_args
        data_enviado = call_args.kwargs.get("data") or call_args[1].get("data") or call_args[0][1]
        query_enviada = data_enviado.get("data", "")
        self.assertIn("Sevilla", query_enviada)

    @patch("allowList.services.requests.post")
    def test_pais_iso_incluido_en_query(self, mock_post):
        """Un país reconocido añade filtro ISO a la query de Overpass."""
        mock_post.return_value = self._respuesta_overpass_ok([])
        services.buscar_pois_osm("Madrid", [CategoriaOSM.MUSEO], pais="España")

        call_args = mock_post.call_args
        data_enviado = call_args.kwargs.get("data") or call_args[0][1]
        query_enviada = data_enviado.get("data", "")
        self.assertIn("ES", query_enviada)


# ─────────────────────────────────────────────────────────────────────────────
# Tests de las vistas (endpoints API JSON)
# ─────────────────────────────────────────────────────────────────────────────

class AllowlistPermisosTest(TestCase):
    """Los endpoints solo son accesibles para superusuarios."""

    def setUp(self):
        self.superuser = _superuser()
        self.user = _user_normal()
        self.client = Client()

    def test_panel_requiere_superuser(self):
        """El panel HTML requiere superusuario."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("allowlist:panel"))
        self.assertEqual(response.status_code, 403)

    def test_panel_accesible_para_superuser(self):
        """El panel es accesible para superusuario."""
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("allowlist:panel"))
        self.assertEqual(response.status_code, 200)

    def test_panel_redirige_anonimo(self):
        """Sin autenticar redirige al login."""
        response = self.client.get(reverse("allowlist:panel"))
        self.assertEqual(response.status_code, 302)

    def test_api_listar_requiere_superuser(self):
        """API de listado requiere superusuario."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("allowlist:api_listar"))
        self.assertEqual(response.status_code, 403)

    def test_api_mapa_requiere_superuser(self):
        """API del mapa requiere superusuario."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("allowlist:api_mapa"))
        self.assertEqual(response.status_code, 403)

    def test_api_crear_manual_requiere_superuser(self):
        """API de creación manual requiere superusuario."""
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("allowlist:api_crear_manual"),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_api_buscar_osm_requiere_superuser(self):
        """API de búsqueda OSM requiere superusuario."""
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("allowlist:api_buscar_osm"),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_api_eliminar_requiere_superuser(self):
        """API de eliminación requiere superusuario."""
        poi = _crear_poi()
        self.client.force_login(self.user)
        response = self.client.post(reverse("allowlist:api_eliminar", args=[poi.id]))
        self.assertEqual(response.status_code, 403)


class ApiListarPOIsViewTest(TestCase):
    """Tests del endpoint GET /allowList/api/listar/"""

    def setUp(self):
        self.client = Client()
        self.client.force_login(_superuser())
        _crear_poi(nombre="Museo A", ciudad="Sevilla", categoria=CategoriaOSM.MUSEO, fuente=POI.Fuente.OSM, osm_id=1)
        _crear_poi(nombre="Museo B", ciudad="Madrid", categoria=CategoriaOSM.MUSEO, fuente=POI.Fuente.MANUAL)
        _crear_poi(nombre="Parque C", ciudad="Sevilla", categoria=CategoriaOSM.PARQUE, fuente=POI.Fuente.MANUAL)

    def test_devuelve_todos_sin_filtros(self):
        """Sin filtros devuelve todos los POIs."""
        response = self.client.get(reverse("allowlist:api_listar"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 3)

    def test_filtra_por_ciudad(self):
        """Filtro ciudad funciona correctamente."""
        response = self.client.get(reverse("allowlist:api_listar"), {"ciudad": "Sevilla"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 2)

    def test_filtra_por_categoria(self):
        """Filtro categoria funciona correctamente."""
        response = self.client.get(
            reverse("allowlist:api_listar"), {"categoria": CategoriaOSM.MUSEO}
        )
        data = response.json()
        self.assertEqual(data["total"], 2)

    def test_filtra_por_fuente(self):
        """Filtro fuente funciona correctamente."""
        response = self.client.get(
            reverse("allowlist:api_listar"), {"fuente": POI.Fuente.OSM}
        )
        data = response.json()
        self.assertEqual(data["total"], 1)

    def test_paginacion_con_limit(self):
        """El parámetro limit pagina correctamente."""
        response = self.client.get(reverse("allowlist:api_listar"), {"limit": "2"})
        data = response.json()
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["total_pages"], 2)

    def test_estructura_respuesta(self):
        """La respuesta tiene la estructura esperada."""
        response = self.client.get(reverse("allowlist:api_listar"))
        data = response.json()
        self.assertIn("results", data)
        self.assertIn("total", data)
        self.assertIn("page", data)
        self.assertIn("total_pages", data)
        self.assertEqual(data["status"], "OK")

    def test_solo_acepta_get(self):
        """El endpoint solo acepta GET."""
        response = self.client.post(reverse("allowlist:api_listar"))
        self.assertEqual(response.status_code, 405)


class ApiMapaPOIsViewTest(TestCase):
    """Tests del endpoint GET /allowList/api/mapa/"""

    def setUp(self):
        self.client = Client()
        self.client.force_login(_superuser())
        for idx in range(55):
            _crear_poi(
                nombre=f"POI Sevilla {idx:02d}",
                ciudad="Sevilla",
                categoria=CategoriaOSM.MUSEO if idx % 2 == 0 else CategoriaOSM.PARQUE,
                lat=37.38 + idx * 0.0001,
                lon=-5.99 - idx * 0.0001,
            )
        _crear_poi(nombre="POI Madrid", ciudad="Madrid", categoria=CategoriaOSM.MUSEO)

    def test_devuelve_todos_los_pois_sin_paginacion(self):
        """El mapa recibe todos los POIs que cumplen los filtros."""
        response = self.client.get(reverse("allowlist:api_mapa"), {"ciudad": "Sevilla"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["total"], 55)
        self.assertEqual(len(data["results"]), 55)

    def test_respeta_filtros_del_panel(self):
        """El endpoint del mapa usa los mismos filtros que la tabla."""
        response = self.client.get(
            reverse("allowlist:api_mapa"),
            {"ciudad": "Sevilla", "categoria": CategoriaOSM.PARQUE},
        )
        data = response.json()
        self.assertEqual(data["total"], 27)
        self.assertTrue(all(item["categoria"] == CategoriaOSM.PARQUE for item in data["results"]))

    def test_solo_acepta_get(self):
        """El endpoint del mapa solo acepta GET."""
        response = self.client.post(reverse("allowlist:api_mapa"))
        self.assertEqual(response.status_code, 405)


class ApiCrearManualViewTest(TestCase):
    """Tests del endpoint POST /allowList/api/crear-manual/"""

    def setUp(self):
        self.client = Client()
        self.client.force_login(_superuser())

    def _post(self, payload):
        return self.client.post(
            reverse("allowlist:api_crear_manual"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_crea_poi_correctamente(self):
        """Payload válido crea el POI y devuelve 201."""
        response = self._post({
            "nombre": "Torre del Oro",
            "lat": 37.382,
            "lon": -5.996,
            "categoria": CategoriaOSM.MONUMENTO,
            "ciudad": "Sevilla",
        })

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], "OK")
        self.assertIn("poi_id", data)
        self.assertTrue(POI.objects.filter(id=data["poi_id"]).exists())

    def test_nombre_vacio_retorna_400(self):
        """Nombre vacío retorna 400."""
        response = self._post({"nombre": "", "lat": 37.0, "lon": -5.0, "categoria": CategoriaOSM.OTRO})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "ERROR")

    def test_categoria_invalida_retorna_400(self):
        """Categoría inválida retorna 400."""
        response = self._post({"nombre": "Test", "lat": 37.0, "lon": -5.0, "categoria": "invalida"})
        self.assertEqual(response.status_code, 400)

    def test_coordenadas_invalidas_retorna_400(self):
        """Coordenadas fuera de rango retorna 400."""
        response = self._post({"nombre": "Test", "lat": 200.0, "lon": -5.0, "categoria": CategoriaOSM.OTRO})
        self.assertEqual(response.status_code, 400)

    def test_json_invalido_retorna_400(self):
        """JSON inválido retorna 400."""
        response = self.client.post(
            reverse("allowlist:api_crear_manual"),
            data="{bad json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_campos_opcionales_ciudad_y_direccion(self):
        """Los campos ciudad y dirección son opcionales."""
        response = self._post({"nombre": "Solo coords", "lat": 37.0, "lon": -5.0, "categoria": CategoriaOSM.OTRO})
        self.assertEqual(response.status_code, 201)

    def test_solo_acepta_post(self):
        """El endpoint solo acepta POST."""
        response = self.client.get(reverse("allowlist:api_crear_manual"))
        self.assertEqual(response.status_code, 405)


class ApiEliminarPOIViewTest(TestCase):
    """Tests del endpoint POST /allowList/api/eliminar/<id>/"""

    def setUp(self):
        self.client = Client()
        self.client.force_login(_superuser())

    def test_elimina_poi_existente(self):
        """Eliminar POI existente devuelve 200 y OK."""
        poi = _crear_poi()
        response = self.client.post(reverse("allowlist:api_eliminar", args=[poi.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "OK")
        self.assertFalse(POI.objects.filter(id=poi.id).exists())

    def test_eliminar_poi_inexistente_retorna_404(self):
        """Eliminar POI inexistente retorna 404."""
        response = self.client.post(reverse("allowlist:api_eliminar", args=[99999]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["status"], "ERROR")

    def test_solo_acepta_post(self):
        """El endpoint solo acepta POST."""
        poi = _crear_poi()
        response = self.client.get(reverse("allowlist:api_eliminar", args=[poi.id]))
        self.assertEqual(response.status_code, 405)


class ApiBuscarOSMViewTest(TestCase):
    """Tests del endpoint POST /allowList/api/buscar-osm/"""

    def setUp(self):
        self.client = Client()
        self.client.force_login(_superuser())

    def _post(self, payload):
        return self.client.post(
            reverse("allowlist:api_buscar_osm"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    @patch("allowList.services.requests.post")
    def test_busqueda_valida_devuelve_resultados(self, mock_post):
        """Payload válido con categorías válidas devuelve resultados."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "elements": [
                {"type": "node", "id": 1, "lat": 37.386, "lon": -5.992,
                 "tags": {"name": "Catedral", "tourism": "museum"}},
            ]
        }
        mock_post.return_value = mock_resp

        response = self._post({"ciudad": "Sevilla", "categorias": [CategoriaOSM.MUSEO]})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "OK")
        self.assertIn("resultados", data)
        self.assertIn("total", data)

    def test_ciudad_vacia_retorna_400(self):
        """Ciudad vacía retorna 400."""
        response = self._post({"ciudad": "", "categorias": [CategoriaOSM.MUSEO]})
        self.assertEqual(response.status_code, 400)

    def test_sin_categorias_validas_retorna_400(self):
        """Sin categorías válidas retorna 400."""
        response = self._post({"ciudad": "Sevilla", "categorias": [CategoriaOSM.OTRO]})
        self.assertEqual(response.status_code, 400)

    def test_json_invalido_retorna_400(self):
        """JSON inválido retorna 400."""
        response = self.client.post(
            reverse("allowlist:api_buscar_osm"),
            data="{bad",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("allowList.services.requests.post")
    def test_error_overpass_retorna_502(self, mock_post):
        """Error de red con Overpass retorna 502."""
        import requests as req_lib
        mock_post.side_effect = req_lib.Timeout("timeout")

        response = self._post({"ciudad": "Sevilla", "categorias": [CategoriaOSM.MUSEO]})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["status"], "ERROR")

    def test_solo_acepta_post(self):
        """El endpoint solo acepta POST."""
        response = self.client.get(reverse("allowlist:api_buscar_osm"))
        self.assertEqual(response.status_code, 405)


class ApiImportarOSMViewTest(TestCase):
    """Tests del endpoint POST /allowList/api/importar-osm/"""

    def setUp(self):
        self.client = Client()
        self.client.force_login(_superuser())

    def _post(self, payload):
        return self.client.post(
            reverse("allowlist:api_importar_osm"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_importa_elementos_correctamente(self):
        """Payload válido importa elementos y devuelve 200."""
        response = self._post({
            "ciudad": "Sevilla",
            "elementos": [
                {"osm_id": 9001, "osm_type": "node", "nombre": "Giralda",
                 "lat": 37.386, "lon": -5.992, "categoria": CategoriaOSM.MONUMENTO},
            ],
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["creados"], 1)

    def test_elementos_vacios_retorna_400(self):
        """Lista vacía de elementos retorna 400."""
        response = self._post({"ciudad": "Sevilla", "elementos": []})
        self.assertEqual(response.status_code, 400)

    def test_json_invalido_retorna_400(self):
        """JSON inválido retorna 400."""
        response = self.client.post(
            reverse("allowlist:api_importar_osm"),
            data="{bad",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_solo_acepta_post(self):
        """El endpoint solo acepta POST."""
        response = self.client.get(reverse("allowlist:api_importar_osm"))
        self.assertEqual(response.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# Tests de las vistas HTML
# ─────────────────────────────────────────────────────────────────────────────

class VistasPanelAllowlistTest(TestCase):
    """Tests de las vistas HTML del módulo AllowList."""

    def setUp(self):
        self.client = Client()
        self.client.force_login(_superuser())

    def test_panel_renderiza_correctamente(self):
        """El panel renderiza la plantilla correcta."""
        response = self.client.get(reverse("allowlist:panel"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "allowlist/panel.html")

    def test_panel_incluye_categorias_en_contexto(self):
        """El panel incluye las categorías en el contexto."""
        response = self.client.get(reverse("allowlist:panel"))
        self.assertIn("categorias", response.context)
        self.assertGreater(len(response.context["categorias"]), 0)

    def test_panel_incluye_estadisticas(self):
        """El panel incluye estadísticas de totales."""
        _crear_poi(fuente=POI.Fuente.OSM, osm_id=111)
        _crear_poi(fuente=POI.Fuente.MANUAL)

        response = self.client.get(reverse("allowlist:panel"))
        self.assertIn("total_osm", response.context)
        self.assertIn("total_manual", response.context)
        self.assertEqual(response.context["total_osm"], 1)
        self.assertEqual(response.context["total_manual"], 1)

    def test_buscar_osm_renderiza_correctamente(self):
        """La vista de búsqueda OSM renderiza su plantilla."""
        response = self.client.get(reverse("allowlist:buscar_osm"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "allowlist/buscar_osm.html")

    def test_crear_manual_renderiza_correctamente(self):
        """La vista de creación manual renderiza su plantilla."""
        response = self.client.get(reverse("allowlist:crear_manual"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "allowlist/crear_manual.html")

    def test_crear_manual_incluye_categorias(self):
        """La vista de creación manual incluye las categorías."""
        response = self.client.get(reverse("allowlist:crear_manual"))
        self.assertIn("categorias", response.context)

    def test_vistas_html_solo_aceptan_get(self):
        """Las vistas HTML solo aceptan GET."""
        for url_name in ["allowlist:panel", "allowlist:buscar_osm", "allowlist:crear_manual"]:
            response = self.client.post(reverse(url_name))
            self.assertEqual(response.status_code, 405, f"{url_name} debería rechazar POST")


# ─────────────────────────────────────────────────────────────────────────────
# Tests de utilidades internas (normalización, helpers)
# ─────────────────────────────────────────────────────────────────────────────

class NormalizacionNombreLugarTest(TestCase):
    """Tests de la función _normalizar_nombre_lugar."""

    def test_capitaliza_primera_letra(self):
        resultado = services._normalizar_nombre_lugar("sevilla")
        self.assertEqual(resultado[0], "S")

    def test_mantiene_particulas_en_minusculas(self):
        resultado = services._normalizar_nombre_lugar("santiago de compostela")
        self.assertIn("de", resultado)

    def test_normaliza_mayusculas(self):
        resultado = services._normalizar_nombre_lugar("CORDOBA")
        self.assertEqual(resultado, "Cordoba")

    def test_texto_con_espacios_extra(self):
        resultado = services._normalizar_nombre_lugar("  sevilla  ")
        self.assertEqual(resultado, "Sevilla")


class CategoriaNormalizacionTest(TestCase):
    """Tests de la normalización de categorías desde tags OSM."""

    def test_reconoce_museo(self):
        tags = {"tourism": "museum"}
        cat = services._normalizar_categoria_desde_tags(tags)
        self.assertEqual(cat, CategoriaOSM.MUSEO)

    def test_reconoce_restaurante(self):
        tags = {"amenity": "restaurant"}
        cat = services._normalizar_categoria_desde_tags(tags)
        self.assertEqual(cat, CategoriaOSM.RESTAURANTE)

    def test_tag_desconocido_devuelve_otro(self):
        tags = {"foo": "bar"}
        cat = services._normalizar_categoria_desde_tags(tags)
        self.assertEqual(cat, CategoriaOSM.OTRO)

    def test_tags_vacios_devuelve_otro(self):
        cat = services._normalizar_categoria_desde_tags({})
        self.assertEqual(cat, CategoriaOSM.OTRO)


class ExtraerCoordenadasElementoTest(TestCase):
    """Tests de la función _extraer_coordenadas_elemento."""

    def test_extrae_coordenadas_de_node(self):
        elemento = {"type": "node", "lat": 37.386, "lon": -5.992}
        resultado = services._extraer_coordenadas_elemento(elemento)
        self.assertEqual(resultado, (37.386, -5.992))

    def test_extrae_coordenadas_de_way_con_center(self):
        elemento = {"type": "way", "center": {"lat": 37.386, "lon": -5.992}}
        resultado = services._extraer_coordenadas_elemento(elemento)
        self.assertEqual(resultado, (37.386, -5.992))

    def test_devuelve_none_sin_coordenadas(self):
        elemento = {"type": "node"}
        resultado = services._extraer_coordenadas_elemento(elemento)
        self.assertIsNone(resultado)

    def test_devuelve_none_way_sin_center(self):
        elemento = {"type": "way"}
        resultado = services._extraer_coordenadas_elemento(elemento)
        self.assertIsNone(resultado)
