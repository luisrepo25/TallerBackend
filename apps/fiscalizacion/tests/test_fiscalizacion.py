import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.gis.geos import Polygon
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.campanias.models import Campania, CampaniaFuncionario
from apps.campanias.services import crear_campania
from apps.catastro.models import CatalogoTipoPredio
from apps.catastro.services import crear_predio
from apps.fiscalizacion.models import (
    ActaInspeccion,
    CatalogoEstadoExtintor,
    CatalogoInfraccion,
    CatalogoMaterialCombustible,
    EvidenciaFotografica,
    Infraccion,
    MaterialRegistrado,
)
from apps.fiscalizacion.services import (
    FiscalizacionConflicto,
    FiscalizacionError,
    calcular_carga_fuego,
    calcular_scoring_riesgo,
    cerrar_acta,
    registrar_acta,
    registrar_infraccion,
    registrar_materiales,
    subir_evidencia,
)
from apps.usuarios.models import Rol
from apps.usuarios.services import crear_usuario


def poligono_cuadrado(x, y, lado=0.005):
    """Poligono cuadrado (lon/lat, SRID 4326) con esquina en (x, y)."""
    return Polygon(
        ((x, y), (x + lado, y), (x + lado, y + lado), (x, y + lado), (x, y)),
        srid=4326,
    )


class BaseFiscalizacionTestCase(TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:6]
        self.admin = self._usuario("Administrador", "administrador", "admin")
        self.oficial = self._usuario("Oficial de Mando", "oficial_mando", "oficial")
        self.inspector = self._usuario("Inspector Tecnico", "inspector_tecnico", "insp")
        self.inspector2 = self._usuario("Inspector Tecnico", "inspector_tecnico", "insp2")

        # Tipo predio Mercado con riesgo_activacion = 1.50
        self.tipo_mercado, _ = CatalogoTipoPredio.objects.get_or_create(
            nombre=f"Mercado {self.suffix}",
            defaults={
                "categoria_riesgo_base": "Alto",
                "riesgo_activacion": Decimal("1.50"),
            },
        )

        # Estados de extintor
        self.extintor_vigente, _ = CatalogoEstadoExtintor.objects.get_or_create(
            nombre=f"Vigente {self.suffix}"
        )
        self.extintor_vencido, _ = CatalogoEstadoExtintor.objects.get_or_create(
            nombre=f"Vencido {self.suffix}"
        )
        self.extintor_no_posee, _ = CatalogoEstadoExtintor.objects.get_or_create(
            nombre=f"No posee {self.suffix}"
        )

        # Materiales combustibles tabulados segun NB 58005
        self.mat_madera, _ = CatalogoMaterialCombustible.objects.get_or_create(
            nombre=f"Madera {self.suffix}",
            defaults={
                "poder_calorifico_mj_kg": Decimal("18.41"),
                "coeficiente_peligrosidad": Decimal("1.00"),
            },
        )
        self.mat_plastico, _ = CatalogoMaterialCombustible.objects.get_or_create(
            nombre=f"Plastico {self.suffix}",
            defaults={
                "poder_calorifico_mj_kg": Decimal("25.00"),
                "coeficiente_peligrosidad": Decimal("1.50"),
            },
        )

        # Catalogo infracciones
        self.inf_extintor, _ = CatalogoInfraccion.objects.get_or_create(
            nombre=f"Falta de extintores {self.suffix}",
            defaults={"peso_severidad": Decimal("1.00")},
        )
        self.inf_electrica, _ = CatalogoInfraccion.objects.get_or_create(
            nombre=f"Instalacion electrica precaria {self.suffix}",
            defaults={"peso_severidad": Decimal("2.00")},
        )

        self.zona_campania = poligono_cuadrado(-63.20, -17.80, lado=0.01)
        self.client = APIClient()

    def _usuario(self, rol, subtipo, prefijo):
        return crear_usuario(
            nombre_completo=f"{prefijo} {self.suffix}",
            email=f"{prefijo}.{self.suffix}@uubr.org.bo",
            password="claveSegura123",
            rol=Rol.objects.get(nombre=rol),
            subtipo=subtipo,
        )

    def crear_campania(self, **kwargs):
        datos = {
            "nombre": f"Campania {self.suffix}",
            "fecha_inicio": date.today(),
            "fecha_fin": date.today() + timedelta(days=30),
            "creado_por": self.admin.administrador,
            "geom": self.zona_campania,
        }
        datos.update(kwargs)
        return crear_campania(**datos)

    def asignar_inspector(self, campania, inspector=None):
        insp = inspector or self.inspector
        CampaniaFuncionario.objects.get_or_create(
            campania=campania,
            usuario=insp.inspectortecnico,
        )

    def crear_predio(self, x=-63.198, y=-17.798, area_m2=200, **kwargs):
        datos = {
            "nombre": f"Predio {self.suffix}",
            "tipo_predio": self.tipo_mercado,
            "area_m2": Decimal(str(area_m2)),
            "geom": poligono_cuadrado(x, y, lado=0.001),
            "registrado_por": self.admin,
        }
        datos.update(kwargs)
        return crear_predio(**datos)

    def crear_acta(self, campania=None, predio=None, inspector=None, **kwargs):
        camp = campania or self.crear_campania()
        insp = inspector or self.inspector
        self.asignar_inspector(camp, insp)
        p = predio or self.crear_predio()

        carga_fuego = kwargs.pop("carga_fuego", None)
        scoring_riesgo = kwargs.pop("scoring_riesgo", None)

        datos = {
            "predio": p,
            "campania": camp,
            "inspector": insp.inspectortecnico,
            "estado_extintores": self.extintor_vigente,
            "fallas_electricas": False,
            "rutas_evacuacion_despejadas": True,
            "distancia_hidrante_m": Decimal("100.00"),
        }
        datos.update(kwargs)
        acta = registrar_acta(**datos)
        if carga_fuego is not None or scoring_riesgo is not None:
            if carga_fuego is not None:
                acta.carga_fuego = carga_fuego
            if scoring_riesgo is not None:
                acta.scoring_riesgo = scoring_riesgo
            acta.save(update_fields=["carga_fuego", "scoring_riesgo"])
        return acta


