import os
from celery import Celery

# Establecer el módulo de configuración de Django por defecto para 'celery'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Instanciar la app de Celery (le damos el nombre de la carpeta principal)
app = Celery('config')

# Cargar la configuración desde settings.py de Django usando el prefijo "CELERY_"
app.config_from_object('django.conf:settings', namespace='CELERY')

# Autodescubrir tareas asíncronas en todas las aplicaciones instaladas de Django
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')