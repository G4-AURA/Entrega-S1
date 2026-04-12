import time
from django.core.management.base import BaseCommand
from django.db import DatabaseError, IntegrityError
import requests
from rutas.models import Parada
from rutas.services import obtener_o_generar_curiosidad_parada

class Command(BaseCommand):
    help = 'Genera mediante IA (Gemini+Wikimedia) de forma masiva curiosidades para todas las paradas que NO tengan una.'

    def handle(self, *args, **kwargs):
        paradas = Parada.objects.select_related('ruta').all()
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
            except ValueError as e:
                # _generar_curiosidad_ia lanza ValueError para JSON inválido o respuesta malformada
                self.stdout.write(self.style.ERROR(
                    f"  ✖ Respuesta de IA inválida para '{parada.nombre}': {e}"
                ))
            except RuntimeError as e:
                # _generar_curiosidad_ia lanza RuntimeError para errores de red con Gemini/SDK
                self.stdout.write(self.style.ERROR(
                    f"  ✖ Error de red con la IA para '{parada.nombre}': {e}"
                ))
            except (DatabaseError, IntegrityError) as e:
                # _guardar_curiosidad_en_cache puede fallar al persistir
                self.stdout.write(self.style.ERROR(
                    f"  ✖ Error de base de datos guardando curiosidad de '{parada.nombre}': {e}"
                ))
            except requests.RequestException as e:
                # _buscar_wikimedia puede lanzar RequestException no capturada en algún path
                self.stdout.write(self.style.ERROR(
                    f"  ✖ Error de red con Wikimedia para '{parada.nombre}': {e}"
                ))

        self.stdout.write(self.style.SUCCESS(f"\n¡Proceso finalizado! Se invocó a Gemini y Wikimedia para {generadas_ahora} paradas nuevas."))
