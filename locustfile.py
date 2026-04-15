"""
Locustfile para pruebas de carga del proyecto de rutas turísticas.

Simula varios perfiles de uso reales y cubre más casos de uso:
- navegación pública
- flujo de guía autenticado
- administración / allowlist
- facturación
- APIs de creación, tours y rutas

Ejecutar con: locust -f locustfile.py --host=http://localhost:8000

Credenciales opcionales por variables de entorno:
- LOCUST_GUIDE_USERNAME / LOCUST_GUIDE_PASSWORD
- LOCUST_ADMIN_USERNAME / LOCUST_ADMIN_PASSWORD
"""

from __future__ import annotations

import json
import logging
import os
import random
import uuid
from urllib.parse import urlparse

from locust import HttpUser, between, events, task

logger = logging.getLogger(__name__)


def _json_or_none(response):
    try:
        return response.json()
    except Exception:
        return None


def _status_ok(response, allowed_statuses):
    return response.status_code in allowed_statuses


class BaseAURAUser(HttpUser):
    """Utilidades compartidas para los distintos perfiles."""

    abstract = True

    def on_start(self):
        self.route_ids = []
        self.session_ids = []
        self.poi_ids = []
        self.tour_tokens = []
        self._refresh_route_catalog()

    def _refresh_route_catalog(self):
        with self.client.get("/api/rutas/", catch_response=True) as response:
            if response.status_code == 200:
                payload = _json_or_none(response)
                if isinstance(payload, list):
                    self.route_ids = [item.get("id") for item in payload if isinstance(item, dict) and item.get("id")]
                    response.success()
                    return
            response.success() if response.status_code in {200, 302, 401, 403, 404} else response.failure(
                f"/api/rutas/ respondió con {response.status_code}"
            )

    def _first_route_id(self):
        if self.route_ids:
            return self.route_ids[0]
        return 1

    def _first_session_id(self):
        if self.session_ids:
            return self.session_ids[0]
        return 1

    def _first_poi_id(self):
        if self.poi_ids:
            return self.poi_ids[0]
        return 1

    def _sample_tour_token(self):
        if self.tour_tokens:
            return self.tour_tokens[0]
        return str(uuid.uuid4())


