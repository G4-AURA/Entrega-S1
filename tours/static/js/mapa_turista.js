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
let countdownTimerId  = null;
let countdownPollId   = null;
const paradasMarkers  = new Map();
const paradasDataById = new Map();
let paradaSeleccionadaId = null;

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
    const tileUrl = token
        ? `https://api.mapbox.com/styles/v1/mapbox/light-v11/tiles/256/{z}/{x}/{y}@2x?access_token=${token}`
        : 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';

    L.tileLayer(tileUrl, {
        maxZoom:     19,
        attribution: token
            ? '© <a href="https://mapbox.com">Mapbox</a> © <a href="https://openstreetmap.org">OpenStreetMap</a>'
            : '© <a href="https://carto.com">CARTO</a> © <a href="https://openstreetmap.org">OpenStreetMap</a>',
    }).addTo(map);

    L.control.zoom({ position: 'bottomright' }).addTo(map);

    // ── Dibujar recorrido y paradas ───────────────────────────────────────
    _dibujarRutaYParadas();
    _initParadaFocusButtons();

    // ── Posición propia ───────────────────────────────────────────────────
    _iniciarRastreoLocal();

    // ── Posición del guía (polling cada 5 s, solo turistas) ───────────────
    if (!esGuia) {
        _obtenerUbicacionGuia();
        setInterval(_obtenerUbicacionGuia, 5000);
    }

    // ── Panel expandible ──────────────────────────────────────────────────
    const panelHeader = document.querySelector('.panel-header');
    const tourPanel   = document.querySelector('.tour-panel');
    if (panelHeader && tourPanel) {
        panelHeader.addEventListener('click', () => tourPanel.classList.toggle('expanded'));
    }

    // ── Tabs Itinerario / Chat ─────────────────────────────────────────────
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
    }
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

            // El guía envía su posición al servidor para que los turistas la vean
            if (esGuia) {
                fetch('/tours/ubicacion/', {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _getCsrf() },
                    body:    JSON.stringify({ latitud: lat, longitud: lng, sesion_id: sesionId }),
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
        timelineItem.classList.add('selected-stop');
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