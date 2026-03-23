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
let followMeMode = false;
let routeBounds = null;
        const origin = lastKnownPosition
            ? `${lastKnownPosition.lat},${lastKnownPosition.lng}`
            : null;
        const mapsUrl = _buildExternalMapUrl(destination, origin);
        timerContainer.classList.remove('waiting');
        countdownTimerId = null;
let lastKnownPosition = null;
let latestSessionSummary = null;
let isIOSDevice = false;

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

    isIOSDevice = _detectIOSDevice();

    // Tiles minimalistas: fondo neutro claro donde la polilínea y los marcadores
    // destacan sin competir con texturas de satélite.
    const token = typeof mapboxToken !== 'undefined' ? mapboxToken : '';
    const tileUrl = token
        ? `https://api.mapbox.com/styles/v1/mapbox/light-v11/tiles/256/{z}/{x}/{y}@2x?access_token=${token}`
        : 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';

    const baseLayer = L.tileLayer(tileUrl, {
        maxZoom:     19,
        attribution: token
            ? '© <a href="https://mapbox.com">Mapbox</a> © <a href="https://openstreetmap.org">OpenStreetMap</a>'
            : '© <a href="https://carto.com">CARTO</a> © <a href="https://openstreetmap.org">OpenStreetMap</a>',
    }).addTo(map);

    let hasTileFallback = false;
    baseLayer.on('tileerror', () => {
        if (hasTileFallback || !map || !token) return;
        hasTileFallback = true;
        map.removeLayer(baseLayer);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            maxZoom: 19,
            attribution: '© <a href="https://carto.com">CARTO</a> © <a href="https://openstreetmap.org">OpenStreetMap</a>',
        }).addTo(map);
    });

    L.control.zoom({ position: 'bottomright' }).addTo(map);

    // iOS Safari puede calcular mal el tamaño inicial del mapa con barras dinámicas.
    const refreshMapSize = () => {
        if (!map) return;
        map.invalidateSize({ pan: false, animate: false });
    };
    window.setTimeout(refreshMapSize, 120);
    window.addEventListener('resize', refreshMapSize);
    window.addEventListener('orientationchange', () => window.setTimeout(refreshMapSize, 180));

    // ── Dibujar recorrido y paradas ───────────────────────────────────────
    _dibujarRutaYParadas();
    _initParadaFocusButtons();
    _initMapActionControls();
    _initSessionSummaryPanel();


    // ── Posición propia ───────────────────────────────────────────────────
    _iniciarRastreoLocal();

    // ── Polling de posiciones en vivo ──────────────────────────────────────
    if (!esGuia) {
        _obtenerUbicacionGuia();
        setInterval(_obtenerUbicacionGuia, 5000);
    } else {
        _obtenerUbicacionesTuristas();
        setInterval(_obtenerUbicacionesTuristas, 5000);
    }

    // ── Panel expandible ──────────────────────────────────────────────────
    const panelHeader = document.querySelector('.panel-header');
    const tourPanel   = document.querySelector('.tour-panel');
    if (panelHeader && tourPanel) {
        _initDraggableTourPanel(tourPanel, panelHeader);
    }

    // ── Tabs Itinerario / Chat ─────────────────────────────────────────────
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const target = this.getAttribute('data-tab');
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            this.classList.add('active');
            const targetContent = document.getElementById('tab-' + target);
            if (targetContent) targetContent.classList.add('active');
            if (target === 'chat') {
                const badge = document.getElementById('chat-badge');
                if (badge) badge.style.display = 'none';
                document.dispatchEvent(new CustomEvent('chatOpened'));
            }
        });
    });

    // ── Chat ──────────────────────────────────────────────────────────────
    _initSessionCountdown();
    _initChat();
});


// ── Dibujar recorrido y marcadores ─────────────────────────────────────────

