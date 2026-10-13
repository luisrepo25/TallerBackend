import random

from django.test import SimpleTestCase, TestCase

from apps.analitica import demo
from apps.analitica import demo_simulacion as sim
from apps.campanias.models import Campania
from apps.catastro.models import Hidrante, Predio
from apps.fiscalizacion.models import ActaInspeccion
from apps.usuarios.models import Usuario

MATERIALES = ["Madera", "Papel y carton", "Telas y textiles", "Plasticos (PVC/PET)", "Liquidos"]
INFRACCIONES = ["Extintor vencido", "Instalacion electrica", "Ruta obstruida", "Inflamables"]


def muestras(riesgo, n=400, area=500.0):
    rng = random.Random(1)
    return [sim.simular_inspeccion(riesgo, area, MATERIALES, INFRACCIONES, rng) for _ in range(n)]


class SimulacionTests(SimpleTestCase):
    def test_misma_semilla_misma_inspeccion(self):
        a = sim.simular_inspeccion(0.6, 300.0, MATERIALES, INFRACCIONES, random.Random(5))
        b = sim.simular_inspeccion(0.6, 300.0, MATERIALES, INFRACCIONES, random.Random(5))
        self.assertEqual(a, b)

    def test_los_predios_industriales_son_mas_riesgosos_que_los_educativos(self):
        rng = random.Random(3)

        def media(tipo):
            return sum(sim.riesgo_latente(tipo, rng) for _ in range(1000)) / 1000

        self.assertGreater(media("Industrial"), media("Educativo") + 0.2)

    def test_mas_riesgo_mas_hallazgos(self):
        bajo, alto = muestras(0.05), muestras(0.95)

        def frecuencia(datos, f):
            return sum(map(f, datos)) / len(datos)

        self.assertGreater(
            frecuencia(alto, lambda i: i.extintores == "No posee"),
            frecuencia(bajo, lambda i: i.extintores == "No posee") + 0.3,
        )
        self.assertGreater(
            frecuencia(alto, lambda i: i.fallas_electricas),
            frecuencia(bajo, lambda i: i.fallas_electricas) + 0.3,
        )
        self.assertGreater(
            frecuencia(bajo, lambda i: i.rutas_despejadas),
            frecuencia(alto, lambda i: i.rutas_despejadas) + 0.3,
        )
        self.assertGreater(
            frecuencia(alto, lambda i: sum(kg for _, kg in i.materiales)),
            frecuencia(bajo, lambda i: sum(kg for _, kg in i.materiales)) * 5,
        )
        self.assertGreater(
            frecuencia(alto, lambda i: len(i.infracciones)),
            frecuencia(bajo, lambda i: len(i.infracciones)) + 1,
        )

    def test_datos_validos_para_el_catalogo_y_la_base(self):
        for i in muestras(0.9, area=400_000.0):
            nombres = [n for n, _ in i.materiales]
            self.assertTrue(1 <= len(nombres) <= 3)
            self.assertEqual(len(set(nombres)), len(nombres))
            self.assertTrue(all(1 <= kg <= sim.PESO_MAX_KG for _, kg in i.materiales))
            self.assertEqual(len(set(i.infracciones)), len(i.infracciones))
            self.assertTrue(set(i.infracciones) <= set(INFRACCIONES))
            self.assertIn(i.extintores, {"Vigente", "Vencido", "No posee"})

    def test_la_reinspeccion_mantiene_el_riesgo_entre_0_y_1(self):
        rng = random.Random(9)
        for riesgo in (0.0, 0.5, 1.0):
            for _ in range(200):
                self.assertTrue(0.0 <= sim.riesgo_en_reinspeccion(riesgo, rng) <= 1.0)


class CargarDatosDemoTests(TestCase):
    def test_carga_usa_los_servicios_reales_y_se_borra_completa(self):
        predios_reales = Predio.objects.exclude(atributos_extra__demo=True).count()
        actas_reales = ActaInspeccion.objects.exclude(predio__atributos_extra__demo=True).count()

        resultado = demo.cargar(por_tipo=1)

        demo_predios = Predio.objects.filter(atributos_extra__demo=True)
        self.assertEqual(demo_predios.count(), 5)  # uno por cada tipo de predio
        self.assertEqual(len({p.tipo_predio_id for p in demo_predios}), 5)
        self.assertTrue(all(p.area_m2 and p.area_m2 > 0 for p in demo_predios))
        actas = ActaInspeccion.objects.filter(predio__atributos_extra__demo=True)
        self.assertEqual(actas.count(), resultado["actas"])
        self.assertGreaterEqual(resultado["actas"], 5)
        # La carga de fuego y el scoring los calculo cerrar_acta, no la simulacion
        self.assertTrue(all(a.cerrada and a.scoring_riesgo is not None for a in actas))
        self.assertTrue(all(a.carga_fuego is not None for a in actas))
        campania = Campania.objects.get(pk=resultado["campania_id"])
        self.assertEqual(campania.estado, Campania.ESTADO_CERRADA)
        self.assertTrue(Usuario.objects.filter(email=demo.EMAIL_INSPECTOR).exists())
        self.assertTrue(Hidrante.objects.filter(codigo__startswith=demo.PREFIJO_HIDRANTE).exists())

        with self.assertRaises(demo.DemoError):
            demo.cargar(por_tipo=1)  # no se carga dos veces

        borrado = demo.borrar()
        self.assertEqual(borrado["predios"], 5)
        self.assertEqual(borrado["actas"], resultado["actas"])
        self.assertFalse(Predio.objects.filter(atributos_extra__demo=True).exists())
        self.assertFalse(Campania.objects.filter(nombre__startswith=demo.PREFIJO_CAMPANIA).exists())
        self.assertFalse(Hidrante.objects.filter(codigo__startswith=demo.PREFIJO_HIDRANTE).exists())
        self.assertFalse(Usuario.objects.filter(email=demo.EMAIL_INSPECTOR).exists())
        # Los datos reales no se tocaron
        self.assertEqual(Predio.objects.count(), predios_reales)
        self.assertEqual(ActaInspeccion.objects.count(), actas_reales)
