(function () {
    'use strict';

    const cronometroUrl = document.querySelector('meta[name="cronometro-url"]').content;
    const mapaUrl       = document.querySelector('meta[name="mapa-url"]').content;

    const enterBtn      = document.getElementById('enter-btn');
    const enterIcon     = document.getElementById('enter-icon');
    const enterLabel    = document.getElementById('enter-label');
    const waitingMsg    = document.getElementById('waiting-message');
    const illustration  = document.getElementById('waiting-illustration');
    const mainIcon      = document.getElementById('main-icon');
    const statusBadge   = document.getElementById('status-badge');
    const statusDot     = document.getElementById('status-dot');
    const statusLabel   = document.getElementById('status-label');

    // En lugar de la línea con template tags:
    let tourStarted = statusBadge.classList.contains('active');
    let pollInterval = null;

    function activateTour() {
        if (tourStarted) return;
        tourStarted = true;

        // Botón habilitado
        enterBtn.removeAttribute('aria-disabled');
        enterBtn.removeAttribute('tabindex');
        enterBtn.style.pointerEvents = '';
        enterIcon.textContent  = 'map';
        enterLabel.textContent = 'Entrar al tour';

        // Mensaje
        waitingMsg.innerHTML = '<span class="material-icons-round" style="vertical-align:middle;font-size:18px;">check_circle</span> ¡Todo listo! Entra cuando quieras.';
        waitingMsg.classList.add('ready');

        // Ilustración
        illustration.classList.add('ready');
        mainIcon.textContent = 'check_circle';

        // Badge de estado
        statusBadge.classList.replace('pending', 'active');
        statusDot.classList.replace('pending', 'active');
        statusLabel.textContent = 'EN CURSO';

        clearInterval(pollInterval);
    }

    async function pollEstado() {
        try {
            const resp = await fetch(cronometroUrl, { headers: { 'Accept': 'application/json' } });
            if (!resp.ok) return;
            const data = await resp.json();
            if (data.estado === 'en_curso') activateTour();
            if (data.estado === 'finalizado') window.location.href = '/';
        } catch (_) {
            // red inestable — ignorar, reintentar en el siguiente tick
        }
    }

    // Si el tour ya estaba iniciado al cargar, no hace falta polling
    if (!tourStarted) {
        // Bloquear el enlace mientras está pendiente
        enterBtn.style.pointerEvents = 'none';
        enterBtn.style.cursor = 'not-allowed';

        pollInterval = setInterval(pollEstado, 3000);
    }
})();