(function() {
    let stopCount = 2;
    const stopsContainer = document.getElementById('stops-container');
    const display = document.getElementById('counter-display');

    function updateDisplay() {
        display.textContent = stopCount;
    }

    window.previewImage = function(input, id) {
        if (input.files && input.files[0]) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const area = document.getElementById('img-area-' + id);
                area.style.backgroundImage = 'url(' + e.target.result + ')';
                while (area.firstChild) area.removeChild(area.firstChild);
                area.style.border = 'none';
            };
            reader.readAsDataURL(input.files[0]);
        }
    };

    function buildStopCard(n) {
        const div = document.createElement('div');
        div.className = 'stop-card';
        div.id = 'stop-' + n;

        // header
        const header = document.createElement('div');
        header.className = 'stop-header';
        const badge = document.createElement('span');
        badge.className = 'stop-number-badge';
        badge.textContent = 'PARADA ' + n;
        const handle = document.createElement('span');
        handle.className = 'material-icons-round';
        handle.style.cssText = 'color:var(--text-muted);cursor:grab;';
        handle.textContent = 'drag_handle';
        header.appendChild(badge);
        header.appendChild(handle);

        // image area
        const imgArea = document.createElement('div');
        imgArea.className = 'image-upload-area';
        imgArea.id = 'img-area-' + n;
        const fileId = 'file-' + n;
        imgArea.addEventListener('click', function() {
            document.getElementById(fileId).click();
        });
        const imgIcon = document.createElement('span');
        imgIcon.className = 'material-icons-round';
        imgIcon.textContent = 'add_photo_alternate';
        const imgText = document.createElement('span');
        imgText.className = 'image-upload-text';
        imgText.textContent = 'Cargar Imagen';
        imgArea.appendChild(imgIcon);
        imgArea.appendChild(imgText);

        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.id = fileId;
        fileInput.hidden = true;
        fileInput.accept = 'image/*';
        const capturedN = n;
        fileInput.addEventListener('change', function() {
            window.previewImage(this, capturedN);
        });

        // name group
        const nameGroup = document.createElement('div');
        nameGroup.className = 'form-group';
        const nameLabel = document.createElement('label');
        nameLabel.className = 'input-label';
        nameLabel.textContent = 'Nombre del Lugar';
        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.className = 'input-field stop-nombre';
        nameInput.placeholder = 'Nombre...';
        nameGroup.appendChild(nameLabel);
        nameGroup.appendChild(nameInput);

        // location group
        const locGroup = document.createElement('div');
        locGroup.className = 'form-group';
        locGroup.style.marginBottom = '0';
        const locLabel = document.createElement('label');
        locLabel.className = 'input-label';
        locLabel.textContent = 'Ubicación';
        const locRow = document.createElement('div');
        locRow.className = 'location-group';
        const locInput = document.createElement('input');
        locInput.type = 'text';
        locInput.className = 'input-field stop-ubicacion';
        locInput.placeholder = 'Dirección...';
        const mapBtn = document.createElement('button');
        mapBtn.className = 'btn-map';
        mapBtn.type = 'button';
        const mapIcon = document.createElement('span');
        mapIcon.className = 'material-icons-round';
        mapIcon.textContent = 'map';
        mapBtn.appendChild(mapIcon);
        locRow.appendChild(locInput);
        locRow.appendChild(mapBtn);
        locGroup.appendChild(locLabel);
        locGroup.appendChild(locRow);

        div.appendChild(header);
        div.appendChild(imgArea);
        div.appendChild(fileInput);
        div.appendChild(nameGroup);
        div.appendChild(locGroup);
        return div;
    }

    window.addStop = function() {
        stopCount++;
        updateDisplay();
        const div = buildStopCard(stopCount);
        stopsContainer.appendChild(div);
        setTimeout(() => div.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100);
    };

    window.removeStop = function() {
        if (stopCount > 1) {
            const el = document.getElementById('stop-' + stopCount);
            if (el) el.remove();
            stopCount--;
            updateDisplay();
        }
    };

    function setBtnSaveState(btn, saving) {
        btn.disabled = saving;
        while (btn.firstChild) btn.removeChild(btn.firstChild);
        const icon = document.createElement('span');
        icon.className = 'material-icons-round';
        icon.textContent = saving ? 'hourglass_empty' : 'save';
        btn.appendChild(icon);
        btn.appendChild(document.createTextNode(saving ? ' Guardando...' : ' Guardar'));
    }

    function getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    }

    document.getElementById('btn-guardar-tour').addEventListener('click', async function() {
        setBtnSaveState(this, true);
        const btnSave = this;

        const titulo = document.getElementById('ruta-titulo').value;
        const descripcion = document.getElementById('ruta-descripcion').value;
        const duracion = document.getElementById('ruta-duracion').value;
        const personas = document.getElementById('ruta-personas').value;
        const exigencia = document.getElementById('ruta-exigencia').value;

        const paradas = [];
        document.querySelectorAll('.stop-card').forEach(function(card, index) {
            const nombreInput = card.querySelector('.stop-nombre');
            const ubicacionInput = card.querySelector('.stop-ubicacion');
            const lat = ubicacionInput && ubicacionInput.dataset.lat ? parseFloat(ubicacionInput.dataset.lat) : 37.38;
            const lon = ubicacionInput && ubicacionInput.dataset.lon ? parseFloat(ubicacionInput.dataset.lon) : -5.99;
            paradas.push({
                nombre: nombreInput ? nombreInput.value : 'Parada ' + (index + 1),
                direccion: ubicacionInput ? ubicacionInput.value : '',
                lat: lat,
                lon: lon
            });
        });

        const payload = {
            titulo,
            descripcion,
            paradas,
            duracion_horas: duracion,
            num_personas: personas,
            nivel_exigencia: exigencia,
            mood: []
        };

        try {
            const response = await fetch('/crear-ruta/api/guardar-manual/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            if (response.ok && data.status === 'OK') {
                alert('Ruta guardada con éxito.');
                window.location.href = '/catalogo/';
            } else {
                throw new Error(data.mensaje || 'Error desconocido al guardar la ruta');
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Error al guardar la ruta: ' + error.message);
        } finally {
            setBtnSaveState(btnSave, false);
        }
    });

    // Map modal
    let mapInstance = null;
    let mapMarker = null;
    let currentInputTarget = null;
    let tempCoords = null;

    function initMap() {
        if (!mapInstance) {
            mapInstance = L.map('leaflet-map').setView([37.3886, -5.9823], 13);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors'
            }).addTo(mapInstance);
            mapInstance.on('click', function(e) {
                tempCoords = e.latlng;
                if (mapMarker) mapMarker.setLatLng(tempCoords);
                else mapMarker = L.marker(tempCoords).addTo(mapInstance);
            });
        }
    }

    document.addEventListener('click', function(e) {
        const mapBtn = e.target.closest('.btn-map');
        if (mapBtn) {
            e.preventDefault();
            currentInputTarget = mapBtn.previousElementSibling;
            document.getElementById('map-modal-overlay').style.display = 'flex';
            initMap();
            setTimeout(function() {
                mapInstance.invalidateSize();
            }, 100);
        }
    });

    function closeMapModal() {
        document.getElementById('map-modal-overlay').style.display = 'none';
        tempCoords = null;
        if (mapMarker) {
            mapInstance.removeLayer(mapMarker);
            mapMarker = null;
        }
    }

    document.getElementById('close-map-btn').addEventListener('click', closeMapModal);
    document.getElementById('cancel-map-btn').addEventListener('click', closeMapModal);

    document.getElementById('confirm-map-btn').addEventListener('click', function() {
        if (tempCoords && currentInputTarget) {
            currentInputTarget.dataset.lat = tempCoords.lat;
            currentInputTarget.dataset.lon = tempCoords.lng;
            currentInputTarget.value = 'Ubicación guardada (' + tempCoords.lat.toFixed(4) + ', ' + tempCoords.lng.toFixed(4) + ')';
            closeMapModal();
        } else {
            alert('Haz clic en el mapa para seleccionar una ubicación primero.');
        }
    });
})();
