(function() {
    if (window._catalogoInit) return;
    window._catalogoInit = true;

    const feedback = window.AuraFeedback;
    const confirmar = async (options) => {
        try {
            if (feedback && typeof feedback.confirm === 'function') {
                return Boolean(await feedback.confirm(options));
            }
        } catch (error) {
            console.error('[AURA feedback] Error mostrando confirmación personalizada:', error);
        }

        const message = String(options?.message || '¿Deseas continuar?');
        if (typeof window.confirm === 'function') {
            return window.confirm(message);
        }
        return false;
    };
    const avisar = (message, type = 'info') => {
        if (feedback && typeof feedback.toast === 'function') {
            feedback.toast(message, { type });
            return;
        }
        console.warn('[AURA feedback]', message);
    };

    async function syncCheckoutAfterSuccessRedirect() {
        const searchParams = new URLSearchParams(window.location.search || '');
        
        if (searchParams.get('billing') !== 'success') {
            return;
        }

        const sessionId = (searchParams.get('session_id') || '').trim();
        try {
            const response = await fetch('/billing/sync-checkout-session/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify(sessionId ? { session_id: sessionId } : {})
            });
            
            const payload = await response.json().catch(() => ({}));

            if (!response.ok) {
                if (payload.code === 'BILLING_NOTHING_TO_SYNC') return;
                avisar(payload.mensaje || 'No se pudo sincronizar el checkout.', 'warning');
                return;
            }

            const premiumStates = ['active', 'trialing', 'past_due'];
            if (premiumStates.includes(String(payload.subscription_status || '').toLowerCase())) {
                avisar('Pago confirmado. ¡Ya eres Premium! Actualizando la página...', 'success');
                
                window.setTimeout(function () {
                    window.location.assign(window.location.pathname);
                }, 1500);
                return;
            }

            avisar('Checkout recibido. La suscripción está en verificación.', 'warning');
        } catch (_error) {
            avisar('Error de conexión. Recarga la página en unos segundos.', 'warning');
        }
    }

    syncCheckoutAfterSuccessRedirect();
    // ---------------------------------------------------

    let currentLimit = 3;
    let pageManual = 1;
    let pageIa = 1;

    document.addEventListener('DOMContentLoaded', async function() {
        await Promise.all([cargarRutas('manual'), cargarRutas('ia')]);

        if (new URLSearchParams(window.location.search).get('tipo') === 'ia') {
            const seccionIa = document.getElementById('rutas-ia-section');
            if (seccionIa) seccionIa.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        document.getElementById('limite-rutas').addEventListener('change', function(e) {
            currentLimit = parseInt(e.target.value);
            if (currentLimit > 10) currentLimit = 10;
            pageManual = 1;
            pageIa = 1;
            cargarRutas('manual');
            cargarRutas('ia');
        });

        document.getElementById('btn-prev-manual').addEventListener('click', () => {
            if (pageManual > 1) { pageManual--; cargarRutas('manual'); }
        });
        document.getElementById('btn-next-manual').addEventListener('click', () => {
            pageManual++; cargarRutas('manual');
        });
        document.getElementById('btn-prev-ia').addEventListener('click', () => {
            if (pageIa > 1) { pageIa--; cargarRutas('ia'); }
        });
        document.getElementById('btn-next-ia').addEventListener('click', () => {
            pageIa++; cargarRutas('ia');
        });
    });

    async function cargarRutas(tipo) {
        const loadingEl = document.getElementById('loading');
        const errorEl = document.getElementById('error-message');
        const page = tipo === 'manual' ? pageManual : pageIa;

        try {
            const response = await fetch(`/api/rutas/?tipo=${tipo}&limit=${currentLimit}&page=${page}`);
            if (!response.ok) throw new Error(`Error cargando catálogo (${response.status})`);

            const data = await response.json();
            const rutas = data.results;

            loadingEl.style.display = 'none';
            const controlsEl = document.getElementById('controls-row');
            if (controlsEl) controlsEl.style.display = '';

            const containerId = tipo === 'manual' ? 'rutas-container' : 'rutas-ia-container';
            const sectionId  = tipo === 'manual' ? 'rutas-catalogo-section' : 'rutas-ia-section';
            const countId    = tipo === 'manual' ? 'rutas-catalogo-count' : 'rutas-ia-count';
            const prevBtnId  = tipo === 'manual' ? 'btn-prev-manual' : 'btn-prev-ia';
            const nextBtnId  = tipo === 'manual' ? 'btn-next-manual' : 'btn-next-ia';

            const container = document.getElementById(containerId);
            while (container.firstChild) container.removeChild(container.firstChild);

            if (rutas.length > 0) {
                document.getElementById(sectionId).style.display = 'block';
                document.getElementById(countId).textContent =
                    `Página ${data.current_page} de ${data.total_pages} (${data.total_items} rutas en total)`;
                rutas.forEach(ruta => container.appendChild(createRutaCard(ruta, tipo === 'ia')));
            } else if (page === 1) {
                document.getElementById(sectionId).style.display = 'none';
            }

            document.getElementById(prevBtnId).disabled = data.current_page <= 1;
            document.getElementById(nextBtnId).disabled = data.current_page >= data.total_pages;

        } catch (error) {
            console.error(`Error al cargar rutas ${tipo}:`, error);
            loadingEl.style.display = 'none';
            errorEl.classList.remove('d-none');
            errorEl.textContent = 'Error al cargar las rutas: ' + error.message;
        }
    }

    function makeSvgIcon(path) {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'info-icon');
        svg.setAttribute('fill', 'none');
        svg.setAttribute('stroke', 'currentColor');
        svg.setAttribute('viewBox', '0 0 24 24');
        const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        p.setAttribute('stroke-linecap', 'round');
        p.setAttribute('stroke-linejoin', 'round');
        p.setAttribute('stroke-width', '2');
        p.setAttribute('d', path);
        svg.appendChild(p);
        return svg;
    }

    function createRutaCard(ruta, destacarIa = false) {
    const col = document.createElement('div');
    col.className = 'col-12 col-md-6 col-lg-4';

    const exigenciaClass = `exigencia-${String(ruta.nivel_exigencia || '').toLowerCase()}`;
    const isIa = Boolean(ruta.es_generada_ia);

    const card = document.createElement('div');
    card.className = 'ruta-card';

    const link = document.createElement('a');
    link.href = `/catalogo/${ruta.id}/`;
    link.className = 'ruta-card-link';

    const body = document.createElement('div');
    body.className = 'ruta-card-body';

    // --- BLOQUE SUPERIOR (Agrupado para evitar huecos en medio) ---
    const mainContent = document.createElement('div');
    mainContent.className = 'ruta-card-main';

    const title = document.createElement('h3');
    title.className = 'ruta-title';
    title.textContent = ruta.titulo;
    mainContent.appendChild(title);

    const desc = document.createElement('p');
    desc.className = 'ruta-description';
    desc.textContent = ruta.descripcion || 'Sin descripción disponible';
    mainContent.appendChild(desc);

    // Info row
    const infoRow = document.createElement('div');
    infoRow.className = 'ruta-info';

    const itemDuracion = document.createElement('div');
    itemDuracion.className = 'info-item';
    itemDuracion.appendChild(makeSvgIcon('M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z'));
    const spanDuracion = document.createElement('span');
    spanDuracion.textContent = `${ruta.duracion_horas}h`;
    itemDuracion.appendChild(spanDuracion);

    const itemPersonas = document.createElement('div');
    itemPersonas.className = 'info-item';
    itemPersonas.appendChild(makeSvgIcon('M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z'));
    const spanPersonas = document.createElement('span');
    spanPersonas.textContent = `${ruta.num_personas} personas`;
    itemPersonas.appendChild(spanPersonas);

    const itemExigencia = document.createElement('div');
    itemExigencia.className = 'info-item';
    const badgeExig = document.createElement('span');
    badgeExig.className = `badge-exigencia ${exigenciaClass}`;
    badgeExig.textContent = ruta.nivel_exigencia;
    itemExigencia.appendChild(badgeExig);

    infoRow.appendChild(itemDuracion);
    infoRow.appendChild(itemPersonas);
    infoRow.appendChild(itemExigencia);
    mainContent.appendChild(infoRow);

    // Mood tags
    if (ruta.mood && ruta.mood.length > 0) {
        const moodDiv = document.createElement('div');
        moodDiv.className = 'mood-tags';
        ruta.mood.forEach(mood => {
            const tag = document.createElement('span');
            tag.className = 'mood-tag';
            tag.textContent = mood;
            moodDiv.appendChild(tag);
        });
        mainContent.appendChild(moodDiv);
    }

    // IA badge
    if (isIa || destacarIa) {
        const badge = document.createElement('span');
        badge.className = 'badge-ia';
        badge.textContent = 'Ruta generada por IA';
        mainContent.appendChild(badge);
    }

    // Añadimos todo lo de arriba al body
    body.appendChild(mainContent);

    // --- BLOQUE INFERIOR (Footer que empuja hacia abajo) ---
    const footer = document.createElement('div');
    footer.className = 'ruta-card-footer';

    const btnDiv = document.createElement('div');
    btnDiv.className = 'mt-2';
    const sesionLink = document.createElement('a');
    sesionLink.className = 'w-100';
    if (ruta.sesion_activa_id) {
        sesionLink.className += ' btn btn-primary';
        sesionLink.href = `/tours/sesiones/${ruta.sesion_activa_id}/guia/`;
        sesionLink.textContent = 'Acceder a sesión';
    } else {
        sesionLink.className += ' btn btn-success';
        sesionLink.href = `/tours/sesiones/crear/?ruta_id=${ruta.id}`;
        sesionLink.textContent = 'Crear sesión';
    }
    btnDiv.appendChild(sesionLink);
    footer.appendChild(btnDiv);

    // Añadimos el footer al final
    body.appendChild(footer);

    link.appendChild(body);
    card.appendChild(link);

    // Botón eliminar (absoluto)
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'ruta-card-actions';
    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'btn-delete-route';
    deleteBtn.dataset.rutaId = String(ruta.id);
    deleteBtn.textContent = 'Eliminar';
    deleteBtn.addEventListener('click', async (event) => {
        event.preventDefault();
        event.stopPropagation();
        const confirmacion = await confirmar({
            title: 'Eliminar ruta',
            message: '¿Seguro que quieres eliminar esta ruta?',
            confirmText: 'Eliminar',
            cancelText: 'Cancelar',
            type: 'danger',
        });
        if (!confirmacion) return;
        try {
            const resp = await fetch(`/catalogo/${ruta.id}/eliminar/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
            });
            if (!resp.ok) throw new Error('No se pudo eliminar la ruta');
            avisar('Ruta eliminada correctamente.', 'success');
            cargarRutas('manual');
            cargarRutas('ia');
        } catch (err) {
            avisar(err.message || 'Error al eliminar la ruta', 'error');
        }
    });
    actionsDiv.appendChild(deleteBtn);
    card.appendChild(actionsDiv);

    col.appendChild(card);
    return col;
}

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
})();