function _dibujarRutaYParadas() {

    // 1. Polilínea del recorrido real (geometría calculada por GraphHopper, guardada en BD)
    //    `geometriaRuta` se inyecta desde el template como [[lat,lon],...] o null.
    if (typeof geometriaRuta !== 'undefined' && geometriaRuta && geometriaRuta.length >= 2) {
        const routeLine = L.polyline(geometriaRuta, {
            color:        '#4f46e5',   // índigo — color primario de AURA
            weight:       4,
            opacity:      0.75,
            smoothFactor: 1,
        }).addTo(map);

        routeBounds = routeLine.getBounds();
        map.fitBounds(routeBounds, { padding: [48, 48] });
    }

    if (typeof paradasData === 'undefined' || !Array.isArray(paradasData)) return;

    const bounds = [];

    paradasData.forEach(parada => {
        if (parada.lat == null || parada.lng == null) return;

        bounds.push([parada.lat, parada.lng]);

        const marker = L.marker([parada.lat, parada.lng], {
            icon: _buildParadaIcon(parada),
        })
        .addTo(map)
        .bindPopup(
            `<strong>${parada.nombre}</strong>` +
            `<br><span style="color:#6b7280;font-size:.8rem;">Parada ${parada.orden}</span>`
        );

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

        routeBounds = bounds.length === 1
            ? L.latLngBounds([bounds[0], bounds[0]])
            : L.latLngBounds(bounds);
    }
}


function _detectIOSDevice() {
    const ua = navigator.userAgent || '';
    const isClassicIOS = /iPad|iPhone|iPod/i.test(ua);
    const isIPadOS = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;
    return isClassicIOS || isIPadOS;
}


function _initDraggableTourPanel(tourPanel, panelHeader) {
    if (!tourPanel || !panelHeader) return;

    const getLimits = () => {
        const vh = window.innerHeight || document.documentElement.clientHeight || 800;
        const collapsed = Math.round(Math.max(240, Math.min(vh * 0.36, 360)));
        const expanded = Math.round(Math.max(420, Math.min(vh * 0.88, vh - 14)));
        return {
            collapsed,
            expanded: Math.max(expanded, collapsed + 120),
        };
    };

    const clamp = (value, min, max) => Math.max(min, Math.min(value, max));

    let limits = getLimits();
    let currentHeight = limits.collapsed;
    let dragging = false;
    let moved = false;
    let startY = 0;
    let startHeight = limits.collapsed;

    const applyHeight = (height, withTransition) => {
        currentHeight = clamp(height, limits.collapsed, limits.expanded);
        tourPanel.style.transition = withTransition ? 'height 220ms cubic-bezier(0.22, 1, 0.36, 1)' : 'none';
        tourPanel.style.height = `${Math.round(currentHeight)}px`;
        tourPanel.classList.toggle('expanded', currentHeight > (limits.collapsed + limits.expanded) / 2);
    };

    const expand = () => applyHeight(limits.expanded, true);
    const collapse = () => applyHeight(limits.collapsed, true);

    applyHeight(currentHeight, false);

    panelHeader.addEventListener('pointerdown', event => {
        dragging = true;
        moved = false;
        startY = event.clientY;
        startHeight = currentHeight;
        tourPanel.style.willChange = 'height';
        panelHeader.setPointerCapture(event.pointerId);
    });

    panelHeader.addEventListener('pointermove', event => {
        if (!dragging) return;
        const delta = startY - event.clientY;
        if (Math.abs(delta) > 3) moved = true;
        const nextHeight = clamp(startHeight + delta, limits.collapsed, limits.expanded);
        applyHeight(nextHeight, false);
    });

    const endDrag = () => {
        if (!dragging) return;
        dragging = false;
        tourPanel.style.willChange = '';

        if (!moved) {
            if (tourPanel.classList.contains('expanded')) collapse();
            else expand();
            return;
        }

        const threshold = (limits.collapsed + limits.expanded) / 2;
        if (currentHeight >= threshold) expand();
        else collapse();
    };

    panelHeader.addEventListener('pointerup', endDrag);
    panelHeader.addEventListener('pointercancel', endDrag);

        // Fallback para Safari iOS que puede no disparar Pointer Events de forma fiable.
        panelHeader.addEventListener('touchstart', event => {
            const touch = event.touches && event.touches[0];
            if (!touch) return;
            dragging = true;
            moved = false;
            startY = touch.clientY;
            startHeight = currentHeight;
            tourPanel.style.willChange = 'height';
        }, { passive: true });

        panelHeader.addEventListener('touchmove', event => {
            if (!dragging) return;
            const touch = event.touches && event.touches[0];
            if (!touch) return;
            const delta = startY - touch.clientY;
            if (Math.abs(delta) > 3) moved = true;
            const nextHeight = clamp(startHeight + delta, limits.collapsed, limits.expanded);
            applyHeight(nextHeight, false);
        }, { passive: true });

        panelHeader.addEventListener('touchend', endDrag, { passive: true });
        panelHeader.addEventListener('touchcancel', endDrag, { passive: true });

    window.addEventListener('resize', () => {
        limits = getLimits();
        applyHeight(currentHeight, false);
    });
}


function _buildExternalMapUrl(destination, origin) {
    const destinationParam = encodeURIComponent(destination);

    if (isIOSDevice) {
        const originParam = origin ? `&saddr=${encodeURIComponent(origin)}` : '';
        return `https://maps.apple.com/?daddr=${destinationParam}${originParam}&dirflg=w`;
    }

    const originParam = origin ? `&origin=${encodeURIComponent(origin)}` : '';
    return `https://www.google.com/maps/dir/?api=1&destination=${destinationParam}${originParam}&travelmode=walking`;
}


// ── Posición propia (punto pulsante) ───────────────────────────────────────

function _iniciarRastreoLocal() {
    if (!navigator.geolocation) return;

    navigator.geolocation.watchPosition(
        position => {
            const { latitude: lat, longitude: lng } = position.coords;
            const pos = [lat, lng];

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

            lastKnownPosition = { lat, lng };
            _renderNavigationMetrics();

            if (followMeMode && map) {
                map.flyTo(pos, Math.max(map.getZoom(), 16), { duration: 0.5 });
            }

            // El guía envía su posición al servidor para que los turistas la vean
            if (esGuia) {
                fetch('/tours/ubicacion/', {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _getCsrf() },
                    body:    JSON.stringify({ latitud: lat, longitud: lng, sesion_id: sesionId }),
                }).catch(() => {});
            } else {
                fetch(`/tours/sesiones/${sesionId}/ubicacion_turista/`, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _getCsrf() },
                    body:    JSON.stringify({ latitud: lat, longitud: lng }),
                }).catch(() => {});
            }
        },
        () => {},
        { enableHighAccuracy: true, maximumAge: 0, timeout: 6000 },
    );
}


