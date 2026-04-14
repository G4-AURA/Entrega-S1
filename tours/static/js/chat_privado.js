/* ============================================================
   AURA — Chat Privado  (chat_privado.js)

   Gestiona el canal privado Guía ↔ Turista individual.

   Funcionalidades:
     · Guía: bandeja tipo WhatsApp con lista de turistas activos,
             apertura de hilo privado por turista, polling de mensajes.
     · Turista: hilo directo con el guía, polling de mensajes.
     · Envío de texto e imágenes.
     · Gestión de badges de mensajes no leídos en la pestaña.
     · Integración con el sistema de tabs del mapa.
   ============================================================ */

'use strict';

(function () {

  // ── Variables de estado ─────────────────────────────────────────────────
  let activeTuristaId    = null;   // guía: turista del hilo abierto
  let activeTuristaAlias = null;
  let lastPrivateMsgTime = null;   // último timestamp de mensaje privado recibido
  let privatePollingId   = null;
  let bandejaPollingId   = null;
  let unreadPrivate      = 0;
  let privateTabVisible  = false;
  let selectedPrivateFile = null;
  let privatePreviewObjUrl = null;
  const MAX_PRIVATE_IMAGE_SIZE = 5 * 1024 * 1024;
  const ALLOWED_PRIVATE_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

  function notifyPrivateChat(message, type = 'warning') {
    const feedback = window.AuraFeedback;
    if (feedback && typeof feedback.toast === 'function') {
      feedback.toast(message, { type, duration: 3600 });
      return;
    }
    console.warn('[AURA private chat]', message);
  }

  // ── Referencias DOM ─────────────────────────────────────────────────────
  const privateBadge       = document.getElementById('chat-privado-badge');
  const tabPrivadoBtn      = document.querySelector('[data-tab="chat-privado"]');
  const tabChatBtn         = document.querySelector('[data-tab="chat"]');

  // ── Guía: elementos ─────────────────────────────────────────────────────
  const privateInboxView   = document.getElementById('private-inbox-view');
  const privateChatView    = document.getElementById('private-chat-view');
  const privateInbox       = document.getElementById('private-inbox');
  const btnBackToInbox     = document.getElementById('btn-back-to-inbox');
  const privateChatTitle   = document.getElementById('private-chat-title');

  // ── Compartido: mensajes, input, envío ──────────────────────────────────
  const privateChatMessages = document.getElementById('private-chat-messages');
  const privateChatInput    = document.getElementById('private-chat-input');
  const privateChatSend     = document.getElementById('private-chat-send');
  const privateImageBtn     = document.getElementById('private-image-btn');
  const privateImageInput   = document.getElementById('private-image-input');
  const privatePreviewCont  = document.getElementById('private-preview-container');

  // ── Seguridad CSRF ───────────────────────────────────────────────────────
  function getCsrf() {
    const c = document.cookie.split(';').map(s => s.trim()).find(s => s.startsWith('csrftoken='));
    return c ? c.slice('csrftoken='.length) : '';
  }

  // ── Utilidades DOM ───────────────────────────────────────────────────────
  function escHtml(t) {
    const d = document.createElement('div');
    d.textContent = String(t ?? '');
    return d.innerHTML;
  }

  function formatTime(isoString) {
    try {
      return new Date(isoString).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
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

  function incrementBadge() {
    unreadPrivate += 1;
    if (privateBadge) {
      privateBadge.textContent = unreadPrivate > 99 ? '99+' : unreadPrivate;
      privateBadge.style.display = 'block';
    }
  }

  function clearBadge() {
    unreadPrivate = 0;
    if (privateBadge) privateBadge.style.display = 'none';
  }

  // ── Renderizado de mensajes privados ─────────────────────────────────────
  function renderPrivateMessages(mensajes, containerEl) {
    if (!containerEl || !mensajes.length) return;

    containerEl.querySelector('.chat-empty')?.remove();

    const guiaUserId = null; // No necesitamos distinguir por ID: usamos es_guia del payload
    const myName = typeof currentUserName !== 'undefined' ? currentUserName : '';

    mensajes.forEach(msg => {
      if (containerEl.querySelector(`[data-message-id="${msg.id}"]`)) return;

      lastPrivateMsgTime = msg.momento;

      const isMine = msg.nombre_remitente === myName;
      const isGuide = Boolean(msg.es_guia);

      // Determinar clase CSS de la burbuja
      let bubbleClass = '';
      if (isMine) {
        bubbleClass = isGuide ? 'private-sent' : 'private-sent';
      } else {
        bubbleClass = 'private-received';
      }

      const div = document.createElement('div');
      div.className = `chat-message ${isMine ? 'sent ' : 'received '}${bubbleClass}`;
      div.setAttribute('data-message-id', msg.id);

      const textoHtml  = msg.texto  ? escHtml(msg.texto)  : '';
      const imagenHtml = msg.imagen_url
        ? `<a href="/tours/sesiones/${sesionId}/mensajes/${msg.id}/imagen/" title="Descargar imagen">
             <img src="${escHtml(msg.imagen_url)}" class="chat-message-img" alt="Imagen adjunta">
           </a>`
        : '';
      const bubbleHtml = textoHtml ? `<div class="chat-message-bubble">${textoHtml}</div>` : '';

      div.innerHTML = `
        <div class="chat-message-header">
          <span class="chat-message-sender">${escHtml(msg.nombre_remitente)}</span>
          <span class="chat-message-time">${formatTime(msg.momento)}</span>
        </div>
        ${bubbleHtml}
        ${imagenHtml}`;

      containerEl.appendChild(div);
    });

    containerEl.scrollTop = containerEl.scrollHeight;
  }

  // ── Polling de mensajes privados ─────────────────────────────────────────
  function buildPrivateMensajesUrl(turistaId) {
    let url = `${mensajesPrivadosBaseUrl}${turistaId}/mensajes/`;
    if (lastPrivateMsgTime) {
      try {
        url += `?desde=${encodeURIComponent(new Date(lastPrivateMsgTime).toISOString())}`;
      } catch {
        url += `?desde=${encodeURIComponent(lastPrivateMsgTime)}`;
      }
    }
    return url;
  }

  function fetchPrivateMessages(turistaId) {
    if (!turistaId) return;
    fetch(buildPrivateMensajesUrl(turistaId))
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => {
        const msgs = data.mensajes || [];
        if (!msgs.length) return;

        renderPrivateMessages(msgs, privateChatMessages);

        // Badge si la pestaña no está visible
        if (!privateTabVisible) {
          msgs.forEach(m => {
            const myName = typeof currentUserName !== 'undefined' ? currentUserName : '';
            if (m.nombre_remitente !== myName) incrementBadge();
          });
        }
      })
      .catch(() => {});
  }

  function startPrivatePolling(turistaId) {
    stopPrivatePolling();
    fetchPrivateMessages(turistaId);
    privatePollingId = setInterval(() => fetchPrivateMessages(turistaId), 4000);
  }

  function stopPrivatePolling() {
    if (privatePollingId) {
      clearInterval(privatePollingId);
      privatePollingId = null;
    }
  }

  // ── Polling turista — mensajes privados (sin turista_id en URL, usa cookie) ─
  // El turista siempre consulta su propio hilo
  function fetchPrivateMessagesTurista() {
    if (typeof turistaId === 'undefined' || !turistaId) return;
    fetch(buildPrivateMensajesUrl(turistaId))
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => {
        const msgs = data.mensajes || [];
        if (!msgs.length) return;
        renderPrivateMessages(msgs, privateChatMessages);
        if (!privateTabVisible) {
          const myName = typeof currentUserName !== 'undefined' ? currentUserName : '';
          msgs.forEach(m => {
            if (m.nombre_remitente !== myName) incrementBadge();
          });
        }
      })
      .catch(() => {});
  }

  // ── Bandeja del guía ──────────────────────────────────────────────────────
  function renderBandeja(bandeja) {
    if (!privateInbox) return;

    if (!bandeja.length) {
      privateInbox.innerHTML = `
        <div class="inbox-empty">
          <span class="material-icons-round">people_outline</span>
          <p>Aún no hay turistas activos en la sesión.</p>
        </div>`;
      return;
    }

    // Actualizar items existentes sin destruir el DOM completo
    const existingIds = new Set(
      Array.from(privateInbox.querySelectorAll('.private-inbox-item'))
        .map(el => el.dataset.turistaId)
    );

    bandeja.forEach(item => {
      const idStr = String(item.turista_id);
      let el = privateInbox.querySelector(`.private-inbox-item[data-turista-id="${idStr}"]`);

      if (!el) {
        el = document.createElement('div');
        el.className = 'private-inbox-item';
        el.setAttribute('data-turista-id', idStr);
        el.setAttribute('tabindex', '0');
        el.setAttribute('role', 'button');
        el.setAttribute('aria-label', `Chat privado con ${item.alias}`);
        privateInbox.querySelector('.inbox-empty')?.remove();
        privateInbox.appendChild(el);

        el.addEventListener('click', () => abrirHiloPrivado(item.turista_id, item.alias));
        el.addEventListener('keydown', e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            abrirHiloPrivado(item.turista_id, item.alias);
          }
        });
      }

      const inicial = (item.alias || '?').charAt(0).toUpperCase();
      const preview = item.ultimo_mensaje
        ? escHtml(item.ultimo_mensaje)
        : '<span style="font-style:italic;opacity:.7;">Sin mensajes</span>';
      const hora = item.ultimo_momento ? formatTime(item.ultimo_momento) : '';

      el.innerHTML = `
        <div class="inbox-avatar">${escHtml(inicial)}</div>
        <div class="inbox-info">
          <p class="inbox-alias">${escHtml(item.alias)}</p>
          <p class="inbox-preview">${preview}</p>
        </div>
        <div class="inbox-meta">
          <span class="inbox-time">${hora}</span>
        </div>`;

      // Marcar como activo si es el hilo abierto
      el.classList.toggle('active', activeTuristaId === item.turista_id);

      existingIds.delete(idStr);
    });

    // Eliminar items que ya no están (turistas inactivos)
    existingIds.forEach(id => {
      privateInbox.querySelector(`.private-inbox-item[data-turista-id="${id}"]`)?.remove();
    });
  }

  function fetchBandeja() {
    if (!esGuia) return;
    fetch(bandejaPrivadaUrl)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => renderBandeja(data.bandeja || []))
      .catch(() => {});
  }

  function startBandejaPolling() {
    fetchBandeja();
    bandejaPollingId = setInterval(fetchBandeja, 8000);
  }

  function stopBandejaPolling() {
    if (bandejaPollingId) {
      clearInterval(bandejaPollingId);
      bandejaPollingId = null;
    }
  }

  // ── Abrir hilo privado (guía) ─────────────────────────────────────────────
  function abrirHiloPrivado(turistaId, alias) {
    activeTuristaId    = turistaId;
    activeTuristaAlias = alias;
    lastPrivateMsgTime = null;

    // Limpiar mensajes anteriores
    if (privateChatMessages) {
      privateChatMessages.innerHTML = `
        <div class="chat-empty">
          <span class="material-icons-round">lock_open</span>
          <p>Empieza la conversación privada</p>
        </div>`;
    }

    // Título del hilo
    if (privateChatTitle) privateChatTitle.textContent = alias;

    // Cambiar vistas
    if (privateInboxView) privateInboxView.style.display = 'none';
    if (privateChatView)  privateChatView.style.display  = 'flex';

    // Focus en el input
    if (privateChatInput) privateChatInput.focus();

    // Iniciar polling
    startPrivatePolling(turistaId);
  }

  function volverBandeja() {
    stopPrivatePolling();
    activeTuristaId    = null;
    activeTuristaAlias = null;
    lastPrivateMsgTime = null;

    if (privateChatView)  privateChatView.style.display  = 'none';
    if (privateInboxView) privateInboxView.style.display = 'block';
  }

  // ── Envío de mensajes privados ────────────────────────────────────────────
  function clearPrivatePreview() {
    if (privatePreviewObjUrl) {
      URL.revokeObjectURL(privatePreviewObjUrl);
      privatePreviewObjUrl = null;
    }
    selectedPrivateFile = null;
    if (privateImageInput)  privateImageInput.value = '';
    if (privatePreviewCont) privatePreviewCont.innerHTML = '';
  }

  function renderPrivatePreview(file) {
    if (privatePreviewObjUrl) URL.revokeObjectURL(privatePreviewObjUrl);
    privatePreviewObjUrl = URL.createObjectURL(file);
    if (!privatePreviewCont) return;
    privatePreviewCont.innerHTML = `
      <div class="chat-preview-item">
        <img src="${privatePreviewObjUrl}" alt="Vista previa" class="chat-preview-img">
        <button type="button" class="chat-preview-remove" title="Quitar imagen" id="private-preview-remove">
          <span class="material-icons-round">close</span>
        </button>
      </div>`;
    document.getElementById('private-preview-remove')?.addEventListener('click', clearPrivatePreview);
  }

  function sendPrivateMessage() {
    const texto = privateChatInput ? privateChatInput.value.trim() : '';
    if (!texto && !selectedPrivateFile) {
      notifyPrivateChat('El mensaje no puede estar vacío.', 'warning');
      return;
    }

    // Bloquear controles durante el envío
    [privateChatSend, privateChatInput, privateImageBtn].forEach(el => {
      if (el) el.disabled = true;
    });

    const formData = new FormData();
    formData.append('texto', texto);
    formData.append('es_privado', 'true');

    // El guía indica el destinatario; el turista no lo indica (destinatario implícito = guía)
    if (esGuia && activeTuristaId) {
      formData.append('destinatario_turista_id', activeTuristaId);
    }

    if (selectedPrivateFile) {
      formData.append('imagen', selectedPrivateFile);
    }

    fetch(enviarMensajeUrl, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf() },
      body: formData,
    })
      .then(async (r) => {
        const data = await readJsonOrText(r);
        if (!r.ok || data?.status !== 'ok') {
          throw new Error(extraerMensajeDeError(data, 'No se pudo enviar el mensaje.'));
        }

        if (privateChatInput) privateChatInput.value = '';
        clearPrivatePreview();

        // Recargar mensajes inmediatamente
        if (esGuia && activeTuristaId) {
          fetchPrivateMessages(activeTuristaId);
        } else if (!esGuia && turistaId) {
          fetchPrivateMessagesTurista();
        }
      })
      .catch((error) => {
        notifyPrivateChat(error?.message || 'No se pudo enviar el mensaje.', 'error');
      })
      .finally(() => {
        [privateChatSend, privateChatInput, privateImageBtn].forEach(el => {
          if (el) el.disabled = false;
        });
        if (privateChatInput) privateChatInput.focus();
      });
  }

  // ── Gestión de tabs ───────────────────────────────────────────────────────
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', function () {
      const target = this.getAttribute('data-tab');
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      this.classList.add('active');
      document.getElementById('tab-' + target)?.classList.add('active');

      if (target === 'chat-privado') {
        privateTabVisible = true;
        clearBadge();
        if (esGuia) {
          // Actualizar bandeja al abrir
          fetchBandeja();
          // Si hay hilo abierto, activar polling
          if (activeTuristaId) startPrivatePolling(activeTuristaId);
          else stopPrivatePolling();
        } else {
          // Turista: arrancar polling del hilo con el guía
          startPrivatePollingTurista();
        }
      } else {
        privateTabVisible = false;
        stopPrivatePolling();
      }

      if (target === 'chat') {
        const badge = document.getElementById('chat-badge');
        if (badge) badge.style.display = 'none';
        document.dispatchEvent(new CustomEvent('chatOpened'));
      }
    });
  });

  function startPrivatePollingTurista() {
    stopPrivatePolling();
    fetchPrivateMessagesTurista();
    privatePollingId = setInterval(fetchPrivateMessagesTurista, 4000);
  }

  // ── Event listeners ───────────────────────────────────────────────────────
  if (btnBackToInbox) {
    btnBackToInbox.addEventListener('click', volverBandeja);
  }

  if (privateChatSend) {
    privateChatSend.addEventListener('click', sendPrivateMessage);
  }

  if (privateChatInput) {
    privateChatInput.addEventListener('keypress', e => {
      if (e.key === 'Enter') sendPrivateMessage();
    });
  }

  if (privateImageBtn && privateImageInput) {
    privateImageBtn.addEventListener('click', () => privateImageInput.click());
    privateImageInput.addEventListener('change', () => {
      if (!privateImageInput.files || !privateImageInput.files.length) {
        clearPrivatePreview();
        return;
      }
      const file = privateImageInput.files[0];
      if (!ALLOWED_PRIVATE_IMAGE_TYPES.has(file.type)) {
        notifyPrivateChat('Formato de imagen no permitido. Usa JPEG, PNG o WebP.', 'warning');
        clearPrivatePreview();
        return;
      }
      if (file.size > MAX_PRIVATE_IMAGE_SIZE) {
        notifyPrivateChat('La imagen supera el tamaño máximo de 5MB.', 'warning');
        clearPrivatePreview();
        return;
      }
      selectedPrivateFile = file;
      renderPrivatePreview(file);
    });
  }

  // ── Inicialización ─────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    if (esGuia) {
      startBandejaPolling();
    }
    // El turista inicia polling solo cuando abre la pestaña privada (ahorra requests)
  });

})();