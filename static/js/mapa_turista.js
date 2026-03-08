/* ============================================================
   AURA — Mapa Inmersivo del Turista  (mapa_turista.js)

   Funcionalidades:
     · Mapa Leaflet con tiles Mapbox satélite-calles
     · Marcador de propia ubicación (turista en azul / guía en rojo)
     · Marcadores de paradas (actual en verde, resto en gris)
     · Polilínea completa de la ruta del tour (púrpura, desde BD)
     · Polilínea de navegación turista→parada actual (cian, GraphHopper)
     · Banner de navegación con distancia y ETA en tiempo real
     · Detección de llegada (<40 m de la parada actual)
     · Polling del estado de la sesión (5 s) para detectar cambio de parada
     · Throttle de GraphHopper: solo recalcula si se movió >25 m o pasaron >30 s
     · Ubicación del guía en tiempo real (solo para turistas)
     · Chat con polling (5 s) y badge de mensajes nuevos
   ============================================================ */

'use strict';

// ── Variables globales de mapa ─────────────────────────────────────────────
let map               = null;
let guiaMarker        = null;
let miUbicacionMarker = null;

// Polilíneas
let rutaCompletaLine  = null;   // Ruta del tour completa (púrpura, desde BD)
let navLine           = null;   // Navegación turista→parada actual (cian)

// Marcadores de paradas
const paradaMarkers   = {};     // { parada_id: L.marker }

// ── Estado de navegación ───────────────────────────────────────────────────
let miPosActual       = null;   // [lat, lng] última posición conocida del turista
let paradaActualId    = null;   // ID de la parada actual en esta sesión
let llegadaNotificada = false;  // Para evitar repetir el toast de "¡Has llegado!"
let ultimoRecalculo   = 0;      // timestamp del último recálculo GraphHopper
let ultimaPosRecalculo= null;   // posición en el último recálculo

// Umbrales de throttle
const UMBRAL_DISTANCIA_M  = 25;   // metros mínimos de movimiento para recalcular
const UMBRAL_TIEMPO_MS    = 30000; // 30 s máximo entre recálculos
const RADIO_LLEGADA_M     = 40;   // metros para considerar que se ha llegado

// ── Inicialización ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {

    const mapElement = document.getElementById('mapa-tour');
    if (!mapElement) return;

    // Ocultar navbar para experiencia inmersiva
    const navbar = document.querySelector('.navbar');
    if (navbar) navbar.style.display = 'none';
    const mainContainer = document.querySelector('main.container');
    if (mainContainer) { mainContainer.style.maxWidth = '100%'; mainContainer.style.padding = '0'; }

    // ── Inicializar Leaflet ────────────────────────────────────────────────
    map = L.map('mapa-tour', { zoomControl: false }).setView([37.3891, -5.9845], 16);

    const token = typeof mapboxToken !== 'undefined' ? mapboxToken : '';
    const tileUrl = token
        ? `https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12/tiles/256/{z}/{x}/{y}@2x?access_token=${token}`
        : 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';

    L.tileLayer(tileUrl, {
        maxZoom: 19,
        attribution: token ? '© Mapbox © OpenStreetMap' : '© OpenStreetMap',
    }).addTo(map);

    // Control de zoom en esquina inferior derecha (lejos del panel)
    L.control.zoom({ position: 'bottomright' }).addTo(map);

    // ── Dibujar paradas iniciales y ruta completa ─────────────────────────
    _dibujarParadasIniciales();

    // ── Iniciar tracking de posición propia ───────────────────────────────
    iniciarRastreoLocal();

    // ── Polling: estado de sesión (detecta cambio de parada) ─────────────
    _pollEstadoSesion();
    setInterval(_pollEstadoSesion, 5000);

    // ── Polling: ubicación del guía (solo turistas) ───────────────────────
    if (!esGuia) {
        obtenerUbicacionGuia();
        setInterval(obtenerUbicacionGuia, 5000);
    }

    // ── Panel expandible ──────────────────────────────────────────────────
    const tourPanel   = document.querySelector('.tour-panel');
    const panelHeader = document.querySelector('.panel-header');
    if (tourPanel && panelHeader) {
        panelHeader.addEventListener('click', () => tourPanel.classList.toggle('expanded'));
    }

    // ── Tabs Itinerario / Chat ─────────────────────────────────────────────
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const targetTab = this.getAttribute('data-tab');
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            this.classList.add('active');
            document.getElementById('tab-' + targetTab)?.classList.add('active');

            if (targetTab === 'chat') {
                const badge = document.getElementById('chat-badge');
                if (badge) badge.style.display = 'none';
                document.dispatchEvent(new CustomEvent('chatOpened'));
            }
        });
    });

    // ── Chat ──────────────────────────────────────────────────────────────
    initChat();
});


