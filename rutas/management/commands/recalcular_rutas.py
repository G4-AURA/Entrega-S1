"""
rutas/management/commands/recalcular_rutas.py

Recalcula la geometría GraphHopper para todas las rutas que no la tienen.
Ejecutar con: python manage.py recalcular_rutas

Opciones:
  --todas       Recalcula también las rutas que ya tienen geometría
  --ruta <id>   Recalcula solo la ruta con ese ID
  --dry-run     Muestra qué haría sin ejecutar nada
"""
import time
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Recalcula la geometría GraphHopper de las rutas existentes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--todas',
            action='store_true',
            help='Recalcula también las rutas que ya tienen geometría',
        )
        parser.add_argument(
            '--ruta',
            type=int,
            metavar='ID',
            help='Recalcula únicamente la ruta con este ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra qué haría sin ejecutar ningún cálculo',
        )

    def handle(self, *args, **options):
        from rutas.models import Ruta
        from rutas.services import recalcular_ruta_graphhopper

        dry = options['dry_run']

        self.stdout.write(self.style.HTTP_INFO(
            '\n══════════════════════════════════════════'
        ))
        self.stdout.write(self.style.HTTP_INFO(
            '  RECALCULAR RUTAS — GraphHopper'
            + (' (DRY RUN)' if dry else '')
        ))
        self.stdout.write(self.style.HTTP_INFO('══════════════════════════════════════════\n'))

        # ── Construir queryset ────────────────────────────────────────────────
        if options['ruta']:
            qs = Ruta.objects.filter(id=options['ruta'])
            if not qs.exists():
                self.stdout.write(self.style.ERROR(
                    f'❌ No existe ninguna ruta con id={options["ruta"]}'
                ))
                return
        elif options['todas']:
            qs = Ruta.objects.all()
        else:
            # Por defecto: solo las que no tienen geometría
            qs = Ruta.objects.filter(geometria_ruta__isnull=True)

        # Filtrar las que tienen < 2 paradas (no calculables)
        candidatas = []
        saltadas   = []
        for ruta in qs.prefetch_related('paradas'):
            n_paradas = sum(1 for p in ruta.paradas.all() if p.coordenadas)
            if n_paradas >= 2:
                candidatas.append(ruta)
            else:
                saltadas.append((ruta, n_paradas))

        total = len(candidatas)

        if not candidatas:
            self.stdout.write(self.style.WARNING(
                '⚠️  No hay rutas candidatas.\n'
                '   Si esperas rutas sin geometría, comprueba que tienen ≥2 paradas '
                'con coordenadas o usa --todas.'
            ))
            return

        self.stdout.write(f'Rutas a procesar: {total}')
        if saltadas:
            self.stdout.write(
                f'Rutas omitidas por < 2 paradas: {len(saltadas)}'
            )

        if dry:
            self.stdout.write('\nRutas que SE CALCULARÍAN:')
            for ruta in candidatas:
                self.stdout.write(f'  id={ruta.id} | "{ruta.titulo}"')
            return

        # ── Procesar ──────────────────────────────────────────────────────────
        exitos  = 0
        errores = 0

        for i, ruta in enumerate(candidatas, 1):
            self.stdout.write(f'[{i}/{total}] "{ruta.titulo}" (id={ruta.id})... ', ending='')

            try:
                ok = recalcular_ruta_graphhopper(ruta)
                if ok:
                    ruta.refresh_from_db()
                    dist = f'{ruta.distancia_total_m:.0f}m' if ruta.distancia_total_m else '?'
                    dur  = f'{ruta.duracion_total_min}min' if ruta.duracion_total_min else '?'
                    self.stdout.write(self.style.SUCCESS(f'✅ {dist} · {dur}'))
                    exitos += 1
                else:
                    self.stdout.write(self.style.WARNING('⚠️  sin resultado (ver logs)'))
                    errores += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ {e}'))
                errores += 1

            # Pequeña pausa para respetar los límites de la API gratuita de GraphHopper
            # (250 req/día en plan free; con N-1 llamadas por segmento, espaciar es prudente)
            if i < total:
                time.sleep(0.3)

        # ── Resumen ───────────────────────────────────────────────────────────
        self.stdout.write('\n' + self.style.HTTP_INFO('─── RESULTADO ───'))
        self.stdout.write(self.style.SUCCESS(f'✅ Éxitos:  {exitos}'))
        if errores:
            self.stdout.write(self.style.ERROR(
                f'❌ Errores: {errores}  '
                '→ revisa los logs del servidor para ver el detalle'
            ))
        self.stdout.write('')