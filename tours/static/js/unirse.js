/* =========================================
   AURA - Lógica para unirse a Tours (Código manual)
========================================= */

// Utilidad para extraer el CSRF Token de las cookies de Django
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

const codigoInput = document.getElementById('codigo-input');

// --- LÓGICA DEL BOTÓN "VERIFICAR Y UNIRSE" ---
const btnUnirse = document.getElementById('btn-unirse');
if (btnUnirse) {
    btnUnirse.addEventListener('click', function() {
        const codigoValor = (codigoInput?.value || '').trim().toUpperCase();
        const mensajeDiv = document.getElementById('mensaje-resultado');
        const csrftoken = getCookie('csrftoken');

        // Resetear mensajes
        mensajeDiv.classList.add('d-none');
        mensajeDiv.classList.remove('alert-success', 'alert-danger');

        if (!codigoValor) {
            mensajeDiv.innerText = "Por favor, introduce un código válido.";
            mensajeDiv.classList.add('alert-danger');
            mensajeDiv.classList.remove('d-none');
            return;
        }

        const originalText = this.innerText;
        this.disabled = true;
        this.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Conectando...';

        // Petición POST al endpoint
        fetch('/tours/sesiones/unirse/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({ codigo_acceso: codigoValor })
        })
        .then(response => response.json().then(data => ({ status: response.status, body: data })))
        .then(result => {
            mensajeDiv.classList.remove('d-none');
            
            if (result.status === 200) {
                // Éxito
                mensajeDiv.innerHTML = "<strong>¡Conectado!</strong> Preparando el mapa en vivo...";
                mensajeDiv.classList.add('alert-success');
                
                // Redirección suave al mapa
                setTimeout(() => {
                    window.location.href = '/tours/turista';
                }, 1500);
            } else {
                // Error de validación del backend
                mensajeDiv.innerText = result.body.error || "Código inválido o tour no disponible.";
                mensajeDiv.classList.add('alert-danger');
                this.disabled = false;
                this.innerText = originalText;
            }
        })
        .catch(error => {
            // Error de red
            mensajeDiv.innerText = "Error de conexión con el servidor.";
            mensajeDiv.classList.remove('d-none', 'alert-success');
            mensajeDiv.classList.add('alert-danger');
            this.disabled = false;
            this.innerText = originalText;
        });
    });
}

// --- ACCESIBILIDAD Y UX DEL MODAL ---
const joinModal = document.getElementById('joinModal');
if (joinModal) {
    // Auto-focus en el input al abrir
    joinModal.addEventListener('shown.bs.modal', function () {
        if (codigoInput) {
            codigoInput.focus();
        }
    });
    
    // Limpiar input al cerrar
    joinModal.addEventListener('hidden.bs.modal', function () {
        if (codigoInput) {
            codigoInput.value = '';
        }
        document.getElementById('mensaje-resultado')?.classList.add('d-none');
    });
}

// Permitir pulsar "Enter" en el input para enviar
if (codigoInput) {
    codigoInput.addEventListener("keypress", function(event) {
        if (event.key === "Enter") {
            event.preventDefault();
            document.getElementById('btn-unirse').click();
        }
    });
}
