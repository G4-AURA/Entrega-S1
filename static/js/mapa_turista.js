/* =========================================
   AURA - Lógica del Mapa Inmersivo del Turista
========================================= */

let guiaMarker = null;
let map = null;

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
    map = L.map('mapa-tour', {
        zoomControl: false 
    }).setView([37.3891, -5.9845], 16);

    const token = typeof mapboxToken !== 'undefined' ? mapboxToken : 'pk.tu_token_aqui';

    // Capa Híbrida de Mapbox (Satélite + Calles)
    L.tileLayer('https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12/tiles/256/{z}/{x}/{y}@2x?access_token=' + token, {
        maxZoom: 19,
        attribution: '© Mapbox © OpenStreetMap'
    }).addTo(map);

    // TODOS los usuarios rastrean su propia ubicación localmente para verse a sí mismos
    iniciarRastreoLocal();

    // SOLO los turistas necesitan pedir la ubicación del guía al servidor
    if (typeof esGuia !== 'undefined' && !esGuia) {
        obtenerUbicacionGuia();
        setInterval(obtenerUbicacionGuia, 5000);
    }

    // 3. Renderizar Paradas Dinámicamente
    if (typeof paradasData !== 'undefined' && Array.isArray(paradasData)) {
        const bounds = [];
        
        paradasData.forEach(function(parada) {
            if (parada.lat != null && parada.lng != null) {
                // Crear icono según si es la parada actual o no
                const iconHtml = parada.es_actual 
                    ? `<div style="background: linear-gradient(135deg, #10B981, #059669); width: 32px; height: 32px; border-radius: 50%; border: 4px solid white; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.6); display: flex; align-items: center; justify-content: center;">
                         <span style="color: white; font-size: 18px; font-weight: bold;">${parada.orden}</span>
                       </div>`
                    : `<div style="background-color: #9CA3AF; width: 24px; height: 24px; border-radius: 50%; border: 3px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.3); opacity: 0.7; display: flex; align-items: center; justify-content: center;">
                         <span style="color: white; font-size: 12px; font-weight: bold;">${parada.orden}</span>
                       </div>`;
                
                const icon = L.divIcon({
                    className: 'custom-div-icon',
                    html: iconHtml,
                    iconSize: parada.es_actual ? [32, 32] : [24, 24],
                    iconAnchor: parada.es_actual ? [16, 16] : [12, 12]
                });

                const marker = L.marker([parada.lat, parada.lng], {icon: icon}).addTo(map);
                marker.bindPopup(`<strong>${parada.nombre}</strong><br>Parada ${parada.orden}`);
                
                bounds.push([parada.lat, parada.lng]);
                
                // Centrar el mapa en la parada actual
                if (parada.es_actual) {
                    map.setView([parada.lat, parada.lng], 17);
                }
            }
        });
        
        // Si hay paradas pero ninguna es actual, ajustar bounds para mostrar todas
        if (bounds.length > 0 && !paradasData.some(p => p.es_actual)) {
            map.fitBounds(bounds, {padding: [50, 50]});
        }
    }

    // 4. Lógica del Panel Expandible (Bottom Sheet)
    const tourPanel = document.querySelector('.tour-panel');
    const panelHeader = document.querySelector('.panel-header');

    if (tourPanel && panelHeader) {
        panelHeader.addEventListener('click', function() {
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
                
                // Resetear contador de mensajes no leídos dentro del scope de initChat
                // Esto se manejará desde initChat
                const event = new CustomEvent('chatOpened');
                document.dispatchEvent(event);
            }
        });
    });

    // 6. Sistema de Chat
    initChat();
});

let miUbicacionMarker = null;