// ╔══════════════════════════════════════════════════════════════════════════╗
// ║  PARADAS Y RUTA COMPLETA                                                ║
// ╚══════════════════════════════════════════════════════════════════════════╝

function _dibujarParadasIniciales() {
    if (typeof paradasData === 'undefined' || !Array.isArray(paradasData)) return;

    const bounds = [];

    paradasData.forEach(parada => {
        if (parada.lat == null || parada.lng == null) return;

        const marker = _crearMarcadorParada(parada);
        marker.addTo(map);
        paradaMarkers[parada.id] = marker;
        bounds.push([parada.lat, parada.lng]);

        if (parada.es_actual) {
            paradaActualId = parada.id;
            map.setView([parada.lat, parada.lng], 17);
        }
    });

    if (bounds.length > 0 && !paradasData.some(p => p.es_actual)) {
        map.fitBounds(bounds, { padding: [50, 50] });
    }
}

function _crearMarcadorParada(parada) {
    const esActual = parada.es_actual;
    const iconHtml = esActual
        ? `<div style="background:linear-gradient(135deg,#10B981,#059669);width:34px;height:34px;
                border-radius:50%;border:4px solid white;box-shadow:0 4px 14px rgba(16,185,129,.7);
                display:flex;align-items:center;justify-content:center;">
             <span style="color:white;font-size:16px;font-weight:bold;">${parada.orden}</span>
           </div>`
        : `<div style="background:#9CA3AF;width:26px;height:26px;border-radius:50%;
                border:3px solid white;box-shadow:0 2px 6px rgba(0,0,0,.25);opacity:.75;
                display:flex;align-items:center;justify-content:center;">
             <span style="color:white;font-size:12px;font-weight:bold;">${parada.orden}</span>
           </div>`;

    const icon = L.divIcon({
        className: '',
        html: iconHtml,
        iconSize:   esActual ? [34, 34] : [26, 26],
        iconAnchor: esActual ? [17, 17] : [13, 13],
        popupAnchor:[0, -20],
    });

    return L.marker([parada.lat, parada.lng], { icon })
             .bindPopup(`<strong>${parada.nombre}</strong><br>Parada ${parada.orden}`);
}

/**
 * Actualiza el marcador de una parada cuando cambia su estado (actual/no actual).
 * Evita recrear todos los marcadores en cada poll.
 */
function _actualizarMarcadorParada(parada) {
    const marker = paradaMarkers[parada.id];
    if (!marker) return;
    const iconHtml = parada.es_actual
        ? `<div style="background:linear-gradient(135deg,#10B981,#059669);width:34px;height:34px;
                border-radius:50%;border:4px solid white;box-shadow:0 4px 14px rgba(16,185,129,.7);
                display:flex;align-items:center;justify-content:center;">
             <span style="color:white;font-size:16px;font-weight:bold;">${parada.orden}</span>
           </div>`
        : `<div style="background:#9CA3AF;width:26px;height:26px;border-radius:50%;
                border:3px solid white;box-shadow:0 2px 6px rgba(0,0,0,.25);opacity:.75;
                display:flex;align-items:center;justify-content:center;">
             <span style="color:white;font-size:12px;font-weight:bold;">${parada.orden}</span>
           </div>`;

    marker.setIcon(L.divIcon({
        className: '',
        html: iconHtml,
        iconSize:   parada.es_actual ? [34, 34] : [26, 26],
        iconAnchor: parada.es_actual ? [17, 17] : [13, 13],
        popupAnchor:[0, -20],
    }));
}

/**
 * Dibuja la polilínea completa de la ruta del tour en el mapa (color púrpura).
 * Se obtiene del campo Ruta.geometria_ruta_coords via el endpoint estado_sesion.
 * Solo se dibuja una vez (o cuando cambia la ruta) — no en cada poll.
 */
