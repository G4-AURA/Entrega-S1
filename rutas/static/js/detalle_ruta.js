/**
 * detalle_ruta.js
 * S2.1-31: Dibuja la polilínea GraphHopper al cargar.
 * S2.1-32: Botón "Recalcular ruta" y función recalcularRutaAjax().
 */

// ── Datos del servidor ─────────────────────────────────────────────────────
const paradas       = JSON.parse(document.getElementById('paradas-json').textContent || '[]');
const geometriaRuta = JSON.parse(document.getElementById('geometria-ruta-json').textContent);
const mapboxToken   = document.querySelector('meta[name="mapbox-token"]')?.content || '';
const rutaId        = parseInt(document.querySelector('meta[name="ruta-id"]')?.content || '0');
const csrfToken     = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

// ── Inicializar mapa ───────────────────────────────────────────────────────
const primeraConCoords = paradas.find(p => Array.isArray(p.coordenadas) && p.coordenadas.length === 2);
const centroInicial    = primeraConCoords ? primeraConCoords.coordenadas : [40.4167, -3.7037];

const mapa = L.map('mapa-ruta').setView(centroInicial, 14);

const tileUrl = mapboxToken
    ? `https://api.mapbox.com/styles/v1/mapbox/streets-v12/tiles/256/{z}/{x}/{y}@2x?access_token=${mapboxToken}`
    : 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';

L.tileLayer(tileUrl, { attribution: mapboxToken ? '© Mapbox' : '© OpenStreetMap contributors' }).addTo(mapa);

// ── Marcadores ─────────────────────────────────────────────────────────────
const puntos = [];
paradas.forEach(parada => {
    if (!Array.isArray(parada.coordenadas) || parada.coordenadas.length !== 2) return;
    puntos.push(parada.coordenadas);
    L.marker(parada.coordenadas)
        .addTo(mapa)
        .bindPopup(`<b>${parada.orden}. ${parada.nombre}</b>`);
});

// ── Estado del badge en el mapa ────────────────────────────────────────────
const mapBadge = document.getElementById('map-route-badge');

function setBadge(estado, texto) {
    if (!mapBadge) return;
    mapBadge.className = `map-route-status ${estado}`;
    mapBadge.textContent = texto;
}

// ── Polilínea GraphHopper (S2.1-31) ───────────────────────────────────────
let rutaPolyline       = null;
let fallbackPolyline   = null;

/**
 * Dibuja la polilínea de ruta real. Elimina el fallback si existe.
 * @param {Array|null} coords  [[lat, lon], ...] en formato Leaflet
 */
function dibujarPolilinea(coords) {
    if (rutaPolyline)     { mapa.removeLayer(rutaPolyline);     rutaPolyline   = null; }
    if (fallbackPolyline) { mapa.removeLayer(fallbackPolyline); fallbackPolyline = null; }

    if (coords && coords.length >= 2) {
        rutaPolyline = L.polyline(coords, {
            color: '#4f46e5',
            weight: 4,
            opacity: 0.8,
            smoothFactor: 1,
        }).addTo(mapa);

        mapa.fitBounds(rutaPolyline.getBounds(), { padding: [40, 40] });
        setBadge('ok', '✅ Ruta real calculada');

    } else if (puntos.length >= 2) {
        fallbackPolyline = L.polyline(puntos, {
            color: '#9ca3af',
            weight: 2,
            opacity: 0.5,
            dashArray: '8 6',
        }).addTo(mapa);

        mapa.fitBounds(L.latLngBounds(puntos), { padding: [40, 40] });
        setBadge('warn', '⚠️ Sin ruta calculada (línea recta)');

    } else if (puntos.length === 1) {
        mapa.setView(puntos[0], 15);
        setBadge('warn', '⚠️ Solo 1 parada');
    }
}

// Dibujo inicial
dibujarPolilinea(geometriaRuta && geometriaRuta.length >= 2 ? geometriaRuta : null);

// ── Panel de métricas (S2.1-29) ───────────────────────────────────────────
function makeMetricSpan(icon, label, value) {
    const span = document.createElement('span');
    span.className = 'metric-item';
    span.textContent = icon + ' ' + label + ': ';
    const val = document.createElement('span');
    val.className = 'metric-value';
    val.textContent = value;
    span.appendChild(val);
    return span;
}

function makeSep() {
    const span = document.createElement('span');
    span.className = 'metric-sep';
    span.textContent = '|';
    return span;
}

function makeRecalcularBtn() {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'btn-recalcular';
    btn.className = 'btn-recalcular';
    btn.title = 'Recalcular ruta con GraphHopper';
    btn.textContent = '🔄 Recalcular ruta';
    btn.addEventListener('click', handleRecalcular);
    return btn;
}

