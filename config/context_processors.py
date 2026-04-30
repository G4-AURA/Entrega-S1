from django.conf import settings


def mapbox_settings(request):
    return {
        'MAPBOX_ACCESS_TOKEN': settings.MAPBOX_ACCESS_TOKEN,
        'MAP_TILE_CONFIG': {
            'provider': settings.MAP_TILE_PROVIDER,
            'url': settings.MAP_TILE_URL,
            'attribution': settings.MAP_TILE_ATTRIBUTION,
            'maxZoom': settings.MAP_TILE_MAX_ZOOM,
            'mapboxToken': settings.MAPBOX_ACCESS_TOKEN or '',
        },
    }
