from django.core.management.base import BaseCommand, CommandError

from apps.analitica import services


class Command(BaseCommand):
    help = (
        "Ejecuta el clustering K-Means sobre todas las actas cerradas (como el boton del "
        "Administrador) para que las actas nuevas reciban su nivel de riesgo. Programar de "
        "noche (Cloud Scheduler). La ejecucion se atribuye al primer Administrador activo."
    )

    def handle(self, *args, **options):
        try:
            usuario = services.administrador_para_ejecucion_automatica()
            resultado = services.ejecutar_clustering(usuario=usuario, automatico=True)
        except services.AnaliticaConflicto as exc:
            # Pocas actas o actas identicas: no es un fallo del sistema, solo no hay que agrupar.
            self.stdout.write(self.style.WARNING(f"Clustering omitido: {exc.mensaje}"))
            return
        except (services.SinAdministrador, services.cliente_ml.ServicioMLNoDisponible) as exc:
            raise CommandError(str(exc)) from exc

        ejecucion = resultado["ejecucion"]
        self.stdout.write(
            self.style.SUCCESS(
                f"Clustering automatico listo: {resultado['cantidad_actas']} actas, "
                f"silueta {ejecucion.coeficiente_silueta}."
            )
        )
