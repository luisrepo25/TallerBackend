import uuid
from datetime import date, timedelta

from django.contrib.gis.geos import Polygon
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.campanias.models import Campania, CampaniaFuncionario
from apps.campanias.services import (
    CampaniaConflicto,
    CampaniaError,
    asignar_inspectores,
    calcular_avance,
    cerrar_campania,
    cerrar_campanias_vencidas,
    crear_campania,
    predios_en_zona,
    quitar_inspector,
)
from apps.catastro.models import CatalogoTipoPredio
from apps.catastro.services import crear_predio
from apps.fiscalizacion.models import ActaInspeccion, CatalogoEstadoExtintor
from apps.usuarios.models import BitacoraAuditoria, Rol
from apps.usuarios.services import crear_usuario


def cuadrado(x, y, lado=0.001):
    """Poligono cuadrado (lon/lat, SRID 4326) con esquina inferior izquierda en (x, y)."""
    return Polygon(((x, y), (x + lado, y), (x + lado, y + lado), (x, y + lado), (x, y)), srid=4326)


# Zona de la campania: cuadrado de 0.01 grados. Los predios de prueba son cuadrados chicos.
ZONA = cuadrado(-63.20, -17.80, lado=0.01)


class BaseCampaniaTestCase(TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:6]
        self.admin = self._usuario("Administrador", "administrador", "admin")
        self.oficial = self._usuario("Oficial de Mando", "oficial_mando", "oficial")
        self.inspector = self._usuario("Inspector Tecnico", "inspector_tecnico", "insp1")
        self.inspector2 = self._usuario("Inspector Tecnico", "inspector_tecnico", "insp2")
        self.tipo_predio = CatalogoTipoPredio.objects.first()
        self.estado_extintor = CatalogoEstadoExtintor.objects.first()
        self.client = APIClient()

    def _usuario(self, rol, subtipo, prefijo):
        return crear_usuario(
            nombre_completo=f"{prefijo} {self.suffix}",
            email=f"{prefijo}.{self.suffix}@uubr.org.bo",
            password="claveSegura123",
            rol=Rol.objects.get(nombre=rol),
            subtipo=subtipo,
        )

    def crear_campania(self, geom=ZONA, **kwargs):
        datos = {
            "nombre": f"Campania {self.suffix}",
            "fecha_inicio": date.today(),
            "fecha_fin": date.today() + timedelta(days=30),
            "creado_por": self.admin.administrador,
            "geom": geom,
        }
        datos.update(kwargs)
        return crear_campania(**datos)

    def crear_predio(self, x, y, nombre="Predio"):
        return crear_predio(
            nombre=f"{nombre} {uuid.uuid4().hex[:4]}",
            tipo_predio=self.tipo_predio,
            geom=cuadrado(x, y, lado=0.0005),
            registrado_por=self.admin,
        )

    def crear_acta(self, campania, predio, inspector=None, cerrada=True):
        return ActaInspeccion.objects.create(
            predio=predio,
            campania=campania,
            inspector=(inspector or self.inspector).inspectortecnico,
            estado_extintores=self.estado_extintor,
            cerrada=cerrada,
        )


class CrearCampaniaServiceTests(BaseCampaniaTestCase):
    def test_nace_pendiente_y_con_creador(self):
        campania = self.crear_campania()
        self.assertEqual(campania.estado, Campania.ESTADO_PENDIENTE)
        self.assertEqual(campania.creado_por_id, self.admin.pk)

    def test_rechaza_fecha_fin_anterior_a_inicio(self):
        with self.assertRaises(CampaniaError):
            self.crear_campania(
                fecha_inicio=date.today(), fecha_fin=date.today() - timedelta(days=1)
            )

    def test_rechaza_poligono_invalido(self):
        # "Corbata": los lados se cruzan, el poligono es invalido.
        bowtie = Polygon(((0, 0), (1, 1), (1, 0), (0, 1), (0, 0)), srid=4326)
        with self.assertRaises(CampaniaError):
            self.crear_campania(geom=bowtie)


