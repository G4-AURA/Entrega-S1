"""
tests/e2e/test_tour_chat_e2e.py
================================
Prueba E2E end-to-end que valida el flujo completo de:
  1. Autenticación del Guía.
  2. Creación de una Sesión de Tour.
  3. Unión anónima de un Turista mediante código de acceso.
  4. Chat grupal bidireccional (Guía → Turista y Turista → Guía).

Herramientas: pytest + pytest-playwright + Django live_server.

Ejecución:
    pytest tests/e2e/test_tour_chat_e2e.py -v --headed
    pytest tests/e2e/test_tour_chat_e2e.py -v               # headless (CI)

Dependencias adicionales:
    pip install pytest-playwright pytest-django
    playwright install chromium
"""

from __future__ import annotations

import re
import time

import pytest
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from playwright.sync_api import Browser, BrowserContext, Page, expect


# ─────────────────────────────────────────────────────────────────────────────
# SELECTORES CSS / LOCATORS
# Centraliza aquí todos los selectores para facilitar el mantenimiento.
# Sustitúyelos por los IDs reales de tu HTML si difieren.
# ─────────────────────────────────────────────────────────────────────────────

class Sel:
    """Diccionario de selectores de la aplicación AURA."""

    # ── Login ──────────────────────────────────────────────────────────────
    LOGIN_USERNAME  = "input[name='username']"
    LOGIN_PASSWORD  = "input[name='password']"
    LOGIN_SUBMIT    = "button[type='submit']"

    # ── Catálogo de rutas ──────────────────────────────────────────────────
    # Botón "Crear sesión" generado por JS en cada tarjeta de ruta.
    # Coincide con el primer enlace que contiene "/tours/sesiones/crear/".
    BTN_CREAR_SESION = "a[href*='/tours/sesiones/crear/']"

    # ── Panel del Guía (guia_sesion.html) ─────────────────────────────────
    # Código de acceso mostrado en <div id="sesion-code">
    SESION_CODE     = "#sesion-code"
    # Botón "Iniciar Tour"
    BTN_INICIAR     = "#iniciar-tour"
    # Estado de la sesión (label)
    SESION_ESTADO   = "#sesion-estado"

    # ── Join Tour (join_tour.html) ─────────────────────────────────────────
    # Input del alias del turista
    ALIAS_INPUT     = "input[name='alias']"
    # Botón "Unirse al Tour"
    BTN_JOIN        = "button[type='submit']"

    # ── Sala de espera (sala_espera.html) ─────────────────────────────────
    BTN_ENTRAR      = "#enter-btn"

    # ── Mapa / Chat grupal ─────────────────────────────────────────────────
    # Tab del chat grupal
    TAB_CHAT        = "[data-tab='chat']"
    # Input de texto del chat
    CHAT_INPUT      = "#chat-input"
    # Botón de envío
    CHAT_SEND       = "#chat-send"
    # Contenedor de mensajes (contiene todos los .chat-message)
    CHAT_MESSAGES   = "#chat-messages"
    # Selector individual de burbuja de mensaje
    CHAT_BUBBLE     = ".chat-message-bubble"


# ─────────────────────────────────────────────────────────────────────────────
# TIMEOUTS
# ─────────────────────────────────────────────────────────────────────────────

# El chat usa polling cada 5 s; damos margen amplio para CI con carga variable.
POLLING_TIMEOUT_MS   = 15_000   # 15 s para esperar un mensaje nuevo
NAVIGATION_TIMEOUT   = 20_000   # 20 s para cargas de página
PAGE_READY_TIMEOUT   = 10_000   # 10 s para que un elemento sea visible


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES DE BASE DE DATOS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def guia_credentials() -> dict:
    """Credenciales del guía de prueba."""
    return {"username": "guia_e2e", "password": "Aura_e2e_2024!"}