// ── Posición del guía (solo turistas) ─────────────────────────────────────

function _obtenerUbicacionGuia() {
    if (!map) return;

    fetch(`/tours/sesiones/${sesionId}/ubicacion_guia/`)
        .then(r => { if (!r.ok) throw new Error(); return r.json(); })
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


// ── Cronómetro de sesión ──────────────────────────────────────────────────

function _initSessionCountdown() {
    const timerContainer = document.getElementById('session-countdown');
    const timerValue = document.getElementById('session-countdown-time');
    const startBtn = document.getElementById('start-countdown-btn');
    if (!timerContainer || !timerValue) return;

    const horasBase = (typeof duracionRutaHoras !== 'undefined' && Number.isFinite(duracionRutaHoras) && duracionRutaHoras > 0)
        ? duracionRutaHoras
        : 1;
    const countdownMs = Math.round(horasBase * 60 * 60 * 1000);
    let sesionIniciada = (typeof sesionEstado !== 'undefined' && sesionEstado === 'en_curso');
    let startTimestamp = (typeof sesionFechaInicioEpochMs !== 'undefined' && Number.isFinite(sesionFechaInicioEpochMs))
        ? sesionFechaInicioEpochMs
        : Date.now();

    const setWaitingUi = () => {
        timerValue.textContent = _formatRemainingTime(countdownMs);
        timerContainer.classList.remove('finished');
        timerContainer.classList.add('waiting');
    };

    const startTicker = () => {
        if (countdownTimerId) {
            clearInterval(countdownTimerId);
            countdownTimerId = null;
        }

        timerContainer.classList.remove('waiting');
        let endTimestamp = startTimestamp + countdownMs;
        let remainingSeconds = Math.max(0, Math.floor((endTimestamp - Date.now()) / 1000));
        let lastTickAt = Date.now();

        const render = () => {
            timerValue.textContent = _formatRemainingTime(remainingSeconds * 1000);
            if (remainingSeconds === 0) {
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
            const tickNow = Date.now();
            const elapsedSeconds = Math.max(1, Math.floor((tickNow - lastTickAt) / 1000));
            remainingSeconds = Math.max(0, remainingSeconds - elapsedSeconds);
            lastTickAt = tickNow;
            if (remainingSeconds > 0) endTimestamp = tickNow + (remainingSeconds * 1000);
            render();
        }, 1000);
    };

    const applyRemoteState = (data) => {
        if (!data || !data.estado) return;
        const remoteStarted = data.estado === 'en_curso';

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
                startBtn.innerHTML = '<span class="material-icons-round">check</span>Cronómetro iniciado';
            }
            startTicker();
        } else {
            sesionIniciada = false;
            if (!countdownTimerId) setWaitingUi();
        }
    };

    const fetchCountdownState = () => {
        if (typeof countdownStatusUrl === 'undefined' || !countdownStatusUrl) return;
        const separator = countdownStatusUrl.includes('?') ? '&' : '?';
        const liveStatusUrl = `${countdownStatusUrl}${separator}_=${Date.now()}`;
        fetch(liveStatusUrl, { cache: 'no-store' })
            .then(r => r.ok ? r.json() : Promise.reject())
            .then(applyRemoteState)
            .catch(() => {});
    };

    if (sesionIniciada) startTicker();
    else setWaitingUi();

    fetchCountdownState();
    countdownPollId = setInterval(fetchCountdownState, 1200);

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
                    if (data && data.estado === 'en_curso' && data.fecha_inicio) {
                        const parsed = Date.parse(data.fecha_inicio);
                        if (Number.isFinite(parsed)) startTimestamp = parsed;
                        sesionIniciada = true;
                        startBtn.innerHTML = '<span class="material-icons-round">check</span>Cronómetro iniciado';
                        startTicker();
                    } else {
                        startBtn.disabled = false;
                    }
                })
                .catch(() => { startBtn.disabled = false; });
        });
    }
}

