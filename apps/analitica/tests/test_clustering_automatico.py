from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command

from apps.analitica import cliente_ml, services
from apps.analitica.models import ClusteringEjecucion
from apps.analitica.tests.base import BaseAnaliticaTestCase
from apps.analitica.tests.test_clustering import LLAMADA_ML, ml_simulado
from apps.usuarios.models import BitacoraAuditoria


class ClusteringAutomaticoTests(BaseAnaliticaTestCase):
    def ejecutar(self):
        salida = StringIO()
        call_command("ejecutar_clustering_automatico", stdout=salida)
        return salida.getvalue()

    def test_clasifica_las_actas_y_registra_la_ejecucion_automatica(self):
        nueva = self.crear_acta(scoring="90.00")
        with patch(LLAMADA_ML, side_effect=ml_simulado):
            salida = self.ejecutar()

        nueva.refresh_from_db()
        self.assertEqual(nueva.cluster_riesgo, "Critico")
        self.assertIn("Clustering automatico listo", salida)
        self.assertTrue(ClusteringEjecucion.objects.exists())
        self.assertTrue(
            BitacoraAuditoria.objects.filter(
                accion="Ejecutar clustering de riesgo (automatico)"
            ).exists()
        )

    def test_con_pocas_actas_se_omite_sin_error(self):
        rechazo = cliente_ml.ServicioMLRechazo("Se necesitan al menos 4 actas cerradas.")
        with patch(LLAMADA_ML, side_effect=rechazo):
            self.assertIn("Clustering omitido", self.ejecutar())

    def test_si_el_ml_no_responde_el_comando_falla_para_que_el_job_lo_reporte(self):
        caido = cliente_ml.ServicioMLNoDisponible("No se pudo contactar al servicio.")
        with patch(LLAMADA_ML, side_effect=caido), self.assertRaises(CommandError):
            self.ejecutar()

    def test_sin_administrador_activo_falla_con_mensaje_claro(self):
        with patch(
            "apps.analitica.services.Administrador.objects.select_related"
        ) as consulta:
            consulta.return_value.filter.return_value.order_by.return_value.first.return_value = None
            with self.assertRaises(services.SinAdministrador):
                services.administrador_para_ejecucion_automatica()