@pytest.fixture(scope="function")
def setup_db(db, guia_credentials: dict):
    """
    Crea en base de datos:
      - Un usuario Django (guía).
      - El perfil AuthUser + Guia correspondiente.
      - Una Ruta básica con dos Paradas mínimas.

    Devuelve un dict con los objetos creados para ser usados por el test.
    """
    from rutas.models import AuthUser, Guia, Parada, Ruta

    # ── Usuario Django ─────────────────────────────────────────────────────
    user = User.objects.create_user(
        username=guia_credentials["username"],
        password=guia_credentials["password"],
        email="guia_e2e@aura.test",
        first_name="Guía",
        last_name="E2E",
    )

    # ── Perfil AuthUser → Guia ─────────────────────────────────────────────
    auth_user = AuthUser.objects.create(user=user)
    guia = Guia.objects.create(
        user=auth_user,
        tipo_suscripcion=Guia.Suscripcion.FREEMIUM,
    )

    # ── Ruta con dos paradas mínimas (Sevilla centro) ─────────────────────
    ruta = Ruta.objects.create(
        titulo="Ruta E2E - Centro de Sevilla",
        descripcion="Ruta creada automáticamente para tests E2E.",
        duracion_horas=1.5,
        num_personas=10,
        nivel_exigencia=Ruta.Exigencia.BAJA,
        mood=[Ruta.Mood.HISTORIA],
        es_generada_ia=False,
        guia=guia,
    )

    Parada.objects.bulk_create([
        Parada(
            ruta=ruta,
            orden=1,
            nombre="Catedral de Sevilla",
            descripcion="La catedral gótica más grande del mundo.",
            coordenadas=Point(-5.9926, 37.3860, srid=4326),  # (lon, lat)
        ),
        Parada(
            ruta=ruta,
            orden=2,
            nombre="Torre del Oro",
            descripcion="Torre árabe a orillas del Guadalquivir.",
            coordenadas=Point(-5.9963, 37.3824, srid=4326),
        ),
    ])

    return {
        "user": user,
        "auth_user": auth_user,
        "guia": guia,
        "ruta": ruta,
    }


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DE NAVEGACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def login_as_guia(page: Page, base_url: str, username: str, password: str) -> None:
    """Realiza el login del guía en la aplicación."""
    page.goto(f"{base_url}/accounts/login/")

    page.fill(Sel.LOGIN_USERNAME, username)
    page.fill(Sel.LOGIN_PASSWORD, password)
    page.click(Sel.LOGIN_SUBMIT)
    # Esperar redirección al catálogo (indica login correcto)
    page.wait_for_url(re.compile(r"/(catalogo|$)"), timeout=NAVIGATION_TIMEOUT)


def crear_sesion_tour(page: Page, base_url: str, ruta_id: int) -> str:
    """
    Navega a crear sesión y devuelve el código de acceso extraído del DOM.

    Retorna:
        str: El código de acceso (ej. "ABC123").
    """
    # Navegar directamente a la URL de creación de sesión para la ruta dada.
    page.goto(
        f"{base_url}/tours/sesiones/crear/?ruta_id={ruta_id}",
        wait_until="networkidle",
    )

    # La vista crear_sesion redirige al panel del guía; esperamos que cargue el código.
    code_locator = page.locator(Sel.SESION_CODE)
    expect(code_locator).to_be_visible(timeout=NAVIGATION_TIMEOUT)

    codigo = code_locator.inner_text().strip()
    assert codigo, "No se obtuvo un código de acceso del panel del guía."
    return codigo


def iniciar_tour_como_guia(page: Page) -> None:
    """
    Pulsa 'Iniciar Tour' en el panel del guía si el botón está presente y
    confirma el diálogo de confirmación que lanza AuraFeedback.confirm().
    """
    btn_iniciar = page.locator(Sel.BTN_INICIAR)
    if btn_iniciar.is_visible(timeout=3_000):
        # El botón lanza un modal de confirmación asíncrono (AuraFeedback).
        # Lo aceptamos pulsando el botón de confirmación que renderiza en el DOM.
        btn_iniciar.click()
        # Esperamos que aparezca el botón "Confirmar" del modal de AuraFeedback.
        confirm_btn = page.locator("#aura-feedback-confirm")
        expect(confirm_btn).to_be_visible(timeout=PAGE_READY_TIMEOUT)
        confirm_btn.click()

        # Esperar que el estado cambie a "EN CURSO".
        expect(page.locator(Sel.SESION_ESTADO)).to_contain_text(
            "EN CURSO", timeout=PAGE_READY_TIMEOUT
        )


def unirse_como_turista(
    page: Page,
    base_url: str,
    codigo: str,
    alias: str = "Turista E2E",
) -> None:
    """
    Flujo completo de unión anónima del turista:
      1. Accede a la URL pública del código de acceso.
      2. Introduce su alias.
      3. Espera en la sala de espera hasta que el tour esté "en curso".
    """
    # Paso 3a: Navegar a la URL de unión por código
    page.goto(
        f"{base_url}/tours/live/code/{codigo}/",
        wait_until="networkidle",
    )

    # Paso 3b: Rellenar el formulario de alias (join_tour.html)
    alias_input = page.locator(Sel.ALIAS_INPUT)
    expect(alias_input).to_be_visible(timeout=PAGE_READY_TIMEOUT)
    alias_input.fill(alias)
    page.click(Sel.BTN_JOIN)

    # Paso 3c: Sala de espera — esperar que el botón "Entrar" esté habilitado.
    # La sala hace polling cada 3 s al endpoint /sesiones/<id>/cronometro/estado/.
    btn_entrar = page.locator(Sel.BTN_ENTRAR)
    expect(btn_entrar).to_be_visible(timeout=NAVIGATION_TIMEOUT)

    # El botón pasa a ser activo cuando el estado es "en_curso".
    # Reintentamos hasta que no tenga el atributo aria-disabled.
    expect(btn_entrar).not_to_have_attribute(
        "aria-disabled", "true", timeout=POLLING_TIMEOUT_MS
    )
    btn_entrar.click()

    # Esperar que el mapa cargue completamente.
    page.wait_for_url(re.compile(r"/tours/live/.+/mapa/"), timeout=NAVIGATION_TIMEOUT)