function _dibujarRutaCompleta(coords) {
    if (rutaCompletaLine) { map.removeLayer(rutaCompletaLine); rutaCompletaLine = null; }
    if (!coords || coords.length < 2) return;

    rutaCompletaLine = L.polyline(coords, {
        color:   '#7c3aed',
        weight:  4,
        opacity: 0.55,
        dashArray: null,
        smoothFactor: 1,
    }).addTo(map);
}


// ╔══════════════════════════════════════════════════════════════════════════╗
// ║  NAVEGACIÓN EN TIEMPO REAL                                              ║
// ╚══════════════════════════════════════════════════════════════════════════╝

/**
 * Dibuja la polilínea de navegación turista→parada actual (cian).
 * Reemplaza la línea anterior en cada recálculo.
 */
function _dibujarNavLine(coords) {
    if (navLine) { map.removeLayer(navLine); navLine = null; }
    if (!coords || coords.length < 2) return;

    navLine = L.polyline(coords, {
        color:       '#06b6d4',   // cian para distinguirlo de la ruta completa
        weight:      5,
        opacity:     0.9,
        smoothFactor:1,
        dashArray:   null,
    }).addTo(map);
}

/**
 * Calcula la distancia haversine entre dos puntos [lat, lng] en metros.
 * Se usa para el throttle (evitar llamadas a GraphHopper si el turista no se ha movido).
 */
function _distanciaM(p1, p2) {
    if (!p1 || !p2) return Infinity;
    const R  = 6371000;
    const φ1 = p1[0] * Math.PI / 180;
    const φ2 = p2[0] * Math.PI / 180;
    const Δφ = (p2[0] - p1[0]) * Math.PI / 180;
    const Δλ = (p2[1] - p1[1]) * Math.PI / 180;
    const a  = Math.sin(Δφ/2)**2 + Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ/2)**2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

/**
 * Muestra el banner de navegación con distancia y ETA hacia la parada actual.
 * Si distanciaM < RADIO_LLEGADA_M, muestra un toast de llegada y oculta el banner.
 */
function _actualizarBannerNavegacion(parada, distanciaM, duracionS) {
    const banner     = document.getElementById('nav-banner');
    const toastEl    = document.getElementById('nav-toast');
    if (!banner) return;

    if (distanciaM < RADIO_LLEGADA_M) {
        // ¡Ha llegado!
        banner.style.display = 'none';
        if (!llegadaNotificada && toastEl) {
            toastEl.textContent = `✅ ¡Has llegado a ${parada.nombre}!`;
            toastEl.style.display = 'flex';
            llegadaNotificada = true;
            setTimeout(() => { toastEl.style.display = 'none'; }, 5000);
        }
        return;
    }

    llegadaNotificada = false;
    if (toastEl) toastEl.style.display = 'none';

    // Formatear distancia y ETA
    const distTexto = distanciaM < 1000
        ? `${Math.round(distanciaM)} m`
        : `${(distanciaM / 1000).toFixed(1)} km`;
    const etaTexto  = duracionS < 60
        ? `${duracionS} s`
        : `${Math.round(duracionS / 60)} min`;

    const nombreEl  = banner.querySelector('.nav-parada-nombre');
    const distEl    = banner.querySelector('.nav-distancia');
    const etaEl     = banner.querySelector('.nav-eta');
    if (nombreEl) nombreEl.textContent = parada.nombre;
    if (distEl)   distEl.textContent   = distTexto;
    if (etaEl)    etaEl.textContent    = `≈ ${etaTexto}`;

    banner.style.display = 'flex';
}

function _ocultarBannerNavegacion() {
    const banner = document.getElementById('nav-banner');
    if (banner) banner.style.display = 'none';
}

/**
 * Llama al endpoint /ruta-a-parada/ con la posición actual del turista.
 * Actualiza la polilínea de navegación y el banner.
 *
 * Throttle: solo llama si el turista se ha movido >UMBRAL_DISTANCIA_M metros
 * O han pasado más de UMBRAL_TIEMPO_MS desde el último recálculo.
 */
