import uuid
from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.campanias.services import cerrar_campania
from apps.fiscalizacion.models import (
    ActaInspeccion,
    EvidenciaFotografica,
    Infraccion,
    MaterialRegistrado,
)
from apps.fiscalizacion.tests.test_fiscalizacion import BaseFiscalizacionTestCase


class SincronizacionTests(BaseFiscalizacionTestCase):
    """RF-21: el celular envia actas COMPLETAS hechas sin conexion."""

    def setUp(self):
        super().setUp()
        self.campania = self.crear_campania()
        self.asignar_inspector(self.campania)
        self.predio = self.crear_predio()
        self.client.force_authenticate(self.inspector)

    def acta(self, **cambios):
        datos = {
            "uuid_local": str(uuid.uuid4()),
            "predio_id": self.predio.pk,
            "campania_id": self.campania.pk,
            "estado_extintores_id": self.extintor_vigente.pk,
            "fallas_electricas": False,
            "rutas_evacuacion_despejadas": True,
            "materiales": [
                {"material_id": self.mat_madera.pk, "peso_kg": "300.00"},
                {"material_id": self.mat_plastico.pk, "peso_kg": "150.00"},
            ],
            "infracciones": [
                {"tipo_infraccion_id": self.inf_extintor.pk, "descripcion": "Sin carga"}
            ],
            "evidencias": [{"url_imagen": "https://res.cloudinary.com/x/foto1.jpg"}],
        }
        datos.update(cambios)
        return datos

    def enviar(self, *actas):
        return self.client.post(
            reverse("fiscalizacion:sync-actas"), {"actas": list(actas)}, format="json"
        )

    def test_acta_completa_se_guarda_se_cierra_y_calcula_en_el_servidor(self):
        datos = self.acta()

        respuesta = self.enviar(datos)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        resultado = respuesta.data["resultados"][0]
        self.assertEqual(resultado["estado"], "sincronizada")
        # Ejemplo verificado NB 58005: 300 kg madera + 150 kg plastico, mercado 200 m2
        self.assertEqual(resultado["carga_fuego"], Decimal("83.61"))
        self.assertIsNotNone(resultado["scoring_riesgo"])

        acta = ActaInspeccion.objects.get(uuid_local=datos["uuid_local"])
        self.assertTrue(acta.cerrada)
        self.assertTrue(acta.sincronizada)
        self.assertIsNotNone(acta.fecha_sincronizacion)
        self.assertEqual(acta.inspector_id, self.inspector.pk)
        self.assertEqual(MaterialRegistrado.objects.filter(acta=acta).count(), 2)
        self.assertEqual(Infraccion.objects.filter(acta=acta).count(), 1)
        self.assertEqual(EvidenciaFotografica.objects.filter(acta=acta).count(), 1)

    def test_se_respeta_la_fecha_en_que_se_hizo_la_inspeccion(self):
        hace_tres_dias = timezone.now() - timedelta(days=3)
        datos = self.acta(fecha_inspeccion=hace_tres_dias.isoformat())

        self.enviar(datos)

        acta = ActaInspeccion.objects.get(uuid_local=datos["uuid_local"])
        self.assertAlmostEqual(
            acta.fecha_inspeccion.timestamp(), hace_tres_dias.timestamp(), delta=1
        )
        self.assertGreater(acta.fecha_sincronizacion, acta.fecha_inspeccion)

    def test_fecha_futura_se_rechaza(self):
        datos = self.acta(fecha_inspeccion=(timezone.now() + timedelta(days=1)).isoformat())

        resultado = self.enviar(datos).data["resultados"][0]

        self.assertEqual(resultado["estado"], "rechazada")
        self.assertIn("futuro", resultado["detalle"])
        self.assertFalse(ActaInspeccion.objects.filter(uuid_local=datos["uuid_local"]).exists())

    def test_reenviar_el_mismo_uuid_no_duplica_el_acta(self):
        datos = self.acta()

        primera = self.enviar(datos).data["resultados"][0]
        segunda = self.enviar(datos).data["resultados"][0]

        self.assertEqual(primera["estado"], "sincronizada")
        self.assertEqual(segunda["estado"], "ya_sincronizada")
        self.assertEqual(segunda["acta_id"], primera["acta_id"])
        self.assertEqual(segunda["carga_fuego"], primera["carga_fuego"])
        self.assertEqual(ActaInspeccion.objects.filter(uuid_local=datos["uuid_local"]).count(), 1)
        self.assertEqual(MaterialRegistrado.objects.filter(acta_id=primera["acta_id"]).count(), 2)

    def test_lote_parcial_un_acta_mala_no_frena_a_las_buenas(self):
        buena = self.acta()
        mala = self.acta(predio_id=999_999_999)  # predio inexistente
        otra_buena = self.acta()

        resultados = self.enviar(buena, mala, otra_buena).data["resultados"]

        self.assertEqual(
            [r["estado"] for r in resultados], ["sincronizada", "rechazada", "sincronizada"]
        )
        self.assertEqual(resultados[1]["codigo"], "validacion")
        self.assertEqual(resultados[1]["uuid_local"], mala["uuid_local"])
        self.assertTrue(ActaInspeccion.objects.filter(uuid_local=buena["uuid_local"]).exists())
        self.assertTrue(ActaInspeccion.objects.filter(uuid_local=otra_buena["uuid_local"]).exists())
        self.assertFalse(ActaInspeccion.objects.filter(uuid_local=mala["uuid_local"]).exists())

    def test_acta_mal_formada_se_rechaza_sin_tumbar_el_lote(self):
        buena = self.acta()
        sin_predio = self.acta()
        del sin_predio["predio_id"]

        respuesta = self.enviar(sin_predio, buena)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        malo, bueno = respuesta.data["resultados"]
        self.assertEqual(malo["codigo"], "datos_invalidos")
        self.assertIn("predio_id", malo["detalle"])
        self.assertEqual(bueno["estado"], "sincronizada")

    def test_campania_cerrada_mientras_estaba_sin_conexion_se_rechaza_con_motivo(self):
        datos = self.acta()
        cerrar_campania(self.campania, usuario=self.admin, forzar=True)

        resultado = self.enviar(datos).data["resultados"][0]

        self.assertEqual(resultado["estado"], "rechazada")
        self.assertEqual(resultado["codigo"], "conflicto")
        self.assertIn("cerrada", resultado["detalle"])

    def test_predio_fuera_de_la_zona_se_rechaza(self):
        lejano = self.crear_predio(x=-63.50, y=-17.50, nombre=f"Lejano {self.suffix}")

        resultado = self.enviar(self.acta(predio_id=lejano.pk)).data["resultados"][0]

        self.assertEqual(resultado["estado"], "rechazada")
        self.assertIn("poligono", resultado["detalle"])

    def test_inspector_no_asignado_a_la_campania_se_rechaza(self):
        self.client.force_authenticate(self.inspector2)

        resultado = self.enviar(self.acta()).data["resultados"][0]

        self.assertEqual(resultado["estado"], "rechazada")
        self.assertIn("asignado", resultado["detalle"])

    def test_un_error_a_mitad_no_deja_el_acta_a_medias(self):
        datos = self.acta(
            materiales=[
                {"material_id": self.mat_madera.pk, "peso_kg": "10.00"},
                {"material_id": 999_999_999, "peso_kg": "5.00"},  # no existe
            ]
        )

        resultado = self.enviar(datos).data["resultados"][0]

        self.assertEqual(resultado["estado"], "rechazada")
        self.assertFalse(ActaInspeccion.objects.filter(uuid_local=datos["uuid_local"]).exists())
        self.assertFalse(Infraccion.objects.filter(acta__uuid_local=datos["uuid_local"]).exists())

    def test_la_reincidencia_la_detecta_el_servidor_y_se_informa(self):
        self.enviar(self.acta())  # primera infraccion de ese tipo en el predio

        segunda = self.enviar(self.acta()).data["resultados"][0]

        self.assertEqual(
            segunda["infracciones"],
            [{"tipo_infraccion_id": self.inf_extintor.pk, "es_reincidencia": True}],
        )

    def test_el_uuid_de_otro_inspector_no_se_toca_ni_se_revela(self):
        datos = self.acta()
        self.enviar(datos)
        self.asignar_inspector(self.campania, self.inspector2)
        self.client.force_authenticate(self.inspector2)

        resultado = self.enviar(datos).data["resultados"][0]

        self.assertEqual(resultado["estado"], "rechazada")
        self.assertEqual(resultado["codigo"], "uuid_en_uso")
        self.assertNotIn("acta_id", resultado)

    def test_solo_el_inspector_puede_sincronizar(self):
        for usuario in (self.admin, self.oficial):
            self.client.force_authenticate(usuario)
            self.assertEqual(self.enviar(self.acta()).status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(None)
        self.assertEqual(self.enviar(self.acta()).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_lote_vacio_o_demasiado_grande_se_rechaza(self):
        vacio = self.client.post(reverse("fiscalizacion:sync-actas"), {"actas": []}, format="json")
        enorme = self.client.post(
            reverse("fiscalizacion:sync-actas"), {"actas": [{}] * 51}, format="json"
        )

        self.assertEqual(vacio.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(enorme.status_code, status.HTTP_400_BAD_REQUEST)
