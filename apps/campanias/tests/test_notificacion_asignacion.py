from unittest.mock import patch

from apps.campanias.models import Campania
from apps.campanias.services import (
    CampaniaConflicto,
    CampaniaError,
    asignar_inspectores,
    cerrar_campania,
)
from apps.campanias.tests.test_campanias import BaseCampaniaTestCase

NOTIFICAR = "apps.campanias.services.notificar_usuarios"


class AvisoDeAsignacionTests(BaseCampaniaTestCase):
    """El Inspector se entera por push cuando se le asigna una campania."""

    def asignar(self, campania, ids):
        with self.captureOnCommitCallbacks(execute=True):
            return asignar_inspectores(campania, ids)

    def test_avisa_al_inspector_asignado_con_el_nombre_de_la_campania(self):
        campania = self.crear_campania()
        with patch(NOTIFICAR) as notificar:
            self.asignar(campania, [self.inspector.pk])

        notificar.assert_called_once()
        self.assertEqual(notificar.call_args.args[0], [self.inspector.pk])
        self.assertEqual(notificar.call_args.kwargs["titulo"], "Nueva campaña asignada")
        self.assertEqual(notificar.call_args.kwargs["cuerpo"], campania.nombre)
        self.assertEqual(
            notificar.call_args.kwargs["datos"],
            {"tipo": "campania_asignada", "campania_id": campania.pk},
        )

    def test_solo_avisa_a_los_nuevos_no_a_los_que_ya_estaban(self):
        campania = self.crear_campania()
        with patch(NOTIFICAR):
            self.asignar(campania, [self.inspector.pk])
        with patch(NOTIFICAR) as notificar:
            self.asignar(campania, [self.inspector.pk, self.inspector2.pk])

        self.assertEqual(notificar.call_args.args[0], [self.inspector2.pk])

    def test_reasignar_al_mismo_inspector_no_vuelve_a_avisar(self):
        campania = self.crear_campania()
        with patch(NOTIFICAR):
            self.asignar(campania, [self.inspector.pk])
        with patch(NOTIFICAR) as notificar:
            self.asignar(campania, [self.inspector.pk])

        notificar.assert_not_called()

    def test_no_avisa_hasta_que_la_asignacion_se_confirma(self):
        campania = self.crear_campania()
        with patch(NOTIFICAR) as notificar:
            with self.captureOnCommitCallbacks(execute=False) as pendientes:
                asignar_inspectores(campania, [self.inspector.pk])
            notificar.assert_not_called()
            self.assertEqual(len(pendientes), 1)

    def test_una_asignacion_invalida_no_avisa_a_nadie(self):
        campania = self.crear_campania()
        with patch(NOTIFICAR) as notificar:
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(CampaniaError):
                    asignar_inspectores(campania, [self.oficial.pk])

        notificar.assert_not_called()

    def test_en_una_campania_cerrada_no_hay_asignacion_ni_aviso(self):
        campania = self.crear_campania(geom=None)
        cerrar_campania(campania, usuario=self.admin, forzar=True)
        with patch(NOTIFICAR) as notificar:
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(CampaniaConflicto):
                    asignar_inspectores(campania, [self.inspector.pk])

        notificar.assert_not_called()
        self.assertEqual(Campania.objects.get(pk=campania.pk).estado, Campania.ESTADO_CERRADA)