function _formatRemainingTime(milliseconds) {
    const totalSeconds = Math.floor(milliseconds / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}


// ── Chat ───────────────────────────────────────────────────────────────────

function _initChat() {
    const chatMessages = document.getElementById('chat-messages');
    const chatInput    = document.getElementById('chat-input');
    const chatSendBtn  = document.getElementById('chat-send');
    if (!chatMessages || !chatInput || !chatSendBtn) return;

    let lastMessageTime = null;
    let unread          = 0;
    let chatVisible     = false;

    document.addEventListener('chatOpened', () => { chatVisible = true; unread = 0; });

    const escHtml = t => { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; };
    const myName  = () => (typeof currentUserName !== 'undefined' && currentUserName)
        ? currentUserName
        : (document.body.getAttribute('data-username') || '');

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
        const emptyState = chatMessages.querySelector('.chat-empty');
        if (emptyState) emptyState.remove();
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
            div.innerHTML = `
                <div class="chat-message-header">
                    <span class="chat-message-sender">${escHtml(msg.nombre_remitente)}</span>
                    <span class="chat-message-time">${t}</span>
                </div>
                <div class="chat-message-bubble">${escHtml(msg.texto)}</div>`;
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
        let url = `/tours/sesiones/${sesionId}/mensajes/`;
        if (lastMessageTime) {
            try { url += `?desde=${encodeURIComponent(new Date(lastMessageTime).toISOString())}`; }
            catch { url += `?desde=${encodeURIComponent(lastMessageTime)}`; }
        }
        fetch(url)
            .then(r => r.ok ? r.json() : Promise.reject())
            .then(data => renderMessages(data.mensajes || data))
            .catch(() => {});
    }

    function sendMessage() {
        const texto = chatInput.value.trim();
        if (!texto) return;
        chatSendBtn.disabled = chatInput.disabled = true;
        fetch(`/tours/sesiones/${sesionId}/mensajes/enviar/`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _getCsrf() },
            body:    JSON.stringify({ texto }),
        })
        .then(r => r.json())
        .then(() => { chatInput.value = ''; fetchMessages(); })
        .catch(() => {})
        .finally(() => { chatSendBtn.disabled = chatInput.disabled = false; chatInput.focus(); });
    }

    chatSendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', e => { if (e.key === 'Enter') sendMessage(); });

    fetchMessages();
    setInterval(fetchMessages, 5000);
}