async function _recalcularNavegacion(paradaActual, forzar = false) {
    if (!miPosActual || !paradaActual) { _ocultarBannerNavegacion(); return; }

    const ahora        = Date.now();
    const distMovido   = _distanciaM(miPosActual, ultimaPosRecalculo);
    const tiempoTransc = ahora - ultimoRecalculo;

    const debeRecalcular = forzar
        || !ultimaPosRecalculo
        || distMovido   > UMBRAL_DISTANCIA_M
        || tiempoTransc > UMBRAL_TIEMPO_MS;

    if (!debeRecalcular) return;

    ultimoRecalculo      = ahora;
    ultimaPosRecalculo   = [...miPosActual];

    try {
        const resp = await fetch(`/tours/sesiones/${sesionId}/ruta-a-parada/`, {
            method:  'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken':  getCsrfToken(),
            },
            body: JSON.stringify({ lat: miPosActual[0], lon: miPosActual[1] }),
        });

        if (!resp.ok) {
            // 503 = GraphHopper no disponible → mostrar línea recta como fallback
            _dibujarNavLineFallback(paradaActual);
            return;
        }

        const data = await resp.json();

        if (data.geometria && data.geometria.length >= 2) {
            _dibujarNavLine(data.geometria);
            _actualizarBannerNavegacion(paradaActual, data.distancia_m, data.duracion_s);
        } else {
            // Respuesta vacía → fallback
            _dibujarNavLineFallback(paradaActual);
            _actualizarBannerNavegacion(paradaActual, data.distancia_m || 0, data.duracion_s || 0);
        }

    } catch (err) {
        console.warn('[AURA nav] Error al calcular ruta:', err);
        _dibujarNavLineFallback(paradaActual);
    }
}

/** Línea recta como fallback cuando GraphHopper no está disponible. */
function _dibujarNavLineFallback(paradaActual) {
    if (!miPosActual) return;
    if (navLine) { map.removeLayer(navLine); navLine = null; }

    navLine = L.polyline([miPosActual, [paradaActual.lat, paradaActual.lng]], {
        color:     '#06b6d4',
        weight:    3,
        opacity:   0.6,
        dashArray: '10 8',   // discontinua para indicar que es estimada
    }).addTo(map);
}


// ╔══════════════════════════════════════════════════════════════════════════╗
// ║  POLLING ESTADO DE SESIÓN                                               ║
// ╚══════════════════════════════════════════════════════════════════════════╝

let _geometriaRutaDibujada = false;   // Solo dibujar la ruta completa una vez

async function _pollEstadoSesion() {
    try {
        const resp = await fetch(`/tours/sesiones/${sesionId}/estado/`);
        if (!resp.ok) return;

        const data = await resp.json();

        // ── Dibujar ruta completa la primera vez que llegue la geometría ───
        if (!_geometriaRutaDibujada && data.geometria_ruta && data.geometria_ruta.length >= 2) {
            _dibujarRutaCompleta(data.geometria_ruta);
            _geometriaRutaDibujada = true;
        }

        // ── Detectar cambio de parada ──────────────────────────────────────
        const nuevaParadaId = data.parada_actual_id;
        if (nuevaParadaId !== paradaActualId) {
            paradaActualId    = nuevaParadaId;
            llegadaNotificada = false;
            ultimoRecalculo   = 0;   // forzar recálculo inmediato en el próximo ciclo

            // Actualizar estilos de marcadores
            if (typeof paradasData !== 'undefined') {
                paradasData.forEach(p => {
                    p.es_actual = (p.id === nuevaParadaId);
                    _actualizarMarcadorParada(p);
                });
            }

            // Actualizar timeline del panel
            _actualizarTimeline(nuevaParadaId);

            // Limpiar línea de navegación anterior y recalcular
            if (navLine) { map.removeLayer(navLine); navLine = null; }

            if (data.parada_actual) {
                _centrarEnParada(data.parada_actual);
                // Forzar recálculo inmediato con la nueva parada
                await _recalcularNavegacion(data.parada_actual, true);
            } else {
                _ocultarBannerNavegacion();
            }
        } else {
            // Parada no cambió: recálculo normal con throttle
            if (data.parada_actual) {
                await _recalcularNavegacion(data.parada_actual);
            }
        }

    } catch (err) {
        console.warn('[AURA poll] Error en estado de sesión:', err);
    }
}

function _centrarEnParada(paradaData) {
    if (!paradaData) return;
    map.setView([paradaData.lat, paradaData.lng], Math.max(map.getZoom(), 17), {
        animate: true,
        duration: 0.8,
    });
}

