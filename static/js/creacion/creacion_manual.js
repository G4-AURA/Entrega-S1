(function () {
    const config = JSON.parse(document.getElementById('creacion-manual-config').textContent);

    const container = document.getElementById('stops-container');
    const display = document.getElementById('counter-display');
    const btnAddStop = document.getElementById('btn-add-stop');
    const btnRemoveStop = document.getElementById('btn-remove-stop');
    const btnGuardar = document.getElementById('btn-guardar-tour');
    const mapModal = document.getElementById('map-modal-overlay');

    let stopCount = container.querySelectorAll('.stop-card').length;
    let currentInputTarget = null;

    const selectorUbicacion = window.MapaCreacion.crearSelectorUbicacion({
        mapId: 'leaflet-map',
        initialCoords: [37.3886, -5.9823],
    });

    function updateDisplay() {
        display.innerText = stopCount;
    }

    function crearTarjetaParada(index) {
        return `<div class="stop-card" id="stop-${index}">
            <div class="stop-header">
                <span class="stop-number-badge">PARADA ${index}</span>
                <span class="material-icons-round" style="color: var(--text-sec); cursor: grab;">drag_handle</span>
            </div>

            <div class="image-upload-area" id="img-area-${index}" data-file-input="file-${index}">
                <span class="material-icons-round">add_photo_alternate</span>
                <span class="image-upload-text">Cargar Imagen</span>
            </div>
            <input type="file" id="file-${index}" hidden accept="image/*" data-stop-id="${index}">

            <div class="form-group">
                <label class="input-label">Nombre del Lugar</label>
                <input type="text" class="input-field stop-nombre" placeholder="Nombre...">
            </div>

            <div class="form-group" style="margin-bottom: 0;">
                <label class="input-label">Ubicación</label>
                <div class="location-group">
                    <input type="text" class="input-field stop-ubicacion" placeholder="Dirección...">
                    <button class="btn-map"><span class="material-icons-round">map</span></button>
                </div>
            </div>
        </div>`;
    }

    function previewImage(input, id) {
        if (!input.files || !input.files[0]) {
            return;
        }

        const reader = new FileReader();
        reader.onload = function (event) {
            const area = document.getElementById(`img-area-${id}`);
            area.style.backgroundImage = `url(${event.target.result})`;
            area.innerHTML = '';
            area.style.border = 'none';
        };
        reader.readAsDataURL(input.files[0]);
    }

    function addStop() {
        stopCount += 1;
        updateDisplay();

        container.insertAdjacentHTML('beforeend', crearTarjetaParada(stopCount));
        document.getElementById(`stop-${stopCount}`).scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function removeStop() {
        if (stopCount <= 1) {
            return;
        }

        const el = document.getElementById(`stop-${stopCount}`);
        if (el) {
            el.remove();
        }
        stopCount -= 1;
        updateDisplay();
    }

    function leerFormulario() {
        const paradas = Array.from(container.querySelectorAll('.stop-card')).map(function (card, index) {
            const nombreInput = card.querySelector('.stop-nombre');
            const ubicacionInput = card.querySelector('.stop-ubicacion');

            return {
                nombre: nombreInput && nombreInput.value ? nombreInput.value : `Parada ${index + 1}`,
                direccion: ubicacionInput ? ubicacionInput.value : '',
                lat: ubicacionInput && ubicacionInput.dataset.lat ? parseFloat(ubicacionInput.dataset.lat) : 37.38,
                lon: ubicacionInput && ubicacionInput.dataset.lon ? parseFloat(ubicacionInput.dataset.lon) : -5.99,
            };
        });

        return {
            titulo: document.getElementById('ruta-titulo').value,
            descripcion: document.getElementById('ruta-descripcion').value,
            duracion_horas: document.getElementById('ruta-duracion').value,
            num_personas: document.getElementById('ruta-personas').value,
            nivel_exigencia: document.getElementById('ruta-exigencia').value,
            mood: [],
            paradas,
        };
    }

    async function enviarPeticion(payload) {
        const response = await fetch(config.urls.guardarManual, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': config.csrfToken,
            },
            body: JSON.stringify(payload),
        });

        const data = await response.json();
        if (!response.ok || data.status !== 'OK') {
            throw new Error(data.mensaje || 'Error desconocido al guardar la ruta');
        }

        return data;
    }

    function renderizarMapa() {
        mapModal.style.display = 'flex';
        selectorUbicacion.open();
    }

    function renderizarErrores(mensaje) {
        alert(`Ocurrió un error al intentar guardar la ruta: ${mensaje}`);
    }

    function cerrarModalMapa() {
        mapModal.style.display = 'none';
        selectorUbicacion.close();
    }

    btnAddStop.addEventListener('click', addStop);
    btnRemoveStop.addEventListener('click', removeStop);

    container.addEventListener('click', function (event) {
        const uploadArea = event.target.closest('.image-upload-area');
        if (uploadArea) {
            const fileInputId = uploadArea.dataset.fileInput;
            const fileInput = document.getElementById(fileInputId);
            if (fileInput) {
                fileInput.click();
            }
            return;
        }

        const mapBtn = event.target.closest('.btn-map');
        if (mapBtn) {
            event.preventDefault();
            currentInputTarget = mapBtn.previousElementSibling;
            renderizarMapa();
        }
    });

    container.addEventListener('change', function (event) {
        const inputFile = event.target.closest('input[type="file"]');
        if (inputFile) {
            previewImage(inputFile, inputFile.dataset.stopId);
        }
    });

    document.getElementById('close-map-btn').addEventListener('click', cerrarModalMapa);
    document.getElementById('cancel-map-btn').addEventListener('click', cerrarModalMapa);

    document.getElementById('confirm-map-btn').addEventListener('click', function () {
        const coords = selectorUbicacion.getCoords();
        if (!coords || !currentInputTarget) {
            alert('Por favor, haz clic en el mapa para seleccionar una ubicación primero.');
            return;
        }

        currentInputTarget.dataset.lat = coords.lat;
        currentInputTarget.dataset.lon = coords.lng;
        currentInputTarget.value = `📍 Ubicación guardada (${coords.lat.toFixed(4)}, ${coords.lng.toFixed(4)})`;
        cerrarModalMapa();
    });

    document.querySelector('.btn-back').addEventListener('click', function () {
        window.location.href = config.urls.volver;
    });

    btnGuardar.addEventListener('click', async function () {
        const originalText = btnGuardar.innerHTML;
        btnGuardar.innerHTML = '<span class="material-icons-round">hourglass_empty</span> Guardando...';
        btnGuardar.disabled = true;

        try {
            const payload = leerFormulario();
            await enviarPeticion(payload);
            alert('¡Ruta guardada con éxito!');
            window.location.href = config.urls.catalogo;
        } catch (error) {
            console.error(error);
            renderizarErrores(error.message);
        } finally {
            btnGuardar.innerHTML = originalText;
            btnGuardar.disabled = false;
        }
    });
})();