function _obtenerUbicacionesTuristas() {
    if (!map || !esGuia) return;

    fetch(`/tours/sesiones/${sesionId}/ubicaciones_turistas/`)
        .then(r => { if (!r.ok) throw new Error(); return r.json(); })
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

function _resaltarParadaSeleccionada(paradaId) {
    if (!paradaId) return;

    if (paradaSeleccionadaId && paradaSeleccionadaId !== paradaId) {
        const previousMarker = paradasMarkers.get(paradaSeleccionadaId);
        const previousParada = paradasDataById.get(paradaSeleccionadaId);
        if (previousMarker && previousParada) {
            previousMarker.setIcon(_buildParadaIcon(previousParada));
            previousMarker.setZIndexOffset(0);
        }
    }

    // Sincroniza el estado visual del itinerario para todos los usuarios.
    document.querySelectorAll('.timeline-item').forEach(item => {
        item.classList.remove('active', 'selected-stop');
        const stopName = item.querySelector('.timeline-stop-name');
        if (stopName) stopName.classList.add('text-muted');
    });

    document.querySelectorAll('.timeline-item.selected-stop').forEach(item => {
        item.classList.remove('selected-stop');
    });

    const marker = paradasMarkers.get(paradaId);
    const parada = paradasDataById.get(paradaId);
    if (marker && parada) {
        marker.setIcon(_buildParadaIcon(parada, true));
        marker.setZIndexOffset(1200);
    }

    const timelineItem = document.querySelector(`.timeline-item[data-parada-id="${paradaId}"]`);
    if (timelineItem) {
        timelineItem.classList.add('active');
        timelineItem.classList.add('selected-stop');
        const stopName = timelineItem.querySelector('.timeline-stop-name');
        if (stopName) stopName.classList.remove('text-muted');
    }

    document.querySelectorAll('.parada-focus-btn').forEach(btn => {
        const btnParadaId = btn.getAttribute('data-parada-id');
        const isSelected = btnParadaId === paradaId;
        btn.textContent = isSelected ? 'Parada actual seleccionada' : 'Seleccionar parada actual';
        btn.classList.toggle('is-selected', isSelected);
    });

    paradaSeleccionadaId = paradaId;
}

function _buildParadaIcon(parada, highlighted = false) {
    const esActual = Boolean(parada && parada.es_actual);
    const size = highlighted ? 40 : (esActual ? 34 : 26);
    const backgroundColor = highlighted ? '#f97316' : (esActual ? '#4f46e5' : '#d1d5db');
    const borderWidth = highlighted ? 3 : (esActual ? 3 : 2);
    const borderColor = highlighted ? '#fff7ed' : '#ffffff';
    const shadow = highlighted
        ? '0 0 0 4px rgba(249,115,22,.25),0 4px 12px rgba(249,115,22,.45)'
        : (esActual ? '0 2px 10px rgba(79,70,229,.45)' : '0 1px 5px rgba(0,0,0,.18)');
    const textColor = highlighted || esActual ? '#ffffff' : '#6b7280';
    const textSize = highlighted ? 15 : (esActual ? 14 : 11);
    const textWeight = highlighted ? 800 : (esActual ? 700 : 600);

    return L.divIcon({
        className: '',
        html: `<div style="
                background:${backgroundColor};
                width:${size}px;height:${size}px;
                border-radius:50%;border:${borderWidth}px solid ${borderColor};
                box-shadow:${shadow};
                display:flex;align-items:center;justify-content:center;">
                <span style="color:${textColor};font-size:${textSize}px;font-weight:${textWeight};">${parada.orden}</span>
              </div>`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
        popupAnchor: [0, -(size / 2) - 4],
    });
}


function _initMapActionControls() {
    const btnCenterRoute = document.getElementById('btn-center-route');
    const btnCenterMe = document.getElementById('btn-center-me');
    const btnFollowMe = document.getElementById('btn-follow-me');

    if (btnCenterRoute) {
        btnCenterRoute.addEventListener('click', () => {
            if (!map || !routeBounds || !routeBounds.isValid()) return;
            map.fitBounds(routeBounds, { padding: [42, 42] });
        });
    }

    if (btnCenterMe) {
        btnCenterMe.addEventListener('click', () => {
            if (!map || !miUbicacionMarker) return;
            const pos = miUbicacionMarker.getLatLng();
            map.flyTo([pos.lat, pos.lng], Math.max(map.getZoom(), 16), { duration: 0.45 });
        });
    }

    if (btnFollowMe) {
        btnFollowMe.addEventListener('click', () => {
            followMeMode = !followMeMode;
            btnFollowMe.classList.toggle('is-active', followMeMode);
        });
    }
}


function _initSessionSummaryPanel() {
    if (typeof mapSummaryUrl === 'undefined' || !mapSummaryUrl) return;

    const fetchSummary = () => {
        fetch(`${mapSummaryUrl}?_=${Date.now()}`, { cache: 'no-store' })
            .then(r => r.ok ? r.json() : Promise.reject())
            .then(_renderSessionSummary)
            .catch(() => {});
    };

    fetchSummary();
    sessionSummaryPollId = setInterval(fetchSummary, 5000);
}


function _renderSessionSummary(summary) {
    if (!summary) return;
    latestSessionSummary = summary;

    const rutaData = summary.ruta || {};
    const paradaActual = summary.parada_actual || null;
    const guiaUbicacion = summary.guia_ubicacion || null;

    const hudRuta = document.getElementById('hud-ruta');
    const hudParticipantes = document.getElementById('hud-participantes');
    const hudParada = document.getElementById('hud-parada-actual');

    const routeTitle = rutaData.titulo || 'Ruta en sesión';
    const participantCount = Number.isFinite(summary.participantes_activos)
        ? summary.participantes_activos
        : 0;
    const currentStopName = paradaActual && paradaActual.nombre ? paradaActual.nombre : 'Sin parada activa';

    if (hudRuta) hudRuta.textContent = routeTitle;
    if (hudParticipantes) hudParticipantes.textContent = `${participantCount} participantes`;
    if (hudParada) hudParada.textContent = `Parada actual: ${currentStopName}`;

    const codeLive = document.getElementById('session-code-live');
    const stateLive = document.getElementById('session-state-live');
    const durationLive = document.getElementById('session-duration-live');
    const stopsLive = document.getElementById('session-stops-live');
    const currentStopLive = document.getElementById('session-current-stop-name');
    const durationHours = rutaData.duracion_horas != null ? rutaData.duracion_horas : '-';
    const totalStops = rutaData.paradas_total != null ? rutaData.paradas_total : 0;

    if (codeLive) codeLive.textContent = summary.codigo_acceso || '-';
    if (stateLive) stateLive.textContent = String(summary.estado || '-').replace('_', ' ').toUpperCase();
    if (durationLive) durationLive.textContent = `${durationHours} h`;
    if (stopsLive) stopsLive.textContent = `${totalStops}`;
    if (currentStopLive) {
        currentStopLive.textContent = paradaActual
            ? `${paradaActual.nombre} · Parada ${paradaActual.orden}`
            : 'Sin parada activa';
    }

}

        const startTicker = () => {
            if (countdownTimerId) {
                clearInterval(countdownTimerId);
                countdownTimerId = null;
            }

            timerContainer.classList.remove('waiting');
            let endTimestamp = startTimestamp + countdownMs;
            let remainingSeconds = Math.max(0, Math.floor((endTimestamp - Date.now()) / 1000));
            let lastTickAt = Date.now();

            const render = () => {
                timerValue.textContent = _formatRemainingTime(remainingSeconds * 1000);
                if (remainingSeconds === 0) {
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
                const tickNow = Date.now();
                const elapsedSeconds = Math.max(1, Math.floor((tickNow - lastTickAt) / 1000));
                remainingSeconds = Math.max(0, remainingSeconds - elapsedSeconds);
                lastTickAt = tickNow;
                if (remainingSeconds > 0) endTimestamp = tickNow + (remainingSeconds * 1000);
                render();
            }, 1000);
        };

        if (sesionIniciada) startTicker();
        else setWaitingUi();

        fetchCountdownState();
        countdownPollId = setInterval(fetchCountdownState, 1200);

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
                        if (data && data.estado === 'en_curso' && data.fecha_inicio) {
                            const parsed = Date.parse(data.fecha_inicio);
                            if (Number.isFinite(parsed)) startTimestamp = parsed;
                            sesionIniciada = true;
                            startBtn.innerHTML = '<span class="material-icons-round">check</span>Cronómetro iniciado';
                            startTicker();
                        } else {
                            startBtn.disabled = false;
                        }
                    })
                    .catch(() => { startBtn.disabled = false; });
            });
        }


