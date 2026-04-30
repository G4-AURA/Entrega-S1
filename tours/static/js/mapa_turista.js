/* ============================================================
   AURA — Mapa del Turista  (mapa_turista.js)

   Muestra el recorrido pre-calculado de la ruta sobre un mapa
   minimalista. Sin lógica de navegación en tiempo real.

   Funcionalidades:
     · Tiles minimalistas (Mapbox Light / CartoDB Positron)
     · Polilínea del recorrido guardado en BD (GraphHopper)
     · Marcadores numerados de paradas (actual en índigo, resto en gris)
     · Punto pulsante con la posición propia del usuario
     · Marcador de la posición del guía en tiempo real (solo turistas)
     · Panel inferior: timeline del itinerario + chat con polling
   ============================================================ */

'use strict';

let map               = null;
let guiaMarker        = null;
let miUbicacionMarker = null;
const turistasMarkers = new Map();
let countdownTimerId  = null;
let countdownPollId   = null;
let curiosidadStatePollId = null;

// --- Variables para el control del fin de sesión del tour ---
let ubicacionPollId   = null;
let chatPollId        = null;
let geolocationWatchId = null;
let tourFinalizado    = false;
let ultimaPosicionTurista = null;
let primeraUbicacionTuristaCentrada = false;
const LOCATION_SEND_CONFIG = {
    guia: { minIntervalMs: 3000, minDistanceM: 4 },
    turista: { minIntervalMs: 10000, minDistanceM: 8 },
    hiddenIntervalMultiplier: 3,
};
const LAST_LOCATION_SENT = {
    guia: { atMs: 0, lat: null, lng: null },
    turista: { atMs: 0, lat: null, lng: null },
};
const LOCATION_SEND_IN_FLIGHT = {
    guia: false,
    turista: false,
};
// ------------------------------------------------------------

const paradasMarkers  = new Map();
const paradasDataById = new Map();
let paradaSeleccionadaId = null;
const curiosidadesMostradas = new Set();
const curiosidadesCachePorParada = new Map();
const curiosidadesTimelineCargando = new Set();
let paradaEnRadioActual = null;
let solicitudCuriosidadEnCurso = false;
let curiosidadPopupActual = null;
let sesionEstadoActual = (typeof sesionEstado !== 'undefined' && sesionEstado) ? sesionEstado : '';
const RADIO_PARADA_METROS = 75;

// ── Estados de centrado del mapa ───────────────────────────────────────────
const CENTRADO_STATES = {
    TURISTA: 'turista',
    GUIA: 'guia',
    PARADA: 'parada',
};
let estadoCentradoActual = CENTRADO_STATES.PARADA;
let primeraParadaCentrada = false;

const paradasRole = new Map();

// ── Inicialización ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {

    const mapElement = document.getElementById('mapa-tour');
    if (!mapElement) return;

    // Experiencia inmersiva: ocultar navbar y quitar márgenes del contenedor
    const navbar = document.querySelector('.navbar');
    if (navbar) navbar.style.display = 'none';
    const main = document.querySelector('main.container');
    if (main) { main.style.maxWidth = '100%'; main.style.padding = '0'; }

    // ── Inicializar mapa ───────────────────────────────────────────────────
    map = L.map('mapa-tour', { zoomControl: false }).setView([37.3891, -5.9845], 15);

    // Tiles minimalistas: fondo neutro claro donde la polilínea y los marcadores
    // destacan sin competir con texturas de satélite.
    const token = typeof mapboxToken !== 'undefined' ? mapboxToken : '';
    window.AuraMapTiles.createTileLayer({ token, style: 'light' }).addTo(map);

    L.control.zoom({ position: 'bottomright' }).addTo(map);

    // ── Dibujar recorrido y paradas ───────────────────────────────────────
    _dibujarRutaYParadas();
    _initParadaFocusButtons();
    _initMostrarCuriosidadButtons();


    // ── Posición propia ───────────────────────────────────────────────────
    _iniciarRastreoLocal();

    // ── Polling de posiciones en vivo ──────────────────────────────────────
    if (!esGuia) {
        _obtenerUbicacionGuia();
        ubicacionPollId = setInterval(_obtenerUbicacionGuia, 5000);
    } else {
        _obtenerUbicacionesTuristas();
        ubicacionPollId = setInterval(_obtenerUbicacionesTuristas, 5000);
    }

    // ── Overlay de sesión + navegación inferior ────────────────────────────
    const tourPanel = document.querySelector('.tour-panel');
    const sessionPanelTitle = document.getElementById('session-panel-title');
    const sessionNavButtons = document.querySelectorAll('.session-nav-btn');
    const chatSwitch = document.getElementById('session-chat-switch');
    const chatSwitchButtons = document.querySelectorAll('.session-chat-switch-btn');
    let lastChatTab = privateChatEnabled ? 'chat' : 'chat';
    document.body.classList.remove('session-overlay-open');

    const setActiveTab = (target) => {
        const btn = document.querySelector(`.tab-btn[data-tab="${target}"]`);
        if (!btn) return;
        btn.click();
    };

    const getActiveTab = () => {
        const activeBtn = document.querySelector('.tab-btn.active');
        return activeBtn ? activeBtn.getAttribute('data-tab') : null;
    };

    const syncSessionChrome = () => {
        const activeTab = getActiveTab();
        const panelOpen = Boolean(tourPanel && tourPanel.classList.contains('session-open'));

        if (activeTab === 'chat' || activeTab === 'chat-privado') {
            lastChatTab = activeTab;
        }

        if (sessionPanelTitle) {
            if (activeTab === 'notificaciones') sessionPanelTitle.textContent = 'Alertas';
            else if (activeTab === 'chat' || activeTab === 'chat-privado') sessionPanelTitle.textContent = 'Chats';
            else sessionPanelTitle.textContent = 'Itinerario';
        }

        sessionNavButtons.forEach((btn) => {
            const target = btn.getAttribute('data-open-tab');
            const isChatNav = target === 'chat' && (activeTab === 'chat' || activeTab === 'chat-privado');
            const isCurrent = target === activeTab || isChatNav;
            btn.classList.toggle('active', panelOpen && isCurrent);
        });

        const showChatSwitch = panelOpen && privateChatEnabled
            && (activeTab === 'chat' || activeTab === 'chat-privado');
        if (chatSwitch) {
            chatSwitch.style.display = showChatSwitch ? 'inline-flex' : 'none';
        }
        chatSwitchButtons.forEach((btn) => {
            btn.classList.toggle('active', btn.getAttribute('data-chat-tab') === activeTab);
        });
    };

    const closeSessionPanel = () => {
        if (!tourPanel) return;
        tourPanel.classList.remove('session-open');
        document.body.classList.remove('session-overlay-open');
        document.dispatchEvent(new CustomEvent('chatClosed'));
        document.dispatchEvent(new CustomEvent('privateChatClosed'));
        syncSessionChrome();
    };

    const openSessionPanel = (tabRequested) => {
        if (!tourPanel) return;
        const targetTab = tabRequested === 'chat' ? lastChatTab : tabRequested;
        tourPanel.classList.add('session-open');
        document.body.classList.add('session-overlay-open');
        setActiveTab(targetTab);
        syncSessionChrome();
    };

    sessionNavButtons.forEach((btn) => {
        btn.addEventListener('click', () => {
            const target = btn.getAttribute('data-open-tab');
            if (!target) return;
            const panelOpen = Boolean(tourPanel && tourPanel.classList.contains('session-open'));
            const activeTab = getActiveTab();
            const isChatTarget = target === 'chat' && (activeTab === 'chat' || activeTab === 'chat-privado');
            const isCurrent = target === activeTab || isChatTarget;
            if (panelOpen && isCurrent) {
                closeSessionPanel();
                return;
            }
            openSessionPanel(target);
        });
    });

    chatSwitchButtons.forEach((btn) => {
        btn.addEventListener('click', () => {
            const target = btn.getAttribute('data-chat-tab');
            if (!target) return;
            setActiveTab(target);
            syncSessionChrome();
        });
    });

    // ── Tabs internas (se mantienen para reutilizar lógica existente) ──────
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const target = this.getAttribute('data-tab');
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            this.classList.add('active');
            document.getElementById('tab-' + target)?.classList.add('active');

            if (target === 'chat') {
                const badge = document.getElementById('chat-badge');
                if (badge) badge.style.display = 'none';
                document.dispatchEvent(new CustomEvent('chatOpened'));
            } else {
                document.dispatchEvent(new CustomEvent('chatClosed'));
            }

            if (target === 'chat-privado') {
                const privBadge = document.getElementById('chat-privado-badge');
                if (privBadge) privBadge.style.display = 'none';
                document.dispatchEvent(new CustomEvent('privateChatOpened'));
            } else {
                document.dispatchEvent(new CustomEvent('privateChatClosed'));
            }

            if (target === 'notificaciones') {
                const badge = document.getElementById('recordatorios-badge');
                if (badge) badge.style.display = 'none';
                document.dispatchEvent(new CustomEvent('recordatoriosOpened'));
            }

            syncSessionChrome();
        });
    });

    syncSessionChrome();

    // ── Inicializar botón de centrado ──────────────────────────────────────
    _initBotónCentraMapa();
    
    // ── Centralizar en primera parada al cargar ────────────────────────────
    _centro_primera_parada();

    // ── Chat ──────────────────────────────────────────────────────────────
    _initSessionCountdown();
    _initCuriosidadStateSync();
    _initChat();
    _initRecordatorios();
});


// ── Dibujar recorrido y marcadores ─────────────────────────────────────────