class AsignacionServiceTests(BaseCampaniaTestCase):
    def test_primera_asignacion_pasa_a_en_curso(self):
        campania = self.crear_campania()
        campania = asignar_inspectores(campania, [self.inspector.pk])
        self.assertEqual(campania.estado, Campania.ESTADO_EN_CURSO)

    def test_asignar_dos_veces_es_idempotente(self):
        campania = self.crear_campania()
        asignar_inspectores(campania, [self.inspector.pk])
        asignar_inspectores(campania, [self.inspector.pk, self.inspector2.pk])
        self.assertEqual(CampaniaFuncionario.objects.filter(campania=campania).count(), 2)

    def test_solo_se_asignan_inspectores_tecnicos(self):
        campania = self.crear_campania()
        with self.assertRaises(CampaniaError) as ctx:
            asignar_inspectores(campania, [self.oficial.pk])
        self.assertEqual(ctx.exception.extra["ids_invalidos"], [self.oficial.pk])

    def test_no_se_asigna_a_campania_cerrada(self):
        campania = self.crear_campania(geom=None)
        cerrar_campania(campania, usuario=self.admin, forzar=True)
        with self.assertRaises(CampaniaConflicto):
            asignar_inspectores(campania, [self.inspector.pk])

    def test_quitar_inspector_sin_actas(self):
        campania = self.crear_campania()
        asignar_inspectores(campania, [self.inspector.pk])
        quitar_inspector(campania, self.inspector.pk)
        self.assertFalse(CampaniaFuncionario.objects.filter(campania=campania).exists())

    def test_no_se_quita_inspector_con_actas(self):
        campania = self.crear_campania()
        asignar_inspectores(campania, [self.inspector.pk])
        self.crear_acta(campania, self.crear_predio(-63.195, -17.795))
        with self.assertRaises(CampaniaConflicto):
            quitar_inspector(campania, self.inspector.pk)


class InterseccionYAvanceServiceTests(BaseCampaniaTestCase):
    def setUp(self):
        super().setUp()
        self.campania = self.crear_campania()
        self.dentro1 = self.crear_predio(-63.195, -17.795, "Dentro1")
        self.dentro2 = self.crear_predio(-63.197, -17.797, "Dentro2")
        self.dentro3 = self.crear_predio(-63.193, -17.793, "Dentro3")
        self.fuera = self.crear_predio(-63.100, -17.700, "Fuera")

    def test_predios_en_zona_usa_interseccion_espacial(self):
        ids = set(predios_en_zona(self.campania).values_list("id", flat=True))
        self.assertTrue({self.dentro1.id, self.dentro2.id, self.dentro3.id} <= ids)
        self.assertNotIn(self.fuera.id, ids)

    def test_predio_en_el_borde_cuenta_como_dentro(self):
        borde = self.crear_predio(-63.2003, -17.795, "Borde")  # cruza el limite oeste
        self.assertIn(borde.id, predios_en_zona(self.campania).values_list("id", flat=True))

    def test_avance_cuenta_predio_inspeccionado(self):
        base = calcular_avance(self.campania)["total_predios"]
        self.crear_acta(self.campania, self.dentro1, cerrada=True)
        avance = calcular_avance(self.campania)
        self.assertEqual(avance["total_predios"], base)
        self.assertEqual(avance["predios_inspeccionados"], 1)
        self.assertEqual(avance["predios_pendientes"], base - 1)

    def test_acta_abierta_no_cuenta_como_avance(self):
        self.crear_acta(self.campania, self.dentro1, cerrada=False)
        self.assertEqual(calcular_avance(self.campania)["predios_inspeccionados"], 0)

    def test_acta_de_predio_fuera_de_zona_no_cuenta(self):
        self.crear_acta(self.campania, self.fuera, cerrada=True)
        self.assertEqual(calcular_avance(self.campania)["predios_inspeccionados"], 0)

    def test_dos_actas_del_mismo_predio_cuentan_una_vez(self):
        self.crear_acta(self.campania, self.dentro1)
        self.crear_acta(self.campania, self.dentro1)
        self.assertEqual(calcular_avance(self.campania)["predios_inspeccionados"], 1)

    def test_sin_poligono_el_avance_es_cero_sin_dividir_por_cero(self):
        campania = self.crear_campania(geom=None)
        avance = calcular_avance(campania)
        self.assertEqual(avance["total_predios"], 0)
        self.assertEqual(str(avance["porcentaje"]), "0.00")

    def test_porcentaje_exacto(self):
        # Zona aislada con exactamente 3 predios y 1 inspeccionado -> 33.33 %.
        zona = cuadrado(-63.50, -17.50, lado=0.01)
        campania = self.crear_campania(geom=zona)
        p1 = self.crear_predio(-63.495, -17.495)
        self.crear_predio(-63.493, -17.493)
        self.crear_predio(-63.497, -17.497)
        self.crear_acta(campania, p1)
        avance = calcular_avance(campania)
        self.assertEqual(avance["total_predios"], 3)
        self.assertEqual(str(avance["porcentaje"]), "33.33")