function _escapeHtml(value) {
    const container = document.createElement('div');
    container.textContent = String(value == null ? '' : value);
    return container.innerHTML;
}


function _renderNavigationMetrics() {
    const targetEl = document.getElementById('session-nav-target');
    const distanceEl = document.getElementById('session-nav-distance');
    const etaEl = document.getElementById('session-nav-eta');
    const nextStopEl = document.getElementById('session-nav-next-stop');
    const navigateBtn = document.getElementById('session-open-navigation');

    if (!targetEl || !distanceEl || !etaEl || !nextStopEl || !navigateBtn) return;

    if (isIOSDevice) {
        navigateBtn.innerHTML = '<span class="material-icons-round">map</span>Abrir en Mapas';
        navigateBtn.setAttribute('aria-label', 'Abrir en Mapas');
        navigateBtn.setAttribute('title', 'Abrir en Mapas');
    } else {
        navigateBtn.innerHTML = '<span class="material-icons-round">navigation</span>Abrir navegación externa';
        navigateBtn.setAttribute('aria-label', 'Abrir navegación externa');
        navigateBtn.setAttribute('title', 'Abrir navegación externa');
    }

    const currentStop = latestSessionSummary && latestSessionSummary.parada_actual
        ? latestSessionSummary.parada_actual
        : null;
    const nextStop = _resolveNextStop(currentStop);
    const navTarget = currentStop || nextStop;

    targetEl.textContent = navTarget ? `${navTarget.nombre} · Parada ${navTarget.orden}` : 'Sin objetivo';
    nextStopEl.textContent = nextStop ? `${nextStop.nombre} · Parada ${nextStop.orden}` : 'Fin de ruta';

    if (!navTarget || navTarget.lat == null || navTarget.lng == null) {
        distanceEl.textContent = '--';
        etaEl.textContent = '--';
        navigateBtn.disabled = true;
        navigateBtn.dataset.destination = '';
        return;
    }

    navigateBtn.disabled = false;
    navigateBtn.dataset.destination = `${navTarget.lat},${navTarget.lng}`;

    if (!lastKnownPosition) {
        distanceEl.textContent = 'Activa ubicación';
        etaEl.textContent = '--';
    } else {
        const meters = _haversineMeters(
            lastKnownPosition.lat,
            lastKnownPosition.lng,
            Number(navTarget.lat),
            Number(navTarget.lng),
        );
        distanceEl.textContent = _formatDistance(meters);
        etaEl.textContent = _formatEta(meters, 1.35);
    }

    if (!navigateBtn.dataset.bound) {
        navigateBtn.addEventListener('click', () => {
            const destination = navigateBtn.dataset.destination;
            if (!destination) return;

            const origin = lastKnownPosition
                ? `${lastKnownPosition.lat},${lastKnownPosition.lng}`
                : null;
            const mapsUrl = _buildExternalMapUrl(destination, origin);
            window.open(mapsUrl, '_blank');
        });
        navigateBtn.dataset.bound = '1';
    }
}


