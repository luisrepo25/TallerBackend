import io
import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import openpyxl
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.analitica.tests.test_clustering import LLAMADA_ML, ml_simulado
from apps.catastro.models import CatalogoTipoPredio
from apps.fiscalizacion.models import (
    ActaInspeccion,
    CatalogoEstadoExtintor,
    CatalogoInfraccion,
    CatalogoMaterialCombustible,
)
from apps.reportes.models import ReporteGenerado
from apps.usuarios.models import BitacoraAuditoria, Rol
from apps.usuarios.services import crear_usuario


class FlujoCompletoIntegracionE2ETests(TestCase):
    """Suite de integracion end-to-end (Fase 8):
    crear campania -> asignar inspector -> registrar acta con materiales e infraccion ->
    cerrar acta -> ejecutar clustering K-Means -> generar reporte ejecutivo y dictamen."""

    def setUp(self):
        self.suffix = uuid.uuid4().hex[:6]
        self.admin = self._usuario("Administrador", "administrador", "admin")
        self.oficial = self._usuario("Oficial de Mando", "oficial_mando", "oficial")
        self.inspector = self._usuario("Inspector Tecnico", "inspector_tecnico", "insp")

        self.tipo_mercado, _ = CatalogoTipoPredio.objects.get_or_create(
            nombre=f"Mercado E2E {self.suffix}",
            defaults={
                "categoria_riesgo_base": "Alto",
                "riesgo_activacion": Decimal("1.50"),
            },
        )
        self.extintor_vigente = CatalogoEstadoExtintor.objects.get(nombre="Vigente")
        self.mat_madera, _ = CatalogoMaterialCombustible.objects.get_or_create(
            nombre=f"Madera E2E {self.suffix}",
            defaults={
                "poder_calorifico_mj_kg": Decimal("18.41"),
                "coeficiente_peligrosidad": Decimal("1.00"),
            },
        )
        self.mat_plastico, _ = CatalogoMaterialCombustible.objects.get_or_create(
            nombre=f"Plastico E2E {self.suffix}",
            defaults={
                "poder_calorifico_mj_kg": Decimal("25.00"),
                "coeficiente_peligrosidad": Decimal("1.50"),
            },
        )
        self.infraccion_tipo, _ = CatalogoInfraccion.objects.get_or_create(
            nombre=f"Falta senalizacion E2E {self.suffix}",
            defaults={"peso_severidad": Decimal("1.00")},
        )
        self.client = APIClient()

    def _usuario(self, rol, subtipo, prefijo):
        return crear_usuario(
            nombre_completo=f"{prefijo} {self.suffix}",
            email=f"{prefijo}.e2e.{self.suffix}@uubr.org.bo",
            password="claveSegura123",
            rol=Rol.objects.get(nombre=rol),
            subtipo=subtipo,
        )

    def test_flujo_completo_de_punta_a_punta_via_api(self):
        # 1. Administrador registra un predio en catastro dentro de la zona
        self.client.force_authenticate(user=self.admin)
        res_predio = self.client.post(
            "/api/catastro/predios/",
            {
                "nombre": f"Mercado Central {self.suffix}",
                "direccion": "Av. Grigota #100",
                "tipo_predio": self.tipo_mercado.pk,
                "aforo": 300,
                "area_m2": "200.00",
                "geom": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-63.198, -17.798],
                            [-63.197, -17.798],
                            [-63.197, -17.797],
                            [-63.198, -17.797],
                            [-63.198, -17.798],
                        ]
                    ],
                },
            },
            format="json",
        )
        self.assertEqual(res_predio.status_code, status.HTTP_201_CREATED)
        predio_id = res_predio.data["id"]

        # 2. Administrador crea la campania delimitando el poligono de la zona
        res_campania = self.client.post(
            "/api/campanias/campanias/",
            {
                "nombre": f"Campania E2E {self.suffix}",
                "fecha_inicio": str(date.today()),
                "fecha_fin": str(date.today() + timedelta(days=15)),
                "geom": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-63.200, -17.800],
                            [-63.190, -17.800],
                            [-63.190, -17.790],
                            [-63.200, -17.790],
                            [-63.200, -17.800],
                        ]
                    ],
                },
            },
            format="json",
        )
        self.assertEqual(res_campania.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_campania.data["estado"], "pendiente")
        campania_id = res_campania.data["id"]

        # 3. Administrador asigna al inspector tecnico -> campania pasa a 'en_curso'
        res_asignar = self.client.post(
            f"/api/campanias/campanias/{campania_id}/asignar-inspectores/",
            {"usuarios_ids": [self.inspector.pk]},
            format="json",
        )
        self.assertEqual(res_asignar.status_code, status.HTTP_200_OK)
        self.assertEqual(res_asignar.data["estado"], "en_curso")

        # 4. Inspector registra acta de inspeccion con materiales e infraccion
        self.client.force_authenticate(user=self.inspector)
        res_acta = self.client.post(
            "/api/fiscalizacion/actas/",
            {
                "predio": predio_id,
                "campania": campania_id,
                "estado_extintores": self.extintor_vigente.pk,
                "fallas_electricas": True,
                "rutas_evacuacion_despejadas": False,
                "distancia_hidrante_m": "100.00",
                "materiales": [
                    {"material_id": self.mat_madera.pk, "peso_kg": "300.00"},
                    {"material_id": self.mat_plastico.pk, "peso_kg": "150.00"},
                ],
            },
            format="json",
        )
        self.assertEqual(res_acta.status_code, status.HTTP_201_CREATED)
        acta_id = res_acta.data["id"]

        res_inf = self.client.post(
            f"/api/fiscalizacion/actas/{acta_id}/infracciones/",
            {
                "tipo_infraccion_id": self.infraccion_tipo.pk,
                "descripcion": "Pasillo principal bloqueado",
            },
            format="json",
        )
        self.assertEqual(res_inf.status_code, status.HTTP_201_CREATED)

        # 5. Inspector cierra el acta -> calcula carga de fuego NB 58005 (83.61) y scoring
        res_cerrar = self.client.post(
            f"/api/fiscalizacion/actas/{acta_id}/cerrar/", {}, format="json"
        )
        self.assertEqual(res_cerrar.status_code, status.HTTP_200_OK)
        self.assertTrue(res_cerrar.data["cerrada"])
        self.assertEqual(res_cerrar.data["carga_fuego"], "83.61")
        self.assertIsNotNone(res_cerrar.data["scoring_riesgo"])

        # Verifica que cada accion de fiscalizacion se registro una sola vez en bitacora
        self.assertEqual(
            BitacoraAuditoria.objects.filter(
                usuario=self.inspector, accion="Registrar acta de inspeccion"
            ).count(),
            1,
        )
        self.assertEqual(
            BitacoraAuditoria.objects.filter(
                usuario=self.inspector, accion="Cerrar acta de inspeccion"
            ).count(),
            1,
        )

        # 6. Administrador ejecuta el clustering K-Means
        self.client.force_authenticate(user=self.admin)
        with patch(LLAMADA_ML, side_effect=ml_simulado):
            res_clustering = self.client.post("/api/analitica/clustering/")
        self.assertEqual(res_clustering.status_code, status.HTTP_201_CREATED)

        acta_actualizada = ActaInspeccion.objects.get(pk=acta_id)
        self.assertIn(acta_actualizada.cluster_riesgo, {"Bajo", "Medio", "Critico"})

        # 7. Oficial de Mando consulta avance de la campania (100 %) y genera reportes
        self.client.force_authenticate(user=self.oficial)
        res_avance = self.client.get(f"/api/campanias/campanias/{campania_id}/avance/")
        self.assertEqual(res_avance.status_code, status.HTTP_200_OK)
        self.assertEqual(res_avance.data["predios_inspeccionados"], 1)
        self.assertEqual(str(res_avance.data["porcentaje"]), "100.00")

        res_pdf = self.client.post(
            "/api/reportes/generar/",
            {"tipo": "dictamen", "formato": "PDF", "acta_id": acta_id},
            format="json",
        )
        self.assertEqual(res_pdf.status_code, status.HTTP_200_OK)
        self.assertTrue(res_pdf.content.startswith(b"%PDF-"))

        res_excel = self.client.post(
            "/api/reportes/generar/",
            {"tipo": "ejecutivo", "formato": "Excel", "campania_id": campania_id},
            format="json",
        )
        self.assertEqual(res_excel.status_code, status.HTTP_200_OK)
        wb = openpyxl.load_workbook(io.BytesIO(res_excel.content))
        self.assertIn("Resumen Ejecutivo", wb.sheetnames)
        self.assertEqual(ReporteGenerado.objects.filter(generado_por=self.oficial).count(), 2)