class CierreServiceTests(BaseCampaniaTestCase):
    def test_cierre_bloqueado_con_predios_pendientes(self):
        campania = self.crear_campania(geom=cuadrado(-63.60, -17.60, lado=0.01))
        self.crear_predio(-63.595, -17.595)
        with self.assertRaises(CampaniaConflicto) as ctx:
            cerrar_campania(campania, usuario=self.admin)
        self.assertEqual(ctx.exception.extra["predios_pendientes"], 1)
        campania.refresh_from_db()
        self.assertNotEqual(campania.estado, Campania.ESTADO_CERRADA)

    def test_cierre_exitoso_cuando_todo_esta_inspeccionado(self):
        campania = self.crear_campania(geom=cuadrado(-63.70, -17.70, lado=0.01))
        predio = self.crear_predio(-63.695, -17.695)
        self.crear_acta(campania, predio, cerrada=True)
        resultado = cerrar_campania(campania, usuario=self.admin)
        self.assertEqual(resultado["campania"].estado, Campania.ESTADO_CERRADA)
        self.assertFalse(resultado["forzado"])

    def test_cierre_bloqueado_con_acta_abierta(self):
        campania = self.crear_campania(geom=cuadrado(-63.80, -17.80, lado=0.01))
        predio = self.crear_predio(-63.795, -17.795)
        self.crear_acta(campania, predio, cerrada=True)
        self.crear_acta(campania, predio, cerrada=False)
        with self.assertRaises(CampaniaConflicto):
            cerrar_campania(campania, usuario=self.admin)

    def test_cierre_forzado_ignora_pendientes_y_queda_en_bitacora(self):
        campania = self.crear_campania(geom=cuadrado(-63.90, -17.90, lado=0.01))
        self.crear_predio(-63.895, -17.895)
        resultado = cerrar_campania(campania, usuario=self.admin, forzar=True)
        self.assertTrue(resultado["forzado"])
        self.assertEqual(resultado["campania"].estado, Campania.ESTADO_CERRADA)
        self.assertTrue(
            BitacoraAuditoria.objects.filter(
                usuario=self.admin, accion="Cerrar campania (forzado)"
            ).exists()
        )

    def test_no_se_cierra_dos_veces(self):
        campania = self.crear_campania(geom=None)
        cerrar_campania(campania, usuario=self.admin, forzar=True)
        with self.assertRaises(CampaniaConflicto):
            cerrar_campania(campania, usuario=self.admin, forzar=True)


class CierreAutomaticoTests(BaseCampaniaTestCase):
    def test_cierra_solo_las_vencidas(self):
        hoy = date.today()
        vencida = self.crear_campania(
            geom=None, fecha_inicio=hoy - timedelta(days=10), fecha_fin=hoy - timedelta(days=1)
        )
        vigente = self.crear_campania(geom=None)
        cerradas = cerrar_campanias_vencidas()
        self.assertIn(vencida.id, cerradas)
        self.assertNotIn(vigente.id, cerradas)
        vencida.refresh_from_db()
        vigente.refresh_from_db()
        self.assertEqual(vencida.estado, Campania.ESTADO_CERRADA)
        self.assertNotEqual(vigente.estado, Campania.ESTADO_CERRADA)

    def test_el_dia_de_fecha_fin_aun_no_vence(self):
        campania = self.crear_campania(geom=None, fecha_fin=date.today())
        self.assertNotIn(campania.id, cerrar_campanias_vencidas())

    def test_cierra_aunque_haya_pendientes(self):
        hoy = date.today()
        campania = self.crear_campania(
            geom=cuadrado(-64.00, -18.00, lado=0.01),
            fecha_inicio=hoy - timedelta(days=10),
            fecha_fin=hoy - timedelta(days=1),
        )
        self.crear_predio(-63.995, -17.995)
        self.assertIn(campania.id, cerrar_campanias_vencidas())

    def test_es_idempotente(self):
        hoy = date.today()
        self.crear_campania(
            geom=None, fecha_inicio=hoy - timedelta(days=10), fecha_fin=hoy - timedelta(days=1)
        )
        cerrar_campanias_vencidas()
        self.assertEqual(cerrar_campanias_vencidas(), [])


