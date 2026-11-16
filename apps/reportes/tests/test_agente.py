from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.usuarios.models import Rol
from apps.usuarios.services import crear_usuario


class AgenteReportesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        rol_admin = Rol.objects.get(nombre="Administrador")
        rol_inspector = Rol.objects.get(nombre="Inspector Tecnico")

        self.admin = crear_usuario(
            nombre_completo="Admin Test Agente",
            email="admin.agente.test@uubr.org.bo",
            password="password123",
            rol=rol_admin,
            subtipo="administrador",
        )
        self.inspector = crear_usuario(
            nombre_completo="Inspector Solo Movil",
            email="inspector.solo@uubr.org.bo",
            password="password123",
            rol=rol_inspector,
            subtipo="inspector_tecnico",
        )

    def test_agente_requiere_autenticacion(self):
        resp = self.client.post("/api/reportes/agente/", {"pregunta": "Ver predios"})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_agente_requiere_rol_oficial_o_admin(self):
        self.client.force_authenticate(user=self.inspector)
        resp = self.client.post("/api/reportes/agente/", {"pregunta": "Ver predios"})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_agente_genera_reporte_con_exito(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            "/api/reportes/agente/",
            {"pregunta": "Mostrar los predios en riesgo Critico en el Distrito Industrial"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn("id", data)
        self.assertIn("columnas", data)
        self.assertIn("columnas_disponibles", data)
        self.assertIn("filas", data)
        self.assertIn("respuesta_nl", data)
        self.assertIn("interpretacion", data)

        reporte_id = data["id"]

        # Probar consulta de detalle
        resp_det = self.client.get(f"/api/reportes/agente/{reporte_id}/")
        self.assertEqual(resp_det.status_code, status.HTTP_200_OK)

        # Probar exportacion PDF
        resp_pdf = self.client.get(f"/api/reportes/agente/{reporte_id}/exportar/?formato=PDF")
        self.assertEqual(resp_pdf.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_pdf["Content-Type"], "application/pdf")

        # Probar exportacion Excel
        resp_xlsx = self.client.get(f"/api/reportes/agente/{reporte_id}/exportar/?formato=Excel")
        self.assertEqual(resp_xlsx.status_code, status.HTTP_200_OK)
        self.assertIn("spreadsheetml", resp_xlsx["Content-Type"])

        # Probar exportacion TXT
        resp_txt = self.client.get(f"/api/reportes/agente/{reporte_id}/exportar/?formato=TXT")
        self.assertEqual(resp_txt.status_code, status.HTTP_200_OK)
        self.assertIn("text/plain", resp_txt["Content-Type"])

        # Probar exportacion CSV
        resp_csv = self.client.get(f"/api/reportes/agente/{reporte_id}/exportar/?formato=CSV")
        self.assertEqual(resp_csv.status_code, status.HTTP_200_OK)
        self.assertIn("text/csv", resp_csv["Content-Type"])
        self.assertTrue(len(resp_csv.content) > 0)

    def test_agente_idempotencia(self):
        self.client.force_authenticate(user=self.admin)
        key = "idem-test-12345"
        resp1 = self.client.post(
            "/api/reportes/agente/",
            {"pregunta": "Resumen de distritos municipales", "idempotency_key": key},
        )
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        id1 = resp1.json()["id"]

        resp2 = self.client.post(
            "/api/reportes/agente/",
            {"pregunta": "Cualquier otra pregunta", "idempotency_key": key},
        )
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        id2 = resp2.json()["id"]
        self.assertEqual(id1, id2)
