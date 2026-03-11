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

    // ── Geolocalización anticipada ────────────────────────────────────────────
    // Se lanza en cuanto el módulo se carga, sin esperar al submit.
    const metadataPromise = recogerMetadata();
    // ─────────────────────────────────────────────────────────────────────────

    function setCargando(estaCargando) {
        pantallaCarga.style.display = estaCargando ? 'flex' : 'none';
        boton.disabled = estaCargando;
        boton.textContent = estaCargando ? 'Generando...' : 'Generar la ruta';
    }

    async function recogerMetadata() {
        const meta = {
            idioma: navigator.language || navigator.userLanguage || null,
            zona_horaria: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
            hora_local: new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }),
            dispositivo: /Mobi|Android/i.test(navigator.userAgent) ? 'móvil' : 'escritorio',
            ubicacion: null,
        };

        if ('geolocation' in navigator) {
            try {
                const pos = await new Promise((resolve, reject) =>
                    navigator.geolocation.getCurrentPosition(resolve, reject, {
                        timeout: 5000,
                        maximumAge: 300_000,
                    }),
                );
                meta.ubicacion = {
                    coords: [
                        parseFloat(pos.coords.latitude.toFixed(4)),
                        parseFloat(pos.coords.longitude.toFixed(4)),
                    ],
                };

                try {
                    const { latitude, longitude } = pos.coords;
                    const url = `https://nominatim.openstreetmap.org/reverse?lat=${latitude}&lon=${longitude}&format=json&addressdetails=1`;
                    const resp = await fetch(url, { headers: { 'Accept-Language': 'es' } });
                    if (resp.ok) {
                        const geo = await resp.json();
                        const addr = geo.address || {};
                        meta.ubicacion.ciudad = (
                            addr.city || addr.town || addr.village || addr.county || ''
                        ).trim() || null;
                        meta.ubicacion.pais = addr.country || null;
                    }
                } catch (_) {}
            } catch (_) {}
        }
        return meta;
    }

    const MAX_DESEOS = 5;
    const MAX_CHARS_DESEO = 50;

    function inicializarDeseos() {
        const lista = document.getElementById('deseos-lista');
        const btnAñadir = document.getElementById('btn-añadir-deseo');
        const counter = document.getElementById('deseos-count');

        if (!lista || !btnAñadir || !counter) return;

        function actualizarEstado() {
            const total = lista.querySelectorAll('.deseo-item').length;
            counter.textContent = total;
            btnAñadir.disabled = total >= MAX_DESEOS;
            btnAñadir.classList.toggle('deseos-limit', total >= MAX_DESEOS);
        }

        function crearItemDeseo() {
            const item = document.createElement('div');
            item.className = 'deseo-item';
            item.innerHTML = `
                <input
                    type="text"
                    class="deseo-input"
                    maxlength="${MAX_CHARS_DESEO}"
                    placeholder="Ej: incluir una parada con vistas al río..."
                    aria-label="Deseo personalizado"
                >
                <span class="deseo-chars">0/${MAX_CHARS_DESEO}</span>
                <button type="button" class="deseo-btn-eliminar" aria-label="Eliminar deseo">
                    <span class="material-icons-round">close</span>
                </button>
            `;

            const input = item.querySelector('.deseo-input');
            const charCount = item.querySelector('.deseo-chars');

            input.addEventListener('input', () => {
                const len = input.value.length;
                charCount.textContent = `${len}/${MAX_CHARS_DESEO}`;
                charCount.classList.toggle('deseo-chars--limit', len >= MAX_CHARS_DESEO);
            });

            item.querySelector('.deseo-btn-eliminar').addEventListener('click', () => {
                item.remove();
                actualizarEstado();
            });

            return item;
        }

        btnAñadir.addEventListener('click', () => {
            if (lista.querySelectorAll('.deseo-item').length >= MAX_DESEOS) return;
            const item = crearItemDeseo();
            lista.appendChild(item);
            item.querySelector('.deseo-input').focus();
            actualizarEstado();
        });

        actualizarEstado();
    }

    function leerDeseos() {
        return Array.from(document.querySelectorAll('.deseo-input'))
            .map((input) => input.value.trim())
            .filter(Boolean);
    }

    async function leerFormulario() {
        const moodSeleccionados = Array.from(form.querySelectorAll('input[name="mood"]:checked')).map(
            (checkbox) => checkbox.value,
        );

        const metadata = await metadataPromise;

        return {
            ciudad: document.getElementById('ciudad').value,
            duracion: document.getElementById('duracion').value,
            personas: document.getElementById('personas').value,
            exigencia: document.getElementById('exigencia').value,
            mood: moodSeleccionados,
            deseos: leerDeseos(),
            metadata,
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
            const payload = await leerFormulario();
            const data = await enviarPeticion(payload);
            form.classList.add('d-none');
            document.getElementById('subtitulo-form').classList.add('d-none');
            renderizarRuta(data.datos_ruta);

            estado.className = 'alert alert-success mt-3';
            estado.innerHTML = `${data.mensaje} — <a href="/catalogo/${data.ruta_id}/" class="alert-link">Para más opciones accede a la ruta desde el catálogo</a>.`;
            estado.classList.remove('d-none');
        } catch (error) {
            console.error(error);
            renderizarErrores(error.message);
        } finally {
            setCargando(false);
        }
    });

    inicializarDeseos();

})();
