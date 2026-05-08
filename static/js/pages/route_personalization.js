(function () {
    const config = JSON.parse(document.getElementById('personalizacion-config').textContent);
    const PERSONAS_MAX_PLAN = Number(config?.limits?.personasMax) || 50;

    const form = document.getElementById('form-personalizacion-ruta');
    const boton = document.getElementById('btn-generar-ruta');
    const estado = document.getElementById('estado-respuesta');
    const pantallaCarga = document.getElementById('pantalla-carga');
    const loadingStatusTitle = document.getElementById('loading-status-title');
    const loadingStatusDetail = document.getElementById('loading-status-detail');
    const rutaMeta = document.getElementById('ruta-meta');
    const seccionResultados = document.getElementById('seccion-resultados');
    const listaParadas = document.getElementById('lista-paradas');
    const selectExigencia = document.getElementById('exigencia');
    const exigenciaAyuda = document.getElementById('exigencia-ayuda');
    const ayudaSeleccionParadas = document.getElementById('seleccion-paradas-ayuda');
    const resumenSeleccionParadas = document.getElementById('resumen-seleccion-paradas');
    const accionesSeleccionRuta = document.getElementById('acciones-seleccion-ruta');
    const btnConfirmarSeleccion = document.getElementById('btn-confirmar-seleccion');
    const btnGenerarAdicionales = document.getElementById('btn-generar-adicionales');
    const inputSugerenciasAdicionales = document.getElementById('input-sugerencias-adicionales');
    const moodButtonsContainer = form?.querySelector('.mood-buttons');
    const moodError = document.getElementById('mood-error');
    const IA_SESSION_STORAGE_KEY = 'aura_sesiones_generacion_ia';
    const feedback = window.AuraFeedback;

    let leafletMap = null;
    let sesionGeneracionActiva = null;
    let propuestasParadasActivas = [];
    let progressTimerId = null;
    let progressStepIndex = 0;

    const PROGRESS_STEPS_GENERAR = [
        { title: 'Validando solicitud...', detail: 'Comprobando ciudad, preferencias y parámetros del grupo.' },
        { title: 'Generando alternativas IA...', detail: 'Creando varias rutas candidatas para esta solicitud.' },
        { title: 'Validando paradas...', detail: 'Detectando duplicados y validando coherencia geográfica.' },
        { title: 'Reintentando paradas inválidas...', detail: 'Pidiendo automáticamente alternativas para las no válidas.' },
        { title: 'Seleccionando mejor ruta...', detail: 'Evaluando distancia, diversidad y coherencia temática.' },
    ];

    const PROGRESS_STEPS_ADICIONALES = [
        { title: 'Analizando sugerencias del guía...', detail: 'Aplicando tus indicaciones para nuevas propuestas.' },
        { title: 'Generando nuevas paradas...', detail: 'Buscando alternativas adicionales sin duplicar la selección actual.' },
        { title: 'Validando calidad de paradas...', detail: 'Filtrando por coherencia geográfica y duplicidad.' },
    ];

    const EXIGENCIA_DESCRIPCIONES = {
        baja: 'Ritmo tranquilo, trayectos cortos y pausas frecuentes. Recomendada para paseos relajados o grupos con movilidad reducida.',
        media: 'Ritmo equilibrado, con caminatas moderadas y pausas razonables. Opción recomendada para la mayoría de grupos.',
        alta: 'Ritmo intenso, más distancia caminada y menos pausas. Pensada para grupos habituados a caminar.',
    };
    const AVISO_COORDENADAS_IA = {
        title: 'Revisión recomendada',
        message:
            'Las coordenadas generadas por la IA pueden no ser exactas. Revisa cada parada antes de guardar la ruta.',
        buttonText: 'Entendido',
        type: 'info',
    };

    function actualizarMensajeProgreso(step) {
        if (loadingStatusTitle) loadingStatusTitle.textContent = step.title;
        if (loadingStatusDetail) loadingStatusDetail.textContent = step.detail;
    }

    function formatearCheckpointIA(checkpoint) {
        const checkpointKey = String(checkpoint || '').trim();
        const labels = {
            payload_normalizado: 'Preparando tus preferencias',
            ruta_generada: 'Propuesta lista para revisar',
            validacion_paradas: 'Revisando la calidad de las paradas',
            paradas_adicionales_generadas: 'Nuevas paradas listas',
            seleccion_paradas_guia: 'Selección aplicada',
            sugerencias_generadas: 'Sugerencias preparadas',
            feedback_usuario: 'Cambios recibidos',
            ruta_guardada: 'Ruta guardada',
        };
        return labels[checkpointKey] || 'Avanzando con tu ruta';
    }

    function mostrarMensajeConCheckpoint(mensaje, checkpoint) {
        estado.className = 'alert alert-success mt-3';
        estado.textContent = mensaje || 'La IA ha actualizado la propuesta.';

        const checkpointBadge = document.createElement('span');
        checkpointBadge.className = 'badge bg-warning text-dark ms-2';
        checkpointBadge.textContent = `Estado: ${formatearCheckpointIA(checkpoint)}`;
        estado.appendChild(checkpointBadge);
        estado.classList.remove('d-none');
    }

    function iniciarMensajesProgreso(tipo = 'generar') {
        detenerMensajesProgreso();
        const steps = tipo === 'adicionales' ? PROGRESS_STEPS_ADICIONALES : PROGRESS_STEPS_GENERAR;
        progressStepIndex = 0;
        actualizarMensajeProgreso(steps[progressStepIndex]);

        progressTimerId = window.setInterval(() => {
            progressStepIndex = (progressStepIndex + 1) % steps.length;
            actualizarMensajeProgreso(steps[progressStepIndex]);
        }, 5000);
    }

    function detenerMensajesProgreso() {
        if (progressTimerId) {
            window.clearInterval(progressTimerId);
            progressTimerId = null;
        }
    }

    function actualizarAyudaExigencia() {
        if (!selectExigencia || !exigenciaAyuda) return;

        const clave = String(selectExigencia.value || '').toLowerCase();
        exigenciaAyuda.textContent = EXIGENCIA_DESCRIPCIONES[clave] || EXIGENCIA_DESCRIPCIONES.media;
    }

    function configurarIncrementoDuracionMediaHora(inputId) {
        const input = document.getElementById(inputId);
        if (!input) {
            return;
        }

        input.step = '0.5';
        input.setAttribute('step', '0.5');

        input.addEventListener('keydown', function (event) {
            if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') {
                return;
            }

            event.preventDefault();

            const current = Number(input.value);
            const min = Number(input.min);
            const max = Number(input.max);
            const base = Number.isFinite(current)
                ? current
                : (Number.isFinite(min) ? min : 0.5);
            const delta = event.key === 'ArrowUp' ? 0.5 : -0.5;
            let next = Math.round((base + delta) * 2) / 2;

            if (Number.isFinite(min)) {
                next = Math.max(min, next);
            }
            if (Number.isFinite(max)) {
                next = Math.min(max, next);
            }

            input.value = next.toFixed(1);
            input.dispatchEvent(new Event('input', { bubbles: true }));
        });
    }

    configurarIncrementoDuracionMediaHora('duracion');

    function guardarSesionGeneracionEnStorage(rutaId, sesionGeneracionId) {
        if (!rutaId || !sesionGeneracionId) return;

        try {
            const raw = window.localStorage.getItem(IA_SESSION_STORAGE_KEY);
            const mapa = raw ? JSON.parse(raw) : {};
            mapa[String(rutaId)] = String(sesionGeneracionId);
            window.localStorage.setItem(IA_SESSION_STORAGE_KEY, JSON.stringify(mapa));
        } catch (_error) {
            // Si localStorage no está disponible, continuamos sin persistencia en frontend.
        }
    }

    // ── Geolocalización anticipada ────────────────────────────────────────────
    // Se lanza en cuanto el módulo se carga, sin esperar al submit.
    const metadataPromise = recogerMetadata();
    // ─────────────────────────────────────────────────────────────────────────

    function setCargando(estaCargando) {
        pantallaCarga.style.display = estaCargando ? 'flex' : 'none';
        boton.disabled = estaCargando;
        boton.textContent = estaCargando ? 'Generando...' : 'Generar la ruta';
        if (!estaCargando) {
            detenerMensajesProgreso();
            actualizarMensajeProgreso({ title: 'Generando ruta...', detail: 'Preparando el proceso...' });
        }
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
                let permisoSolicitado = true;
                if (feedback && typeof feedback.confirm === 'function') {
                    permisoSolicitado = await feedback.confirm({
                        title: 'Compartir ubicación',
                        message: '¿Quieres permitir tu ubicación para sugerir una ciudad automáticamente?',
                        confirmText: 'Permitir',
                        cancelText: 'Ahora no',
                        type: 'info',
                    });
                }

                if (!permisoSolicitado) {
                    return meta;
                }

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
            } catch (_) {
                if (feedback && typeof feedback.toast === 'function') {
                    feedback.toast('No se pudo obtener tu ubicación automática.', {
                        type: 'info',
                        duration: 2800,
                    });
                }
            }
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
            modo_seleccion: true,
        };
    }

    function normalizarMensajeError(errorValue) {
        if (Array.isArray(errorValue)) {
            return errorValue.map((v) => String(v || '').trim()).filter(Boolean).join(' ');
        }
        if (errorValue == null) return '';
        return String(errorValue).trim();
    }

    function limpiarErrorMood() {
        if (moodError) {
            moodError.textContent = '';
            moodError.classList.add('d-none');
        }
        moodButtonsContainer?.classList.remove('mood-buttons--error');
    }

    function limpiarErroresFormulario() {
        limpiarErrorMood();
    }

    function aplicarErroresDeCampo(errores) {
        const moodMensaje = normalizarMensajeError(errores?.mood);
        if (moodMensaje && moodError) {
            moodError.textContent = moodMensaje;
            moodError.classList.remove('d-none');
            moodButtonsContainer?.classList.add('mood-buttons--error');
            return true;
        }
        return false;
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

        const rawText = await response.text();
        let data = null;
        try {
            data = rawText ? JSON.parse(rawText) : null;
        } catch (_error) {
            data = null;
        }

        if (!data) {
            const snippet = rawText ? rawText.slice(0, 120).replace(/\s+/g, ' ').trim() : '';
            throw new Error(
                response.ok
                    ? 'La respuesta del servidor no es JSON válido.'
                    : `El servidor respondió con un error no JSON${snippet ? `: ${snippet}` : '.'}`,
            );
        }

        if (!response.ok || data.status !== 'OK') {
            const error = new Error(data.mensaje || 'Error desconocido al generar la ruta');
            if (data?.errores && typeof data.errores === 'object') {
                error.fieldErrors = data.errores;
            }
            throw error;
        }

        return data;
    }

    function validarPayloadPersonalizacion(payload) {
        const duracion = Number(payload?.duracion);
        const personas = Number(payload?.personas);
        if (!Number.isFinite(duracion)) {
            throw new Error('La duración debe ser un número válido.');
        }
        if (duracion < 0.5 || duracion > 24) {
            throw new Error('La duración debe estar entre 0.5 y 24 horas.');
        }
        if (Math.abs(duracion * 2 - Math.round(duracion * 2)) > 1e-9) {
            throw new Error('La duración debe indicarse en bloques de 0.5 horas.');
        }
        if (!Number.isInteger(personas)) {
            throw new Error('El número de personas debe ser un entero válido.');
        }
        if (personas < 1 || personas > PERSONAS_MAX_PLAN) {
            throw new Error(`El número de personas debe estar entre 1 y ${PERSONAS_MAX_PLAN}.`);
        }

        payload.duracion = duracion;
        payload.personas = personas;
        return payload;
    }

    async function obtenerEstadoSesionGeneracion(sesionGeneracionId) {
        if (!sesionGeneracionId || !config?.urls?.obtenerSesion) return null;

        const url = config.urls.obtenerSesion.replace('__SESSION_ID__', encodeURIComponent(sesionGeneracionId));
        try {
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': config.csrfToken,
                },
            });

            if (!response.ok) return null;

            const data = await response.json();
            if (data?.status !== 'OK') return null;
            return data.datos;
        } catch (_error) {
            return null;
        }
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

    function renderizarErrores(mensaje, errores = null) {
        const hayErrorMood = aplicarErroresDeCampo(errores);
        const mensajeGeneral = normalizarMensajeError(mensaje);

        if (hayErrorMood && !normalizarMensajeError(errores?.general)) {
            estado.classList.add('d-none');
            return;
        }

        estado.className = 'alert alert-danger mt-3';
        estado.textContent = `Error: ${mensajeGeneral || 'Revisa los datos introducidos.'}`;
        estado.classList.remove('d-none');
    }

    async function mostrarAvisoRevisionCoordenadasIA() {
        if (feedback && typeof feedback.alert === 'function') {
            await feedback.alert(AVISO_COORDENADAS_IA);
            return;
        }
        window.alert(AVISO_COORDENADAS_IA.message);
    }

    function firmaParada(parada) {
        const nombre = String(parada?.nombre || '').trim().toLowerCase();
        const coords = Array.isArray(parada?.coordenadas) ? parada.coordenadas : [null, null];
        const lat = Number(coords[0]);
        const lon = Number(coords[1]);
        const latKey = Number.isFinite(lat) ? lat.toFixed(5) : 'x';
        const lonKey = Number.isFinite(lon) ? lon.toFixed(5) : 'x';
        return `${nombre}|${latKey}|${lonKey}`;
    }

    function actualizarResumenSeleccionParadas() {
        if (!resumenSeleccionParadas) return;

        const total = propuestasParadasActivas.length;
        const seleccionadas = obtenerIndicesSeleccionados().length;
        const rechazadas = Math.max(0, total - seleccionadas);
        resumenSeleccionParadas.textContent = `Paradas seleccionadas: ${seleccionadas} · Paradas rechazadas: ${rechazadas}`;
        resumenSeleccionParadas.classList.remove('d-none');
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

    function renderizarRutaPropuesta(datos, opciones = {}) {
        seccionResultados.classList.remove('d-none');
        listaParadas.innerHTML = '';

        rutaMeta.classList.remove('d-none');
        rutaMeta.textContent = `${datos.titulo || 'Ruta propuesta'} · ${datos.duracion_horas || datos.duracion_estimada || '-'}h · Selecciona paradas`;

        const firmasSeleccionadas = opciones.firmasSeleccionadas || null;
        const firmasPrevias = opciones.firmasPrevias || null;

        propuestasParadasActivas = Array.isArray(datos.paradas) ? datos.paradas : [];
        propuestasParadasActivas.forEach((parada, idx) => {
            const firma = firmaParada(parada);
            let checked = true;
            if (firmasSeleccionadas && firmasPrevias) {
                if (firmasSeleccionadas.has(firma)) checked = true;
                else if (firmasPrevias.has(firma)) checked = false;
                else checked = true;
            } else if (firmasSeleccionadas) {
                checked = firmasSeleccionadas.has(firma) || !firmasSeleccionadas.size;
            }
            listaParadas.insertAdjacentHTML(
                'beforeend',
                `<label class="list-group-item border-start border-warning border-4 mb-2">
                    <div class="d-flex justify-content-between align-items-start gap-2">
                        <div>
                            <div class="fw-bold text-dark">Parada ${parada.orden || idx + 1}: ${parada.nombre || `Parada ${idx + 1}`}</div>
                            <div class="small text-muted">${parada.descripcion || parada.desc || parada.justificacion || 'Sin descripción'}</div>
                        </div>
                        <div class="form-check mt-1">
                            <input class="form-check-input parada-propuesta-check" type="checkbox" data-index="${idx}" ${checked ? 'checked' : ''}>
                        </div>
                    </div>
                </label>`,
            );
        });

        ayudaSeleccionParadas?.classList.remove('d-none');
        accionesSeleccionRuta?.classList.remove('d-none');
        actualizarResumenSeleccionParadas();

        document.querySelectorAll('.parada-propuesta-check').forEach((check) => {
            check.addEventListener('change', actualizarResumenSeleccionParadas);
        });

        renderizarMapa(propuestasParadasActivas);
    }

    function obtenerIndicesSeleccionados() {
        return Array.from(document.querySelectorAll('.parada-propuesta-check:checked'))
            .map((check) => Number(check.dataset.index))
            .filter((idx) => Number.isInteger(idx));
    }

    async function confirmarSeleccionRutaIA() {
        if (!sesionGeneracionActiva) {
            throw new Error('No hay una sesión de generación activa para confirmar.');
        }

        const seleccion = obtenerIndicesSeleccionados();
        if (!seleccion.length) {
            throw new Error('Debes seleccionar al menos una parada para guardar la ruta.');
        }

        const response = await fetch(config.urls.confirmar, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': config.csrfToken,
            },
            body: JSON.stringify({
                sesion_generacion_id: sesionGeneracionActiva,
                seleccion_indices: seleccion,
            }),
        });

        const data = await response.json();
        if (!response.ok || data.status !== 'OK') {
            throw new Error(data.mensaje || 'No se pudo confirmar la selección de paradas.');
        }

        return data;
    }

    async function generarParadasAdicionalesIA() {
        if (!sesionGeneracionActiva) {
            throw new Error('No hay una sesión activa para generar más paradas.');
        }

        const sugerencias = (inputSugerenciasAdicionales?.value || '').trim();
        const response = await fetch(config.urls.adicionales, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': config.csrfToken,
            },
            body: JSON.stringify({
                sesion_generacion_id: sesionGeneracionActiva,
                cantidad: 3,
                sugerencias,
            }),
        });

        const data = await response.json();
        if (!response.ok || data.status !== 'OK') {
            throw new Error(data.mensaje || 'No se pudieron generar más paradas.');
        }

        return data;
    }

    document.querySelectorAll('.mood-btn input[type="checkbox"]').forEach(function (checkbox) {
        checkbox.addEventListener('change', function () {
            this.closest('.mood-btn').classList.toggle('active', this.checked);
            if (this.checked) {
                limpiarErrorMood();
            }
        });
    });

    if (selectExigencia) {
        selectExigencia.addEventListener('change', actualizarAyudaExigencia);
        actualizarAyudaExigencia();
    }
    
    form.addEventListener('submit', async function (event) {
        event.preventDefault();
        estado.classList.add('d-none');
        limpiarErroresFormulario();
        setCargando(true);
        iniciarMensajesProgreso('generar');

        try {
            let payload = await leerFormulario();
            payload = validarPayloadPersonalizacion(payload);
            const data = await enviarPeticion(payload);
            sesionGeneracionActiva = data.sesion_generacion_id || null;

            form.classList.add('d-none');
            document.getElementById('subtitulo-form').classList.add('d-none');
            renderizarRutaPropuesta(data.datos_ruta || {});
            await mostrarAvisoRevisionCoordenadasIA();

            mostrarMensajeConCheckpoint(data.mensaje, data.checkpoint_actual || 'ruta_generada');
        } catch (error) {
            console.error(error);
            renderizarErrores(error.message, error.fieldErrors || null);
        } finally {
            setCargando(false);
        }
    });

    inicializarDeseos();

    if (btnConfirmarSeleccion) {
        btnConfirmarSeleccion.addEventListener('click', async () => {
            estado.classList.add('d-none');
            btnConfirmarSeleccion.disabled = true;
            btnConfirmarSeleccion.textContent = 'Guardando...';

            try {
                const confirmacion = await confirmarSeleccionRutaIA();
                guardarSesionGeneracionEnStorage(confirmacion.ruta_id, confirmacion.sesion_generacion_id);
                window.location.href = '/catalogo/?tipo=ia';
            } catch (error) {
                console.error(error);
                renderizarErrores(error.message);
                btnConfirmarSeleccion.disabled = false;
                btnConfirmarSeleccion.textContent = 'Guardar ruta con selección';
            }
        });
    }

    if (btnGenerarAdicionales) {
        btnGenerarAdicionales.addEventListener('click', async () => {
            estado.classList.add('d-none');
            btnGenerarAdicionales.disabled = true;
            btnGenerarAdicionales.textContent = 'Generando...';
            setCargando(true);
            iniciarMensajesProgreso('adicionales');

            try {
                const firmasSeleccionadas = new Set(
                    obtenerIndicesSeleccionados().map((idx) => firmaParada(propuestasParadasActivas[idx]))
                );
                const firmasPrevias = new Set(propuestasParadasActivas.map((p) => firmaParada(p)));

                const resultado = await generarParadasAdicionalesIA();
                const estadoSesion = await obtenerEstadoSesionGeneracion(resultado.sesion_generacion_id);
                const checkpoint = estadoSesion?.checkpoint_actual || resultado.checkpoint_actual || 'paradas_adicionales_generadas';
                const propuestas = resultado?.datos?.paradas_propuestas || [];

                renderizarRutaPropuesta(
                    {
                        titulo: 'Ruta propuesta actualizada',
                        duracion_horas: null,
                        paradas: propuestas,
                    },
                    { firmasSeleccionadas, firmasPrevias },
                );
                await mostrarAvisoRevisionCoordenadasIA();

                if (inputSugerenciasAdicionales) inputSugerenciasAdicionales.value = '';

                mostrarMensajeConCheckpoint(resultado.mensaje, checkpoint);
            } catch (error) {
                console.error(error);
                renderizarErrores(error.message);
            } finally {
                setCargando(false);
                btnGenerarAdicionales.disabled = false;
                btnGenerarAdicionales.textContent = 'Generar más paradas';
            }
        });
    }

})();