function _dibujarRutaYParadas() {

    // 1. Polilínea del recorrido real (geometría calculada por GraphHopper, guardada en BD)
    //    `geometriaRuta` se inyecta desde el template como [[lat,lon],...] o null.
    if (typeof geometriaRuta !== 'undefined' && geometriaRuta && geometriaRuta.length >= 2) {
        L.polyline(geometriaRuta, {
            color:        '#4f46e5',   // índigo — color primario de AURA
            weight:       4,
            opacity:      0.75,
            smoothFactor: 1,
        }).addTo(map);

        map.fitBounds(L.latLngBounds(geometriaRuta), { padding: [48, 48] });
    }

    // 2. Marcadores de paradas
    if (typeof paradasData === 'undefined' || !Array.isArray(paradasData)) return;

    const bounds = [];

    const paradasConCoordenadas = paradasData.filter(p => p.lat != null && p.lng != null);
    const ordenMin = paradasConCoordenadas.length > 0
        ? Math.min(...paradasConCoordenadas.map(p => p.orden))
        : null;
    const ordenMax = paradasConCoordenadas.length > 0
        ? Math.max(...paradasConCoordenadas.map(p => p.orden))
        : null;

    paradasData.forEach(parada => {
        if (parada.lat == null || parada.lng == null) return;

        bounds.push([parada.lat, parada.lng]);

        let role = null;
        if (paradasConCoordenadas.length >= 2) {
            if (parada.orden === ordenMin) role = 'origin';
            else if (parada.orden === ordenMax) role = 'destination';
        }

        if (parada.id != null) {
            paradasRole.set(String(parada.id), role);
        }

        const marker = L.marker([parada.lat, parada.lng], {
            icon: _buildParadaIcon(parada, false, role),
        })
        .addTo(map)
        .bindPopup(_buildPopupTour(parada, role));

        if (parada.id != null) {
            const paradaId = String(parada.id);
            paradasMarkers.set(paradaId, marker);
            paradasDataById.set(paradaId, parada);
        }
    });

    // Si no hay geometría, ajustar la vista a los marcadores
    if ((typeof geometriaRuta === 'undefined' || !geometriaRuta) && bounds.length > 0) {
        bounds.length === 1
            ? map.setView(bounds[0], 16)
            : map.fitBounds(L.latLngBounds(bounds), { padding: [48, 48] });
    }
}


// ── Posición propia (punto pulsante) ───────────────────────────────────────

async function _iniciarRastreoLocal() {
    if (!navigator.geolocation) return;

    geolocationWatchId = navigator.geolocation.watchPosition(
        position => {
            const { latitude: lat, longitude: lng } = position.coords;
            const pos = [lat, lng];
            ultimaPosicionTurista = { lat, lng };

            if (!miUbicacionMarker) {
                const color = esGuia ? '#ef4444' : '#3b82f6';
                miUbicacionMarker = L.marker(pos, {
                    icon: L.divIcon({
                        className: '',
                        html: `<div style="position:relative;width:22px;height:22px;">
                                 <div style="position:absolute;inset:0;border-radius:50%;
                                      background:${color};opacity:.25;
                                      animation:pulse 1.8s infinite;"></div>
                                 <div style="position:absolute;inset:4px;border-radius:50%;
                                      background:${color};border:2px solid white;
                                      box-shadow:0 1px 6px rgba(0,0,0,.25);"></div>
                               </div>`,
                        iconSize:   [22, 22],
                        iconAnchor: [11, 11],
                    }),
                    zIndexOffset: 1000,
                }).addTo(map).bindPopup(esGuia ? 'Guía (tú)' : 'Tú');
            } else {
                miUbicacionMarker.setLatLng(pos);
            }

            if (!esGuia && !primeraUbicacionTuristaCentrada && map) {
                map.flyTo(pos, Math.max(map.getZoom(), 16), { duration: 0.6 });
                primeraUbicacionTuristaCentrada = true;
            }

            // El guía envía su posición al servidor para que los turistas la vean
            if (esGuia) {
                if (_shouldSendLocationUpdate('guia', lat, lng)) {
                    _setLocationUpdateInFlight('guia', true);
                    fetch('/tours/ubicacion/', {
                        method:  'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _getCsrf() },
                        body:    JSON.stringify({ latitud: lat, longitud: lng, sesion_id: sesionId }),
                    })
                        .then((r) => {
                            if (!r.ok) throw new Error('No se pudo registrar ubicación del guía.');
                            _markLocationUpdateSent('guia', lat, lng);
                        })
                        .catch(() => {})
                        .finally(() => {
                            _setLocationUpdateInFlight('guia', false);
                        });
                }
            } else {
                if (_shouldSendLocationUpdate('turista', lat, lng)) {
                    _setLocationUpdateInFlight('turista', true);
                    fetch(`/tours/sesiones/${sesionId}/ubicacion_turista/`, {
                        method:  'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _getCsrf() },
                        body:    JSON.stringify({ latitud: lat, longitud: lng }),
                    })
                        .then(r => {
                            if (!r.ok) throw new Error('No se pudo registrar ubicación del turista.');
                            _markLocationUpdateSent('turista', lat, lng);
                            return r.json();
                        })
                        .then(data => {
                            const curiosidadCercana = data?.curiosidad_cercana;
                            const parada = curiosidadCercana?.parada;
                            const curiosidad = curiosidadCercana?.curiosidad;
                            if (!parada?.id || !curiosidad) return;

                            const paradaId = String(parada.id);
                            if (curiosidadesMostradas.has(paradaId)) return;

                            curiosidadesMostradas.add(paradaId);
                            _mostrarCuriosidadAutomatica(parada, curiosidad);
                        })
                        .catch(() => {})
                        .finally(() => {
                            _setLocationUpdateInFlight('turista', false);
                        });
                }

                _detectarParadaYSolicitarCuriosidad(lat, lng);
            }
        },
        error => {
            const feedback = window.AuraFeedback;
            const mensaje =
                error?.code === error.PERMISSION_DENIED
                    ? 'El navegador ha bloqueado la ubicación. Revisa los permisos del sitio.'
                    : error?.code === error.POSITION_UNAVAILABLE
                        ? 'No se pudo obtener una posición válida en este momento.'
                        : error?.code === error.TIMEOUT
                            ? 'La localización está tardando demasiado en responder.'
                            : 'No se pudo detectar la ubicación automáticamente.';

            if (feedback && typeof feedback.toast === 'function') {
                feedback.toast(mensaje, { type: 'warning', duration: 3800 });
            } else {
                console.warn('[AURA geolocation]', mensaje);
            }
        },
        { enableHighAccuracy: true, maximumAge: 0, timeout: 6000 },
    );
}


function _shouldSendLocationUpdate(role, lat, lng) {
    const roleKey = (role === 'guia') ? 'guia' : 'turista';
    const cfg = LOCATION_SEND_CONFIG[roleKey];
    const state = LAST_LOCATION_SENT[roleKey];
    if (!cfg || !state) return true;
    if (LOCATION_SEND_IN_FLIGHT[roleKey]) return false;

    if (!Number.isFinite(state.atMs) || state.atMs <= 0) return true;

    const hiddenMultiplier = (document.visibilityState === 'hidden')
        ? LOCATION_SEND_CONFIG.hiddenIntervalMultiplier
        : 1;
    const minIntervalMs = cfg.minIntervalMs * hiddenMultiplier;
    const elapsedMs = Date.now() - state.atMs;

    let distanceM = Number.POSITIVE_INFINITY;
    if (Number.isFinite(state.lat) && Number.isFinite(state.lng)) {
        distanceM = _distanciaMetros(lat, lng, state.lat, state.lng);
    }

    return !(elapsedMs < minIntervalMs && distanceM < cfg.minDistanceM);
}


function _setLocationUpdateInFlight(role, isInFlight) {
    const roleKey = (role === 'guia') ? 'guia' : 'turista';
    if (!(roleKey in LOCATION_SEND_IN_FLIGHT)) return;
    LOCATION_SEND_IN_FLIGHT[roleKey] = Boolean(isInFlight);
}


function _markLocationUpdateSent(role, lat, lng) {
    const roleKey = (role === 'guia') ? 'guia' : 'turista';
    const state = LAST_LOCATION_SENT[roleKey];
    if (!state) return;

    state.atMs = Date.now();
    state.lat = lat;
    state.lng = lng;
}


// ── Posición del guía (solo turistas) ─────────────────────────────────────

function _obtenerUbicacionGuia() {
    if (!map || tourFinalizado) return;

    fetch(`/tours/sesiones/${sesionId}/ubicacion_guia/`)
        .then(r => { 
            if ([401, 403, 410].includes(r.status)) {
                _manejarFinDeTour(); throw new Error('Fin');
            }
            if (!r.ok) throw new Error(); 
            return r.json(); 
        })
        .then(data => {
            if (!data.lat || !data.lng) return;
            const pos = [data.lat, data.lng];

            if (!guiaMarker) {
                guiaMarker = L.marker(pos, {
                    icon: L.divIcon({
                        className: '',
                        html: `<div style="
                                background:#ef4444;width:30px;height:30px;
                                border-radius:50%;border:3px solid white;
                                box-shadow:0 2px 8px rgba(239,68,68,.5);
                                display:flex;align-items:center;justify-content:center;">
                                <svg viewBox="0 0 24 24" width="14" height="14" fill="white">
                                  <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75
                                           7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5
                                           -2.5S10.62 6.5 12 6.5s2.5 1.12 2.5 2.5S13.38 11.5 12 11.5z"/>
                                </svg>
                               </div>`,
                        iconSize:   [30, 30],
                        iconAnchor: [15, 15],
                    }),
                    zIndexOffset: 900,
                }).addTo(map).bindPopup('Guía');
            } else {
                guiaMarker.setLatLng(pos);
            }
        })
        .catch(() => {});
}