class CargaFuegoTests(BaseFiscalizacionTestCase):
    def test_calculo_exacto_ejemplo_verificado_nb58005(self):
        """Verifica la formula NB 58005 con el caso de prueba documentado:
        Madera (300 kg, Hi=18.41, Ci=1.00) + Plastico (150 kg, Hi=25.00, Ci=1.50)
        en un Mercado (Ra=1.50) de 200 m2 -> Exactamente 83.61 MJ/m2.
        """
        acta = self.crear_acta()
        registrar_materiales(
            acta,
            [
                {"material_id": self.mat_madera.pk, "peso_kg": Decimal("300.00")},
                {"material_id": self.mat_plastico.pk, "peso_kg": Decimal("150.00")},
            ],
        )

        carga = calcular_carga_fuego(acta)
        self.assertEqual(carga, Decimal("83.61"))

    def test_sin_materiales_retorna_cero(self):
        acta = self.crear_acta()
        carga = calcular_carga_fuego(acta)
        self.assertEqual(carga, Decimal("0.00"))


class ScoringRiesgoTests(BaseFiscalizacionTestCase):
    def test_scoring_riesgo_cero(self):
        """Variables en su mejor estado posible:
        Q=0 (0), Vigente (0), sin fallas (0), rutas despejadas (0), hidrante 0m (0) -> 0.00.
        """
        acta = self.crear_acta(
            carga_fuego=Decimal("0.00"),
            estado_extintores=self.extintor_vigente,
            fallas_electricas=False,
            rutas_evacuacion_despejadas=True,
            distancia_hidrante_m=Decimal("0.00"),
        )
        acta.carga_fuego = Decimal("0.00")
        score = calcular_scoring_riesgo(acta)
        self.assertEqual(score, Decimal("0.00"))

    def test_scoring_riesgo_maximo(self):
        """Variables en su peor estado posible:
        Q=1200 (>=1000 -> 1.0), No posee (1.0), con fallas (1.0),
        rutas obstruidas (1.0), distancia hidrante 600m (>=500 -> 1.0) -> 100.00.
        """
        acta = self.crear_acta(
            estado_extintores=self.extintor_no_posee,
            fallas_electricas=True,
            rutas_evacuacion_despejadas=False,
            distancia_hidrante_m=Decimal("600.00"),
        )
        acta.carga_fuego = Decimal("1200.00")
        score = calcular_scoring_riesgo(acta)
        self.assertEqual(score, Decimal("100.00"))

    def test_scoring_intermedio_calculado_a_mano(self):
        """Caso intermedio:
        Q=500 -> min(500/1000, 1) = 0.50 -> * 0.30 = 0.15
        Extintores Vencido -> 0.50 -> * 0.20 = 0.10
        Fallas electricas True -> 1.00 -> * 0.20 = 0.20
        Rutas despejadas True -> 0.00 -> * 0.20 = 0.00
        Distancia hidrante 250m -> min(250/500, 1) = 0.50 -> * 0.10 = 0.05
        Total = 100 * (0.15 + 0.10 + 0.20 + 0.00 + 0.05) = 50.00
        """
        acta = self.crear_acta(
            estado_extintores=self.extintor_vencido,
            fallas_electricas=True,
            rutas_evacuacion_despejadas=True,
            distancia_hidrante_m=Decimal("250.00"),
        )
        acta.carga_fuego = Decimal("500.00")
        score = calcular_scoring_riesgo(acta)
        self.assertEqual(score, Decimal("50.00"))

    def test_sin_hidrantes_asume_penalizacion_maxima_de_distancia(self):
        acta = self.crear_acta(
            estado_extintores=self.extintor_vigente,
            fallas_electricas=False,
            rutas_evacuacion_despejadas=True,
            distancia_hidrante_m=None,
        )
        acta.carga_fuego = Decimal("0.00")
        score = calcular_scoring_riesgo(acta)
        # Distancia hidrante None toma 1.0 * 0.10 * 100 = 10.00
        self.assertEqual(score, Decimal("10.00"))


