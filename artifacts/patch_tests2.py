import os
import re

file_path = 'creacion/tests/test_services.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Only add @patch on specific methods inside GenerarCandidatosParadasIATests
tests_to_patch = [
    'test_genera_candidatos_exactos_y_regenera_hasta_completar_cantidad',
    'test_falla_si_no_puede_completar_cantidad_objetivo',
    'test_descarta_duplicados_y_respeta_dedupe_en_regeneracion',
    'test_fallback_relajado_devuelve_sugerencias_si_falla_validacion_externa'
]

for test in tests_to_patch:
    # find definition
    find_str = f"def {test}(self):"
    
    # replace definition with mock injected
    replacement = f"""@patch('allowList.services.resolver_poi')
    def {test}(self, mock_resolver_poi):
        class FalsaPOI:
            def __init__(self, lat=0, lon=0, nombre="", categoria="general"):
                self.lat = lat
                self.lon = lon
                self.nombre = nombre
                self.categoria = categoria
        mock_resolver_poi.side_effect = lambda n,c,t: FalsaPOI(lat=37.3891, lon=-5.9845, nombre=n, categoria=t)
"""
    content = content.replace("    def " + test + "(self):", replacement)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("tests patched safely!")
