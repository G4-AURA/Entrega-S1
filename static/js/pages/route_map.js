(function () {
    function crearMapaRuta({ elementId, center, token }) {
        const map = L.map(elementId).setView(center, 14);
        window.AuraMapTiles.createTileLayer({ token, style: 'streets' }).addTo(map);
        return map;
    }

    function renderizarParadasEnMapa(map, paradas) {
        const puntos = [];

        paradas.forEach((parada, idx) => {
            const coords = parada.coordenadas || parada.coords;
            if (!coords || coords.length < 2) {
                return;
            }

            puntos.push(coords);
            L.marker(coords)
                .addTo(map)
                .bindPopup(`<b>${parada.orden || idx + 1}. ${parada.nombre || `Parada ${idx + 1}`}</b>`);
        });

        if (puntos.length > 1) {
            L.polyline(puntos, { color: '#0d6efd', weight: 4, opacity: 0.7 }).addTo(map);
            map.fitBounds(puntos, { padding: [50, 50] });
        }
    }

    function crearSelectorUbicacion({ mapId, initialCoords = [37.3886, -5.9823] }) {
        let map = null;
        let marker = null;
        let tempCoords = null;

        function ensureMap() {
            if (map) {
                return map;
            }

            map = L.map(mapId).setView(initialCoords, 13);
            window.AuraMapTiles.createTileLayer({ style: 'streets' }).addTo(map);

            map.on('click', function (event) {
                tempCoords = event.latlng;
                if (marker) {
                    marker.setLatLng(tempCoords);
                } else {
                    marker = L.marker(tempCoords).addTo(map);
                }
            });

            return map;
        }

        function open() {
            ensureMap();
            setTimeout(function () {
                map.invalidateSize();
            }, 100);
        }

        function close() {
            tempCoords = null;
            if (map && marker) {
                map.removeLayer(marker);
                marker = null;
            }
        }

        function getCoords() {
            return tempCoords;
        }

        return { open, close, getCoords };
    }

    window.MapaCreacion = {
        crearMapaRuta,
        renderizarParadasEnMapa,
        crearSelectorUbicacion,
    };
})();
