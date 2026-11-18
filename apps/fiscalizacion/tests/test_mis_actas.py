from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status

from apps.campanias.services import cerrar_campania
from apps.fiscalizacion.models import ActaInspeccion
from apps.fiscalizacion.services import (
    cerrar_acta,
    registrar_infraccion,
    registrar_materiales,
)
from apps.fiscalizacion.tests.test_fiscalizacion import BaseFiscalizacionTestCase

URL = "/api/fiscalizacion/mis-actas/"


class MisActasTests(BaseFiscalizacionTestCase):
    """El inspector recupera lo que ya inspecciono (reinstalacion, otro telefono)."""

    def setUp(self):
        super().setUp()
        self.campania = self.crear_campania()
        self.asignar_inspector(self.campania)
        self.predio = self.crear_predio()
        self.client.force_authenticate(self.inspector)

    def acta_cerrada(self, predio=None, campania=None, inspector=None, hace_minutos=0):
        acta = self.crear_acta(
            campania=campania or self.campania,
            predio=predio or self.predio,
            inspector=inspector,
        )
        registrar_materiales(
            acta, [{"material_id": self.mat_madera.pk, "peso_kg": Decimal("300.00")}]
        )
        registrar_infraccion(acta=acta, tipo_infraccion=self.inf_extintor, descripcion="Sin carga")
        acta = cerrar_acta(acta)
        ActaInspeccion.objects.filter(pk=acta.pk).update(
            fecha_inspeccion=timezone.now() - timedelta(minutes=hace_minutos)
        )
        return acta

    def pedir(self):
        return self.client.get(URL)

    def test_devuelve_la_acta_cerrada_con_lo_necesario_para_mostrarla(self):
        acta = self.acta_cerrada()

        r = self.pedir()

        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data), 1)
        fila = r.data[0]
        self.assertEqual(fila["id"], acta.pk)
        self.assertEqual(str(fila["uuid_local"]), str(acta.uuid_local))
        self.assertEqual(fila["predio_id"], self.predio.pk)
        self.assertEqual(fila["campania_id"], self.campania.pk)
        self.assertEqual(fila["estado_extintores_id"], self.extintor_vigente.pk)
        self.assertIsNotNone(fila["scoring_riesgo"])
        self.assertEqual(fila["materiales"][0]["material_id"], self.mat_madera.pk)
        self.assertEqual(fila["materiales"][0]["peso_kg"], "300.00")
        self.assertEqual(fila["infracciones"][0]["descripcion"], "Sin carga")

    def test_de_cada_predio_trae_solo_la_ultima_inspeccion(self):
        self.acta_cerrada(hace_minutos=10)
        ultima = self.acta_cerrada(hace_minutos=1)

        r = self.pedir()

        self.assertEqual([f["id"] for f in r.data], [ultima.pk])

    def test_un_predio_distinto_o_una_campania_distinta_cuentan_aparte(self):
        otro_predio = self.crear_predio(x=-63.196, y=-17.796)
        segunda = self.crear_campania(nombre=f"Otra {self.suffix}")
        self.asignar_inspector(segunda)
        self.acta_cerrada()
        self.acta_cerrada(predio=otro_predio)
        self.acta_cerrada(campania=segunda)

        self.assertEqual(len(self.pedir().data), 3)

    def test_no_trae_actas_de_otros_inspectores(self):
        self.acta_cerrada(inspector=self.inspector2)
        self.assertEqual(self.pedir().data, [])

    def test_no_trae_actas_abiertas(self):
        self.crear_acta(campania=self.campania, predio=self.predio)
        self.assertEqual(self.pedir().data, [])

    def test_no_trae_actas_de_campanias_cerradas(self):
        self.acta_cerrada()
        cerrar_campania(self.campania, usuario=self.admin, forzar=True)
        self.assertEqual(self.pedir().data, [])

    def test_solo_el_inspector_puede_pedirlas(self):
        for usuario in (self.admin, self.oficial):
            self.client.force_authenticate(usuario)
            self.assertEqual(self.pedir().status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(None)
        self.assertEqual(self.pedir().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_sin_actas_devuelve_lista_vacia(self):
        r = self.pedir()
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data, [])