// ── Utilidades ─────────────────────────────────────────────────────────────

function _getCsrf() {
    const c = document.cookie.split(';').map(s => s.trim()).find(s => s.startsWith('csrftoken='));
    return c ? c.slice('csrftoken='.length) : '';
}

function _detectarParadaYSolicitarCuriosidad(lat, lng) {
    if (esGuia || !_sesionEnCurso() || !Array.isArray(paradasData) || !paradasData.length) return;

    const paradaMasCercana = _buscarParadaMasCercanaEnRadio(lat, lng, RADIO_PARADA_METROS);

    if (!paradaMasCercana) {
        paradaEnRadioActual = null;
        return;
    }

    const paradaId = String(paradaMasCercana.id);
    if (!paradaId) return;

    if (paradaEnRadioActual === paradaId) return;
    paradaEnRadioActual = paradaId;

    if (curiosidadesMostradas.has(paradaId) || solicitudCuriosidadEnCurso) return;

    _solicitarCuriosidadParada(paradaId);
}

function _buscarParadaMasCercanaEnRadio(lat, lng, radioMetros) {
    let paradaCandidata = null;
    let menorDistancia = Number.POSITIVE_INFINITY;

    paradasData.forEach(parada => {
        if (parada?.lat == null || parada?.lng == null || parada?.id == null) return;

        const distancia = _distanciaMetros(lat, lng, parada.lat, parada.lng);
        if (distancia <= radioMetros && distancia < menorDistancia) {
            menorDistancia = distancia;
            paradaCandidata = parada;
        }
    });

    return paradaCandidata;
}

function _distanciaMetros(lat1, lng1, lat2, lng2) {
    const toRad = value => (value * Math.PI) / 180;
    const earthRadiusM = 6371000;

    const dLat = toRad(lat2 - lat1);
    const dLng = toRad(lng2 - lng1);
    const lat1Rad = toRad(lat1);
    const lat2Rad = toRad(lat2);

    const a = Math.sin(dLat / 2) ** 2
        + Math.cos(lat1Rad) * Math.cos(lat2Rad) * Math.sin(dLng / 2) ** 2;
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

    return earthRadiusM * c;
}

async function _solicitarCuriosidadParada(paradaId) {
    solicitudCuriosidadEnCurso = true;

    try {
        const response = await fetch(`/tours/sesiones/${sesionId}/paradas/${paradaId}/curiosidad/`, {
            method: 'GET',
            headers: { 'Accept': 'application/json' },
        });

        if (!response.ok) return;

        const payload = await response.json();
        if (!payload?.curiosidad) return;

        curiosidadesMostradas.add(String(paradaId));
        _mostrarCuriosidadAutomatica(payload.parada, payload.curiosidad);
    } catch {
        return;
    } finally {
        solicitudCuriosidadEnCurso = false;
    }
}

function _mostrarCuriosidadAutomatica(parada, curiosidad) {
    if (!curiosidad) return;

    const urlSeguridad = (typeof fallbackCuriosidadImg !== 'undefined' && fallbackCuriosidadImg) 
                         ? fallbackCuriosidadImg 
                         : 'https://images.unsplash.com/photo-1524661135-423995f22d0b?q=80&w=600&auto=format&fit=crop';
                         
    const tieneImagen = curiosidad.imagen_url && curiosidad.imagen_url.trim() !== '';
    const finalImgUrl = tieneImagen ? curiosidad.imagen_url : urlSeguridad;

    const paradaId = parada && parada.id != null ? String(parada.id) : null;
    if (paradaId && !esGuia) {
        curiosidadesCachePorParada.set(paradaId, { parada, curiosidad });
        _renderCuriosidadEnTimeline(paradaId, curiosidad);
    }

    _cerrarCuriosidadVisible();

    const popupContent = document.createElement('div');
    popupContent.id = 'curiosidad-auto-card';
    if (parada && parada.id) {
        popupContent.setAttribute('data-parada-id', String(parada.id));
    }
    popupContent.setAttribute('role', 'status');
    popupContent.style.maxWidth = '320px';
    popupContent.style.minWidth = '240px';
    popupContent.style.fontFamily = "'Manrope', sans-serif";
    popupContent.style.color = '#111827';

    const paradaTexto = parada?.nombre ? `Parada: ${parada.nombre}` : 'Parada actual';
    const tipoTexto = curiosidad.tipo ? `<span style="font-size:.72rem;color:#4338ca;font-weight:700;text-transform:uppercase;">${_escapeHtml(curiosidad.tipo)}</span>` : '';
    const tituloTexto = curiosidad.titulo ? _escapeHtml(curiosidad.titulo) : 'Curiosidad de esta parada';
    const cuerpoTexto = curiosidad.texto ? _escapeHtml(curiosidad.texto) : '';

    popupContent.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom: 8px; gap: 12px;">
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                <strong style="font-size:.8rem;color:#111827;">${_escapeHtml(paradaTexto)}</strong>
                ${tipoTexto}
            </div>
            <button type="button" id="curiosidad-auto-close" aria-label="Cerrar curiosidad"
                style="border:none;background:transparent;color:#6b7280;cursor:pointer;font-size:1.25rem;line-height:1;flex-shrink:0;">×</button>
        </div>
        <div id="curiosidad-auto-img-container"></div>
        <div>
            <h4 style="margin:0 0 4px 0;font-size:1rem;color:#111827;">${tituloTexto}</h4>
            <p style="margin:0;font-size:.9rem;color:#374151;line-height:1.35;">${cuerpoTexto}</p>
        </div>`;

    const imgContainer = popupContent.querySelector('#curiosidad-auto-img-container');
    if (imgContainer) {
        const imgEl = document.createElement('img');
        imgEl.src = finalImgUrl;
        imgEl.style.cssText = "width: 100%; height: 160px; object-fit: cover; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);";
        imgEl.alt = "Imagen de la curiosidad";
        imgEl.onerror = function() {
            this.onerror = null;
            this.src = urlSeguridad;
        };
        imgContainer.appendChild(imgEl);
    }

    const closeBtn = popupContent.querySelector('#curiosidad-auto-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', async () => {
            if (esGuia && parada && parada.id) {
                try {
                    await _setCuriosidadVisibilityOnServer(parada.id, false);
                } catch {
                    // Si falla, al menos cerramos localmente.
                }
            }
            _cerrarCuriosidadVisible();
            if (esGuia) _syncCuriosidadButtons(null);
        });
    }

    const latLng = parada && Number.isFinite(parada.lat) && Number.isFinite(parada.lng)
        ? [parada.lat, parada.lng]
        : (parada && parada.id && paradasMarkers.get(String(parada.id))
            ? paradasMarkers.get(String(parada.id)).getLatLng()
            : (map ? map.getCenter() : [0, 0]));

    curiosidadPopupActual = L.popup({
        closeButton: false,
        autoClose: true,
        closeOnClick: false,
        className: 'curiosidad-popup-map',
        offset: [0, -12],
        maxWidth: 360,
    })
        .setLatLng(latLng)
        .setContent(popupContent)
        .openOn(map);

    curiosidadPopupActual.on('remove', () => {
        if (curiosidadPopupActual && curiosidadPopupActual.getElement && curiosidadPopupActual.getElement()) {
            // noop: guardamos el mismo flujo aunque el popup se cierre externamente.
        }
    });

    if (parada && parada.id && esGuia) {
        _setCuriosidadButtonLabel(parada.id, 'Ocultar curiosidad');
    }

    // La curiosidad permanece visible hasta que el guía la cierre manualmente.
}

function _cerrarCuriosidadVisible() {
    const popup = curiosidadPopupActual;
    if (!popup) return;

    const popupContent = popup.getContent ? popup.getContent() : null;
    const paradaId = popupContent && popupContent.getAttribute ? popupContent.getAttribute('data-parada-id') : null;
    if (paradaId && esGuia) {
        _setCuriosidadButtonLabel(paradaId, 'Mostrar curiosidad');
    }

    if (map) {
        map.closePopup(popup);
    }

    curiosidadPopupActual = null;
}

function _setCuriosidadButtonLabel(paradaId, label) {
    const button = document.querySelector(`.mostrar-curiosidad-btn[data-parada-id="${CSS.escape(String(paradaId))}"]`);
    if (!button) return;
    button.textContent = label;
}

async function _setCuriosidadVisibilityOnServer(paradaId, visible) {
    if (!esGuia || !paradaId) return null;
    const response = await fetch(`/tours/sesiones/${sesionId}/paradas/${paradaId}/curiosidad/visibilidad/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': _getCsrf(),
            'Accept': 'application/json',
        },
        body: JSON.stringify({ visible: Boolean(visible) }),
    });
    if (!response.ok) {
        throw new Error('No se pudo actualizar la visibilidad de la curiosidad.');
    }
    return response.json();
}