class ValidacionesActaTests(BaseFiscalizacionTestCase):
    def test_rechaza_campania_cerrada(self):
        camp = self.crear_campania()
        self.asignar_inspector(camp, self.inspector)
        camp.estado = Campania.ESTADO_CERRADA
        camp.save(update_fields=["estado"])
        predio = self.crear_predio()

        with self.assertRaises(FiscalizacionConflicto):
            registrar_acta(
                predio=predio,
                campania=camp,
                inspector=self.inspector.inspectortecnico,
                estado_extintores=self.extintor_vigente,
            )

    def test_rechaza_inspector_no_asignado(self):
        camp = self.crear_campania()
        # No asignamos inspector2 a la campania
        predio = self.crear_predio()

        with self.assertRaises(FiscalizacionError):
            registrar_acta(
                predio=predio,
                campania=camp,
                inspector=self.inspector2.inspectortecnico,
                estado_extintores=self.extintor_vigente,
            )

    def test_rechaza_predio_fuera_de_la_zona(self):
        camp = self.crear_campania()
        self.asignar_inspector(camp, self.inspector)
        # Predio lejos del poligono de la campania
        # (no en (0, 0): a ~10 000 km la distancia a un hidrante real desborda NUMERIC(8,2))
        predio_fuera = self.crear_predio(x=-63.50, y=-17.50)

        with self.assertRaises(FiscalizacionError):
            registrar_acta(
                predio=predio_fuera,
                campania=camp,
                inspector=self.inspector.inspectortecnico,
                estado_extintores=self.extintor_vigente,
            )


