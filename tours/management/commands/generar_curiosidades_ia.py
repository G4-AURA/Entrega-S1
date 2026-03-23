import time
from django.core.management.base import BaseCommand
from rutas.models import Parada
from rutas.services import obtener_o_generar_curiosidad_parada

class Command(BaseCommand):
    help = 'Genera mediante IA (Gemini+Wikimedia) de forma masiva curiosidades para todas las paradas que NO tengan una.'

    def handle(self, *args, **kwargs):
        paradas = Parada.objects.all()
        total = paradas.count()
        
        if total == 0:
            self.stdout.write(self.style.WARNING("No hay paradas en la base de datos."))
            return

        self.stdout.write(self.style.SUCCESS(f"Iniciando Inteligencia Artificial masiva para {total} paradas..."))
        self.stdout.write(self.style.WARNING("¡Atención! Esto puede tardar varios minutos (aprox. 10-15s por parada dependiendo de la API de Gemini)."))

        generadas_ahora = 0

        for idx, parada in enumerate(paradas, 1):
            self.stdout.write(f"\n[{idx}/{total}] Mapeando parada '{parada.nombre}' de la ruta '{parada.ruta.titulo}'...")
            
            # Llamamos a nuestro servicio central (que invoca Gemini si no existe la curiosidad)
            try:
                # El servicio espera la ciudad para la búsqueda; la sacamos de la ruta o usamos Sevilla por defecto
                ciudad_ruta = parada.ruta.ciudad if hasattr(parada.ruta, 'ciudad') and parada.ruta.ciudad else "Sevilla"
                curiosidad, fue_generada = obtener_o_generar_curiosidad_parada(parada, ciudad=ciudad_ruta)

                if fue_generada:
                    generadas_ahora += 1
                    self.stdout.write(self.style.SUCCESS(f"  ✓ IA Generó nuevo texto: '{curiosidad.titulo}'"))
                    if curiosidad.imagen_url:
                        self.stdout.write(self.style.SUCCESS(f"  ✓ Wikipedia descargó foto: Sí"))
                    else:
                        self.stdout.write(self.style.WARNING(f"  ⚠ Wikipedia no obtuvo foto (Fallback activo)"))
                    
                    # Pequeña pausa de 2 segundos para no alcanzar los límites de llamadas (Rate Limits) de la API de Wikipedia y Google
                    time.sleep(2)
                else:
                    self.stdout.write(self.style.NOTICE(f"  - Ya existía en BD (o creada por el seed), se omitió IA."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✖ Error llamando a la IA para '{parada.nombre}': {str(e)}"))

        self.stdout.write(self.style.SUCCESS(f"\n¡Proceso finalizado! Se invocó a Gemini y Wikimedia para {generadas_ahora} paradas nuevas."))
