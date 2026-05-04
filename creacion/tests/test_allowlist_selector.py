from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.test import TestCase

from allowList.models import CategoriaOSM, CityBoundary, POI
from creacion.allowlist_selector import seleccionar_pois_allowlist


class AllowlistSelectorTest(TestCase):
    def _create_poi(
        self,
        *,
        nombre: str,
        lat: float,
        lon: float,
        ciudad: str,
        categoria: str = CategoriaOSM.MONUMENTO,
        rank: int | None = None,
    ) -> POI:
        return POI.objects.create(
            nombre=nombre,
            categoria=categoria,
            ciudad=ciudad,
            coordenadas=Point(lon, lat, srid=4326),
            fuente=POI.Fuente.GOOGLE,
            google_rank_position=rank,
        )

    def test_prioriza_google_rank_position_con_seed(self):
        self._create_poi(nombre='Rank 1', lat=37.389, lon=-5.984, ciudad='Sevilla', rank=1)
        self._create_poi(nombre='Rank 2', lat=37.388, lon=-5.986, ciudad='Sevilla', rank=2)
        self._create_poi(nombre='Rank 10', lat=37.387, lon=-5.988, ciudad='Sevilla', rank=10)

        seleccion = seleccionar_pois_allowlist(
            ciudad='Sevilla',
            moods=['historia'],
            limite=2,
            seed=42,
        )
        nombres = [item['nombre'] for item in seleccion]
        self.assertIn('Rank 1', nombres)

    def test_filtra_por_city_boundary_cuando_existe(self):
        # Polígono simplificado centrado en Sevilla capital.
        poly = Polygon(
            (
                (-6.10, 37.31),
                (-5.86, 37.31),
                (-5.86, 37.47),
                (-6.10, 37.47),
                (-6.10, 37.31),
            ),
            srid=4326,
        )
        CityBoundary.objects.create(
            city_name='Sevilla',
            polygon=MultiPolygon(poly, srid=4326),
            active=True,
        )

        self._create_poi(nombre='Dentro', lat=37.389, lon=-5.984, ciudad='Sevilla', rank=3)
        self._create_poi(nombre='Fuera', lat=37.60, lon=-6.20, ciudad='Sevilla', rank=1)

        seleccion = seleccionar_pois_allowlist(
            ciudad='Sevilla',
            moods=['historia'],
            limite=10,
            seed=1,
        )
        nombres = {item['nombre'] for item in seleccion}
        self.assertIn('Dentro', nombres)
        self.assertNotIn('Fuera', nombres)

    def test_aleatoriedad_controlada_se_repite_con_misma_seed(self):
        for idx in range(1, 8):
            self._create_poi(
                nombre=f'POI {idx}',
                lat=37.38 + idx * 0.001,
                lon=-5.99 + idx * 0.001,
                ciudad='Sevilla',
                rank=idx,
            )

        seleccion_a = seleccionar_pois_allowlist(
            ciudad='Sevilla',
            moods=['historia'],
            limite=4,
            seed=777,
        )
        seleccion_b = seleccionar_pois_allowlist(
            ciudad='Sevilla',
            moods=['historia'],
            limite=4,
            seed=777,
        )
        self.assertEqual(seleccion_a, seleccion_b)
