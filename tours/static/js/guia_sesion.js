function getCsrf() {
    const name = 'csrftoken=';
    const cookie = document.cookie.split(';').map((s) => s.trim()).find((s) => s.startsWith(name));
    return cookie ? cookie.substring(name.length) : '';
}

function getFeedbackUi() {
    const feedback = window.AuraFeedback;
    return {
        confirm: async (options) => {
            if (feedback && typeof feedback.confirm === 'function') {
                return feedback.confirm(options);
            }
            return true;
        },
        toast: (message, options) => {
            if (feedback && typeof feedback.toast === 'function') {
                feedback.toast(message, options);
                return;
            }
            console.warn('[AURA feedback] ', message);
        },
    };
}

function buildParticipantItem(alias, fechaUnion) {
    const item = document.createElement('div');
    item.className = 'participant-item';

    const nameSpan = document.createElement('span');
    nameSpan.className = 'participant-name';

    const avatar = document.createElement('span');
    avatar.className = 'participant-avatar';
    avatar.textContent = alias ? alias.charAt(0).toUpperCase() : '?';

    const nameText = document.createElement('span');
    nameText.textContent = alias;

    nameSpan.appendChild(avatar);
    nameSpan.appendChild(nameText);

    const timeSpan = document.createElement('span');
    timeSpan.className = 'participant-time';
    try {
        timeSpan.textContent = new Date(fechaUnion).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch (_error) {
        timeSpan.textContent = '';
    }

    item.appendChild(nameSpan);
    item.appendChild(timeSpan);
    return item;
}

async function copyText(id, ui) {
    const element = document.getElementById(id);
    const text = element ? element.innerText : '';

    if (!text) {
        ui.toast('No hay código para copiar.', { type: 'error' });
        return;
    }

    if (!navigator.clipboard) {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        const copied = document.execCommand('copy');
        document.body.removeChild(ta);
        ui.toast(copied ? 'Copiado al portapapeles.' : 'No se pudo copiar el código.', {
            type: copied ? 'success' : 'error',
        });
        return;
    }

    try {
        await navigator.clipboard.writeText(text);
        ui.toast('Copiado al portapapeles.', { type: 'success' });
    } catch (_error) {
        ui.toast('No se pudo copiar el código.', { type: 'error' });
    }
}

document.addEventListener('DOMContentLoaded', function () {
    const ui = getFeedbackUi();
    const participantesList = document.getElementById('participantes-list');
    const participantesCount = document.getElementById('participantes-count');
    const emptyMsg = document.getElementById('empty-msg');

    async function fetchParticipants() {
        try {
            const resp = await fetch(document.querySelector('meta[name="participants-url"]')?.content || '');
            if (!resp.ok) return;

            const data = await resp.json();
            const list = data.participantes || [];
            participantesCount.textContent = list.length;

            if (list.length === 0) {
                if (!emptyMsg) {
                    participantesList.textContent = '';
                    const msg = document.createElement('p');
                    msg.id = 'empty-msg';
                    msg.style.cssText = 'color:var(--text-muted);font-size:.875rem;text-align:center;padding:2rem 0;';
                    msg.textContent = 'Esperando participantes...';
                    participantesList.appendChild(msg);
                }
                return;
            }

            participantesList.textContent = '';
            list.forEach((participant) => {
                participantesList.appendChild(buildParticipantItem(participant.alias, participant.fecha_union));
            });
        } catch (_error) {
            // Ignoramos errores de polling para no ensuciar la experiencia.
        }
    }

    fetchParticipants();
    const fetchIntervalId = setInterval(fetchParticipants, 4000);

    const iniciarBtn = document.getElementById('iniciar-tour');
    if (iniciarBtn) {
        iniciarBtn.addEventListener('click', async () => {
            const shouldStart = await ui.confirm({
                title: 'Iniciar tour',
                message: '¿Iniciar el tour? Los turistas podrán comenzar a seguirte.',
                confirmText: 'Iniciar',
                cancelText: 'Cancelar',
                type: 'info',
            });
            if (!shouldStart) return;

            try {
                const startUrl = document.querySelector('meta[name="start-tour-url"]')?.content || '';
                const resp = await fetch(startUrl, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCsrf(),
                        Accept: 'application/json',
                    },
                });

                if (!resp.ok) {
                    ui.toast(`Error iniciando el tour (${resp.status}).`, { type: 'error' });
                    return;
                }

                const data = await resp.json();
                if (data.estado !== 'en_curso') {
                    ui.toast('No se pudo iniciar el tour.', { type: 'error' });
                    return;
                }

                const dot = document.getElementById('status-dot');
                const label = document.getElementById('sesion-estado');
                if (dot) {
                    dot.style.background = 'var(--success)';
                    dot.style.boxShadow = '0 0 0 3px var(--success-light)';
                }
                if (label) {
                    label.textContent = 'EN CURSO';
                    label.style.color = 'var(--success)';
                }

                iniciarBtn.remove();
                ui.toast('¡Tour iniciado!', { type: 'success' });
            } catch (_error) {
                ui.toast('Error conectando con el servidor.', { type: 'error' });
            }
        });
    }

    document.getElementById('copy-code')?.addEventListener('click', async () => {
        await copyText('sesion-code', ui);
    });

    document.getElementById('regenerate-code')?.addEventListener('click', async () => {
        const shouldRegenerate = await ui.confirm({
            title: 'Nuevo código',
            message: '¿Generar un nuevo código de acceso?',
            confirmText: 'Generar',
            cancelText: 'Cancelar',
            type: 'info',
        });
        if (!shouldRegenerate) return;

        try {
            const regenerateUrl = document.querySelector('meta[name="regenerate-code-url"]')?.content || '';
            const resp = await fetch(regenerateUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrf(),
                    Accept: 'application/json',
                },
            });

            if (!resp.ok) {
                ui.toast(`Error regenerando código (${resp.status}).`, { type: 'error' });
                return;
            }

            const data = await resp.json();
            if (!data.codigo_acceso) {
                ui.toast('No se recibió un código válido.', { type: 'error' });
                return;
            }

            document.getElementById('sesion-code').textContent = data.codigo_acceso;
            const joinUrl = `${window.location.origin}/tours/live/code/${encodeURIComponent(data.codigo_acceso)}/`;
            const qrEl = document.getElementById('qr-code');
            if (qrEl) {
                qrEl.src = `https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${encodeURIComponent(joinUrl)}`;
            }

            ui.toast('Código regenerado correctamente.', { type: 'success' });
        } catch (_error) {
            ui.toast('Error conectando con el servidor.', { type: 'error' });
        }
    });

    const closeAccessBtn = document.getElementById('close-access');
    closeAccessBtn?.addEventListener('click', async () => {
        const shouldClose = await ui.confirm({
            title: 'Finalizar sesión',
            message: '¿Finalizar sesión? Esto cerrará el tour permanentemente y nadie podrá volver a unirse.',
            confirmText: 'Finalizar',
            cancelText: 'Cancelar',
            type: 'danger',
        });
        if (!shouldClose) return;

        closeAccessBtn.disabled = true;

        try {
            const closeUrl = document.querySelector('meta[name="close-access-url"]')?.content || '';
            const resp = await fetch(closeUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrf(),
                    Accept: 'application/json',
                },
            });

            if (!resp.ok) {
                ui.toast(`Error cerrando sesión (${resp.status}).`, { type: 'error' });
                closeAccessBtn.disabled = false;
                return;
            }

            const data = await resp.json();
            if (data.status !== 'cerrado') {
                closeAccessBtn.disabled = false;
                ui.toast('No se pudo finalizar la sesión.', { type: 'error' });
                return;
            }

            const dot = document.getElementById('status-dot');
            const label = document.getElementById('sesion-estado');
            if (dot) {
                dot.className = 'status-dot status-dot--closed';
                dot.style.background = '';
                dot.style.boxShadow = '';
            }
            if (label) {
                label.className = 'sesion-estado-label sesion-estado--closed';
                label.textContent = 'FINALIZADO';
                label.style.color = '';
            }

            const accessBlock = document.getElementById('access-block');
            if (accessBlock) {
                accessBlock.textContent = '';
                const finalDiv = document.createElement('div');
                finalDiv.className = 'session-code-display mb-4';
                finalDiv.textContent = 'SESIÓN FINALIZADA';
                finalDiv.style.background = 'var(--bg-surface)';
                finalDiv.style.color = 'var(--text-muted)';
                finalDiv.style.fontSize = '1.1rem';
                finalDiv.style.padding = '2.5rem 1rem';
                accessBlock.appendChild(finalDiv);
            }

            const btnsRow = document.getElementById('action-buttons-container');
            if (btnsRow) btnsRow.style.display = 'none';

            const closeContainer = document.getElementById('close-access-container');
            if (closeContainer) closeContainer.style.display = 'none';

            const mapLinkBtn = document.getElementById('map-link-btn');
            if (mapLinkBtn) mapLinkBtn.remove();

            const backToCatalogContainer = document.getElementById('back-to-catalog-container');
            if (backToCatalogContainer) backToCatalogContainer.classList.remove('d-none');

            clearInterval(fetchIntervalId);
            ui.toast('Sesión finalizada con éxito.', { type: 'success' });
        } catch (_error) {
            closeAccessBtn.disabled = false;
            ui.toast('Error conectando con el servidor.', { type: 'error' });
        }
    });
});
