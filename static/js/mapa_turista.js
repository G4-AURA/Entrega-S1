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
    }).setView([37.3891, -5.9845], 16); // Un poco más de zoom inicial (16)

    const token = typeof mapboxToken !== 'undefined' ? mapboxToken : 'pk.tu_token_aqui';

    // NUEVO: Capa Híbrida de Mapbox (Satélite + Calles)
    L.tileLayer('https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12/tiles/256/{z}/{x}/{y}@2x?access_token=' + token, {
        maxZoom: 19,
        attribution: '© Mapbox © OpenStreetMap'
    }).addTo(map);

    // 3. Marcadores Estáticos
    var iconParada = L.divIcon({
        className: 'custom-div-icon',
        html: "<div style='background-color:#4F46E5; width:20px; height:20px; border-radius:50%; border:3px solid white; box-shadow: 0 2px 5px rgba(0,0,0,0.3);'></div>",
        iconSize: [20, 20],
        iconAnchor: [10, 10]
    });

    L.marker([37.3860, -5.9926], {icon: iconParada}).addTo(map); 
    L.marker([37.3888, -5.9946], {icon: iconParada}).addTo(map);

    // 4. NUEVO: Lógica del Panel Expandible (Bottom Sheet)
    const tourPanel = document.querySelector('.tour-panel');
    const panelHeader = document.querySelector('.panel-header');

    if (tourPanel && panelHeader) {
        panelHeader.addEventListener('click', function() {
            // Alterna la clase 'expanded' cada vez que se hace clic en la cabecera
            tourPanel.classList.toggle('expanded');
        });
    }
});