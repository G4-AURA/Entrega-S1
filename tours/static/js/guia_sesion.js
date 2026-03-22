function copyText(id) {
    const text = document.getElementById(id).innerText;
    if (!navigator.clipboard) {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        alert('Copiado al portapapeles');
        return;
    }
    navigator.clipboard.writeText(text)
        .then(() => alert('Copiado al portapapeles'))
        .catch(() => alert('Error copiando'));
}

function getCsrf() {
    const name = 'csrftoken=';
    const c = document.cookie.split(';').map(s => s.trim()).find(s => s.startsWith(name));
    return c ? c.substring(name.length) : '';
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
            minute: '2-digit'
        });
    } catch (e) {
        timeSpan.textContent = '';
    }

    item.appendChild(nameSpan);
    item.appendChild(timeSpan);
    return item;
}

document.addEventListener('DOMContentLoaded', function() {
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
            } else {
                participantesList.textContent = '';
                list.forEach(p => {
                    participantesList.appendChild(buildParticipantItem(p.alias, p.fecha_union));
                });
            }
        } catch (e) {
            console.error('Error fetch participants', e);
        }
    }

    fetchParticipants();
    setInterval(fetchParticipants, 4000);

    const iniciarBtn = document.getElementById('iniciar-tour');
    if (iniciarBtn) {
        iniciarBtn.addEventListener('click', async() => {
            if (!confirm('¿Iniciar el tour? Los turistas podrán comenzar a seguirte.')) return;
            try {
                const startUrl = document.querySelector('meta[name="start-tour-url"]')?.content || '';
                const resp = await fetch(startUrl, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCsrf(),
                        'Accept': 'application/json'
                    }
                });
                if (!resp.ok) {
                    alert('Error iniciando el tour: ' + resp.status);
                    return;
                }
                const data = await resp.json();
                if (data.estado === 'en_curso') {
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
                    alert('¡Tour iniciado!');
                }
            } catch (e) {
                alert('Error conectando con el servidor.');
            }
        });
    }

    document.getElementById('copy-code')?.addEventListener('click', () => copyText('sesion-code'));

    document.getElementById('regenerate-code')?.addEventListener('click', async() => {
        if (!confirm('¿Generar un nuevo código de acceso?')) return;
        try {
            const regenerateUrl = document.querySelector('meta[name="regenerate-code-url"]')?.content || '';
            const resp = await fetch(regenerateUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrf(),
                    'Accept': 'application/json'
                }
            });
            if (!resp.ok) {
                alert('Error regenerando código: ' + resp.status);
                return;
            }
            const data = await resp.json();
            if (data.codigo_acceso) {
                document.getElementById('sesion-code').textContent = data.codigo_acceso;
                const joinUrl = window.location.origin + '/tours/live/code/' + encodeURIComponent(data.codigo_acceso) + '/';
                const qrEl = document.getElementById('qr-code');
                if (qrEl) qrEl.src = 'https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=' + encodeURIComponent(joinUrl);
                alert('Código regenerado correctamente.');
            }
        } catch (e) {
            alert('Error conectando con el servidor.');
        }
    });

    document.getElementById('close-access')?.addEventListener('click', async() => {
        if (!confirm('¿Cerrar el acceso? Esto finalizará la sesión para todos.')) return;
        try {
            const closeUrl = document.querySelector('meta[name="close-access-url"]')?.content || '';
            const resp = await fetch(closeUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrf(),
                    'Accept': 'application/json'
                }
            });
            if (!resp.ok) {
                alert('Error cerrando acceso: ' + resp.status);
                return;
            }
            const data = await resp.json();
            if (data.status === 'cerrado') {
                document.getElementById('sesion-code').textContent = 'CERRADO';
                const qrEl = document.getElementById('qr-code');
                if (qrEl) qrEl.style.opacity = '0.2';
                document.getElementById('regenerate-code').disabled = true;
                document.getElementById('copy-code').disabled = true;
                document.getElementById('close-access').disabled = true;
                alert('Acceso cerrado.');
            }
        } catch (e) {
            alert('Error conectando con el servidor.');
        }
    });
});
