from django.core.management.base import BaseCommand

from apps.campanias.services import cerrar_campanias_vencidas


class Command(BaseCommand):
    help = (
        "Cierra automaticamente las campanias cuya fecha_fin ya paso. "
        "Programar diariamente (cron / scheduler del hosting)."
    )

    def handle(self, *args, **options):
        cerradas = cerrar_campanias_vencidas()
        self.stdout.write(
            self.style.SUCCESS(f"Campanias cerradas por vencimiento: {len(cerradas)}")
        )
        for campania_id in cerradas:
            self.stdout.write(f"  - campania {campania_id}")
