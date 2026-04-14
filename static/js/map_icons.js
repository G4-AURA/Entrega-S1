// static/js/map_icons.js

window.buildAuraMarkerIcon = function(parada, options = {}) {
    // Valores por defecto si no se pasan opciones
    const { highlighted = false, role = null, esActual = false } = options;

    // 1. ESTADO SELECCIONADO (Naranja)
    if (highlighted) {
        let svg = '';
        if (role === 'origin') svg = '<svg viewBox="0 0 12 12" width="12" height="12" fill="white"><polygon points="6,1 11,10 1,10"/></svg>';
        else if (role === 'destination') svg = '<svg viewBox="0 0 12 12" width="12" height="12" fill="white"><rect x="1" y="1" width="10" height="10" rx="2"/></svg>';

        return L.divIcon({
            className: '',
            html: `<div style="background:#f97316;width:40px;height:40px;border-radius:50%;border:3px solid white;box-shadow:0 0 0 4px rgba(249,115,22,.25),0 4px 12px rgba(249,115,22,.45);display:flex;align-items:center;justify-content:center;flex-direction:column;gap:0;">
                    ${svg}
                    <span style="color:white;font-size:15px;font-weight:800;line-height:1;">${parada.orden}</span>
                  </div>`,
            iconSize: [40, 40], iconAnchor: [20, 20], popupAnchor: [0, -24],
        });
    }

    // 2. ESTADO INICIO
    if (role === 'origin') {
        const bg = esActual ? '#4f46e5' : '#16a34a';
        const shadow = esActual ? 'rgba(79,70,229,.5)' : 'rgba(22,163,74,.5)';
        const size = esActual ? 34 : 30;
        return L.divIcon({
            className: '',
            html: `<div style="background:${bg};width:${size}px;height:${size}px;border-radius:50%;border:3px solid white;box-shadow:0 2px 10px ${shadow};display:flex;align-items:center;justify-content:center;flex-direction:column;gap:0;">
                    <svg viewBox="0 0 12 12" width="11" height="11" fill="white"><polygon points="6,1 11,10 1,10"/></svg>
                    <span style="color:white;font-size:9px;font-weight:800;line-height:1;">${parada.orden}</span>
                  </div>`,
            iconSize: [size, size], iconAnchor: [size/2, size/2], popupAnchor: [0, -(size/2)-4],
        });
    }

    // 3. ESTADO FIN
    if (role === 'destination') {
        const bg = esActual ? '#4f46e5' : '#dc2626';
        const shadow = esActual ? 'rgba(79,70,229,.5)' : 'rgba(220,38,38,.5)';
        const size = esActual ? 34 : 30;
        return L.divIcon({
            className: '',
            html: `<div style="background:${bg};width:${size}px;height:${size}px;border-radius:50%;border:3px solid white;box-shadow:0 2px 10px ${shadow};display:flex;align-items:center;justify-content:center;flex-direction:column;gap:0;">
                    <svg viewBox="0 0 12 12" width="11" height="11" fill="white"><rect x="1" y="1" width="10" height="10" rx="2"/></svg>
                    <span style="color:white;font-size:9px;font-weight:800;line-height:1;">${parada.orden}</span>
                  </div>`,
            iconSize: [size, size], iconAnchor: [size/2, size/2], popupAnchor: [0, -(size/2)-4],
        });
    }

    // 4. ESTADO POR DEFECTO (Intermedias)
    const size = esActual ? 34 : 26;
    const bg = esActual ? '#4f46e5' : '#d1d5db';
    return L.divIcon({
        className: '',
        html: `<div style="background:${bg};width:${size}px;height:${size}px;border-radius:50%;border:${esActual ? 3 : 2}px solid white;box-shadow:0 ${esActual ? '2px 10px rgba(79,70,229,.45)' : '1px 5px rgba(0,0,0,.18)'};display:flex;align-items:center;justify-content:center;">
                <span style="color:${esActual ? '#fff' : '#6b7280'};font-size:${esActual ? 14 : 11}px;font-weight:${esActual ? 700 : 600};">${parada.orden}</span>
              </div>`,
        iconSize: [size, size], iconAnchor: [size/2, size/2], popupAnchor: [0, -(size/2)-4],
    });
};