function actualizarPanelMetricas(data) {
    const panel = document.getElementById('panel-metricas');
    if (!panel) return;

    while (panel.firstChild) panel.removeChild(panel.firstChild);

    if (data.distancia_total_km && data.duracion_total_min) {
        panel.appendChild(makeMetricSpan('📍', 'Distancia', data.distancia_total_km + ' km'));
        panel.appendChild(makeSep());
        panel.appendChild(makeMetricSpan('⏱️', 'Tiempo', data.duracion_total_min + ' min'));
        panel.appendChild(makeSep());
        panel.appendChild(makeMetricSpan('🚶', '', paradas.length + ' paradas'));
    } else {
        const empty = document.createElement('span');
        empty.className = 'metrics-empty';
        empty.textContent = 'ℹ️ Ruta sin calcular.';
        panel.appendChild(empty);
    }

    if (paradas.length >= 2) panel.appendChild(makeRecalcularBtn());
}

// ── Recálculo AJAX (S2.1-32) ──────────────────────────────────────────────
async function recalcularRutaAjax() {
    const btn = document.getElementById('btn-recalcular');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Calculando...'; }
    setBadge('warn', '⏳ Calculando...');

    try {
        const resp = await fetch(`/api/rutas/${rutaId}/recalcular/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        });

        if (!resp.ok) {
            const errText = await resp.text().catch(() => '');
            console.error('[AURA] Recálculo HTTP', resp.status, errText);
            setBadge('error', `❌ Error ${resp.status} al calcular`);
            if (btn) { btn.disabled = false; btn.textContent = '🔄 Reintentar'; }
            return null;
        }

        const data = await resp.json();
        dibujarPolilinea(data.geometria);
        actualizarPanelMetricas(data);

        if (!data.geometria) {
            console.warn('[AURA] GraphHopper devolvió geometría nula. Revisa los logs del servidor.');
        }
        return data;

    } catch (err) {
        console.error('[AURA] Error de red al recalcular:', err);
        setBadge('error', '❌ Sin conexión al servidor');
        if (btn) { btn.disabled = false; btn.textContent = '🔄 Reintentar'; }
        return null;
    }
}

function handleRecalcular() { recalcularRutaAjax(); }

const btnRecalcularInicial = document.getElementById('btn-recalcular');
if (btnRecalcularInicial) btnRecalcularInicial.addEventListener('click', handleRecalcular);

// ── Estado del modo de edición ─────────────────────────────────────────────
let activeParadaForm   = null;
let activeParadaButton = null;
let activeEditMarker   = null;
let activeMode         = null;
let reorderMode        = false;
let draggedItem        = null;

const btnEditarTitulo     = document.getElementById('btn-editar-titulo');
const formEditarTitulo    = document.getElementById('form-editar-titulo');
const btnEditarMeta       = document.getElementById('btn-editar-meta');
const formEditarMeta      = document.getElementById('form-editar-meta');
const btnEditarEtiquetas  = document.getElementById('btn-editar-etiquetas');
const etiquetasLectura    = document.getElementById('etiquetas-lectura');
const formEditarEtiquetas = document.getElementById('form-editar-etiquetas');
const mapEditHint         = document.getElementById('map-edit-hint');
const btnAgregarParada    = document.getElementById('btn-agregar-parada');
const formAgregarParada   = document.getElementById('form-agregar-parada');
const btnReordenarParadas = document.getElementById('btn-reordenar-paradas');
const formReordenarParadas= document.getElementById('form-reordenar-paradas');
const btnCancelarReorden  = document.getElementById('btn-cancelar-reorden');
const stopOrderInput      = document.getElementById('stop-order-input');
const listaParadas        = document.getElementById('lista-paradas');

if (btnEditarTitulo)    btnEditarTitulo.addEventListener('click', () => formEditarTitulo?.classList.toggle('d-none'));
if (btnEditarMeta)      btnEditarMeta.addEventListener('click', () => formEditarMeta?.classList.toggle('d-none'));
if (btnEditarEtiquetas) btnEditarEtiquetas.addEventListener('click', () => {
    etiquetasLectura?.classList.toggle('d-none');
    formEditarEtiquetas?.classList.toggle('d-none');
});

function deactivateParadaEditMode() {
    activeParadaForm?.classList.add('d-none');
    activeParadaForm = null;
    if (activeParadaButton) {
        activeParadaButton.classList.replace('btn-primary', 'btn-outline-primary');
        activeParadaButton.textContent = 'Editar';
        activeParadaButton = null;
    }
    if (activeEditMarker) { mapa.removeLayer(activeEditMarker); activeEditMarker = null; }
    if (mapEditHint) { mapEditHint.classList.add('d-none'); }
    activeMode = null;
}

function activateParadaEditMode(paradaId, triggerButton) {
    const form = document.getElementById(`form-editar-parada-${paradaId}`);
    if (!form) return;
    if (activeParadaForm === form) { deactivateParadaEditMode(); return; }

    deactivateParadaEditMode();
    activeParadaForm = form; activeParadaButton = triggerButton; activeMode = 'edit';
    form.classList.remove('d-none');
    triggerButton.classList.replace('btn-outline-primary', 'btn-primary');
    triggerButton.textContent = 'Editando...';

    const lat = parseFloat(form.querySelector('input[name="lat"]')?.value);
    const lon = parseFloat(form.querySelector('input[name="lon"]')?.value);
    const nombre = form.querySelector('input[name="nombre"]')?.value || 'Parada';

    if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
        activeEditMarker = L.marker([lat, lon]).addTo(mapa);
        mapa.setView([lat, lon], Math.max(mapa.getZoom(), 14));
    }
    if (mapEditHint) {
        mapEditHint.classList.remove('d-none');
        mapEditHint.textContent = `Editando "${nombre}": haz clic en el mapa para moverla.`;
    }
}

function activateAddStopMode() {
    if (!formAgregarParada) return;
    if (activeMode === 'add') { deactivateParadaEditMode(); return; }
    deactivateParadaEditMode();
    activeParadaForm = formAgregarParada; activeMode = 'add';
    formAgregarParada.classList.remove('d-none');
    if (mapEditHint) {
        mapEditHint.classList.remove('d-none');
        mapEditHint.textContent = 'Haz clic en el mapa para elegir la ubicación de la nueva parada.';
    }
}

if (btnAgregarParada) btnAgregarParada.addEventListener('click', activateAddStopMode);

document.querySelectorAll('.btn-editar-parada').forEach(btn => {
    btn.addEventListener('click', () => activateParadaEditMode(btn.dataset.paradaId, btn));
});

mapa.on('click', (event) => {
    if (!activeParadaForm) return;
    const latInput = activeParadaForm.querySelector('input[name="lat"]');
    const lonInput = activeParadaForm.querySelector('input[name="lon"]');
    if (!latInput || !lonInput) return;

    const lat = event.latlng.lat;
    const lon = event.latlng.lng;
    latInput.value = lat.toFixed(6);
    lonInput.value = lon.toFixed(6);

    if (!activeEditMarker) activeEditMarker = L.marker([lat, lon]).addTo(mapa);
    else activeEditMarker.setLatLng([lat, lon]);

    if (activeMode === 'add') {
        const preview = document.getElementById('add-stop-preview');
        if (preview) preview.textContent = `Seleccionado: ${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    }
});

// ── Reordenación ───────────────────────────────────────────────────────────
function updateVisualOrderLabels() {
    Array.from(listaParadas?.querySelectorAll('.parada-item[data-parada-id]') || [])
        .forEach((item, idx) => {
            const el = item.querySelector('.parada-order-num');
            if (el) el.textContent = String(idx + 1);
        });
}

function setReorderMode(enabled) {
    if (!listaParadas || !formReordenarParadas) return;
    reorderMode = enabled;
    if (enabled) {
        deactivateParadaEditMode();
        formAgregarParada?.classList.add('d-none');
        formReordenarParadas.classList.remove('d-none');
        listaParadas.classList.add('reorder-active');
        if (btnReordenarParadas) btnReordenarParadas.textContent = 'Reordenando...';
    } else {
        formReordenarParadas.classList.add('d-none');
        listaParadas.classList.remove('reorder-active');
        if (btnReordenarParadas) btnReordenarParadas.textContent = 'Editar orden';
    }
    Array.from(listaParadas.querySelectorAll('.parada-item[data-parada-id]')).forEach(item => {
        item.draggable = enabled;
        item.querySelector('.drag-handle')?.classList.toggle('d-none', !enabled);
        if (!enabled) item.classList.remove('drag-over');
    });
    updateVisualOrderLabels();
}

if (btnReordenarParadas) btnReordenarParadas.addEventListener('click', () => setReorderMode(true));
if (btnCancelarReorden)  btnCancelarReorden.addEventListener('click',  () => setReorderMode(false));

// ── Drag & Drop ────────────────────────────────────────────────────────────
if (listaParadas) {
    const items = Array.from(listaParadas.querySelectorAll('.parada-item[data-parada-id]'));
    items.forEach(item => {
        item.addEventListener('dragstart', () => { draggedItem = item; item.style.opacity = '0.5'; });
        item.addEventListener('dragend',   () => {
            item.style.opacity = '';
            draggedItem = null;
            items.forEach(i => i.classList.remove('drag-over'));
            updateVisualOrderLabels();
            const ordered = Array.from(listaParadas.querySelectorAll('.parada-item[data-parada-id]'))
                .map(i => i.dataset.paradaId).filter(Boolean);
            if (stopOrderInput) stopOrderInput.value = ordered.join(',');
        });
        item.addEventListener('dragover', e => {
            e.preventDefault();
            if (!draggedItem || draggedItem === item) return;
            items.forEach(i => i.classList.remove('drag-over'));
            item.classList.add('drag-over');
            const mid = item.getBoundingClientRect().top + item.getBoundingClientRect().height / 2;
            listaParadas.insertBefore(draggedItem, e.clientY < mid ? item : item.nextSibling);
        });
        item.addEventListener('dragleave', () => item.classList.remove('drag-over'));
    });
}