function _resolveNextStop(currentStop) {
    if (!Array.isArray(paradasData) || !paradasData.length) return null;

    const sorted = [...paradasData]
        .filter(stop => stop && Number.isFinite(Number(stop.orden)))
        .sort((a, b) => Number(a.orden) - Number(b.orden));

    if (!sorted.length) return null;

    if (!currentStop) {
        return sorted[0] || null;
    }

    const currentOrder = Number(currentStop.orden);
    return sorted.find(stop => Number(stop.orden) > currentOrder) || null;
}


function _haversineMeters(lat1, lon1, lat2, lon2) {
    const toRadians = degrees => (degrees * Math.PI) / 180;
    const earthRadius = 6371000;

    const dLat = toRadians(lat2 - lat1);
    const dLon = toRadians(lon2 - lon1);
    const radLat1 = toRadians(lat1);
    const radLat2 = toRadians(lat2);

    const a = Math.sin(dLat / 2) ** 2
        + Math.cos(radLat1) * Math.cos(radLat2) * Math.sin(dLon / 2) ** 2;
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

    return earthRadius * c;
}


function _formatDistance(meters) {
    if (!Number.isFinite(meters) || meters < 0) return '--';
    if (meters < 1000) return `${Math.round(meters)} m`;
    return `${(meters / 1000).toFixed(2)} km`;
}


function _formatEta(meters, speedMps) {
    if (!Number.isFinite(meters) || !Number.isFinite(speedMps) || speedMps <= 0) return '--';
    const totalMinutes = Math.max(1, Math.round((meters / speedMps) / 60));
    if (totalMinutes < 60) return `${totalMinutes} min`;

    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    return minutes ? `${hours} h ${minutes} min` : `${hours} h`;
}