class CampaniaApiTests(BaseCampaniaTestCase):
    def payload(self, **kwargs):
        datos = {
            "nombre": "Campania API",
            "fecha_inicio": str(date.today()),
            "fecha_fin": str(date.today() + timedelta(days=15)),
            "geom": {"type": "Polygon", "coordinates": [list(map(list, ZONA.coords[0]))]},
        }
        datos.update(kwargs)
        return datos

    def test_admin_crea_campania_y_queda_en_bitacora(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(reverse("campanias:campania-list"), self.payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["estado"], "pendiente")
        self.assertTrue(
            BitacoraAuditoria.objects.filter(usuario=self.admin, accion="Crear campania").exists()
        )

    def test_estado_y_creador_no_se_pueden_forzar_desde_el_body(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            reverse("campanias:campania-list"),
            self.payload(estado="cerrada", creado_por=self.oficial.pk),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        campania = Campania.objects.get(pk=resp.data["id"])
        self.assertEqual(campania.estado, "pendiente")
        self.assertEqual(campania.creado_por_id, self.admin.pk)

    def test_oficial_e_inspector_no_pueden_crear(self):
        for usuario in (self.oficial, self.inspector):
            self.client.force_authenticate(user=usuario)
            resp = self.client.post(
                reverse("campanias:campania-list"), self.payload(), format="json"
            )
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_sin_autenticar_es_401(self):
        resp = self.client.get(reverse("campanias:campania-list"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_fechas_invalidas_dan_400(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            reverse("campanias:campania-list"),
            self.payload(fecha_fin=str(date.today() - timedelta(days=1))),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_geometria_no_poligono_da_400(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            reverse("campanias:campania-list"),
            self.payload(geom={"type": "Point", "coordinates": [-63.18, -17.78]}),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inspector_solo_ve_sus_campanias(self):
        mia = self.crear_campania(nombre="Mia")
        ajena = self.crear_campania(nombre="Ajena")
        asignar_inspectores(mia, [self.inspector.pk])
        asignar_inspectores(ajena, [self.inspector2.pk])

        self.client.force_authenticate(user=self.inspector)
        resp = self.client.get(reverse("campanias:campania-list"))
        ids = {c["id"] for c in resp.data}
        self.assertIn(mia.id, ids)
        self.assertNotIn(ajena.id, ids)

        resp = self.client.get(reverse("campanias:campania-detail", args=[ajena.id]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_oficial_ve_todas_pero_no_modifica(self):
        campania = self.crear_campania()
        self.client.force_authenticate(user=self.oficial)
        self.assertEqual(
            self.client.get(reverse("campanias:campania-detail", args=[campania.id])).status_code,
            status.HTTP_200_OK,
        )
        resp = self.client.patch(
            reverse("campanias:campania-detail", args=[campania.id]),
            {"nombre": "Cambio"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_existe_delete(self):
        campania = self.crear_campania()
        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(reverse("campanias:campania-detail", args=[campania.id]))
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_actualizar_zona(self):
        campania = self.crear_campania(geom=None)
        self.client.force_authenticate(user=self.admin)
        resp = self.client.put(
            reverse("campanias:campania-zona", args=[campania.id]),
            {"geom": {"type": "Polygon", "coordinates": [list(map(list, ZONA.coords[0]))]}},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        campania.refresh_from_db()
        self.assertIsNotNone(campania.geom)

    def test_asignar_y_quitar_inspector(self):
        campania = self.crear_campania()
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            reverse("campanias:campania-asignar-inspectores", args=[campania.id]),
            {"usuarios_ids": [self.inspector.pk]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data["estado"], "en_curso")
        self.assertEqual(len(resp.data["inspectores"]), 1)

        resp = self.client.delete(
            reverse("campanias:campania-quitar-inspector", args=[campania.id, self.inspector.pk])
        )
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_asignar_no_inspector_da_400(self):
        campania = self.crear_campania()
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            reverse("campanias:campania-asignar-inspectores", args=[campania.id]),
            {"usuarios_ids": [self.oficial.pk]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_avance_solo_admin_y_oficial(self):
        campania = self.crear_campania()
        url = reverse("campanias:campania-avance", args=[campania.id])
        asignar_inspectores(campania, [self.inspector.pk])

        self.client.force_authenticate(user=self.inspector)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(user=self.oficial)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)

    def test_cerrar_con_pendientes_409_y_forzado_200(self):
        campania = self.crear_campania(geom=cuadrado(-64.10, -18.10, lado=0.01))
        self.crear_predio(-64.095, -18.095)
        url = reverse("campanias:campania-cerrar", args=[campania.id])
        self.client.force_authenticate(user=self.admin)

        resp = self.client.post(url, {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data["predios_pendientes"], 1)

        resp = self.client.post(url, {"forzar": True}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(resp.data["forzado"])
        self.assertEqual(resp.data["campania"]["estado"], "cerrada")

    def test_oficial_no_puede_cerrar(self):
        campania = self.crear_campania()
        self.client.force_authenticate(user=self.oficial)
        resp = self.client.post(
            reverse("campanias:campania-cerrar", args=[campania.id]), {}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_campania_cerrada_no_se_edita(self):
        campania = self.crear_campania(geom=None)
        cerrar_campania(campania, usuario=self.admin, forzar=True)
        self.client.force_authenticate(user=self.admin)
        resp = self.client.patch(
            reverse("campanias:campania-detail", args=[campania.id]),
            {"nombre": "X"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
