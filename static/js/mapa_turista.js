/* =========================================
   AURA - Lógica del Mapa Inmersivo del Turista
========================================= */

document.addEventListener('DOMContentLoaded', function() {
    
    const mapElement = document.getElementById('mapa-tour');
    if (!mapElement) return;

    // 1. UX: Ocultar el Navbar
    const navbar = document.querySelector('.navbar');
    if (navbar) navbar.style.display = 'none';
    
    const mainContainer = document.querySelector('main.container');
    if (mainContainer) {
        mainContainer.style.maxWidth = '100%';
        mainContainer.style.padding = '0';
    }

    // 2. Inicialización de Leaflet
    var map = L.map('mapa-tour', {
        zoomControl: false 
    }).setView([37.3891, -5.9845], 16);

    const token = typeof mapboxToken !== 'undefined' ? mapboxToken : 'pk.tu_token_aqui';

    // Capa Híbrida de Mapbox (Satélite + Calles)
    L.tileLayer('https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12/tiles/256/{z}/{x}/{y}@2x?access_token=' + token, {
        maxZoom: 19,
        attribution: '© Mapbox © OpenStreetMap'
    }).addTo(map);

    // 3. Renderizar Paradas Dinámicamente
    if (typeof paradasData !== 'undefined' && Array.isArray(paradasData)) {
        const bounds = [];
        
        paradasData.forEach(function(parada) {
            if (parada.lat != null && parada.lng != null) {
                // Crear icono según si es la parada actual o no
                const iconHtml = parada.es_actual 
                    ? `<div style="background: linear-gradient(135deg, #10B981, #059669); width: 32px; height: 32px; border-radius: 50%; border: 4px solid white; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.6); display: flex; align-items: center; justify-content: center;">
                         <span style="color: white; font-size: 18px; font-weight: bold;">${parada.orden}</span>
                       </div>`
                    : `<div style="background-color: #9CA3AF; width: 24px; height: 24px; border-radius: 50%; border: 3px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.3); opacity: 0.7; display: flex; align-items: center; justify-content: center;">
                         <span style="color: white; font-size: 12px; font-weight: bold;">${parada.orden}</span>
                       </div>`;
                
                const icon = L.divIcon({
                    className: 'custom-div-icon',
                    html: iconHtml,
                    iconSize: parada.es_actual ? [32, 32] : [24, 24],
                    iconAnchor: parada.es_actual ? [16, 16] : [12, 12]
                });

                const marker = L.marker([parada.lat, parada.lng], {icon: icon}).addTo(map);
                marker.bindPopup(`<strong>${parada.nombre}</strong><br>Parada ${parada.orden}`);
                
                bounds.push([parada.lat, parada.lng]);
                
                // Centrar el mapa en la parada actual
                if (parada.es_actual) {
                    map.setView([parada.lat, parada.lng], 17);
                }
            }
        });
        
        // Si hay paradas pero ninguna es actual, ajustar bounds para mostrar todas
        if (bounds.length > 0 && !paradasData.some(p => p.es_actual)) {
            map.fitBounds(bounds, {padding: [50, 50]});
        }
    }

    // 4. Lógica del Panel Expandible (Bottom Sheet)
    const tourPanel = document.querySelector('.tour-panel');
    const panelHeader = document.querySelector('.panel-header');

    if (tourPanel && panelHeader) {
        panelHeader.addEventListener('click', function() {
            tourPanel.classList.toggle('expanded');
        });
    }
});