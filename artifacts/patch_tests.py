import os
import re

file_path = 'creacion/tests/test_services.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# I will patch test_genera_candidatos_exactos_y_regenera_hasta_completar_cantidad, test_falla_si_no_puede_completar_cantidad_objetivo, test_descarta_duplicados_y_respeta_dedupe_en_regeneracion, test_fallback_relajado_devuelve_sugerencias_si_falla_validacion_externa
# Since they use `patch('creacion.services.llamar_gemini_bypass', ...)` I can also add `@patch('allowList.services.resolver_poi')` to the class `GenerarCandidatosParadasIATests`.

class_find = r'class GenerarCandidatosParadasIATests\(TestCase\):'
class_replace = r'''class FalsaPOI:
    def __init__(self, lat=0, lon=0, nombre="", categoria=""):
        self.lat = lat
        self.lon = lon
        self.nombre = nombre
        self.categoria = categoria
        
from unittest.mock import patch, MagicMock

@patch('allowList.services.resolver_poi', return_value=FalsaPOI(lat=37.3891, lon=-5.9845, nombre="Mocked POI", categoria="general"))
class GenerarCandidatosParadasIATests(TestCase):'''

content = re.sub(class_find, class_replace, content)

# Update methods:
# Since @patch adds an argument, we need to add `mock_resolver_poi` to each test method.
content = re.sub(
    r'def test_(\w+)\(self\):',
    r'def test_\1(self, mock_resolver_poi):',
    content
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("tests patched!")
