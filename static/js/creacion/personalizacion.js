const form = document.getElementById('form-personalizacion-ruta');
const boton = document.getElementById('btn-generar-ruta');
const estado = document.getElementById('estado-respuesta');
const pantallaCarga = document.getElementById('pantalla-carga');
const rutaMeta = document.getElementById('ruta-meta');

const csrfToken = form.dataset.csrfToken;
const mapboxToken = form.dataset.mapboxToken;

let leafletMap = null;

function setCargando(estaCargando) {
    if (estaCargando) {
        pantallaCarga.style.display = 'flex';
        boton.disabled = true;
        boton.textContent = 'Generando...';
    } else {
        pantallaCarga.style.display = 'none';
        boton.disabled = false;
        boton.textContent = 'Generar la ruta';
    }
}

function renderizarRuta(datos) {
    document.getElementById('seccion-resultados').classList.remove('d-none');
    const lista = document.getElementById('lista-paradas');
    lista.innerHTML = '';

    rutaMeta.classList.remove('d-none');
    rutaMeta.textContent = `${datos.titulo || 'Ruta generada'} · ${datos.duracion_horas || datos.duracion_estimada || '-'}h · Exigencia ${datos.nivel_exigencia || '-'}`;

    if (leafletMap) {
        leafletMap.remove();
    }

    const primeraParada = (datos.paradas && datos.paradas[0]) || null;
    const coordenadaInicial = (primeraParada && (primeraParada.coordenadas || primeraParada.coords))
        ? (primeraParada.coordenadas || primeraParada.coords)
        : [40.4167, -3.7037];

    leafletMap = L.map('mapa-ruta').setView(coordenadaInicial, 14);

    L.tileLayer(`https://api.mapbox.com/styles/v1/mapbox/streets-v12/tiles/256/{z}/{x}/{y}@2x?access_token=${mapboxToken}`, {
        attribution: '© Mapbox',
    }).addTo(leafletMap);

    const puntos = [];

    if (datos.paradas && datos.paradas.length > 0) {
        datos.paradas.forEach((p, idx) => {
            const coords = p.coordenadas || p.coords;
            if (!coords) {
                return;
            }

            puntos.push(coords);

            L.marker(coords).addTo(leafletMap)
                .bindPopup(`<b>${p.orden || idx + 1}. ${p.nombre}</b>`);

            lista.innerHTML += `
                <div class="list-group-item border-start border-primary border-4 mb-2">
                    <div class="fw-bold text-primary">Parada ${p.orden || idx + 1}: ${p.nombre}</div>
                    <div class="small text-muted">${p.descripcion || p.desc || 'Sin descripción'}</div>
                </div>`;
        });

        if (puntos.length > 1) {
            L.polyline(puntos, { color: '#0d6efd', weight: 4, opacity: 0.7 }).addTo(leafletMap);
            leafletMap.fitBounds(puntos, { padding: [50, 50] });
        }
    }
}

document.querySelectorAll('.mood-btn input[type="checkbox"]').forEach((checkbox) => {
    checkbox.addEventListener('change', function () {
        this.closest('.mood-btn').classList.toggle('active', this.checked);
    });
});

form.addEventListener('submit', async (e) => {
    e.preventDefault();

    estado.classList.add('d-none');
    setCargando(true);

    const moodSeleccionados = Array.from(form.querySelectorAll('input[name="mood"]:checked'))
        .map((checkbox) => checkbox.value);

    const payload = {
        ciudad: document.getElementById('ciudad').value,
        duracion: document.getElementById('duracion').value,
        personas: document.getElementById('personas').value,
        exigencia: document.getElementById('exigencia').value,
        mood: moodSeleccionados,
    };

    try {
        const response = await fetch('/crear-ruta/api/generar/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify(payload),
        });

        const data = await response.json();

        if (response.ok && data.status === 'OK') {
            form.classList.add('d-none');
            document.getElementById('subtitulo-form').classList.add('d-none');
            renderizarRuta(data.datos_ruta);
            estado.className = 'alert alert-success mt-3';
            estado.innerHTML = `${data.mensaje} — <a href="/catalogo/${data.ruta_id}/" class="alert-link">Para más opciones, accede a la ruta desde el catálogo</a>.`;
            estado.classList.remove('d-none');
        } else {
            throw new Error(data.mensaje || 'Error desconocido al generar la ruta');
        }
    } catch (error) {
        console.error(error);
        estado.className = 'alert alert-danger mt-3';
        estado.textContent = `Error: ${error.message}`;
        estado.classList.remove('d-none');
    } finally {
        setCargando(false);
    }
});