function iniciarRastreoLocal() {
    if (navigator.geolocation) {

        navigator.geolocation.watchPosition(position => {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;
            const pos = [lat, lng];

            // --- 1. MOSTRAR MI UBICACIÓN (En mi pantalla solamente) ---
            if (!miUbicacionMarker) {
                // Definimos un estilo azul para el turista y rojo para el guía viéndose a sí mismo
                const iconHtml = esGuia 
                    ? '<div style="background-color: #ef4444; width: 20px; height: 20px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 15px rgba(239, 68, 68, 0.8);"></div>'
                    : '<div style="background-color: #3b82f6; width: 18px; height: 18px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 10px rgba(59, 130, 246, 0.8);"></div>';

                const miIcon = L.divIcon({
                    className: 'mi-ubicacion-marker',
                    html: iconHtml,
                    iconSize: [24, 24],
                    iconAnchor: [12, 12]
                });

                miUbicacionMarker = L.marker(pos, {icon: miIcon, zIndexOffset: 1000}).addTo(map);
                miUbicacionMarker.bindPopup(esGuia ? "Mi Ubicación (Guía)" : "Mi Ubicación");
            } else {
                miUbicacionMarker.setLatLng(pos);
            }

            // --- 2. ENVIAR AL SERVIDOR (Solo si soy el guía) ---
            if (typeof esGuia !== 'undefined' && esGuia) {
                fetch('/tours/ubicacion/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify({
                        latitud: lat,
                        longitud: lng,
                        sesion_id: sesionId
                    })
                }).catch(err => console.error("Error enviando ubicación al servidor:", err));
            }

        }, error => {
            console.warn("Error de geolocalización: ", error);
        }, {
            enableHighAccuracy: true,
            maximumAge: 0,
            timeout: 5000
        });
    }
}

function obtenerUbicacionGuia() {
    if (!map) return;
    
    fetch(`/tours/sesiones/${sesionId}/ubicacion_guia/`)
        .then(response => response.json())
        .then(data => {
            if (data.lat && data.lng) {
                const pos = [data.lat, data.lng];
                
                if (!guiaMarker) {
                    const guiaIcon = L.divIcon({
                        className: 'guia-marker-container',
                        html: '<div style="background-color: #ef4444; width: 28px; height: 28px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 15px rgba(239, 68, 68, 0.8); display:flex; justify-content:center; align-items:center;"><span class="material-icons-round" style="font-size: 16px; color: white;">flag</span></div>',
                        iconSize: [34, 34],
                        iconAnchor: [17, 17]
                    });
                    
                    guiaMarker = L.marker(pos, {icon: guiaIcon, zIndexOffset: 900}).addTo(map);
                    guiaMarker.bindPopup("Ubicación del Guía");
                } else {
                    guiaMarker.setLatLng(pos);
                }
            }
        })
        .catch(error => console.error("Error obteniendo ubicación del guía:", error));
}

// FUNCIÓN DE POLLING PARA MOSTRAR AL GUÍA

function getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value || 
               document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
}

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
    let unreadCount = 0; // Contador de mensajes no leídos

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

    // Listener para resetear contador cuando se abre el chat
    document.addEventListener('chatOpened', () => {
        unreadCount = 0;
    });

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
            // Normalizar la fecha a ISO 8601 para evitar formatos inválidos
            let dateStr;
            const parsedDate = new Date(lastMessageTime);
            if (!isNaN(parsedDate)) {
                dateStr = parsedDate.toISOString();
            } else {
                // Si no se puede parsear, enviar el valor tal cual
                dateStr = lastMessageTime;
            }
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
                // Identificar mensajes realmente nuevos (que no existen en el DOM)
                const currentUser = getCurrentUsername();
                const newMessagesFromOthers = data.mensajes.filter(msg => {
                    const isNew = !document.querySelector(`[data-message-id="${msg.id}"]`);
                    const isFromOther = msg.nombre_remitente !== currentUser;
                    return isNew && isFromOther;
                }).length;

                displayMessages(data.mensajes);
                
                // Actualizar el timestamp del último mensaje
                const ultimoMensaje = data.mensajes[data.mensajes.length - 1];
                lastMessageTime = ultimoMensaje.momento;

                // Si no estamos en el chat y hay mensajes nuevos de otros, incrementar contador
                if (!isCurrentlyInChat && newMessagesFromOthers > 0) {
                    unreadCount += newMessagesFromOthers;
                    showChatBadge(unreadCount);
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
            const isSent = mensaje.nombre_remitente === currentUser;
            
            messageDiv.className = `chat-message ${isSent ? 'sent' : 'received'}`;
            messageDiv.setAttribute('data-message-id', mensaje.id);

            // Formatear timestamp
            const timestamp = new Date(mensaje.momento);
            const timeStr = timestamp.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });

            messageDiv.innerHTML = `
                <div class="chat-message-header">
                    <span class="chat-message-sender">${escapeHtml(mensaje.nombre_remitente)}</span>
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
        return (typeof currentUserName !== 'undefined' && currentUserName) ? 
               currentUserName : 
               (document.body.getAttribute('data-username') || 'usuario');
    }

    // Función helper para escapar HTML
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Iniciar polling cada 3 segundos
    fetchMessages(); // Primera carga inmediata
    setInterval(fetchMessages, 5000);
}