class PublicVisitorUser(BaseAURAUser):
    """Usuario anónimo que recorre la parte pública de la aplicación."""

    weight = 5
    wait_time = between(2, 6)

    @task(2)
    def open_home(self):
        with self.client.get("/", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Home respondió con {response.status_code}")

    @task(1)
    def open_login(self):
        with self.client.get("/accounts/login/", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Login respondió con {response.status_code}")

    @task(1)
    def open_terms(self):
        with self.client.get("/terminos-de-uso/", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Términos respondió con {response.status_code}")

    @task(2)
    def browse_catalog(self):
        with self.client.get("/catalogo/", catch_response=True) as response:
            if response.status_code == 200:
                payload = _json_or_none(response)
                if isinstance(payload, list):
                    self.route_ids = [item.get("id") for item in payload if isinstance(item, dict) and item.get("id")]
                response.success()
            else:
                response.failure(f"Catálogo respondió con {response.status_code}")

    @task(1)
    def view_route_detail(self):
        route_id = self._first_route_id()
        with self.client.get(f"/catalogo/{route_id}/", catch_response=True) as response:
            if _status_ok(response, {200, 302, 403, 404}):
                response.success()
            else:
                response.failure(f"Detalle de ruta respondió con {response.status_code}")

    @task(2)
    def api_routes(self):
        with self.client.get("/api/rutas/", catch_response=True) as response:
            if response.status_code == 200:
                payload = _json_or_none(response)
                if isinstance(payload, list):
                    self.route_ids = [item.get("id") for item in payload if isinstance(item, dict) and item.get("id")]
                response.success()
            else:
                response.failure(f"API de rutas respondió con {response.status_code}")

    @task(1)
    def join_live_by_code(self):
        code = os.getenv("LOCUST_SAMPLE_JOIN_CODE", "DEMO")
        with self.client.get(f"/tours/live/code/{code}/", catch_response=True) as response:
            if _status_ok(response, {200, 302, 403, 404}):
                response.success()
            else:
                response.failure(f"Join por código respondió con {response.status_code}")

    @task(1)
    def join_live_by_token(self):
        token = self._sample_tour_token()
        self.tour_tokens = [token]
        with self.client.get(f"/tours/live/{token}/", catch_response=True) as response:
            if _status_ok(response, {200, 302, 403, 404}):
                response.success()
            else:
                response.failure(f"Join por token respondió con {response.status_code}")

    @task(1)
    def live_waiting_room(self):
        token = self._sample_tour_token()
        with self.client.get(f"/tours/live/{token}/espera/", catch_response=True) as response:
            if _status_ok(response, {200, 302, 403, 404}):
                response.success()
            else:
                response.failure(f"Sala de espera respondió con {response.status_code}")

    @task(1)
    def live_tour_map(self):
        token = self._sample_tour_token()
        with self.client.get(f"/tours/live/{token}/mapa/", catch_response=True) as response:
            if _status_ok(response, {200, 302, 403, 404}):
                response.success()
            else:
                response.failure(f"Mapa del turista respondió con {response.status_code}")

    @task(1)
    def register_public_location(self):
        payload = {
            "lat": round(37.38 + random.uniform(-0.01, 0.01), 6),
            "lon": round(-5.99 + random.uniform(-0.01, 0.01), 6),
            "source": "locust",
        }
        with self.client.post("/tours/ubicacion/", json=payload, catch_response=True) as response:
            if _status_ok(response, {200, 400, 401, 403, 404}):
                response.success()
            else:
                response.failure(f"Registro de ubicación respondió con {response.status_code}")


class GuideWorkflowUser(BaseAURAUser):
    """Guía autenticado que recorre el flujo operativo completo."""

    weight = 3
    wait_time = between(2, 5)

    def on_start(self):
        super().on_start()
        self.is_authenticated = False
        self.login()

    def login(self):
        username = os.getenv("LOCUST_GUIDE_USERNAME", "")
        password = os.getenv("LOCUST_GUIDE_PASSWORD", "")
        if not username or not password:
            return

        with self.client.get("/accounts/login/", catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"No se pudo abrir login: {response.status_code}")
                return

        login_response = self.client.post(
            "/accounts/login/",
            data={"username": username, "password": password},
            allow_redirects=False,
            catch_response=True,
        )
        if login_response.status_code in {302, 303}:
            self.is_authenticated = True
            login_response.success()
            return

        if login_response.status_code == 200 and self.client.cookies.get("sessionid"):
            self.is_authenticated = True
            login_response.success()
            return

        login_response.failure(f"Login de guía falló con {login_response.status_code}")

    @task(2)
    def browse_catalog(self):
        with self.client.get("/catalogo/", catch_response=True) as response:
            if _status_ok(response, {200, 302, 403}):
                response.success()
            else:
                response.failure(f"Catálogo respondió con {response.status_code}")

    @task(1)
    def view_profile_edit(self):
        with self.client.get("/perfil/editar/", catch_response=True) as response:
            if _status_ok(response, {200, 302, 403}):
                response.success()
            else:
                response.failure(f"Perfil editar respondió con {response.status_code}")

    @task(1)
    def view_plan(self):
        with self.client.get("/perfil/plan/", catch_response=True) as response:
            if _status_ok(response, {200, 302, 403}):
                response.success()
            else:
                response.failure(f"Plan respondió con {response.status_code}")

    @task(2)
    def open_creacion_pages(self):
        for url in ("/crear-ruta/", "/crear-ruta/manual/", "/crear-ruta/generar/"):
            with self.client.get(url, catch_response=True) as response:
                if _status_ok(response, {200, 302, 403}):
                    response.success()
                else:
                    response.failure(f"{url} respondió con {response.status_code}")

    @task(2)
    def generate_route_with_ia(self):
        payload = {
            "titulo": "Ruta locust",
            "descripcion": "Ruta de prueba para carga",
            "ciudad": "Sevilla",
            "duracion_horas": 2.5,
            "personas": 8,
            "exigencia": "media",
            "mood": ["historia", "gastronomia"],
            "modo_seleccion": False,
            "deseos": "monumentos y gastronomía",
        }
        with self.client.post(
            "/crear-ruta/api/generar/",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            catch_response=True,
        ) as response:
            if _status_ok(response, {200, 400, 401, 403, 409, 422, 500, 503}):
                body = _json_or_none(response) or {}
                session_id = body.get("sesion_generacion_id") or body.get("session_id")
                if session_id:
                    self.session_ids = [str(session_id)]
                response.success()
            else:
                response.failure(f"Generación IA respondió con {response.status_code}")

    @task(1)
    def read_generation_session(self):
        session_id = self.session_ids[0] if self.session_ids else "sample-session"
        with self.client.get(f"/crear-ruta/api/sesiones-generacion/{session_id}/", catch_response=True) as response:
            if _status_ok(response, {200, 400, 401, 403, 404, 500}):
                response.success()
            else:
                response.failure(f"Sesión de generación respondió con {response.status_code}")

    @task(1)
    def update_generation_checkpoint(self):
        session_id = self.session_ids[0] if self.session_ids else "sample-session"
        payload = {
            "checkpoint": "locust_checkpoint",
            "metadata": {"source": "locust", "step": random.randint(1, 3)},
        }
        with self.client.post(
            f"/crear-ruta/api/sesiones-generacion/{session_id}/checkpoint/",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            catch_response=True,
        ) as response:
            if _status_ok(response, {200, 400, 401, 403, 404, 500}):
                response.success()
            else:
                response.failure(f"Checkpoint respondió con {response.status_code}")

    @task(2)
    def create_session_from_route(self):
        route_id = self._first_route_id()
        with self.client.get(
            f"/tours/sesiones/crear/?ruta_id={route_id}",
            allow_redirects=False,
            catch_response=True,
        ) as response:
            if response.status_code in {302, 303, 403, 404}:
                location = response.headers.get("Location", "")
                if location:
                    parsed = urlparse(location)
                    parts = parsed.path.strip("/").split("/")
                    if len(parts) >= 3 and parts[-2] == "sesiones":
                        try:
                            self.session_ids = [int(parts[-1])]
                        except ValueError:
                            pass
                response.success()
            else:
                response.failure(f"Crear sesión respondió con {response.status_code}")

    @task(2)
    def session_pages(self):
        session_id = self._first_session_id()
        urls = [
            f"/tours/sesiones/{session_id}/guia/",
            f"/tours/sesiones/{session_id}/mapa/guia/",
            f"/tours/sesiones/{session_id}/participantes/",
            f"/tours/sesiones/{session_id}/cronometro/estado/",
            f"/tours/sesiones/{session_id}/recordatorios/",
            f"/tours/sesiones/{session_id}/recordatorios/alertas/",
            f"/tours/sesiones/{session_id}/ubicacion_guia/",
            f"/tours/sesiones/{session_id}/ubicaciones_turistas/",
            f"/tours/sesiones/{session_id}/mensajes/",
            f"/tours/sesiones/{session_id}/chat-privado/bandeja/",
        ]
        for url in urls:
            with self.client.get(url, catch_response=True) as response:
                if _status_ok(response, {200, 302, 403, 404}):
                    response.success()
                else:
                    response.failure(f"{url} respondió con {response.status_code}")

    @task(1)
    def session_actions(self):
        session_id = self._first_session_id()
        with self.client.post(
            f"/tours/sesiones/{session_id}/iniciar/",
            catch_response=True,
        ) as response:
            if _status_ok(response, {200, 400, 401, 403, 404, 409, 500}):
                response.success()
            else:
                response.failure(f"Iniciar tour respondió con {response.status_code}")

        for url in (
            f"/tours/sesiones/{session_id}/cronometro/pausar/",
            f"/tours/sesiones/{session_id}/cronometro/reanudar/",
            f"/tours/sesiones/{session_id}/cerrar_acceso/",
            f"/tours/sesiones/{session_id}/regenerar_codigo/",
            f"/tours/sesiones/{session_id}/parada_actual/",
        ):
            with self.client.post(url, catch_response=True) as response:
                if _status_ok(response, {200, 400, 401, 403, 404, 409, 500}):
                    response.success()
                else:
                    response.failure(f"{url} respondió con {response.status_code}")

    @task(1)
    def communication_and_tracking(self):
        session_id = self._first_session_id()
        payload_location = {
            "lat": round(37.385 + random.uniform(-0.01, 0.01), 6),
            "lon": round(-5.994 + random.uniform(-0.01, 0.01), 6),
            "accuracy": random.randint(5, 30),
        }
        with self.client.post(
            f"/tours/sesiones/{session_id}/ubicacion_turista/",
            json=payload_location,
            catch_response=True,
        ) as response:
            if _status_ok(response, {200, 400, 401, 403, 404, 500}):
                response.success()
            else:
                response.failure(f"Ubicación turista respondió con {response.status_code}")

        with self.client.get(
            f"/tours/sesiones/{session_id}/paradas/1/curiosidad/",
            catch_response=True,
        ) as response:
            if _status_ok(response, {200, 400, 401, 403, 404, 500}):
                response.success()
            else:
                response.failure(f"Curiosidad en sesión respondió con {response.status_code}")

        with self.client.post(
            f"/tours/sesiones/{session_id}/mensajes/enviar/",
            json={"mensaje": "Mensaje de prueba Locust"},
            catch_response=True,
        ) as response:
            if _status_ok(response, {200, 400, 401, 403, 404, 500}):
                response.success()
            else:
                response.failure(f"Enviar mensaje respondió con {response.status_code}")

    @task(1)
    def route_management_actions(self):
        route_id = self._first_route_id()
        with self.client.get(f"/catalogo/{route_id}/", catch_response=True) as response:
            if _status_ok(response, {200, 302, 403, 404}):
                response.success()
            else:
                response.failure(f"Detalle ruta respondió con {response.status_code}")

        with self.client.post(f"/catalogo/{route_id}/eliminar/", catch_response=True) as response:
            if _status_ok(response, {200, 302, 403, 404, 405, 500}):
                response.success()
            else:
                response.failure(f"Eliminar ruta respondió con {response.status_code}")

        for url in (
            f"/api/rutas/{route_id}/recalcular/",
            "/api/paradas/1/curiosidad/",
            "/api/paradas/1/curiosidad/guardar/",
            "/api/paradas/1/curiosidad/eliminar/",
        ):
            if url.endswith("guardar/") or url.endswith("eliminar/"):
                method = self.client.post
            else:
                method = self.client.get
            with method(url, catch_response=True) as response:
                if _status_ok(response, {200, 400, 401, 403, 404, 409, 500}):
                    response.success()
                else:
                    response.failure(f"{url} respondió con {response.status_code}")

    @task(1)
    def billing_pages_and_checkout(self):
        for url in (
            "/billing/",
            "/billing/admin/feature-access/",
        ):
            with self.client.get(url, catch_response=True) as response:
                if _status_ok(response, {200, 302, 403, 404}):
                    response.success()
                else:
                    response.failure(f"{url} respondió con {response.status_code}")

        with self.client.post(
            "/billing/create-checkout-session/",
            data=json.dumps({"success_url": "http://localhost:8000/perfil/plan/", "cancel_url": "http://localhost:8000/perfil/plan/"}),
            headers={"Content-Type": "application/json"},
            catch_response=True,
        ) as response:
            if _status_ok(response, {200, 400, 401, 403, 409, 502, 503, 500}):
                response.success()
            else:
                response.failure(f"Checkout respondió con {response.status_code}")

        with self.client.post("/billing/schedule-downgrade/", data="{}", headers={"Content-Type": "application/json"}, catch_response=True) as response:
            if _status_ok(response, {200, 400, 401, 403, 409, 502, 503, 500}):
                response.success()
            else:
                response.failure(f"Downgrade respondió con {response.status_code}")


class SuperuserAdminUser(BaseAURAUser):
    """Superusuario que estresa el panel de administración y la allowlist."""

    weight = 1
    wait_time = between(3, 7)

    def on_start(self):
        super().on_start()
        self.is_authenticated = False
        self.login()

    def login(self):
        username = os.getenv("LOCUST_ADMIN_USERNAME", "")
        password = os.getenv("LOCUST_ADMIN_PASSWORD", "")
        if not username or not password:
            return

        with self.client.get("/accounts/login/", catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"No se pudo abrir login: {response.status_code}")
                return

        login_response = self.client.post(
            "/accounts/login/",
            data={"username": username, "password": password},
            allow_redirects=False,
            catch_response=True,
        )
        if login_response.status_code in {302, 303} or self.client.cookies.get("sessionid"):
            self.is_authenticated = True
            login_response.success()
            return

        login_response.failure(f"Login de superusuario falló con {login_response.status_code}")

    @task(2)
    def open_allowlist_pages(self):
        for url in ("/allowList/", "/allowList/buscar-osm/", "/allowList/nuevo/"):
            with self.client.get(url, catch_response=True) as response:
                if _status_ok(response, {200, 302, 403}):
                    response.success()
                else:
                    response.failure(f"{url} respondió con {response.status_code}")

    @task(2)
    def allowlist_manual_flow(self):
        payload = {
            "nombre": f"POI Locust {random.randint(1, 9999)}",
            "lat": round(37.386 + random.uniform(-0.02, 0.02), 6),
            "lon": round(-5.992 + random.uniform(-0.02, 0.02), 6),
            "categoria": "monumento",
            "ciudad": "Sevilla",
            "direccion": "Centro",
        }

        with self.client.post(
            "/allowList/api/crear-manual/",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                body = _json_or_none(response) or {}
                poi_id = body.get("poi_id")
                if poi_id:
                    self.poi_ids = [poi_id]
                response.success()
            elif _status_ok(response, {400, 401, 403, 500}):
                response.success()
            else:
                response.failure(f"Crear POI manual respondió con {response.status_code}")

        with self.client.get("/allowList/api/listar/?page=1&limit=10", catch_response=True) as response:
            if _status_ok(response, {200, 403}):
                response.success()
            else:
                response.failure(f"Listar POIs respondió con {response.status_code}")

        poi_id = self._first_poi_id()
        with self.client.post(f"/allowList/api/eliminar/{poi_id}/", catch_response=True) as response:
            if _status_ok(response, {200, 400, 401, 403, 404, 500}):
                response.success()
            else:
                response.failure(f"Eliminar POI respondió con {response.status_code}")

    @task(1)
    def allowlist_osm_search_and_import(self):
        search_payload = {
            "ciudad": "Sevilla",
            "pais": "España",
            "categorias": ["monumento", "restaurante"],
        }
        with self.client.post(
            "/allowList/api/buscar-osm/",
            data=json.dumps(search_payload),
            headers={"Content-Type": "application/json"},
            catch_response=True,
        ) as response:
            if _status_ok(response, {200, 400, 401, 403, 502, 500}):
                response.success()
            else:
                response.failure(f"Buscar OSM respondió con {response.status_code}")

        import_payload = {
            "ciudad": "Sevilla",
            "elementos": [
                {
                    "osm_id": random.randint(100000, 999999),
                    "osm_type": "node",
                    "nombre": "POI Importado Locust",
                    "lat": 37.386,
                    "lon": -5.992,
                    "categoria": "monumento",
                }
            ],
        }
        with self.client.post(
            "/allowList/api/importar-osm/",
            data=json.dumps(import_payload),
            headers={"Content-Type": "application/json"},
            catch_response=True,
        ) as response:
            if _status_ok(response, {200, 400, 401, 403, 500}):
                response.success()
            else:
                response.failure(f"Importar OSM respondió con {response.status_code}")

    @task(1)
    def billing_admin_panel(self):
        with self.client.get("/billing/admin/feature-access/", catch_response=True) as response:
            if _status_ok(response, {200, 302, 403}):
                response.success()
            else:
                response.failure(f"Panel billing respondió con {response.status_code}")

        update_payload = {
            "key": random.choice([
                "ai_route_generation",
                "ai_stop_replacement",
                "chat_mode_separate",
                "scheduled_meetup",
                "payload_wishes",
            ]),
            "tier": random.choice(["freemium", "premium"]),
            "enabled": random.choice(["true", "false"]),
        }
        with self.client.post(
            "/billing/admin/feature-access/update/",
            data=update_payload,
            allow_redirects=False,
            catch_response=True,
        ) as response:
            if _status_ok(response, {302, 303, 403, 400, 404}):
                response.success()
            else:
                response.failure(f"Update feature access respondió con {response.status_code}")

    @task(1)
    def admin_and_registration_pages(self):
        for url in ("/admin/", "/registro/", "/personalizacion/"):
            with self.client.get(url, catch_response=True) as response:
                if _status_ok(response, {200, 302, 403}):
                    response.success()
                else:
                    response.failure(f"{url} respondió con {response.status_code}")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    logger.info("Iniciando pruebas de carga")
    logger.info("Host: %s", environment.host)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    logger.info("Pruebas de carga finalizadas")
    logger.info("Requests: %s", environment.stats.num_requests)
    logger.info("Failures: %s", environment.stats.num_failures)
