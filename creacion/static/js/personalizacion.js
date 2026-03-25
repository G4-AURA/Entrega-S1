(function() {
    const form = document.getElementById('form-personalizacion-ruta');
    const boton = document.getElementById('btn-generar-ruta');
    const estado = document.getElementById('estado-respuesta');
    const pantallaCarga = document.getElementById('pantalla-carga');
    const rutaMeta = document.getElementById('ruta-meta');
    
    let leafletMap = null;
    const mapboxToken = document.querySelector('meta[name="mapbox-token"]')?.content || '';

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
        
        // Limpiar lista anterior
        while (lista.firstChild) lista.removeChild(lista.firstChild);

        // Mostrar metadatos de la ruta
        rutaMeta.classList.remove('d-none');
        rutaMeta.textContent = (datos.titulo || 'Ruta generada') + ' · ' + (datos.duracion_horas || datos.duracion_estimada || '-') + 'h · Exigencia ' + (datos.nivel_exigencia || '-');

        // Reiniciar Mapa si ya existe para evitar errores de instancias múltiples
        if (leafletMap) {
            leafletMap.remove();
        }

        // Determinar centro del mapa
        const primeraParada = (datos.paradas && datos.paradas[0]) || null;
        const coordenadaInicial = (primeraParada && (primeraParada.coordenadas || primeraParada.coords)) 
                                  ? (primeraParada.coordenadas || primeraParada.coords) 
                                  : [40.4167, -3.7037]; // Default si falla

        // Crear mapa
        leafletMap = L.map('mapa-ruta').setView(coordenadaInicial, 14);
        
        L.tileLayer(`https://api.mapbox.com/styles/v1/mapbox/streets-v12/tiles/256/{z}/{x}/{y}@2x?access_token=${mapboxToken}`, {
            attribution: '© Mapbox'
        }).addTo(leafletMap);

        const puntos = [];
        
        // Dibujar paradas
        if (datos.paradas && datos.paradas.length > 0) {
            datos.paradas.forEach((p, idx) => {
                // Normalizar coordenadas (pueden venir como 'coords' o 'coordenadas')
                const coords = p.coordenadas || p.coords;
                if(!coords) return;

                puntos.push(coords);
                
                // Marcador en el mapa
                L.marker(coords).addTo(leafletMap)
                    .bindPopup(`<b>${p.orden || idx + 1}. ${p.nombre}</b>`);

                // Elemento en la lista lateral
                const item = document.createElement('div');
                item.className = 'list-group-item border-start border-4 mb-2';
                item.style.borderColor = 'var(--brand-color)';
                const itemTitle = document.createElement('div');
                itemTitle.className = 'fw-bold';
                itemTitle.style.color = 'var(--brand-color)';
                itemTitle.textContent = 'Parada ' + (p.orden || idx + 1) + ': ' + p.nombre;
                const itemDesc = document.createElement('div');
                itemDesc.className = 'small text-muted';
                itemDesc.textContent = p.descripcion || p.desc || 'Sin descripción';
                item.appendChild(itemTitle);
                item.appendChild(itemDesc);
                lista.appendChild(item);
            });

            // Dibujar línea de conexión y ajustar vista
            if (puntos.length > 1) {
                L.polyline(puntos, {color: '#4F46E5', weight: 4, opacity: 0.7}).addTo(leafletMap);
                leafletMap.fitBounds(puntos, {padding: [50, 50]});
            }
        }
    }

    // Manejar la activación visual de los botones de mood
    function initMoodButtons() {
        document.querySelectorAll('.mood-btn input[type="checkbox"]').forEach(checkbox => {
            checkbox.addEventListener('change', function() {
                this.closest('.mood-btn').classList.toggle('active', this.checked);
            });
        });
    }

    function getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Limpiar estados anteriores
        estado.classList.add('d-none');
        setCargando(true);

        const moodSeleccionados = Array.from(form.querySelectorAll('input[name="mood"]:checked'))
            .map(checkbox => checkbox.value);

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
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify(payload),
            });

            const data = await response.json();

            if (response.ok && data.status === "OK") {
                renderizarRuta(data.datos_ruta);
                estado.className = "alert alert-success mt-3";
                estado.textContent = data.mensaje;
                estado.classList.remove('d-none');
            } else {
                throw new Error(data.mensaje || "Error desconocido al generar la ruta");
            }
        } catch (error) {
            console.error(error);
            estado.className = "alert alert-danger mt-3";
            estado.textContent = "Error: " + error.message;
            estado.classList.remove('d-none');
        } finally {
            setCargando(false);
        }
    });

    // Initialize on DOM ready
    document.addEventListener('DOMContentLoaded', initMoodButtons);
})();
