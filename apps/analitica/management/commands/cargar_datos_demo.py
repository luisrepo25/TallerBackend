from django.core.management.base import BaseCommand, CommandError

from apps.analitica import demo

# Carga predios REALES de OpenStreetMap con inspecciones SIMULADAS para probar el mapa de calor,
# las zonas sugeridas y el clustering. Todo queda marcado y se borra con --borrar.
#
#   docker compose run --rm web python manage.py cargar_datos_demo
#   docker compose run --rm web python manage.py cargar_datos_demo --por-tipo 30 --semilla 7
#   docker compose run --rm web python manage.py cargar_datos_demo --borrar
#
# Tarda varios minutos: cada acta pasa por los servicios reales contra Supabase.


class Command(BaseCommand):
    help = "Carga (o borra con --borrar) predios de OpenStreetMap con inspecciones simuladas."

    def add_arguments(self, parser):
        parser.add_argument("--por-tipo", type=int, default=15, help="Predios por tipo (5 tipos).")
        parser.add_argument("--semilla", type=int, default=42, help="Semilla del azar (repetible).")
        parser.add_argument("--borrar", action="store_true", help="Borra todos los datos demo.")

    def handle(self, *args, por_tipo, semilla, borrar, **options):
        if borrar:
            resultado = demo.borrar()
            self.stdout.write(self.style.SUCCESS(f"Datos demo borrados: {resultado}"))
            return
        if por_tipo < 1:
            raise CommandError("--por-tipo debe ser al menos 1.")
        try:
            resultado = demo.cargar(
                por_tipo=por_tipo, semilla=semilla, log=lambda m: self.stdout.write(m)
            )
        except demo.DemoError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Listo: {resultado['predios']} predios y {resultado['actas']} actas cerradas "
                "(simuladas). Ahora puedes ejecutar el clustering como Administrador."
            )
        )
