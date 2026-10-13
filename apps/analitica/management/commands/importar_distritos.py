import json

from django.core.management.base import BaseCommand, CommandError

from apps.analitica.zonificacion import AnaliticaError, importar_distritos

# Carga los poligonos de los distritos municipales desde un GeoJSON (GAMSC u OpenStreetMap).
# Es idempotente: si el distrito ya existe (mismo nombre) se actualiza su poligono.
#
#   docker compose run --rm web python manage.py importar_distritos datos/distritos_gamsc.geojson \
#       --excluir "Área Urbana" "limite jurisdiccional" --reparar
#
# Opciones: --campo-nombre (propiedad con el nombre, por defecto "nombre"), --excluir (nombres
# que NO son distritos, ej. el limite del municipio) y --reparar (corrige poligonos invalidos).


class Command(BaseCommand):
    help = "Importa los distritos municipales desde un archivo GeoJSON."

    def add_arguments(self, parser):
        parser.add_argument("archivo", help="Ruta del GeoJSON (dentro del contenedor).")
        parser.add_argument(
            "--campo-nombre",
            default="nombre",
            help="Propiedad que contiene el nombre del distrito.",
        )
        parser.add_argument(
            "--excluir",
            nargs="*",
            default=[],
            metavar="NOMBRE",
            help="Nombres de elementos del archivo que no son distritos y se omiten.",
        )
        parser.add_argument(
            "--reparar",
            action="store_true",
            help="Corrige con GEOS los poligonos invalidos (ej. contornos que se cruzan).",
        )

    def handle(self, *args, archivo, campo_nombre, excluir, reparar, **options):
        try:
            with open(archivo, encoding="utf-8") as f:
                contenido = json.load(f)
        except (OSError, ValueError) as exc:
            raise CommandError(f"No se pudo leer '{archivo}': {exc}") from exc

        try:
            resultado = importar_distritos(
                contenido, campo_nombre=campo_nombre, reparar=reparar, excluir=excluir
            )
        except AnaliticaError as exc:
            raise CommandError(exc.mensaje) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Distritos importados: {resultado['creados']} nuevos, "
                f"{resultado['actualizados']} actualizados."
            )
        )
        for nombre in resultado["reparados"]:
            self.stdout.write(self.style.WARNING(f"Poligono reparado automaticamente: {nombre}"))