function _actualizarTimeline(nuevaParadaId) {
    document.querySelectorAll('.timeline-item').forEach(item => {
        const esActual = item.dataset.paradaId
            ? parseInt(item.dataset.paradaId, 10) === nuevaParadaId
            : false;
        item.classList.toggle('active', esActual);
        const titulo = item.querySelector('h6');
        if (titulo) titulo.classList.toggle('text-muted', !esActual);
    });
}


// ╔══════════════════════════════════════════════════════════════════════════╗
// ║  RASTREO DE POSICIÓN PROPIA                                             ║
// ╚══════════════════════════════════════════════════════════════════════════╝

function iniciarRastreoLocal() {
    if (!navigator.geolocation) {
        console.warn('[AURA] Geolocalización no disponible.');
        return;
    }

    navigator.geolocation.watchPosition(
        position => {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;
            miPosActual = [lat, lng];

            // ── Actualizar marcador de propia ubicación ────────────────────
            if (!miUbicacionMarker) {
                const iconHtml = esGuia
                    ? '<div style="background:#ef4444;width:20px;height:20px;border-radius:50%;border:3px solid white;box-shadow:0 0 15px rgba(239,68,68,.8);"></div>'
                    : '<div style="background:#3b82f6;width:18px;height:18px;border-radius:50%;border:3px solid white;box-shadow:0 0 10px rgba(59,130,246,.8);"></div>';

                miUbicacionMarker = L.marker([lat, lng], {
                    icon: L.divIcon({
                        className: '',
                        html: iconHtml,
                        iconSize:   [24, 24],
                        iconAnchor: [12, 12],
                    }),
                    zIndexOffset: 1000,
                }).addTo(map).bindPopup(esGuia ? 'Mi Ubicación (Guía)' : 'Mi Ubicación');
            } else {
                miUbicacionMarker.setLatLng([lat, lng]);
            }

            // ── Enviar al servidor solo si soy el guía ─────────────────────
            if (esGuia) {
                fetch('/tours/ubicacion/', {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                    body:    JSON.stringify({ latitud: lat, longitud: lng, sesion_id: sesionId }),
                }).catch(err => console.error('[AURA] Error enviando ubicación:', err));
            }

            // ── Recálculo de navegación turista→parada (con throttle) ──────
            // El poll principal se encarga del recálculo cada 5 s, pero si el turista
            // se ha movido >25 m también lo disparamos desde aquí para respuesta inmediata.
            if (!esGuia) {
                const paradaActualData = _obtenerParadaActualData();
                if (paradaActualData) {
                    _recalcularNavegacion(paradaActualData);
                }
            }
        },
        err => console.warn('[AURA] Error de geolocalización:', err),
        { enableHighAccuracy: true, maximumAge: 0, timeout: 5000 },
    );
}

/** Obtiene los datos de la parada actual desde paradasData (array local). */
function _obtenerParadaActualData() {
    if (typeof paradasData === 'undefined') return null;
    return paradasData.find(p => p.id === paradaActualId) || null;
}


// ╔══════════════════════════════════════════════════════════════════════════╗
// ║  UBICACIÓN DEL GUÍA (solo turistas)                                     ║
// ╚══════════════════════════════════════════════════════════════════════════╝

function obtenerUbicacionGuia() {
    if (!map) return;

    fetch(`/tours/sesiones/${sesionId}/ubicacion_guia/`)
        .then(r => {
            const ct = r.headers.get('content-type');
            if (!ct || !ct.includes('application/json')) throw new Error('Respuesta no JSON');
            return r.json();
        })
        .then(data => {
            if (!data.lat || !data.lng) return;
            const pos = [data.lat, data.lng];

            if (!guiaMarker) {
                guiaMarker = L.marker(pos, {
                    icon: L.divIcon({
                        className: '',
                        html: `<div style="background:#ef4444;width:28px;height:28px;border-radius:50%;
                                     border:4px solid white;box-shadow:0 0 20px rgba(239,68,68,.7);
                                     display:flex;align-items:center;justify-content:center;">
                                 <svg viewBox="0 0 24 24" width="14" height="14" fill="white">
                                   <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5S10.62 6.5 12 6.5s2.5 1.12 2.5 2.5S13.38 11.5 12 11.5z"/>
                                 </svg>
                               </div>`,
                        iconSize:   [28, 28],
                        iconAnchor: [14, 14],
                    }),
                    zIndexOffset: 900,
                }).addTo(map).bindPopup('📍 Guía');
            } else {
                guiaMarker.setLatLng(pos);
            }
        })
        .catch(() => {/* guía sin ubicación todavía — silencioso */});
}