class InfraccionesReincidenciaTests(BaseFiscalizacionTestCase):
    def test_deteccion_automatica_de_reincidencia(self):
        camp = self.crear_campania()
        self.asignar_inspector(camp, self.inspector)
        predio_a = self.crear_predio()
        predio_b = self.crear_predio(x=-63.195, y=-17.795)

        # 1. Primera infraccion en predio A -> No es reincidencia
        acta1 = registrar_acta(
            predio=predio_a,
            campania=camp,
            inspector=self.inspector.inspectortecnico,
            estado_extintores=self.extintor_vigente,
        )
        inf1 = registrar_infraccion(
            acta=acta1,
            tipo_infraccion=self.inf_extintor,
            descripcion="Falta extintor de 6kg",
        )
        self.assertFalse(inf1.es_reincidencia)

        # 2. Segunda infraccion del MISMO tipo en OTRA acta del MISMO predio -> Es reincidencia
        acta2 = registrar_acta(
            predio=predio_a,
            campania=camp,
            inspector=self.inspector.inspectortecnico,
            estado_extintores=self.extintor_vigente,
        )
        inf2 = registrar_infraccion(
            acta=acta2,
            tipo_infraccion=self.inf_extintor,
            descripcion="Persiste la falta de extintor",
        )
        self.assertTrue(inf2.es_reincidencia)

        # 3. Misma infraccion pero en Predio B -> No es reincidencia
        acta3 = registrar_acta(
            predio=predio_b,
            campania=camp,
            inspector=self.inspector.inspectortecnico,
            estado_extintores=self.extintor_vigente,
        )
        inf3 = registrar_infraccion(
            acta=acta3,
            tipo_infraccion=self.inf_extintor,
            descripcion="Falta extintor",
        )
        self.assertFalse(inf3.es_reincidencia)

        # 4. Infraccion de DISTINTO tipo en Predio A -> No es reincidencia
        inf4 = registrar_infraccion(
            acta=acta2,
            tipo_infraccion=self.inf_electrica,
            descripcion="Cables expuestos",
        )
        self.assertFalse(inf4.es_reincidencia)


class CierreActaTests(BaseFiscalizacionTestCase):
    def test_cierre_calcula_carga_fuego_y_scoring(self):
        acta = self.crear_acta()
        registrar_materiales(
            acta,
            [
                {"material_id": self.mat_madera.pk, "peso_kg": Decimal("300.00")},
                {"material_id": self.mat_plastico.pk, "peso_kg": Decimal("150.00")},
            ],
        )

        self.assertFalse(acta.cerrada)
        self.assertIsNone(acta.carga_fuego)
        self.assertIsNone(acta.scoring_riesgo)

        acta_cerrada = cerrar_acta(acta, usuario_autenticado=self.inspector)
        self.assertTrue(acta_cerrada.cerrada)
        self.assertIsNotNone(acta_cerrada.fecha_cierre)
        self.assertEqual(acta_cerrada.carga_fuego, Decimal("83.61"))
        self.assertIsNotNone(acta_cerrada.scoring_riesgo)

        # Persistencia en BD
        recargada = ActaInspeccion.objects.get(pk=acta.pk)
        self.assertTrue(recargada.cerrada)
        self.assertEqual(recargada.carga_fuego, Decimal("83.61"))

    def test_rechaza_cerrar_acta_ya_cerrada(self):
        acta = self.crear_acta()
        cerrar_acta(acta)

        with self.assertRaises(FiscalizacionConflicto):
            cerrar_acta(acta)

    def test_rechaza_operaciones_en_acta_cerrada(self):
        acta = self.crear_acta()
        cerrar_acta(acta)

        with self.assertRaises(FiscalizacionConflicto):
            registrar_materiales(
                acta,
                [{"material_id": self.mat_madera.pk, "peso_kg": Decimal("10.00")}],
            )

        with self.assertRaises(FiscalizacionConflicto):
            registrar_infraccion(acta, self.inf_extintor)

        with self.assertRaises(FiscalizacionConflicto):
            subir_evidencia(acta, "https://storage.uubr.org/evidencia1.jpg")


class BorradoEnCascadaTests(BaseFiscalizacionTestCase):
    def test_entidades_debiles_se_eliminan_en_cascada(self):
        acta = self.crear_acta()
        registrar_materiales(
            acta,
            [{"material_id": self.mat_madera.pk, "peso_kg": Decimal("50.00")}],
        )
        registrar_infraccion(acta, self.inf_extintor, "Falta extintor")
        subir_evidencia(acta, "https://storage.uubr.org/foto.jpg")

        self.assertEqual(MaterialRegistrado.objects.filter(acta=acta).count(), 1)
        self.assertEqual(Infraccion.objects.filter(acta=acta).count(), 1)
        self.assertEqual(EvidenciaFotografica.objects.filter(acta=acta).count(), 1)

        acta_id = acta.pk
        acta.delete()

        self.assertEqual(MaterialRegistrado.objects.filter(acta_id=acta_id).count(), 0)
        self.assertEqual(Infraccion.objects.filter(acta_id=acta_id).count(), 0)
        self.assertEqual(EvidenciaFotografica.objects.filter(acta_id=acta_id).count(), 0)