function _parseParadaId(value) {
    const parsed = Number.parseInt(String(value), 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function _getPopupParadaId() {
    const popupContent = curiosidadPopupActual?.getContent?.();
    const raw = popupContent?.getAttribute?.('data-parada-id');
    return _parseParadaId(raw);
}

function _renderCuriosidadEnTimeline(paradaId, curiosidad) {
    if (!paradaId || !curiosidad) return;

    const contenedor = document.getElementById(`curiosidad-timeline-${paradaId}`);
    if (!contenedor) return;

    const tipoEl = document.getElementById(`curiosidad-timeline-tipo-${paradaId}`);
    const tituloEl = document.getElementById(`curiosidad-timeline-titulo-${paradaId}`);
    const textoEl = document.getElementById(`curiosidad-timeline-texto-${paradaId}`);
    const imgEl = document.getElementById(`curiosidad-timeline-img-${paradaId}`);

    if (tipoEl) tipoEl.textContent = curiosidad.tipo || '';
    if (tituloEl) tituloEl.textContent = curiosidad.titulo || 'Curiosidad';
    if (textoEl) textoEl.textContent = curiosidad.texto || '';

    const imgUrl = curiosidad.imagen_url || curiosidad.manual_url || '';
    if (imgEl) {
        if (imgUrl) {
            imgEl.src = imgUrl;
            imgEl.style.display = 'block';
        } else {
            imgEl.removeAttribute('src');
            imgEl.style.display = 'none';
        }
    }

    contenedor.style.display = 'block';
}

async function _ensureCuriosidadTimeline(paradaId) {
    const key = String(paradaId);
    if (!key || curiosidadesTimelineCargando.has(key)) return;

    const cacheEntry = curiosidadesCachePorParada.get(key);
    if (cacheEntry?.curiosidad) {
        _renderCuriosidadEnTimeline(key, cacheEntry.curiosidad);
        return;
    }

    curiosidadesTimelineCargando.add(key);
    try {
        const response = await fetch(`/tours/sesiones/${sesionId}/paradas/${key}/curiosidad/?solo_existente=1`, {
            method: 'GET',
            headers: { 'Accept': 'application/json' },
        });
        if (!response.ok) return;
        const payload = await response.json();
        if (!payload?.curiosidad) return;
        curiosidadesCachePorParada.set(key, { parada: payload.parada, curiosidad: payload.curiosidad });
        _renderCuriosidadEnTimeline(key, payload.curiosidad);
    } catch {
        return;
    } finally {
        curiosidadesTimelineCargando.delete(key);
    }
}

function _syncCuriosidadButtons(visibleParadaId) {
    if (!esGuia) return;
    document.querySelectorAll('.mostrar-curiosidad-btn').forEach((btn) => {
        const btnParadaId = _parseParadaId(btn.getAttribute('data-parada-id'));
        if (!btnParadaId) return;
        btn.textContent = (visibleParadaId && btnParadaId === visibleParadaId)
            ? 'Ocultar curiosidad'
            : 'Mostrar curiosidad';
    });
}

function _syncCuriosidadStateFromRemote(data) {
    if (!data) return;

    if (esGuia) return;
    const visibleParadaId = _parseParadaId(data.curiosidad_visible_parada_id);

    const historyIds = Array.isArray(data.curiosidades_historial_paradas_ids)
        ? data.curiosidades_historial_paradas_ids.map(_parseParadaId).filter(Boolean)
        : [];

    historyIds.forEach((id) => {
        _ensureCuriosidadTimeline(id);
    });

    const popupParadaId = _getPopupParadaId();
    if (!visibleParadaId) {
        if (popupParadaId) _cerrarCuriosidadVisible();
        return;
    }

    if (popupParadaId === visibleParadaId) return;

    const cached = curiosidadesCachePorParada.get(String(visibleParadaId));
    if (cached?.curiosidad) {
        _mostrarCuriosidadAutomatica(cached.parada, cached.curiosidad);
        return;
    }

    _ensureCuriosidadTimeline(visibleParadaId).then(() => {
        const loaded = curiosidadesCachePorParada.get(String(visibleParadaId));
        if (loaded?.curiosidad) {
            _mostrarCuriosidadAutomatica(loaded.parada, loaded.curiosidad);
        }
    }).catch(() => {});
}

function _initCuriosidadStateSync() {
    if (esGuia) return;
    if (typeof curiosidadesEstadoUrl === 'undefined' || !curiosidadesEstadoUrl) return;

    const poll = () => {
        if (tourFinalizado) return;
        const separator = curiosidadesEstadoUrl.includes('?') ? '&' : '?';
        const liveUrl = `${curiosidadesEstadoUrl}${separator}_=${Date.now()}`;
        fetch(liveUrl, { cache: 'no-store' })
            .then((r) => {
                if ([401, 403, 410].includes(r.status)) {
                    return Promise.reject();
                }
                if (!r.ok) return Promise.reject();
                return r.json();
            })
            .then((data) => {
                _syncCuriosidadStateFromRemote(data);
            })
            .catch(() => {});
    };

    poll();
    curiosidadStatePollId = setInterval(poll, 4000);
}

function _flashCuriosidadButtonLabel(paradaId, temporaryLabel, restoreLabel, timeoutMs = 2400) {
    const button = document.querySelector(`.mostrar-curiosidad-btn[data-parada-id="${CSS.escape(String(paradaId))}"]`);
    if (!button) return;

    button.textContent = temporaryLabel;
    window.setTimeout(() => {
        const currentButton = document.querySelector(`.mostrar-curiosidad-btn[data-parada-id="${CSS.escape(String(paradaId))}"]`);
        if (currentButton) {
            currentButton.textContent = restoreLabel;
        }
    }, timeoutMs);
}

function _escapeHtml(value) {
    const node = document.createElement('div');
    node.textContent = String(value ?? '');
    return node.innerHTML;
}

function _sesionEnCurso() {
    return sesionEstadoActual === 'en_curso';
}

function _manejarFinDeTour() {
    if (tourFinalizado) return;
    tourFinalizado = true;
    sesionEstadoActual = 'finalizada';

    // 1. Limpiar todos los intervalos de peticiones
    if (countdownPollId) clearInterval(countdownPollId);
    if (countdownTimerId) clearInterval(countdownTimerId);
    if (curiosidadStatePollId) clearInterval(curiosidadStatePollId);
    if (ubicacionPollId) clearInterval(ubicacionPollId);
    if (chatPollId) clearInterval(chatPollId);

    // 2. Detener el rastreo GPS local (ahorra batería)
    if (geolocationWatchId && navigator.geolocation) {
        navigator.geolocation.clearWatch(geolocationWatchId);
    }

    // 3. Actualizar la UI del temporizador a "Finalizado"
    const timerContainer = document.getElementById('session-countdown');
    const timerValue = document.getElementById('session-countdown-time');
    const startBtn = document.getElementById('start-countdown-btn');
    const pauseBtn = document.getElementById('pause-countdown-btn');
    if (timerContainer && timerValue) {
        timerContainer.classList.remove('waiting', 'en_curso', 'paused');
        timerContainer.classList.add('finished');
        timerValue.textContent = '00:00';
    }
    if (startBtn) startBtn.disabled = true;
    if (pauseBtn) {
        pauseBtn.disabled = true;
        pauseBtn.classList.add('d-none');
    }
    const estadoBadgeContainer = document.querySelector('#tab-itinerario > div.d-flex.justify-content-between');
    if (estadoBadgeContainer) {
        const oldBadge = estadoBadgeContainer.querySelector('span'); // Selecciona la primera pastilla
        if (oldBadge) {
            oldBadge.outerHTML = `<span style="display:inline-flex;align-items:center;background:var(--border-light);color:var(--text-muted);border-radius:var(--radius-pill);padding:.3rem .8rem;font-size:.67rem;font-weight:700;font-family:'Manrope',sans-serif;letter-spacing:.5px;text-transform:uppercase;">Finalizado</span>`;
        }
    }

    // 4. Disparar el evento para deshabilitar el input del chat
    document.dispatchEvent(new CustomEvent('sessionStateChanged', { detail: { estado: 'finalizada' } }));

    // 5. Notificar al usuario visualmente
    const feedback = window.AuraFeedback;
    if (feedback && typeof feedback.alert === 'function') {
        feedback.alert({
            title: 'Recorrido finalizado',
            message: 'El guía ha terminado el tour. Ya no se actualizará tu ubicación ni el chat, pero puedes consultar el itinerario y los mensajes anteriores. Una vez que salgas del tour, no podrás volver a unirte.',
            confirmText: 'Entendido',
            type: 'info'
        });
    } else {
        alert('El tour ha finalizado. Ya no se recibirán actualizaciones.');
    }
}


// ── Cronómetro de sesión ──────────────────────────────────────────────────

function _initSessionCountdown() {
    const timerContainer = document.getElementById('session-countdown');
    const timerValue = document.getElementById('session-countdown-time');
    const startBtn = document.getElementById('start-countdown-btn');
    const pauseBtn = document.getElementById('pause-countdown-btn');
    if (!timerContainer || !timerValue) return;

    const MINUTE_MS = 60 * 1000;
    const COUNTDOWN_STATUS_POLL_MS = 5000;
    const horasBase = (typeof duracionRutaHoras !== 'undefined' && Number.isFinite(duracionRutaHoras) && duracionRutaHoras > 0)
        ? duracionRutaHoras
        : 1;
    const countdownMs = Math.round(horasBase * 60 * 60 * 1000);
    const countdownTotalMinutes = Math.max(1, Math.ceil(countdownMs / MINUTE_MS));
    let sesionIniciada = (typeof sesionEstado !== 'undefined' && sesionEstado === 'en_curso');
    let cronometroPausado = false;
    let startTimestamp = (typeof sesionFechaInicioEpochMs !== 'undefined' && Number.isFinite(sesionFechaInicioEpochMs))
        ? sesionFechaInicioEpochMs
        : Date.now();
    let pauseBtnRequestInFlight = false;

    const stopTicker = () => {
        if (countdownTimerId) {
            clearInterval(countdownTimerId);
            countdownTimerId = null;
        }
    };

    const setPauseButtonState = () => {
        if (!pauseBtn) return;

        if (!sesionIniciada) {
            pauseBtn.classList.add('d-none');
            pauseBtn.disabled = true;
            pauseBtn.textContent = 'Pausar cronómetro';
            return;
        }

        pauseBtn.classList.remove('d-none');
        pauseBtn.disabled = pauseBtnRequestInFlight;
        if (cronometroPausado) {
            pauseBtn.textContent = 'Reanudar cronómetro';
        } else {
            pauseBtn.textContent = 'Pausar cronómetro';
        }
    };

    const setCountdownProgress = (remainingMinutes) => {
        const normalizedRemaining = Number.isFinite(remainingMinutes)
            ? Math.max(0, Math.min(countdownTotalMinutes, Math.ceil(remainingMinutes)))
            : countdownTotalMinutes;
        const progress = 1 - (normalizedRemaining / countdownTotalMinutes);
        timerContainer.style.setProperty('--countdown-progress', String(Math.max(0, Math.min(1, progress))));
    };

    const setWaitingUi = () => {
        stopTicker();
        timerValue.textContent = _formatRemainingMinutes(countdownTotalMinutes);
        setCountdownProgress(countdownTotalMinutes);
        timerContainer.classList.remove('finished', 'paused');
        timerContainer.classList.add('waiting');
    };

    const startTicker = (remoteRemainingMinutes = null) => {
        stopTicker();

        timerContainer.classList.remove('waiting', 'paused');
        const hasRemoteMinutes = Number.isFinite(remoteRemainingMinutes) && remoteRemainingMinutes >= 0;
        const normalizedRemoteMinutes = hasRemoteMinutes
            ? Math.max(0, Math.ceil(remoteRemainingMinutes))
            : null;
        let endTimestamp = hasRemoteMinutes
            ? Date.now() + (normalizedRemoteMinutes * MINUTE_MS)
            : startTimestamp + countdownMs;

        const render = () => {
            const remainingMinutes = Math.max(0, Math.ceil((endTimestamp - Date.now()) / MINUTE_MS));
            timerValue.textContent = _formatRemainingMinutes(remainingMinutes);
            setCountdownProgress(remainingMinutes);

            if (remainingMinutes === 0) {
                timerContainer.classList.add('finished');
                if (countdownTimerId) {
                    clearInterval(countdownTimerId);
                    countdownTimerId = null;
                }
            } else {
                timerContainer.classList.remove('finished');
            }
        };

        render();
        countdownTimerId = setInterval(() => {
            render();
        }, MINUTE_MS);
    };

    const setPausedUi = (remoteRemainingMinutes = null) => {
        stopTicker();
        timerContainer.classList.remove('waiting', 'finished');
        timerContainer.classList.add('paused');

        if (Number.isFinite(remoteRemainingMinutes) && remoteRemainingMinutes >= 0) {
            timerValue.textContent = _formatRemainingMinutes(remoteRemainingMinutes);
            setCountdownProgress(remoteRemainingMinutes);
        }
    };

    const applyRemoteState = (data) => {
        if (!data || !data.estado) return;
        sesionEstadoActual = data.estado;
        document.dispatchEvent(new CustomEvent('sessionStateChanged', {
            detail: { estado: data.estado },
        }));
        const remoteStarted = data.estado === 'en_curso';
        cronometroPausado = Boolean(data.cronometro_pausado);

        if (data.parada_actual_id != null) {
            _resaltarParadaSeleccionada(String(data.parada_actual_id));
        }

        if (remoteStarted && data.fecha_inicio) {
            const parsedStart = Date.parse(data.fecha_inicio);
            if (Number.isFinite(parsedStart)) startTimestamp = parsedStart;
        }

        if (remoteStarted) {
            sesionIniciada = true;
            if (startBtn) {
                startBtn.disabled = true;
                startBtn.textContent = 'Cronómetro iniciado';
            }
            const remoteMinutes = Number(data.minutos_restantes);
            if (cronometroPausado) {
                setPausedUi(remoteMinutes);
            } else {
                startTicker(remoteMinutes);
            }
        } else {
            sesionIniciada = false;
            cronometroPausado = false;
            setWaitingUi();
            if (startBtn) {
                startBtn.disabled = false;
                startBtn.textContent = 'Iniciar cronómetro';
            }
        }
        setPauseButtonState();
    };

    const fetchCountdownState = () => {
        if (typeof countdownStatusUrl === 'undefined' || !countdownStatusUrl || tourFinalizado) return;
        const separator = countdownStatusUrl.includes('?') ? '&' : '?';
        const liveStatusUrl = `${countdownStatusUrl}${separator}_=${Date.now()}`;
        
        fetch(liveStatusUrl, { cache: 'no-store' })
            .then(r => {
                if ([401, 403, 410].includes(r.status)) {
                    _manejarFinDeTour();
                    return Promise.reject('Fin de sesión');
                }
                return r.ok ? r.json() : Promise.reject();
            })
            .then(data => {
                if (data && data.estado === 'finalizada') {
                    _manejarFinDeTour();
                } else {
                    applyRemoteState(data);
                }
            })
            .catch(() => {});
    };

    if (sesionIniciada) startTicker();
    else setWaitingUi();
    setPauseButtonState();

    fetchCountdownState();
    countdownPollId = setInterval(fetchCountdownState, COUNTDOWN_STATUS_POLL_MS);

    if (startBtn) {
        startBtn.addEventListener('click', () => {
            if (sesionIniciada) return;
            if (typeof startCountdownUrl === 'undefined' || !startCountdownUrl) return;

            startBtn.disabled = true;
            fetch(startCountdownUrl, {
                method: 'POST',
                headers: { 'X-CSRFToken': _getCsrf(), 'Accept': 'application/json' },
            })
                .then(r => r.ok ? r.json() : Promise.reject())
                .then(data => {
                    if (data && data.estado === 'en_curso') {
                        applyRemoteState(data);
                    } else {
                        startBtn.disabled = false;
                    }
                })
                .catch(() => {
                    startBtn.disabled = false;
                });
        });
    }

    if (pauseBtn) {
        pauseBtn.addEventListener('click', () => {
            if (!sesionIniciada || pauseBtnRequestInFlight) return;

            const targetUrl = cronometroPausado ? resumeCountdownUrl : pauseCountdownUrl;
            if (!targetUrl) return;

            pauseBtnRequestInFlight = true;
            setPauseButtonState();

            fetch(targetUrl, {
                method: 'POST',
                headers: { 'X-CSRFToken': _getCsrf(), 'Accept': 'application/json' },
            })
                .then(async (response) => {
                    const data = await response.json().catch(() => ({}));
                    if (!response.ok) {
                        throw new Error(data.error || 'No se pudo actualizar el cronómetro.');
                    }
                    return data;
                })
                .then((data) => {
                    applyRemoteState(data);
                })
                .catch(() => {})
                .finally(() => {
                    pauseBtnRequestInFlight = false;
                    setPauseButtonState();
                });
        });
    }
}

function _formatRemainingMinutes(totalMinutes) {
    const safeMinutes = Number.isFinite(totalMinutes) ? Math.max(0, Math.ceil(totalMinutes)) : 0;
    const hours = Math.floor(safeMinutes / 60);
    const minutes = safeMinutes % 60;
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
}


// ── Chat ───────────────────────────────────────────────────────────────────

function _initChat() {
    const chatMessages = document.getElementById('chat-messages');
    const chatInput    = document.getElementById('chat-input');
    const chatSendBtn  = document.getElementById('chat-send');
    const chatImageBtn = document.getElementById('chat-image-btn');
    const chatImageInput = document.getElementById('chat-image-input');
    const chatPreviewContainer = document.getElementById('chat-preview-container');
    const chatLockedNote = document.getElementById('chat-locked-note');
    if (!chatMessages || !chatInput || !chatSendBtn || !chatImageBtn || !chatImageInput || !chatPreviewContainer) return;

    let lastMessageTime = null;
    let unread          = 0;
    let chatVisible     = false;
    let selectedFile    = null;
    let previewObjectUrl = null;
    const MAX_CHAT_IMAGE_SIZE = 5 * 1024 * 1024;
    const ALLOWED_CHAT_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

    const notifyChat = (message, type = 'warning') => {
        const feedback = window.AuraFeedback;
        if (feedback && typeof feedback.toast === 'function') {
            feedback.toast(message, { type, duration: 3600 });
            return;
        }
        console.warn('[AURA chat]', message);
    };

    document.addEventListener('chatOpened', () => { chatVisible = true; unread = 0; });

    document.addEventListener('chatClosed', () => { chatVisible = false; });

    const escHtml = t => { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; };
    const myName  = () => (typeof currentUserName !== 'undefined' && currentUserName)
        ? currentUserName
        : (document.body.getAttribute('data-username') || '');

    function syncChatAvailability() {
        const enabled = _sesionEnCurso();

        chatInput.disabled = !enabled;
        chatSendBtn.disabled = !enabled;
        chatImageBtn.disabled = !enabled;
        chatInput.placeholder = enabled
            ? 'Escribe un mensaje...'
            : 'El chat se habilita al iniciar el tour';

        if (!enabled) {
            clearPreview();
            chatInput.value = '';
        }

        if (chatLockedNote) {
            chatLockedNote.style.display = enabled ? 'none' : 'block';
        }
    }

    function clearPreview() {
        if (previewObjectUrl) {
            URL.revokeObjectURL(previewObjectUrl);
            previewObjectUrl = null;
        }
        selectedFile = null;
        chatImageInput.value = '';
        chatPreviewContainer.innerHTML = '';
    }

    async function readJsonOrText(response) {
        const raw = await response.text();
        try {
            return raw ? JSON.parse(raw) : null;
        } catch (_error) {
            return { raw };
        }
    }

    function extraerMensajeDeError(payload, fallback) {
        return payload?.error || payload?.mensaje || payload?.detail || fallback;
    }

    function renderPreview(file) {
        if (previewObjectUrl) {
            URL.revokeObjectURL(previewObjectUrl);
        }
        previewObjectUrl = URL.createObjectURL(file);
        chatPreviewContainer.innerHTML = `
            <div class="chat-preview-item">
                <img src="${previewObjectUrl}" alt="Vista previa" class="chat-preview-img">
                <button type="button" class="chat-preview-remove" title="Quitar imagen">
                    <span class="material-icons-round">close</span>
                </button>
            </div>`;

        const removeBtn = chatPreviewContainer.querySelector('.chat-preview-remove');
        if (removeBtn) {
            removeBtn.addEventListener('click', () => {
                clearPreview();
            });
        }
    }

    function _colorFromSender(senderKey, isGuide) {
        if (isGuide) {
            return {
                bg: '#fef3c7',
                border: '#fcd34d',
                sender: '#92400e',
                text: '#111827',
            };
        }

        const key = String(senderKey || 'Participante');
        let hash = 0;
        for (let i = 0; i < key.length; i += 1) {
            hash = ((hash * 33) ^ key.charCodeAt(i)) >>> 0;
        }

        const palette = [
            { bg: '#fee2e2', border: '#fca5a5', sender: '#b91c1c', text: '#111827' },
            { bg: '#ffedd5', border: '#fdba74', sender: '#c2410c', text: '#111827' },
            { bg: '#ecfccb', border: '#bef264', sender: '#3f6212', text: '#111827' },
            { bg: '#cffafe', border: '#67e8f9', sender: '#155e75', text: '#111827' },
            { bg: '#e0f2fe', border: '#7dd3fc', sender: '#075985', text: '#111827' },
            { bg: '#ede9fe', border: '#a78bfa', sender: '#5b21b6', text: '#111827' },
            { bg: '#fce7f3', border: '#f9a8d4', sender: '#9d174d', text: '#111827' },
            { bg: '#e2e8f0', border: '#94a3b8', sender: '#334155', text: '#111827' },
        ];

        return palette[hash % palette.length];
    }

    function renderMessages(msgs) {
        if (!msgs || !msgs.length) return;
        chatMessages.querySelector('.chat-empty')?.remove();
        const me = myName();

        msgs.forEach(msg => {
            if (chatMessages.querySelector(`[data-message-id="${msg.id}"]`)) return;
            lastMessageTime = msg.momento;

            const div = document.createElement('div');
            div.className = `chat-message ${msg.nombre_remitente === me ? 'sent' : 'received'}`;
            div.setAttribute('data-message-id', msg.id);

            const senderKey = msg.remitente_key || msg.nombre_remitente;
            const senderColors = _colorFromSender(senderKey, Boolean(msg.es_guia));
            div.style.setProperty('--msg-bg', senderColors.bg);
            div.style.setProperty('--msg-border', senderColors.border);
            div.style.setProperty('--msg-sender', senderColors.sender);
            div.style.setProperty('--msg-text', senderColors.text);

            const t = new Date(msg.momento).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
            const textoHtml = msg.texto ? escHtml(msg.texto) : '';
            const imagenHtml = msg.imagen_url
                ? `<a class="chat-image-link" href="/tours/sesiones/${sesionId}/mensajes/${msg.id}/imagen/" title="Descargar imagen">
                        <img src="${escHtml(msg.imagen_url)}" class="chat-message-img" alt="Imagen adjunta del chat">
                   </a>`
                : '';
            const bubbleHtml = textoHtml ? `<div class="chat-message-bubble">${textoHtml}</div>` : '';

            div.innerHTML = `
                <div class="chat-message-header">
                    <span class="chat-message-sender">${escHtml(msg.nombre_remitente)}</span>
                    <span class="chat-message-time">${t}</span>
                </div>
                ${bubbleHtml}
                ${imagenHtml}`;
            chatMessages.appendChild(div);

            if (msg.nombre_remitente !== me && !chatVisible) {
                unread++;
                const badge = document.getElementById('chat-badge');
                if (badge) { badge.textContent = unread > 99 ? '99+' : unread; badge.style.display = 'block'; }
            }
        });
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function fetchMessages() {
        if (tourFinalizado) return;
        let url = `/tours/sesiones/${sesionId}/mensajes/`;
        if (lastMessageTime) {
            try { url += `?desde=${encodeURIComponent(new Date(lastMessageTime).toISOString())}`; }
            catch { url += `?desde=${encodeURIComponent(lastMessageTime)}`; }
        }

        fetch(url)
            .then(r => {
                if ([401, 403, 410].includes(r.status)) {
                    _manejarFinDeTour(); return Promise.reject('Fin de sesión');
                }
                return r.ok ? r.json() : Promise.reject();
            })
            .then(data => {
                if (data && data.estado_sesion) {
                    if (data.estado_sesion === 'finalizada') {
                        _manejarFinDeTour();
                        return;
                    }
                    sesionEstadoActual = data.estado_sesion;
                    document.dispatchEvent(new CustomEvent('sessionStateChanged', {
                        detail: { estado: data.estado_sesion },
                    }));
                }
                renderMessages(data.mensajes || data);
            })
            .catch(() => {});
    }

    function sendMessage() {
        if (!_sesionEnCurso()) return;

        const texto = chatInput.value.trim();
        if (!texto && !selectedFile) {
            notifyChat('El mensaje no puede estar vacío.', 'warning');
            return;
        }

        chatSendBtn.disabled = chatInput.disabled = chatImageBtn.disabled = true;

        const payload = new FormData();
        payload.append('texto', texto);
        if (selectedFile) {
            payload.append('imagen', selectedFile);
        }

        fetch(`/tours/sesiones/${sesionId}/mensajes/enviar/`, {
            method:  'POST',
            headers: { 'X-CSRFToken': _getCsrf() },
            body:    payload,
        })
        .then(async (r) => {
            const data = await readJsonOrText(r);
            if (!r.ok || data?.status !== 'ok') {
                throw new Error(extraerMensajeDeError(data, 'No se pudo enviar el mensaje.'));
            }

            chatInput.value = '';
            clearPreview();
            fetchMessages();
        })
        .catch((error) => {
            notifyChat(error?.message || 'No se pudo enviar el mensaje.', 'error');
        })
        .finally(() => {
            chatSendBtn.disabled = chatInput.disabled = chatImageBtn.disabled = false;
            chatInput.focus();
        });
    }

    chatSendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', e => { if (e.key === 'Enter') sendMessage(); });
    chatImageBtn.addEventListener('click', () => chatImageInput.click());
    chatImageInput.addEventListener('change', () => {
        if (!chatImageInput.files || !chatImageInput.files.length) {
            clearPreview();
            return;
        }

        const file = chatImageInput.files[0];
        if (!ALLOWED_CHAT_IMAGE_TYPES.has(file.type)) {
            notifyChat('Formato de imagen no permitido. Usa JPEG, PNG o WebP.', 'warning');
            clearPreview();
            return;
        }

        if (file.size > MAX_CHAT_IMAGE_SIZE) {
            notifyChat('La imagen supera el tamaño máximo de 5MB.', 'warning');
            clearPreview();
            return;
        }

        selectedFile = file;
        renderPreview(file);
    });

    fetchMessages();
    chatPollId = setInterval(fetchMessages, 5000);

    document.addEventListener('sessionStateChanged', () => {
        syncChatAvailability();
    });

    syncChatAvailability();
}


function _initRecordatorios() {
    const recordatoriosEnabled = (typeof scheduledMeetupEnabled === 'undefined')
        ? true
        : Boolean(scheduledMeetupEnabled);
    if (!recordatoriosEnabled) return;

    const listEl = document.getElementById('recordatorios-list');
    if (!listEl) return;

    const horaInput = document.getElementById('recordatorio-hora');
    const avisarInput = document.getElementById('recordatorio-avisar');
    const mensajeInput = document.getElementById('recordatorio-mensaje');
    const crearBtn = document.getElementById('recordatorio-crear-btn');
    const feedbackEl = document.getElementById('recordatorio-feedback');
    const badgeEl = document.getElementById('recordatorios-badge');

    let unreadAlerts = 0;
    let tabVisible = false;
    const alertasActivasPorId = new Map();
    let ultimoRecordatorios = [];

    document.addEventListener('recordatoriosOpened', () => {
        tabVisible = true;
        unreadAlerts = 0;
        if (badgeEl) badgeEl.style.display = 'none';
    });

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            tabVisible = btn.getAttribute('data-tab') === 'notificaciones';
        });
    });

    const tabBtn = document.querySelector('[data-tab="notificaciones"]');
    if (tabBtn && tabBtn.classList.contains('active')) {
        tabVisible = true;
    }

    function showFeedback(msg, isError) {
        if (!feedbackEl) return;
        feedbackEl.textContent = msg || '';
        feedbackEl.classList.toggle('error', Boolean(isError));
        feedbackEl.classList.toggle('ok', !isError && Boolean(msg));
    }

    function formatDate(isoDate) {
        try {
            return new Date(isoDate).toLocaleString('es-ES', {
                day: '2-digit',
                month: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
            });
        } catch {
            return 'Fecha inválida';
        }
    }

    function formatHour(isoDate) {
        try {
            return new Date(isoDate).toLocaleTimeString('es-ES', {
                hour: '2-digit',
                minute: '2-digit',
            });
        } catch {
            return '--:--';
        }
    }

    function clearExpiredActiveAlerts() {
        const nowMs = Date.now();
        Array.from(alertasActivasPorId.entries()).forEach(([id, alerta]) => {
            const endMs = Date.parse(alerta?.hora_objetivo || '');
            if (!Number.isFinite(endMs) || endMs <= nowMs) {
                alertasActivasPorId.delete(id);
            }
        });
    }

    function renderRecordatorios(recordatorios) {
        clearExpiredActiveAlerts();

        if (!Array.isArray(recordatorios) || !recordatorios.length) {
            listEl.innerHTML = `
                <div class="chat-empty">
                    <span class="material-icons-round">notifications_none</span>
                    <p>Aún no hay recordatorios</p>
                </div>`;
            return;
        }

        listEl.innerHTML = '';
        recordatorios.forEach(item => {
            const card = document.createElement('article');
            const itemId = String(item.id);
            const alertaActiva = alertasActivasPorId.has(itemId);
            card.className = `recordatorio-item ${alertaActiva ? 'recordatorio-item-alerta' : ''}`;

            const chipTexto = alertaActiva
                ? `ALERTA HASTA ${formatHour(item.hora_objetivo)}`
                : `${item.avisar_minutos_antes} min antes`;

            card.innerHTML = `
                <div class="recordatorio-item-head">
                    <span class="recordatorio-chip">${_escapeHtml(chipTexto)}</span>
                    <span class="recordatorio-time">${_escapeHtml(formatDate(item.hora_objetivo))}</span>
                </div>
                <p class="recordatorio-text">${_escapeHtml(item.mensaje)}</p>
            `;
            listEl.appendChild(card);
        });
    }

    function pollRecordatorios() {
        if (typeof recordatoriosUrl === 'undefined' || !recordatoriosUrl) return;
        fetch(recordatoriosUrl)
            .then(r => r.ok ? r.json() : Promise.reject())
            .then(data => {
                ultimoRecordatorios = data.recordatorios || [];
                renderRecordatorios(ultimoRecordatorios);
            })
            .catch(() => {});
    }

    async function playReminderSound() {
        try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (!AudioCtx) return;
            const context = new AudioCtx();

            const beep = (startAt, freq) => {
                const osc = context.createOscillator();
                const gain = context.createGain();
                osc.type = 'sine';
                osc.frequency.value = freq;
                gain.gain.setValueAtTime(0.0001, startAt);

                gain.gain.exponentialRampToValueAtTime(0.8, startAt + 0.02); 
                gain.gain.exponentialRampToValueAtTime(0.0001, startAt + 0.3);
                
                osc.connect(gain);
                gain.connect(context.destination);
                osc.start(startAt);
                osc.stop(startAt + 0.32);
            };

            const now = context.currentTime;
            
            for (let i = 0; i < 7; i++) {
                let offset = i * 1.2; 
                beep(now + offset, 880);
                beep(now + offset + 0.35, 660);
                beep(now + offset + 0.7, 880);
            }

            setTimeout(() => {
                context.close().catch(() => {});
            }, 4500); 
            
        } catch {
            return;
        }
    }

    function notifyBrowser(alerta) {
        const title = 'Recordatorio del guía';
        const body = alerta.mensaje || 'Tienes un nuevo recordatorio';

        if (!('Notification' in window)) return;
        if (Notification.permission === 'granted') {
            new Notification(title, { body });
            return;
        }
        if (Notification.permission !== 'denied') {
            Notification.requestPermission().then(permission => {
                if (permission === 'granted') {
                    new Notification(title, { body });
                }
            }).catch(() => {});
        }
    }

    function pollAlertasTurista() {
        if (esGuia) return;
        if (typeof recordatoriosAlertasUrl === 'undefined' || !recordatoriosAlertasUrl) return;

        fetch(recordatoriosAlertasUrl)
            .then(r => r.ok ? r.json() : Promise.reject())
            .then(data => {
                const alertas = data.alertas || [];
                if (!alertas.length) return;

                alertas.forEach(alerta => {
                    alertasActivasPorId.set(String(alerta.id), alerta);
                    notifyBrowser(alerta);
                });

                renderRecordatorios(ultimoRecordatorios);

                playReminderSound();

                if (!tabVisible) {
                    unreadAlerts += alertas.length;
                    if (badgeEl) {
                        badgeEl.textContent = unreadAlerts > 99 ? '99+' : String(unreadAlerts);
                        badgeEl.style.display = 'block';
                    }
                }
            })
            .catch(() => {});
    }

    function createRecordatorio() {
        if (!esGuia || !crearBtn) return;

        const hora = horaInput ? horaInput.value : '';
        const mensaje = mensajeInput ? mensajeInput.value.trim() : '';
        const avisar = avisarInput ? avisarInput.value : '10';

        if (!hora) {
            showFeedback('Debes indicar la hora objetivo.', true);
            return;
        }
        if (!mensaje) {
            showFeedback('Debes escribir un mensaje para el recordatorio.', true);
            return;
        }

        const payload = {
            hora_objetivo: new Date(hora).toISOString(),
            avisar_minutos_antes: Number(avisar || '10'),
            mensaje,
        };

        crearBtn.disabled = true;
        showFeedback('Creando recordatorio...', false);

        fetch(recordatoriosUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': _getCsrf(),
            },
            body: JSON.stringify(payload),
        })
            .then(async r => {
                const data = await r.json().catch(() => ({}));
                if (!r.ok) {
                    throw new Error(data.error || 'No se pudo crear el recordatorio.');
                }
                return data;
            })
            .then(() => {
                if (mensajeInput) mensajeInput.value = '';
                showFeedback('Recordatorio creado correctamente.', false);
                pollRecordatorios();
            })
            .catch(err => {
                showFeedback(err.message || 'No se pudo crear el recordatorio.', true);
            })
            .finally(() => {
                crearBtn.disabled = false;
            });
    }

    if (crearBtn) {
        crearBtn.addEventListener('click', createRecordatorio);
    }

    pollRecordatorios();
    setInterval(pollRecordatorios, 15000);
    setInterval(pollAlertasTurista, 10000);
}


