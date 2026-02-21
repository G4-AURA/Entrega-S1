from django.conf import settings

def mapbox_settings(request):
    return {
        'MAPBOX_ACCESS_TOKEN': settings.MAPBOX_ACCESS_TOKEN
    }