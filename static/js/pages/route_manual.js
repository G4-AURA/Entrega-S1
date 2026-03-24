(function () {
    const LIMITES_MANUAL = {
        duracionMin: 0.5,
        duracionMax: 24,
        personasMin: 1,
        personasMax: 50,
        paradasMin: 2,
    };

    const configElement = document.getElementById('creacion-manual-config');
    const config = configElement
        ? JSON.parse(configElement.textContent)
        : {
              csrfToken: getCookie('csrftoken'),
              urls: {
                  guardarManual: '/crear-ruta/api/guardar-manual/',
                  volver: '/crear-ruta/',
                  catalogo: '/catalogo/',
              },
          };

    const container = document.getElementById('stops-container');
    const display = document.getElementById('counter-display');
    const btnGuardar = document.getElementById('btn-guardar-tour');
    const mapModal = document.getElementById('map-modal-overlay');
    const btnBack = document.querySelector('.btn-back');
    const btnAddStop = document.getElementById('btn-add-stop') || document.querySelector('[data-action="add-stop"]');
    const btnRemoveStop = document.getElementById('btn-remove-stop') || document.querySelector('[data-action="remove-stop"]');
    const selectExigencia = document.getElementById('ruta-exigencia');
    const exigenciaAyuda = document.getElementById('ruta-exigencia-ayuda');

    const EXIGENCIA_DESCRIPCIONES = {
        baja: 'Ritmo tranquilo, trayectos cortos y pausas frecuentes. Recomendada para paseos relajados o grupos con movilidad reducida.',
        media: 'Ritmo equilibrado, con caminatas moderadas y pausas razonables. Opción recomendada para la mayoría de grupos.',
        alta: 'Ritmo intenso, más distancia caminada y menos pausas. Pensada para grupos habituados a caminar.',
    };

    if (!container || !display || !btnGuardar || !mapModal) {
        console.error('Faltan elementos necesarios para inicializar route_manual.js');
        return;
    }

    let stopCount = container.querySelectorAll('.stop-card').length || 0;
    let currentInputTarget = null;

    const hasExternalMapSelector =
        window.MapaCreacion && typeof window.MapaCreacion.crearSelectorUbicacion === 'function';

    const selectorUbicacion = hasExternalMapSelector
        ? window.MapaCreacion.crearSelectorUbicacion({
              mapId: 'leaflet-map',
              initialCoords: [37.3886, -5.9823],
          })
        : createLeafletFallbackSelector();

    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) {
            return parts.pop().split(';').shift();
        }
        return '';
    }

    function updateDisplay() {
        display.innerText = stopCount;
    }
    
    function actualizarAyudaExigencia() {
        if (!selectExigencia || !exigenciaAyuda) {
            return;
        }

        const clave = String(selectExigencia.value || '').trim().toLowerCase();
        exigenciaAyuda.textContent = EXIGENCIA_DESCRIPCIONES[clave] || EXIGENCIA_DESCRIPCIONES.media;
    }

    function crearTarjetaParada(index) {
        return `
            <div class="stop-card" id="stop-${index}">
                <div class="stop-header">
                    <span class="stop-number-badge">PARADA ${index}</span>
                    <span class="material-icons-round drag-icon">drag_handle</span>
                </div>

                <div class="image-upload-area" id="img-area-${index}" data-file-input="file-${index}">
                    <span class="material-icons-round">add_photo_alternate</span>
                    <span class="image-upload-text">Cargar Imagen</span>
                </div>
                <input
                    type="file"
                    id="file-${index}"
                    hidden
                    accept="image/*"
                    class="stop-image-input"
                    data-stop-id="${index}"
                >

                <div class="form-group">
                    <label class="input-label">Nombre del Lugar</label>
                    <input type="text" class="input-field stop-nombre" placeholder="Nombre...">
                </div>

                <div class="form-group">
                    <label class="input-label">Descripción (opcional)</label>
                    <textarea class="input-field stop-descripcion" placeholder="Breve descripción de la parada..." maxlength="500"></textarea>
                </div>

                <div class="form-group form-group-no-margin">
                    <label class="input-label">Ubicación</label>
                    <div class="location-group">
                        <button class="btn-map" type="button">
                            <span class="material-icons-round">map</span>
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    function previewImage(input, id) {
        if (!input.files || !input.files[0]) {
            return;
        }

        const reader = new FileReader();
        reader.onload = function (event) {
            const area = document.getElementById(`img-area-${id}`);
            if (!area) {
                return;
            }
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

        const newStop = document.getElementById(`stop-${stopCount}`);
        if (newStop) {
            setTimeout(() => {
                newStop.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 100);
        }
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
        const moodsSeleccionados = Array.from(
            document.querySelectorAll('#ruta-etiquetas input[name="mood"]:checked')
        ).map(function (checkbox) {
            return checkbox.value;
        });

        const paradas = Array.from(container.querySelectorAll('.stop-card')).map(function (card, index) {
            const nombreInput = card.querySelector('.stop-nombre');
            const descInput = card.querySelector('.stop-descripcion');
            const rawLat = card.dataset.lat;
            const rawLon = card.dataset.lon;

            return {
                nombre: nombreInput && nombreInput.value ? nombreInput.value : `Parada ${index + 1}`,
                descripcion: descInput && descInput.value ? descInput.value : '',
                lat: rawLat === undefined ? null : parseFloat(rawLat),
                lon: rawLon === undefined ? null : parseFloat(rawLon),
            };
        });

        return {
            titulo: document.getElementById('ruta-titulo')?.value || '',
            descripcion: document.getElementById('ruta-descripcion')?.value || '',
            duracion_horas: document.getElementById('ruta-duracion')?.value || '',
            num_personas: document.getElementById('ruta-personas')?.value || '',
            nivel_exigencia: document.getElementById('ruta-exigencia')?.value || '',
            mood: moodsSeleccionados,
            paradas,
        };
    }

    function validarFormulario(payload) {
        const titulo = String(payload.titulo || '').trim();
        const descripcion = String(payload.descripcion || '').trim();
        const duracion = Number(payload.duracion_horas);
        const personas = Number(payload.num_personas);
        const paradas = Array.isArray(payload.paradas) ? payload.paradas : [];

        if (!titulo) {
            return 'El título de la ruta es obligatorio.';
        }
        if (!descripcion) {
            return 'La descripción de la ruta es obligatoria.';
        }
        if (!Number.isFinite(duracion)) {
            return 'La duración debe ser un número válido.';
        }
        if (duracion < LIMITES_MANUAL.duracionMin || duracion > LIMITES_MANUAL.duracionMax) {
            return 'La duración debe estar entre 0.5 y 24 horas.';
        }
        if (!Number.isInteger(personas)) {
            return 'El número de personas debe ser un entero válido.';
        }
        if (personas < LIMITES_MANUAL.personasMin || personas > LIMITES_MANUAL.personasMax) {
            return 'El número de personas debe estar entre 1 y 50.';
        }
        if (paradas.length < LIMITES_MANUAL.paradasMin) {
            return 'Debes añadir al menos 2 paradas.';
        }

        for (let i = 0; i < paradas.length; i += 1) {
            const parada = paradas[i] || {};
            const nombre = String(parada.nombre || '').trim();
            if (!nombre) {
                return `El nombre de la parada ${i + 1} es obligatorio.`;
            }

            const lat = Number(parada.lat);
            const lon = Number(parada.lon);
            if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
                return `Selecciona la ubicación de la parada ${i + 1} en el mapa.`;
            }
            if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
                return `La parada ${i + 1} tiene coordenadas fuera de rango.`;
            }
        }

        return null;
    }

    async function enviarPeticion(payload) {
        const response = await fetch(config.urls.guardarManual, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': config.csrfToken || getCookie('csrftoken'),
            },
            body: JSON.stringify(payload),
        });

        const data = await response.json();

        if (!response.ok || data.status !== 'OK') {
            const error = new Error(data.mensaje || 'Error desconocido al guardar la ruta');
            error.errores = data.errores;
            throw error;
        }

        return data;
    }

    function renderizarMapa() {
        mapModal.style.display = 'flex';
        if (selectorUbicacion && typeof selectorUbicacion.open === 'function') {
            selectorUbicacion.open();
        }
    }

    function cerrarModalMapa() {
        if (currentInputTarget && selectorUbicacion && typeof selectorUbicacion.getCoords === 'function') {
            const coords = selectorUbicacion.getCoords();
            if (coords) {
                currentInputTarget.dataset.lat = coords.lat;
                currentInputTarget.dataset.lon = coords.lng;
            }
        }
        mapModal.style.display = 'none';
        if (selectorUbicacion && typeof selectorUbicacion.close === 'function') {
            selectorUbicacion.close();
        }
    }

    function renderizarErrores(mensaje) {
        alert(`Ocurrió un error al intentar guardar la ruta: ${mensaje}`);
    }

    function renderizarErroresCampos(errores) {
        // Limpiar errores previos
        document.querySelectorAll('.error-message').forEach(el => el.remove());

        for (const [campo, mensaje] of Object.entries(errores)) {
            let input;
            if (campo === 'duracion_horas') {
                input = document.getElementById('ruta-duracion');
            } else if (campo === 'num_personas') {
                input = document.getElementById('ruta-personas');
            } else if (campo === 'titulo') {
                input = document.getElementById('ruta-titulo');
            } else if (campo.startsWith('parada_')) {
                const idx = campo.split('_')[1];
                input = document.querySelector(`#stop-${idx} .stop-nombre`);
            } else {
                // Para general o otros, mostrar alert
                alert(mensaje);
                continue;
            }

            if (input) {
                const errorSpan = document.createElement('span');
                errorSpan.className = 'error-message';
                errorSpan.style.color = 'red';
                errorSpan.style.fontSize = '0.875rem';
                errorSpan.style.marginTop = '0.25rem';
                errorSpan.textContent = mensaje;
                input.parentNode.appendChild(errorSpan);
            }
        }
    }

    function createLeafletFallbackSelector() {
        let map = null;
        let marker = null;
        let selectedCoords = null;

        return {
            open() {
                if (!window.L) {
                    console.error('Leaflet no está disponible.');
                    return;
                }

                if (!map) {
                    map = L.map('leaflet-map').setView([37.3886, -5.9823], 13);

                    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                        attribution: '© OpenStreetMap contributors',
                    }).addTo(map);

                    map.on('click', function (e) {
                        selectedCoords = e.latlng;
                        if (marker) {
                            marker.setLatLng(selectedCoords);
                        } else {
                            marker = L.marker(selectedCoords).addTo(map);
                        }
                    });
                }

                setTimeout(() => {
                    map.invalidateSize();
                }, 100);
            },

            close() {
                selectedCoords = null;
                if (map && marker) {
                    map.removeLayer(marker);
                    marker = null;
                }
            },

            getCoords() {
                return selectedCoords;
            },
        };
    }

    if (btnAddStop) {
        btnAddStop.addEventListener('click', addStop);
    }

    if (btnRemoveStop) {
        btnRemoveStop.addEventListener('click', removeStop);
    }

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
            currentInputTarget = mapBtn.closest('.stop-card');
            renderizarMapa();
        }
    });

    container.addEventListener('change', function (event) {
        const inputFile = event.target.closest('.stop-image-input, input[type="file"]');
        if (inputFile) {
            previewImage(inputFile, inputFile.dataset.stopId);
        }
    });

    document.getElementById('close-map-btn')?.addEventListener('click', cerrarModalMapa);
    document.getElementById('cancel-map-btn')?.addEventListener('click', cerrarModalMapa);

    document.getElementById('confirm-map-btn')?.addEventListener('click', function () {
        const coords =
            selectorUbicacion && typeof selectorUbicacion.getCoords === 'function'
                ? selectorUbicacion.getCoords()
                : null;

        if (!coords || !currentInputTarget) {
            alert('Por favor, haz clic en el mapa para seleccionar una ubicación primero.');
            return;
        }

        currentInputTarget.dataset.lat = coords.lat;
        currentInputTarget.dataset.lon = coords.lng;
        currentInputTarget.value = `📍 Ubicación guardada (${coords.lat.toFixed(4)}, ${coords.lng.toFixed(4)})`;
        cerrarModalMapa();
    });

    if (btnBack) {
        btnBack.addEventListener('click', function () {
            window.location.href = config.urls.volver;
        });
    }

    if (selectExigencia) {
        selectExigencia.addEventListener('change', actualizarAyudaExigencia);
        actualizarAyudaExigencia();
    }

    document.querySelectorAll('#ruta-etiquetas .manual-tag-pill input[type="checkbox"]').forEach(function (checkbox) {
        checkbox.addEventListener('change', function () {
            const tag = this.closest('.manual-tag-pill');
            if (tag) {
                tag.classList.toggle('active', this.checked);
            }
        });
    });

    btnGuardar.addEventListener('click', async function () {
        const originalText = btnGuardar.innerHTML;
        btnGuardar.innerHTML = '<span class="material-icons-round">hourglass_empty</span> Guardando...';
        btnGuardar.disabled = true;

        try {
            const payload = leerFormulario();
            const errorValidacion = validarFormulario(payload);
            if (errorValidacion) {
                throw new Error(errorValidacion);
            }
            await enviarPeticion(payload);
            alert('¡Ruta guardada con éxito!');
            window.location.href = config.urls.catalogo;
        } catch (error) {
            console.error(error);
            if (error.errores) {
                renderizarErroresCampos(error.errores);
            } else {
                renderizarErrores(error.message);
            }
        } finally {
            btnGuardar.innerHTML = originalText;
            btnGuardar.disabled = false;
        }
    });

    updateDisplay();
})();