function _obtenerUbicacionesTuristas() {
    if (!map || !esGuia || tourFinalizado) return;

    fetch(`/tours/sesiones/${sesionId}/ubicaciones_turistas/`)
        .then(r => { 
            if ([401, 403, 410].includes(r.status)) {
                _manejarFinDeTour(); throw new Error('Fin');
            }
            if (!r.ok) throw new Error(); 
            return r.json(); 
        })
        .then(data => _renderizarTuristasEnMapa(data.turistas || []))
        .catch(() => {});
}


function _renderizarTuristasEnMapa(turistas) {
    const visibles = new Set();

    turistas.forEach(turista => {
        if (typeof turista.lat !== 'number' || typeof turista.lng !== 'number') return;

        const key = String(turista.turista_id);
        visibles.add(key);
        const pos = [turista.lat, turista.lng];

        let marker = turistasMarkers.get(key);
        if (!marker) {
            marker = L.marker(pos, {
                icon: L.divIcon({
                    className: '',
                    html: `<div style="
                            background:#0ea5e9;width:24px;height:24px;
                            border-radius:50%;border:2px solid white;
                            box-shadow:0 2px 8px rgba(14,165,233,.45);
                            display:flex;align-items:center;justify-content:center;
                            color:white;font-size:12px;font-weight:700;">T</div>`,
                    iconSize: [24, 24],
                    iconAnchor: [12, 12],
                }),
                zIndexOffset: 850,
            }).addTo(map);
            turistasMarkers.set(key, marker);
        } else {
            marker.setLatLng(pos);
        }

        marker.bindPopup(`Turista: ${turista.alias || 'Anónimo'}`);
    });

    Array.from(turistasMarkers.keys()).forEach(key => {
        if (visibles.has(key)) return;
        const marker = turistasMarkers.get(key);
        if (marker) {
            map.removeLayer(marker);
            turistasMarkers.delete(key);
        }
    });
}

