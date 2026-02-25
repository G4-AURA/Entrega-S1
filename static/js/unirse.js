/* =========================================
   AURA - Lógica para unirse a Tours (QR y Código)
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

// --- LÓGICA DEL ESCÁNER QR ---
let html5QrCode;
const btnStartScan = document.getElementById('btn-start-scan');
const qrReaderElement = document.getElementById('qr-reader');
const codigoInput = document.getElementById('codigo-input');

if (btnStartScan) {
    btnStartScan.addEventListener('click', function() {
        qrReaderElement.style.display = 'block';
        btnStartScan.style.display = 'none';

        html5QrCode = new Html5Qrcode("qr-reader");
        const config = { fps: 10, qrbox: { width: 250, height: 250 } };
        
        html5QrCode.start({ facingMode: "environment" }, config, 
            (decodedText, decodedResult) => {
                // Éxito al leer el QR
                html5QrCode.stop().then(() => {
                    qrReaderElement.style.display = 'none';
                    btnStartScan.style.display = 'flex';
                    codigoInput.value = decodedText;
                    document.getElementById('btn-unirse').click(); // Simula el click de Unirse
                }).catch(err => console.error(err));
            },
            (errorMessage) => { /* Ignorar errores de lectura en proceso */ }
        ).catch((err) => {
            alert("No se pudo acceder a la cámara. Revisa los permisos.");
            qrReaderElement.style.display = 'none';
            btnStartScan.style.display = 'flex';
        });
    });
}

// --- LÓGICA DEL BOTÓN "VERIFICAR Y UNIRSE" ---
const btnUnirse = document.getElementById('btn-unirse');
if (btnUnirse) {
    btnUnirse.addEventListener('click', function() {
        const codigoValor = codigoInput.value.trim().toUpperCase();
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
                    window.location.href = '/tours/'; 
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
        codigoInput.focus();
    });
    
    // Limpiar input y cámara al cerrar
    joinModal.addEventListener('hidden.bs.modal', function () {
        codigoInput.value = '';
        document.getElementById('mensaje-resultado').classList.add('d-none');
        
        // Apagar cámara si el modal se cierra sin leer nada
        if (html5QrCode && html5QrCode.isScanning) {
            html5QrCode.stop().then(() => {
                qrReaderElement.style.display = 'none';
                btnStartScan.style.display = 'flex';
            }).catch(err => console.error(err));
        }
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