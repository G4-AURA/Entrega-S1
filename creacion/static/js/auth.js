document.addEventListener("DOMContentLoaded", function() {
    // Aplicar estilos a inputs de formularios sin estilos
    document.querySelectorAll('.auth-card input:not([type="hidden"]), .auth-card select').forEach(function(el) {
        el.classList.add('form-control');
    });

    document.querySelectorAll('.django-form input:not([type="hidden"]), .django-form select').forEach(function(el) {
        el.classList.add('form-control');
    });

    // Lógica específica del modal de acceso a tour
    const btnIrTour = document.getElementById('btn-ir-tour');
    const codigoInput = document.getElementById('codigo-input');
    const mensajeDiv = document.getElementById('mensaje-codigo');

    if (btnIrTour && codigoInput) {
        function mostrarError(msg) {
            mensajeDiv.textContent = msg;
            mensajeDiv.classList.remove('d-none');
        }

        function irAlTour() {
            const codigo = codigoInput.value.trim().toUpperCase();
            mensajeDiv.classList.add('d-none');
            if (!codigo) {
                mostrarError('Por favor, introduce un código válido.');
                return;
            }
            window.location.href = `/tours/live/code/${codigo}/`;
        }

        btnIrTour.addEventListener('click', irAlTour);
        codigoInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                irAlTour();
            }
        });
        codigoInput.addEventListener('input', function() {
            mensajeDiv.classList.add('d-none');
        });
    }
});
