(function () {
    const config = JSON.parse(document.getElementById('personalizacion-config').textContent);

    const form = document.getElementById('form-personalizacion-ruta');
    const boton = document.getElementById('btn-generar-ruta');
    const estado = document.getElementById('estado-respuesta');
    const pantallaCarga = document.getElementById('pantalla-carga');
    const rutaMeta = document.getElementById('ruta-meta');
    const seccionResultados = document.getElementById('seccion-resultados');
    const listaParadas = document.getElementById('lista-paradas');

    let leafletMap = null;

    function setCargando(estaCargando) {
        pantallaCarga.style.display = estaCargando ? 'flex' : 'none';
        boton.disabled = estaCargando;
        boton.textContent = estaCargando ? 'Generando...' : 'Generar la ruta';
    }

    function leerFormulario() {
        const moodSeleccionados = Array.from(form.querySelectorAll('input[name="mood"]:checked')).map(
            (checkbox) => checkbox.value,
        );

        return {
            ciudad: document.getElementById('ciudad').value,
            duracion: document.getElementById('duracion').value,
            personas: document.getElementById('personas').value,
            exigencia: document.getElementById('exigencia').value,
            mood: moodSeleccionados,
        };
    }

    async function enviarPeticion(payload) {
        const response = await fetch(config.urls.generar, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': config.csrfToken,
            },
            body: JSON.stringify(payload),
        });

        const data = await response.json();
        if (!response.ok || data.status !== 'OK') {
            throw new Error(data.mensaje || 'Error desconocido al generar la ruta');
        }

        return data;
    }

    function renderizarMapa(paradas) {
        if (leafletMap) {
            leafletMap.remove();
        }

        const primeraParada = (paradas && paradas[0]) || null;
        const coordenadaInicial =
            (primeraParada && (primeraParada.coordenadas || primeraParada.coords)) || [40.4167, -3.7037];

        leafletMap = window.MapaCreacion.crearMapaRuta({
            elementId: 'mapa-ruta',
            center: coordenadaInicial,
            token: config.mapboxToken,
        });

        window.MapaCreacion.renderizarParadasEnMapa(leafletMap, paradas || []);
    }

    function renderizarErrores(mensaje) {
        estado.className = 'alert alert-danger mt-3';
        estado.textContent = `Error: ${mensaje}`;
        estado.classList.remove('d-none');
    }

    function renderizarRuta(datos) {
        seccionResultados.classList.remove('d-none');
        listaParadas.innerHTML = '';

        rutaMeta.classList.remove('d-none');
        rutaMeta.textContent = `${datos.titulo || 'Ruta generada'} · ${datos.duracion_horas || datos.duracion_estimada || '-'}h · Exigencia ${datos.nivel_exigencia || '-'}`;

        (datos.paradas || []).forEach((parada, idx) => {
            listaParadas.insertAdjacentHTML(
                'beforeend',
                `<div class="list-group-item border-start border-primary border-4 mb-2">
                    <div class="fw-bold text-primary">Parada ${parada.orden || idx + 1}: ${parada.nombre || `Parada ${idx + 1}`}</div>
                    <div class="small text-muted">${parada.descripcion || parada.desc || 'Sin descripción'}</div>
                </div>`,
            );
        });

        renderizarMapa(datos.paradas || []);
    }

    document.querySelectorAll('.mood-btn input[type="checkbox"]').forEach(function (checkbox) {
        checkbox.addEventListener('change', function () {
            this.closest('.mood-btn').classList.toggle('active', this.checked);
        });
    });

    form.addEventListener('submit', async function (event) {
        event.preventDefault();
        estado.classList.add('d-none');
        setCargando(true);

        try {
            const payload = leerFormulario();
            const data = await enviarPeticion(payload);
            renderizarRuta(data.datos_ruta);

            estado.className = 'alert alert-success mt-3';
            estado.textContent = data.mensaje;
            estado.classList.remove('d-none');
        } catch (error) {
            console.error(error);
            renderizarErrores(error.message);
        } finally {
            setCargando(false);
        }
    });
})();