def abrir_tab_chat(page: Page) -> None:
    """Hace clic en la pestaña de chat grupal del panel inferior del mapa."""
    tab = page.locator(Sel.TAB_CHAT)
    expect(tab).to_be_visible(timeout=PAGE_READY_TIMEOUT)
    tab.click()
    # Verificar que el input del chat está habilitado (sesión en curso).
    expect(page.locator(Sel.CHAT_INPUT)).to_be_enabled(timeout=PAGE_READY_TIMEOUT)


def enviar_mensaje_chat(page: Page, texto: str) -> None:
    """Escribe y envía un mensaje en el chat grupal."""
    chat_input = page.locator(Sel.CHAT_INPUT)
    expect(chat_input).to_be_enabled(timeout=PAGE_READY_TIMEOUT)
    chat_input.fill(texto)
    page.click(Sel.CHAT_SEND)
    # Esperar que el input quede vacío (confirmación de envío).
    expect(chat_input).to_have_value("", timeout=PAGE_READY_TIMEOUT)


def esperar_mensaje_en_chat(page: Page, texto_esperado: str) -> None:
    """
    Espera con reintentos a que aparezca un mensaje concreto en el contenedor
    de chat. Usa el timeout holgado para absorber un ciclo de polling (5 s).

    Args:
        page: La página del navegador que debe recibir el mensaje.
        texto_esperado: Subcadena del texto del mensaje a buscar.
    """
    # Buscamos cualquier burbuja de mensaje que contenga el texto exacto.
    mensaje_locator = page.locator(Sel.CHAT_MESSAGES).locator(
        Sel.CHAT_BUBBLE, has_text=texto_esperado
    )
    expect(mensaje_locator.first).to_be_visible(timeout=POLLING_TIMEOUT_MS)