function _initParadaFocusButtons() {
    const focusButtons = document.querySelectorAll('.parada-focus-btn');
    if (!focusButtons.length) return;

    focusButtons.forEach(button => {
        button.addEventListener('click', async () => {
            const paradaId = button.getAttribute('data-parada-id');
            if (!paradaId || !map) return;

            if (typeof selectCurrentStopUrl === 'undefined' || !selectCurrentStopUrl) return;

            button.disabled = true;
            try {
                const response = await fetch(selectCurrentStopUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': _getCsrf(),
                    },
                    body: JSON.stringify({ parada_id: Number.parseInt(paradaId, 10) }),
                });

                if (!response.ok) throw new Error('No se pudo actualizar la parada actual.');

                _resaltarParadaSeleccionada(paradaId);
            } catch {
                return;
            } finally {
                button.disabled = false;
            }

            const marker = paradasMarkers.get(paradaId);
            if (marker) {
                const pos = marker.getLatLng();
                map.flyTo([pos.lat, pos.lng], Math.max(map.getZoom(), 16), { duration: 0.6 });
                marker.openPopup();
                return;
            }

            const parada = paradasDataById.get(paradaId)
                || (Array.isArray(paradasData) ? paradasData.find(item => String(item.id) === paradaId) : null);

            if (!parada || parada.lat == null || parada.lng == null) return;

            map.flyTo([parada.lat, parada.lng], Math.max(map.getZoom(), 16), { duration: 0.6 });
        });
    });
}

