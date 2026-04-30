(function () {
    function readConfig() {
        const node = document.getElementById('aura-map-tiles-config');
        if (!node) return {};

        try {
            return JSON.parse(node.textContent || '{}');
        } catch (error) {
            console.error('[AURA maps] Configuracion de tiles invalida:', error);
            return {};
        }
    }

    const config = readConfig();
    const providerAttribution = {
        mapbox: '&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        osm: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
        carto: '&copy; <a href="https://carto.com/attributions">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    };

    function createTileDefinition(options) {
        const style = options?.style || 'streets';
        const token = options?.token || config.mapboxToken || '';
        const provider = (options?.provider || config.provider || (token ? 'mapbox' : 'carto')).toLowerCase();
        const maxZoom = Number(options?.maxZoom || config.maxZoom || 19);

        if (config.url) {
            return {
                url: config.url,
                options: {
                    attribution: config.attribution || providerAttribution[provider] || '',
                    maxZoom,
                    referrerPolicy: 'strict-origin-when-cross-origin',
                },
            };
        }

        if (provider === 'mapbox' && token) {
            const mapboxStyle = style === 'light' ? 'light-v11' : 'streets-v12';
            return {
                url: `https://api.mapbox.com/styles/v1/mapbox/${mapboxStyle}/tiles/256/{z}/{x}/{y}@2x?access_token=${token}`,
                options: {
                    attribution: config.attribution || providerAttribution.mapbox,
                    maxZoom,
                },
            };
        }

        if (provider === 'osm') {
            return {
                url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                options: {
                    attribution: config.attribution || providerAttribution.osm,
                    maxZoom,
                    referrerPolicy: 'strict-origin-when-cross-origin',
                },
            };
        }

        return {
            url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
            options: {
                attribution: config.attribution || providerAttribution.carto,
                maxZoom,
            },
        };
    }

    function createTileLayer(options) {
        const definition = createTileDefinition(options);
        return L.tileLayer(definition.url, Object.assign({}, definition.options, options?.leafletOptions || {}));
    }

    window.AuraMapTiles = {
        createTileDefinition,
        createTileLayer,
    };
})();