# ─────────────────────────────────────────────────────────────────────────────
# TEST PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_tour_session_and_group_chat(
    live_server,
    browser: Browser,
    setup_db: dict,
    guia_credentials: dict,
) -> None:
    """
    Flujo E2E completo:
      1. [Guía]    Login → Crea sesión → Captura código → Inicia tour.
      2. [Turista] Se une con el código → Entra al mapa.
      3. [Guía]    Abre el mapa y el chat → Envía un mensaje.
      4. [Turista] Recibe el mensaje del guía (polling).
      5. [Turista] Responde con otro mensaje.
      6. [Guía]    Recibe la respuesta del turista (polling).
    """
    base_url: str = live_server.url
    ruta_id: int  = setup_db["ruta"].id

    # ── Mensajes de prueba ─────────────────────────────────────────────────
    MSG_GUIA    = "¡Bienvenidos al tour! Empezamos en la Catedral."
    MSG_TURISTA = "¡Perfecto! Ya estoy aquí, guía."

    # ─────────────────────────────────────────────────────────────────────
    # ARRANGE: Crear dos contextos de navegador totalmente independientes
    # ─────────────────────────────────────────────────────────────────────

    guia_context: BrowserContext    = browser.new_context(
        viewport={"width": 1280, "height": 800},
    )
    turista_context: BrowserContext = browser.new_context(
        viewport={"width": 390, "height": 844},   # simula móvil
    )

    guia_page:    Page = guia_context.new_page()
    turista_page: Page = turista_context.new_page()

    try:
        # ─────────────────────────────────────────────────────────────────
        # PASO 1 — Guía: Login
        # ─────────────────────────────────────────────────────────────────
        login_as_guia(
            guia_page,
            base_url,
            guia_credentials["username"],
            guia_credentials["password"],
        )

        # Verificar que estamos autenticados (URL en catálogo o raíz)
        assert re.search(r"/(catalogo|)$", guia_page.url), (
            f"El login no redirigió al catálogo. URL actual: {guia_page.url}"
        )

        # ─────────────────────────────────────────────────────────────────
        # PASO 2 — Guía: Crear sesión y capturar el código de acceso
        # ─────────────────────────────────────────────────────────────────
        codigo_acceso: str = crear_sesion_tour(guia_page, base_url, ruta_id)
        assert len(codigo_acceso) >= 4, (
            f"Código de acceso demasiado corto: '{codigo_acceso}'"
        )

        # ─────────────────────────────────────────────────────────────────
        # PASO 3 — Turista: Unirse a la sesión con el código de acceso
        # (en paralelo, mientras el guía inicia el tour)
        # ─────────────────────────────────────────────────────────────────

        # El turista intenta unirse ahora (sesión en estado "pendiente").
        # Entrará en la sala de espera.
        turista_page.goto(
            f"{base_url}/tours/live/code/{codigo_acceso}/",
            wait_until="networkidle",
        )
        alias_input = turista_page.locator(Sel.ALIAS_INPUT)
        expect(alias_input).to_be_visible(timeout=PAGE_READY_TIMEOUT)
        alias_input.fill("Turista E2E")
        turista_page.click(Sel.BTN_JOIN)

        # El turista queda en la sala de espera; continuamos con el guía.

        # ─────────────────────────────────────────────────────────────────
        # PASO 4 — Guía: Iniciar el tour (transición pendiente → en_curso)
        # ─────────────────────────────────────────────────────────────────
        iniciar_tour_como_guia(guia_page)

        # ─────────────────────────────────────────────────────────────────
        # PASO 5 — Turista: Detecta que el tour está en curso y entra al mapa
        # La sala de espera hace polling y habilita el botón "Entrar".
        # ─────────────────────────────────────────────────────────────────
        btn_entrar = turista_page.locator(Sel.BTN_ENTRAR)
        expect(btn_entrar).to_be_visible(timeout=NAVIGATION_TIMEOUT)
        expect(btn_entrar).not_to_have_attribute(
            "aria-disabled", "true", timeout=POLLING_TIMEOUT_MS
        )
        btn_entrar.click()
        turista_page.wait_for_url(
            re.compile(r"/tours/live/.+/mapa/"), timeout=NAVIGATION_TIMEOUT
        )

        # ─────────────────────────────────────────────────────────────────
        # PASO 6 — Guía: Navegar al mapa y abrir el chat
        # ─────────────────────────────────────────────────────────────────
        guia_page.goto(
            f"{base_url}/tours/sesiones/{_extraer_sesion_id(guia_page.url, base_url, ruta_id)}/mapa/guia/",
            wait_until="networkidle",
        )
        abrir_tab_chat(guia_page)

        # El turista también abre el chat
        abrir_tab_chat(turista_page)

        # ─────────────────────────────────────────────────────────────────
        # ACT + ASSERT — Guía envía mensaje → Turista lo recibe
        # ─────────────────────────────────────────────────────────────────
        enviar_mensaje_chat(guia_page, MSG_GUIA)
        esperar_mensaje_en_chat(turista_page, MSG_GUIA)

        # ─────────────────────────────────────────────────────────────────
        # ACT + ASSERT — Turista responde → Guía lo recibe
        # ─────────────────────────────────────────────────────────────────
        enviar_mensaje_chat(turista_page, MSG_TURISTA)
        esperar_mensaje_en_chat(guia_page, MSG_TURISTA)

    finally:
        # ─────────────────────────────────────────────────────────────────
        # TEARDOWN: Cerrar contextos siempre, incluso si el test falla
        # ─────────────────────────────────────────────────────────────────
        guia_context.close()
        turista_context.close()


# ─────────────────────────────────────────────────────────────────────────────
# HELPER PRIVADO
# ─────────────────────────────────────────────────────────────────────────────

def _extraer_sesion_id(current_url: str, base_url: str, ruta_id: int) -> int:
    """
    Extrae el ID de la sesión desde la URL actual del guía.

    La URL del panel del guía sigue el patrón:
        /tours/sesiones/<sesion_id>/guia/

    Si la URL no contiene el patrón (p.ej. se quedó en /catalogo/) busca
    la sesión activa para la ruta en la base de datos como fallback.
    """
    from tours.models import SesionTour

    match = re.search(r"/tours/sesiones/(\d+)/", current_url)
    if match:
        return int(match.group(1))

    # Fallback: buscar la sesión activa más reciente para esta ruta
    sesion = (
        SesionTour.objects.filter(ruta_id=ruta_id)
        .order_by("-id")
        .first()
    )
    if sesion:
        return sesion.id
    raise RuntimeError(
        f"No se pudo determinar el ID de sesión. URL actual: {current_url}"
    )