function _initMostrarCuriosidadButtons() {
    const curiosidadButtons = document.querySelectorAll('.mostrar-curiosidad-btn');
    if (!curiosidadButtons.length) return;

    curiosidadButtons.forEach(button => {
        button.addEventListener('click', async () => {
            const paradaId = button.getAttribute('data-parada-id');
            if (!paradaId) return;

            const popupParadaId = curiosidadPopupActual?.getContent?.()?.getAttribute?.('data-parada-id');
            if (curiosidadPopupActual && popupParadaId === String(paradaId)) {
                button.disabled = true;
                try {
                    await _setCuriosidadVisibilityOnServer(paradaId, false);
                    _cerrarCuriosidadVisible();
                    _syncCuriosidadButtons(null);
                } catch {
                    return;
                } finally {
                    button.disabled = false;
                }
                return;
            }

            button.disabled = true;
            try {
                const response = await fetch(`/tours/sesiones/${sesionId}/paradas/${paradaId}/curiosidad/?solo_existente=1`, {
                    method: 'GET',
                    headers: { 'Accept': 'application/json' },
                });

                if (!response.ok) {
                    _setCuriosidadButtonLabel(paradaId, 'Mostrar curiosidad');
                    return;
                }

                const payload = await response.json();
                if (!payload?.curiosidad) {
                    _setCuriosidadButtonLabel(paradaId, 'Mostrar curiosidad');
                    _flashCuriosidadButtonLabel(paradaId, 'Sin curiosidad', 'Mostrar curiosidad');
                    return;
                }

                await _setCuriosidadVisibilityOnServer(paradaId, true);
                curiosidadesMostradas.add(String(paradaId));
                _mostrarCuriosidadAutomatica(payload.parada, payload.curiosidad);
                _syncCuriosidadButtons(_parseParadaId(paradaId));
            } catch {
                _setCuriosidadButtonLabel(paradaId, 'Mostrar curiosidad');
            } finally {
                button.disabled = false;
            }
        });
    });
}

