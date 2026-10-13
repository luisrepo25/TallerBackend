from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework import status

from apps.analitica import cliente_ml, services
from apps.analitica.models import ClusteringEjecucion
from apps.analitica.tests.base import BaseAnaliticaTestCase
from apps.usuarios.models import BitacoraAuditoria

URL = "/api/analitica/clustering/"
LLAMADA_ML = "apps.analitica.services.cliente_ml.ejecutar_clustering"


def ml_simulado(actas):
    """Imita al microservicio: clasifica por scoring (<34 Bajo, <67 Medio, resto Critico)."""
    nivel = lambda s: "Bajo" if s < 34 else "Medio" if s < 67 else "Critico"  # noqa: E731
    return {
        "k": 3,
        "cantidad_actas": len(actas),
        "coeficiente_silueta": 0.812,
        "clusters": [
            {"acta_id": a["acta_id"], "cluster_riesgo": nivel(a["scoring_riesgo"])} for a in actas
        ],
        "resumen": [{"cluster_riesgo": "Bajo", "cantidad_actas": 1, "scoring_promedio": 10.0}],
    }


class PayloadTests(BaseAnaliticaTestCase):
    def payload_de(self, acta):
        filas = services.actas_para_clustering().filter(pk=acta.pk)
        return services.construir_payload(filas)[0]

    def test_traduce_los_campos_al_contrato_del_ml(self):
        acta = self.crear_acta(
            extintores="Vencido",
            fallas_electricas=True,
            rutas_evacuacion_despejadas=False,
            distancia_hidrante_m=Decimal("120.50"),
            scoring="41.20",
            carga="83.61",
        )
        self.assertEqual(
            self.payload_de(acta),
            {
                "acta_id": acta.pk,
                "carga_fuego": 83.61,
                "riesgo_extintores": 0.5,
                "fallas_electricas": True,
                "rutas_obstruidas": True,
                "distancia_hidrante_m": 120.5,
                "scoring_riesgo": 41.2,
            },
        )

    def test_sin_hidrante_envia_null_y_no_posee_vale_uno(self):
        acta = self.crear_acta(extintores="No posee")
        payload = self.payload_de(acta)
        self.assertIsNone(payload["distancia_hidrante_m"])
        self.assertEqual(payload["riesgo_extintores"], 1.0)

    def test_excluye_actas_abiertas(self):
        abierta = self.crear_acta(cerrada=False)
        self.assertFalse(services.actas_para_clustering().filter(pk=abierta.pk).exists())


class EjecutarClusteringServiceTests(BaseAnaliticaTestCase):
    def test_guarda_el_cluster_en_cada_acta_y_registra_la_ejecucion(self):
        baja = self.crear_acta(scoring="10.00")
        critica = self.crear_acta(scoring="90.00")
        with patch(LLAMADA_ML, side_effect=ml_simulado):
            resultado = services.ejecutar_clustering(usuario=self.admin)

        baja.refresh_from_db()
        critica.refresh_from_db()
        self.assertEqual(baja.cluster_riesgo, "Bajo")
        self.assertEqual(critica.cluster_riesgo, "Critico")
        ejecucion = resultado["ejecucion"]
        ejecucion.refresh_from_db()
        self.assertEqual(ejecucion.coeficiente_silueta, Decimal("0.812"))
        self.assertEqual(ejecucion.ejecutado_por_id, self.admin.pk)

    def test_deja_rastro_en_bitacora(self):
        self.crear_acta()
        with patch(LLAMADA_ML, side_effect=ml_simulado):
            services.ejecutar_clustering(usuario=self.admin)
        self.assertTrue(
            BitacoraAuditoria.objects.filter(
                usuario=self.admin, accion="Ejecutar clustering de riesgo"
            ).exists()
        )

    def test_rechazo_del_ml_es_conflicto_y_no_escribe_nada(self):
        acta = self.crear_acta()
        antes = ClusteringEjecucion.objects.count()
        with patch(
            LLAMADA_ML, side_effect=cliente_ml.ServicioMLRechazo("Se necesitan al menos 4 actas.")
        ):
            with self.assertRaises(services.AnaliticaConflicto):
                services.ejecutar_clustering(usuario=self.admin)
        acta.refresh_from_db()
        self.assertIsNone(acta.cluster_riesgo)
        self.assertEqual(ClusteringEjecucion.objects.count(), antes)

    def test_nivel_desconocido_no_escribe_nada(self):
        acta = self.crear_acta()

        def malo(actas):
            return {
                **ml_simulado(actas),
                "clusters": [{"acta_id": acta.pk, "cluster_riesgo": "Alto"}],
            }

        antes = ClusteringEjecucion.objects.count()
        with patch(LLAMADA_ML, side_effect=malo):
            with self.assertRaises(cliente_ml.ServicioMLNoDisponible):
                services.ejecutar_clustering(usuario=self.admin)
        self.assertEqual(ClusteringEjecucion.objects.count(), antes)


class ClusteringApiTests(BaseAnaliticaTestCase):
    def test_admin_ejecuta_y_recibe_201(self):
        self.crear_acta(scoring="90.00")
        self.client.force_authenticate(self.admin)
        with patch(LLAMADA_ML, side_effect=ml_simulado):
            r = self.client.post(URL)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["ejecucion"]["coeficiente_silueta"], "0.812")
        self.assertEqual(r.data["ejecucion"]["k_value"], 3)

    def test_oficial_no_puede_ejecutar_pero_si_consultar(self):
        self.client.force_authenticate(self.oficial)
        self.assertEqual(self.client.post(URL).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get(URL).status_code, status.HTTP_200_OK)

    def test_inspector_no_entra(self):
        self.client.force_authenticate(self.inspector)
        self.assertEqual(self.client.get(URL).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_sin_autenticar_es_401(self):
        self.assertEqual(self.client.get(URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_pocas_actas_responde_409_con_el_motivo(self):
        self.client.force_authenticate(self.admin)
        rechazo = cliente_ml.ServicioMLRechazo("Se necesitan al menos 4 actas cerradas.")
        with patch(LLAMADA_ML, side_effect=rechazo):
            r = self.client.post(URL)
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("al menos 4", r.data["detail"])

    def test_microservicio_caido_responde_503(self):
        self.client.force_authenticate(self.admin)
        caido = cliente_ml.ServicioMLNoDisponible("No se pudo contactar al servicio de clustering.")
        with patch(LLAMADA_ML, side_effect=caido):
            r = self.client.post(URL)
        self.assertEqual(r.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_historial_lista_las_ejecuciones(self):
        ejecucion = ClusteringEjecucion.objects.create(
            k_value=3, coeficiente_silueta=Decimal("0.700"), ejecutado_por=self.admin
        )
        self.client.force_authenticate(self.oficial)
        r = self.client.get(URL)
        self.assertIn(ejecucion.pk, [fila["id"] for fila in r.data])


@override_settings(ML_SERVICE_URL="http://ml.invalido.test", ML_API_KEY="k", ML_TIMEOUT_SEGUNDOS=1)
class ClienteMLTests(TestCase):
    def test_red_caida_es_servicio_no_disponible(self):
        with patch("urllib.request.urlopen", side_effect=OSError("sin red")):
            with self.assertRaises(cliente_ml.ServicioMLNoDisponible):
                cliente_ml.ejecutar_clustering([])
