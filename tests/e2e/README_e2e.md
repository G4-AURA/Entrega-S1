# Tests E2E — AURA Tour Chat

## Estructura

```
tests/
└── e2e/
    ├── conftest.py                # Configuración de Playwright y fixtures de sesión
    └── test_tour_chat_e2e.py     # Test principal del flujo tour + chat grupal
pytest.ini                        # Configuración global de pytest
```

## Instalación de dependencias

```bash
# Dependencias Python
pip install pytest pytest-django pytest-playwright

# Navegadores Playwright (solo la primera vez)
playwright install chromium
```

## Variables de entorno necesarias

El test usa `live_server` de pytest-django, que levanta un servidor Django
real en un puerto aleatorio. Asegúrate de que tu `settings` de test
apunte a la base de datos correcta y tenga `ALLOWED_HOSTS = ['*']`
o al menos `['localhost', '127.0.0.1']`.

```python
# config/settings_test.py  (o añadir a tu settings.py)
ALLOWED_HOSTS = ['*']
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'aura_test',
        # ...
    }
}
```

### Nota sobre Operaciones Asíncronas (Django)
Playwright utiliza un bucle de eventos asíncrono. Para evitar que Django lance el error `SynchronousOnlyOperation` al montar la base de datos de pruebas, el archivo `tests/e2e/conftest.py` inyecta automáticamente la siguiente variable de entorno:
`os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"`


## Ejecución

```bash
# Modo headless (para CI/CD)
pytest tests/e2e/test_tour_chat_e2e.py -v

# Modo visible (para depuración local)
pytest tests/e2e/test_tour_chat_e2e.py -v --headed

# Con pausa en cada paso (ultra-detallado)
pytest tests/e2e/test_tour_chat_e2e.py -v --headed --slowmo=500

# Solo Firefox
pytest tests/e2e/test_tour_chat_e2e.py -v --browser firefox

# Con captura de vídeo en caso de fallo
pytest tests/e2e/test_tour_chat_e2e.py -v --video=on
```

## Flujo validado por el test

```
Guía (Chrome 1)                         Turista (Chrome 2)
───────────────                         ──────────────────
1. GET /accounts/login/
2. POST credenciales → catálogo
3. GET /tours/sesiones/crear/?ruta_id=X
   → Panel del guía                     
4. Extrae código de acceso              
5. Inicia tour (pendiente → en_curso)   3. GET /tours/join/<código>/
                                           POST alias → sala de espera
                                        4. Sala detecta "en_curso" (polling 3s)
                                        5. Entra al mapa (/tours/live/.../mapa/)
6. GET /tours/sesiones/<id>/mapa/guia/
7. Abre tab "chat"                      6. Abre tab "chat"
8. Envía MSG_GUIA ────────────────────→ 7. Recibe MSG_GUIA (polling 5s)
                    ←────────────────── 8. Envía MSG_TURISTA
9. Recibe MSG_TURISTA (polling 5s)
```

## Ajuste de selectores

Todos los selectores CSS están centralizados en la clase `Sel` al inicio
de `test_tour_chat_e2e.py`. Si el HTML de tu aplicación usa IDs o clases
distintos, solo tienes que editar esa clase:

```python
class Sel:
    LOGIN_USERNAME = "input[name='username']"   # ← cambia aquí si es necesario
    SESION_CODE    = "#sesion-code"
    # ...
```

## Timeouts

| Constante          | Valor  | Uso                                          |
|--------------------|--------|----------------------------------------------|
| `POLLING_TIMEOUT_MS` | 15 000 ms | Esperar mensaje nuevo en el chat (polling 5s) |
| `NAVIGATION_TIMEOUT` | 20 000 ms | Cargas de página completas                  |
| `PAGE_READY_TIMEOUT` | 10 000 ms | Elementos que deben aparecer rápidamente    |

Ajusta estos valores si tu entorno de CI es especialmente lento.