function _resaltarParadaSeleccionada(paradaId) {
    if (!paradaId) return;

    if (paradaSeleccionadaId && paradaSeleccionadaId !== paradaId) {
        const previousMarker = paradasMarkers.get(paradaSeleccionadaId);
        const previousParada = paradasDataById.get(paradaSeleccionadaId);
        
        if (previousMarker && previousParada) {
            const previousRole = paradasRole.get(paradaSeleccionadaId) || null;
            previousMarker.setIcon(_buildParadaIcon(previousParada, false, previousRole));
            previousMarker.setZIndexOffset(0);
        }
    }

    // Sincroniza el estado visual del itinerario para todos los usuarios.
    document.querySelectorAll('.timeline-item').forEach(item => {
        item.classList.remove('active', 'selected-stop');
        const stopName = item.querySelector('.timeline-stop-name');
        if (stopName) stopName.classList.add('text-muted');
        const liveBadge = item.querySelector('.timeline-stop-live-badge');
        if (liveBadge) liveBadge.classList.add('d-none');
    });

    document.querySelectorAll('.timeline-item.selected-stop').forEach(item => {
        item.classList.remove('selected-stop');
    });

    const marker = paradasMarkers.get(paradaId);
    const parada = paradasDataById.get(paradaId);

    if (marker && parada) {
        const role = paradasRole.get(paradaId) || null;
        marker.setIcon(_buildParadaIcon(parada, true, role));
        marker.setZIndexOffset(1200);
    }

    const timelineItem = document.querySelector(`.timeline-item[data-parada-id="${paradaId}"]`);
    if (timelineItem) {
        timelineItem.classList.add('active');
        timelineItem.classList.add('selected-stop');
        const stopName = timelineItem.querySelector('.timeline-stop-name');
        if (stopName) stopName.classList.remove('text-muted');
        const liveBadge = timelineItem.querySelector('.timeline-stop-live-badge');
        if (liveBadge) liveBadge.classList.remove('d-none');
    }

    document.querySelectorAll('.parada-focus-btn').forEach(btn => {
        const btnParadaId = btn.getAttribute('data-parada-id');
        const isSelected = btnParadaId === paradaId;
        btn.textContent = isSelected ? 'Parada actual seleccionada' : 'Seleccionar parada actual';
        btn.classList.toggle('is-selected', isSelected);
    });

    paradaSeleccionadaId = paradaId;
}

function _buildPopupTour(parada, role) {
    let badge = '';
    if (role === 'origin') {
        badge = ' <span style="display:inline-block;background:#16a34a;color:#fff;font-size:10px;font-weight:700;padding:1px 6px;border-radius:10px;letter-spacing:.3px;vertical-align:middle;">INICIO</span>';
    } else if (role === 'destination') {
        badge = ' <span style="display:inline-block;background:#dc2626;color:#fff;font-size:10px;font-weight:700;padding:1px 6px;border-radius:10px;letter-spacing:.3px;vertical-align:middle;">FIN</span>';
    }
    return `<strong>${parada.nombre}${badge}</strong><br><span style="color:#6b7280;font-size:.8rem;">Parada ${parada.orden}</span>`;
}

function _buildParadaIcon(parada, highlighted = false, role = null) {
    return window.buildAuraMarkerIcon(parada, {
        highlighted: highlighted,
        role: role,
        esActual: Boolean(parada && parada.es_actual)
    });
}


// ── Botón de centrado del mapa ─────────────────────────────────────────────

function _centro_primera_parada() {
    if (!map || primeraParadaCentrada) return;
    if (!Array.isArray(paradasData) || paradasData.length === 0) return;

    const existePrimera = paradasData[0];
    if (!existePrimera || existePrimera.lat == null || existePrimera.lng == null) return;

    const pos = [existePrimera.lat, existePrimera.lng];
    map.flyTo(pos, 15, { duration: 0.8 });
    primeraParadaCentrada = true;
}

function _initBotónCentraMapa() {
    const btn = document.getElementById('btn-centrar-mapa');
    if (!btn || !map) return;

    const actualizar_texto = () => {
        const textos = {
            [CENTRADO_STATES.TURISTA]: 'En tu ubicación',
            [CENTRADO_STATES.GUIA]: 'En el guía',
            [CENTRADO_STATES.PARADA]: 'En la parada actual',
        };
        btn.setAttribute('title', textos[estadoCentradoActual] || 'Centrar mapa');
    };

    actualizar_texto();

    btn.addEventListener('click', () => {
        // Rotar a través de los tres estados
        const estados_secuencia = [
            CENTRADO_STATES.TURISTA,
            CENTRADO_STATES.GUIA,
            CENTRADO_STATES.PARADA,
        ];

        const indice_actual = estados_secuencia.indexOf(estadoCentradoActual);
        const indice_siguiente = (indice_actual + 1) % estados_secuencia.length;
        estadoCentradoActual = estados_secuencia[indice_siguiente];

        // Ejecutar centrado según el estado
        switch (estadoCentradoActual) {
            case CENTRADO_STATES.TURISTA:
                _centrar_en_turista();
                break;
            case CENTRADO_STATES.GUIA:
                _centrar_en_guia();
                break;
            case CENTRADO_STATES.PARADA:
                _centrar_en_parada_actual();
                break;
        }

        actualizar_texto();
    });
}

function _centrar_en_turista() {
    if (!map || !miUbicacionMarker) {
        if (ultimaPosicionTurista) {
            map.flyTo([ultimaPosicionTurista.lat, ultimaPosicionTurista.lng], Math.max(map.getZoom(), 16), { duration: 0.6 });
            return;
        }

        console.warn('No se puede centrar: posición del turista no disponible');
        return;
    }

    const pos = miUbicacionMarker.getLatLng();
    map.flyTo([pos.lat, pos.lng], Math.max(map.getZoom(), 16), { duration: 0.6 });
}

function _centrar_en_guia() {
    if (!map) return;

    // Si estoy en guía, centrar en mi posición
    if (esGuia) {
        if (!miUbicacionMarker) {
            console.warn('No se puede centrar: posición del guía no disponible');
            return;
        }
        const pos = miUbicacionMarker.getLatLng();
        map.flyTo([pos.lat, pos.lng], Math.max(map.getZoom(), 16), { duration: 0.6 });
    } else {
        // Si soy turista, centrar en el marcador del guía
        if (!guiaMarker) {
            console.warn('No se puede centrar: posición del guía no disponible aún');
            return;
        }
        const pos = guiaMarker.getLatLng();
        map.flyTo([pos.lat, pos.lng], Math.max(map.getZoom(), 16), { duration: 0.6 });
    }
}

function _centrar_en_parada_actual() {
    if (!map) return;

    // Si hay una parada seleccionada, centrar en ella
    if (paradaSeleccionadaId) {
        const marker = paradasMarkers.get(paradaSeleccionadaId);
        if (marker) {
            const pos = marker.getLatLng();
            map.flyTo([pos.lat, pos.lng], Math.max(map.getZoom(), 16), { duration: 0.6 });
            return;
        }

        // Si no hay marcador visual, buscar en los datos
        const parada = paradasDataById.get(paradaSeleccionadaId);
        if (parada && parada.lat != null && parada.lng != null) {
            map.flyTo([parada.lat, parada.lng], Math.max(map.getZoom(), 16), { duration: 0.6 });
            return;
        }
    }

    // Si no hay parada seleccionada, centrar en la primera parada
    if (Array.isArray(paradasData) && paradasData.length > 0) {
        const primera = paradasData[0];
        if (primera && primera.lat != null && primera.lng != null) {
            map.flyTo([primera.lat, primera.lng], Math.max(map.getZoom(), 16), { duration: 0.6 });
            return;
        }
    }

    console.warn('No hay parada actual para centrar');
}
