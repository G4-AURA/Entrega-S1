/* =========================================
   AURA - Lógica del Mapa Inmersivo del Turista
========================================= */

document.addEventListener('DOMContentLoaded', function() {
    
    const mapElement = document.getElementById('mapa-tour');
    if (!mapElement) return;

    // 1. UX: Ocultar el Navbar
    const navbar = document.querySelector('.navbar');
    if (navbar) navbar.style.display = 'none';
    
    const mainContainer = document.querySelector('main.container');
    if (mainContainer) {
        mainContainer.style.maxWidth = '100%';
        mainContainer.style.padding = '0';
    }

    // 2. Inicialización de Leaflet
    var map = L.map('mapa-tour', {
        zoomControl: false 
    }).setView([37.3891, -5.9845], 16); // Un poco más de zoom inicial (16)

    const token = typeof mapboxToken !== 'undefined' ? mapboxToken : 'pk.tu_token_aqui';

    // NUEVO: Capa Híbrida de Mapbox (Satélite + Calles)
    L.tileLayer('https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12/tiles/256/{z}/{x}/{y}@2x?access_token=' + token, {
        maxZoom: 19,
        attribution: '© Mapbox © OpenStreetMap'
    }).addTo(map);

    // 3. Marcadores Estáticos
    var iconParada = L.divIcon({
        className: 'custom-div-icon',
        html: "<div style='background-color:#4F46E5; width:20px; height:20px; border-radius:50%; border:3px solid white; box-shadow: 0 2px 5px rgba(0,0,0,0.3);'></div>",
        iconSize: [20, 20],
        iconAnchor: [10, 10]
    });

    L.marker([37.3860, -5.9926], {icon: iconParada}).addTo(map); 
    L.marker([37.3888, -5.9946], {icon: iconParada}).addTo(map);

    // 4. Lógica del Panel Expandible (Bottom Sheet)
    const tourPanel = document.querySelector('.tour-panel');
    const panelHeader = document.querySelector('.panel-header');

    if (tourPanel && panelHeader) {
        panelHeader.addEventListener('click', function() {
            // Alterna la clase 'expanded' cada vez que se hace clic en la cabecera
            tourPanel.classList.toggle('expanded');
        });
    }

    // 5. Lógica de Tabs (Itinerario / Chat)
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const targetTab = this.getAttribute('data-tab');
            
            // Remover clase active de todos los botones y contenidos
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            // Agregar clase active al botón clickeado y su contenido
            this.classList.add('active');
            document.getElementById('tab-' + targetTab).classList.add('active');

            // Si cambiamos a chat, limpiar badge y marcar como leídos
            if (targetTab === 'chat') {
                const badge = document.getElementById('chat-badge');
                if (badge) badge.style.display = 'none';
            }
        });
    });

    // 6. Sistema de Chat
    initChat();
});

/* =========================================
   AURA - Sistema de Chat Turista
========================================= */
function initChat() {
    if (typeof sesionId === 'undefined') {
        console.error('sesionId no está definido');
        return;
    }

    const chatInput = document.getElementById('chat-input');
    const chatSendBtn = document.getElementById('chat-send');
    const chatMessages = document.getElementById('chat-messages');
    let lastMessageTime = null;
    let isCurrentlyInChat = false;

    // Detectar si el usuario está viendo el chat
    const observer = new MutationObserver(() => {
        const chatTab = document.getElementById('tab-chat');
        isCurrentlyInChat = chatTab && chatTab.classList.contains('active');
    });

    const chatTab = document.getElementById('tab-chat');
    if (chatTab) {
        observer.observe(chatTab, { attributes: true, attributeFilter: ['class'] });
        isCurrentlyInChat = chatTab.classList.contains('active');
    }

    // Función para enviar mensaje
    function sendMessage() {
        const texto = chatInput.value.trim();
        if (!texto) return;

        // Deshabilitar input mientras se envía
        chatSendBtn.disabled = true;
        chatInput.disabled = true;

        fetch(`/tours/sesiones/${sesionId}/mensajes/enviar/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ texto: texto })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Error al enviar mensaje:', data.error);
                alert('Error al enviar mensaje: ' + data.error);
            } else {
                // Limpiar input
                chatInput.value = '';
                // Obtener mensajes actualizados inmediatamente
                fetchMessages();
            }
        })
        .catch(error => {
            console.error('Error de red:', error);
            alert('Error al enviar el mensaje. Por favor, inténtalo de nuevo.');
        })
        .finally(() => {
            chatSendBtn.disabled = false;
            chatInput.disabled = false;
            chatInput.focus();
        });
    }

    // Event listeners
    chatSendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });

    // Función para obtener mensajes
    function fetchMessages() {
        let url = `/tours/sesiones/${sesionId}/mensajes/`;
        if (lastMessageTime) {
            // Asegurar que la fecha esté en formato correcto (sin microsegundos si causan problema)
            const dateStr = lastMessageTime.split('.')[0] + 'Z';
            url += `?desde=${encodeURIComponent(dateStr)}`;
        }

        fetch(url)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Error al obtener mensajes:', data.error);
                return;
            }

            if (data.mensajes && data.mensajes.length > 0) {
                displayMessages(data.mensajes);
                
                // Actualizar el timestamp del último mensaje
                const ultimoMensaje = data.mensajes[data.mensajes.length - 1];
                lastMessageTime = ultimoMensaje.momento;

                // Si no estamos en el chat, mostrar badge
                if (!isCurrentlyInChat && data.mensajes.length > 0) {
                    showChatBadge(data.mensajes.length);
                }
            }
        })
        .catch(error => {
            console.error('Error al obtener mensajes:', error);
        });
    }

    // Función para mostrar mensajes
    function displayMessages(mensajes) {
        // Remover el mensaje de "chat vacío" si existe
        const emptyMsg = chatMessages.querySelector('.chat-empty');
        if (emptyMsg) {
            emptyMsg.remove();
        }

        // Obtener el username del usuario actual
        const currentUser = getCurrentUsername();

        mensajes.forEach(mensaje => {
            // Verificar si el mensaje ya existe (por su ID)
            if (document.querySelector(`[data-message-id="${mensaje.id}"]`)) {
                return; // Ya existe, no lo agregamos de nuevo
            }

            const messageDiv = document.createElement('div');
            const isSent = mensaje.remitente__username === currentUser;
            
            messageDiv.className = `chat-message ${isSent ? 'sent' : 'received'}`;
            messageDiv.setAttribute('data-message-id', mensaje.id);

            // Formatear timestamp
            const timestamp = new Date(mensaje.momento);
            const timeStr = timestamp.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });

            messageDiv.innerHTML = `
                <div class="chat-message-header">
                    <span class="chat-message-sender">${mensaje.remitente__username}</span>
                    <span class="chat-message-time">${timeStr}</span>
                </div>
                <div class="chat-message-bubble">
                    ${escapeHtml(mensaje.texto)}
                </div>
            `;

            chatMessages.appendChild(messageDiv);
        });

        // Scroll al final
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Función para mostrar badge con contador
    function showChatBadge(count) {
        const badge = document.getElementById('chat-badge');
        if (badge) {
            badge.textContent = count > 99 ? '99+' : count;
            badge.style.display = 'block';
        }
    }

    // Función para obtener el username actual
    function getCurrentUsername() {
        return document.body.getAttribute('data-username') || 'usuario';
    }

    // Función helper para escapar HTML
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Función helper para obtener CSRF token
    function getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value || 
               document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
    }

    // Iniciar polling cada 3 segundos
    fetchMessages(); // Primera carga inmediata
    setInterval(fetchMessages, 3000);
}