// ╔══════════════════════════════════════════════════════════════════════════╗
// ║  UTILIDADES                                                             ║
// ╚══════════════════════════════════════════════════════════════════════════╝

function getCsrfToken() {
    const name  = 'csrftoken=';
    const cookie= document.cookie.split(';').map(s => s.trim()).find(s => s.startsWith(name));
    return cookie ? cookie.slice(name.length) : '';
}


// ╔══════════════════════════════════════════════════════════════════════════╗
// ║  CHAT (copiado del original — sin cambios funcionales)                  ║
// ╚══════════════════════════════════════════════════════════════════════════╝

function initChat() {
    const chatMessages = document.getElementById('chat-messages');
    const chatInput    = document.getElementById('chat-input');
    const chatSendBtn  = document.getElementById('chat-send');
    if (!chatMessages || !chatInput || !chatSendBtn) return;

    let lastMessageTime   = null;
    let mensajesNoLeidos  = 0;
    let chatAbierto       = false;

    document.addEventListener('chatOpened', () => {
        chatAbierto      = true;
        mensajesNoLeidos = 0;
    });

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function getCurrentUsername() {
        return (typeof currentUserName !== 'undefined' && currentUserName)
            ? currentUserName
            : (document.body.getAttribute('data-username') || 'usuario');
    }

    function showChatBadge(count) {
        const badge = document.getElementById('chat-badge');
        if (badge) { badge.textContent = count > 99 ? '99+' : count; badge.style.display = 'block'; }
    }

    function renderMessages(mensajes) {
        if (!mensajes || mensajes.length === 0) return;

        const vacio = chatMessages.querySelector('.chat-empty');
        if (vacio) vacio.remove();

        const miNombre = getCurrentUsername();

        mensajes.forEach(msg => {
            if (chatMessages.querySelector(`[data-message-id="${msg.id}"]`)) return;

            lastMessageTime = msg.momento;
            const esMio     = msg.nombre_remitente === miNombre;
            const div       = document.createElement('div');
            div.className   = `chat-message ${esMio ? 'sent' : 'received'}`;
            div.setAttribute('data-message-id', msg.id);

            const ts  = new Date(msg.momento);
            const time= ts.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });

            div.innerHTML = `
                <div class="chat-message-header">
                    <span class="chat-message-sender">${escapeHtml(msg.nombre_remitente)}</span>
                    <span class="chat-message-time">${time}</span>
                </div>
                <div class="chat-message-bubble">${escapeHtml(msg.texto)}</div>`;

            chatMessages.appendChild(div);

            if (!esMio && !chatAbierto) {
                mensajesNoLeidos++;
                showChatBadge(mensajesNoLeidos);
            }
        });

        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function fetchMessages() {
        let url = `/tours/sesiones/${sesionId}/mensajes/`;
        if (lastMessageTime) {
            try { url += `?desde=${encodeURIComponent(new Date(lastMessageTime).toISOString())}`; }
            catch { url += `?desde=${encodeURIComponent(lastMessageTime)}`; }
        }

        fetch(url)
            .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
            .then(data => renderMessages(data.mensajes || data))
            .catch(err => console.warn('[AURA chat] Error:', err));
    }

    function sendMessage() {
        const texto = chatInput.value.trim();
        if (!texto) return;
        chatSendBtn.disabled = chatInput.disabled = true;

        fetch(`/tours/sesiones/${sesionId}/mensajes/enviar/`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body:    JSON.stringify({ texto }),
        })
        .then(r => r.json())
        .then(() => { chatInput.value = ''; fetchMessages(); })
        .catch(err => console.error('[AURA chat] Error al enviar:', err))
        .finally(() => {
            chatSendBtn.disabled = chatInput.disabled = false;
            chatInput.focus();
        });
    }

    chatSendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', e => { if (e.key === 'Enter') sendMessage(); });

    fetchMessages();
    setInterval(fetchMessages, 5000);
}