class FiscalizacionAPITests(BaseFiscalizacionTestCase):
    def setUp(self):
        super().setUp()
        self.campania = self.crear_campania()
        self.asignar_inspector(self.campania, self.inspector)
        self.predio = self.crear_predio()

    def test_inspector_crea_acta_via_api(self):
        self.client.force_authenticate(user=self.inspector)
        url = reverse("fiscalizacion:acta-list")
        payload = {
            "predio": self.predio.pk,
            "campania": self.campania.pk,
            "estado_extintores": self.extintor_vigente.pk,
            "fallas_electricas": False,
            "rutas_evacuacion_despejadas": True,
            "distancia_hidrante_m": 120.5,
            "materiales": [
                {"material_id": self.mat_madera.pk, "peso_kg": 150.0},
            ],
        }
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["predio"], self.predio.pk)
        self.assertEqual(len(res.data["materiales"]), 1)

    def test_crear_acta_en_campania_cerrada_retorna_409(self):
        self.campania.estado = Campania.ESTADO_CERRADA
        self.campania.save(update_fields=["estado"])

        self.client.force_authenticate(user=self.inspector)
        url = reverse("fiscalizacion:acta-list")
        payload = {
            "predio": self.predio.pk,
            "campania": self.campania.pk,
            "estado_extintores": self.extintor_vigente.pk,
        }
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_agregar_materiales_via_api(self):
        acta = self.crear_acta(campania=self.campania, predio=self.predio)
        self.client.force_authenticate(user=self.inspector)
        url = reverse("fiscalizacion:acta-materiales", args=[acta.pk])
        payload = [
            {"material_id": self.mat_madera.pk, "peso_kg": 200.0},
            {"material_id": self.mat_plastico.pk, "peso_kg": 50.0},
        ]
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 2)

    def test_registrar_infraccion_via_api(self):
        acta = self.crear_acta(campania=self.campania, predio=self.predio)
        self.client.force_authenticate(user=self.inspector)
        url = reverse("fiscalizacion:acta-infracciones", args=[acta.pk])
        payload = {
            "tipo_infraccion_id": self.inf_extintor.pk,
            "descripcion": "Extintor vencido hace 6 meses",
        }
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertFalse(res.data["es_reincidencia"])

    def test_subir_evidencia_via_api(self):
        acta = self.crear_acta(campania=self.campania, predio=self.predio)
        self.client.force_authenticate(user=self.inspector)
        url = reverse("fiscalizacion:acta-evidencias", args=[acta.pk])
        payload = {
            "url_imagen": "https://storage.uubr.org/evidencias/foto1.jpg",
            "descripcion_infraccion": "Tablero electrico sin tapa",
        }
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["url_imagen"], payload["url_imagen"])

    def test_cerrar_acta_via_api(self):
        acta = self.crear_acta(campania=self.campania, predio=self.predio)
        registrar_materiales(
            acta,
            [
                {"material_id": self.mat_madera.pk, "peso_kg": Decimal("300.00")},
                {"material_id": self.mat_plastico.pk, "peso_kg": Decimal("150.00")},
            ],
        )

        self.client.force_authenticate(user=self.inspector)
        url = reverse("fiscalizacion:acta-cerrar", args=[acta.pk])
        res = self.client.post(url, {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["cerrada"])
        self.assertEqual(res.data["carga_fuego"], "83.61")
        self.assertIsNotNone(res.data["scoring_riesgo"])

    def test_historial_inspecciones(self):
        acta = self.crear_acta(campania=self.campania, predio=self.predio)
        cerrar_acta(acta)

        self.client.force_authenticate(user=self.oficial)
        url = reverse("fiscalizacion:acta-historial")
        res = self.client.get(url, {"predio_id": self.predio.pk})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["id"], acta.pk)

    def test_permisos_oficial_solo_lectura(self):
        self.client.force_authenticate(user=self.oficial)
        url = reverse("fiscalizacion:acta-list")
        payload = {
            "predio": self.predio.pk,
            "campania": self.campania.pk,
            "estado_extintores": self.extintor_vigente.pk,
        }
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
