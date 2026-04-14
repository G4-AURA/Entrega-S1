# tests/e2e/conftest.py
"""
Configuración de pytest para los tests E2E de AURA.

Registra los fixtures de pytest-playwright y configura el entorno Django
para que el servidor en vivo sea accesible desde los navegadores headless.
"""
import django
import pytest
import os

# Apaga la protección asíncrona de Django exclusivamente para los tests
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"


# ─────────────────────────────────────────────────────────────────────────────
# Configuración global de pytest-playwright
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """
    Ajustes globales para todos los contextos de navegador:
      - ignore_https_errors: evita fallos por el certificado autofirmado
        del servidor de pruebas de Django.
      - locale: fuerza español para evitar variaciones en textos UI.
    """
    return {
        **browser_context_args,
        "ignore_https_errors": True,
        "locale": "es-ES",
    }


@pytest.fixture(scope="session")
def playwright_options():
    """Timeout por defecto para todas las operaciones de Playwright."""
    return {"timeout": 30_000}
