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
const sesionEnCurso   = typeof sesionEstado !== 'undefined' && sesionEstado === 'en_curso';

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

    // ── Posición propia ───────────────────────────────────────────────────
    _iniciarRastreoLocal();

    // ── Posición del guía (polling cada 5 s, solo turistas) ───────────────
    if (!esGuia && sesionEnCurso) {
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

        const esActual = parada.es_actual;
        const size     = esActual ? 34 : 26;

        const iconHtml = esActual
            ? `<div style="
                  background:#4f46e5;
                  width:${size}px;height:${size}px;
                  border-radius:50%;border:3px solid white;
                  box-shadow:0 2px 10px rgba(79,70,229,.45);
                  display:flex;align-items:center;justify-content:center;">
                  <span style="color:white;font-size:14px;font-weight:700;">${parada.orden}</span>
               </div>`
            : `<div style="
                  background:#d1d5db;
                  width:${size}px;height:${size}px;
                  border-radius:50%;border:2px solid white;
                  box-shadow:0 1px 5px rgba(0,0,0,.18);
                  display:flex;align-items:center;justify-content:center;">
                  <span style="color:#6b7280;font-size:11px;font-weight:600;">${parada.orden}</span>
               </div>`;

        L.marker([parada.lat, parada.lng], {
            icon: L.divIcon({
                className:  '',
                html:       iconHtml,
                iconSize:   [size, size],
                iconAnchor: [size / 2, size / 2],
                popupAnchor:[0, -(size / 2) - 4],
            }),
        })
        .addTo(map)
        .bindPopup(
            `<strong>${parada.nombre}</strong>` +
            `<br><span style="color:#6b7280;font-size:.8rem;">Parada ${parada.orden}</span>`
        );
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
            if (esGuia && sesionEnCurso) {
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
    if (!map || !sesionEnCurso) return;

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


// ── Chat ───────────────────────────────────────────────────────────────────

function _initChat() {
    const chatMessages = document.getElementById('chat-messages');
    const chatInput    = document.getElementById('chat-input');
    const chatSendBtn  = document.getElementById('chat-send');
    if (!chatMessages || !chatInput || !chatSendBtn) return;

    if (!sesionEnCurso) {
        chatInput.value = '';
        chatInput.disabled = true;
        chatSendBtn.disabled = true;
        chatInput.placeholder = 'El chat estará disponible cuando el tour esté en curso.';
        return;
    }

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
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(() => { chatInput.value = ''; fetchMessages(); })
        .catch(() => {})
        .finally(() => { chatSendBtn.disabled = chatInput.disabled = false; chatInput.focus(); });
    }

    chatSendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', e => { if (e.key === 'Enter') sendMessage(); });

    fetchMessages();
    setInterval(fetchMessages, 5000);
}