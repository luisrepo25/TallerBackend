# Simulacion de inspecciones para los datos de demostracion. Sin base de datos: solo decide QUE
# encontro un inspector ficticio en un predio (extintores, fallas, materiales, infracciones).
# La carga de fuego, el scoring y el cluster NO se calculan aqui: los calcula el sistema real
# (fiscalizacion/services.py y el microservicio) a partir de estos datos.
#
# Todo parte de un "riesgo latente" r entre 0 y 1 por predio; mientras mas alto, mas probable es
# encontrar extintores vencidos, fallas electricas, rutas obstruidas, mas material combustible y
# mas infracciones. Es aleatorio (con semilla) y el riesgo promedio depende del tipo de predio,
# pero los grupos se traslapan a proposito: no es un dataset de juguete perfectamente separable.

import random
from dataclasses import dataclass

# Parametros (alfa, beta) de una distribucion Beta por tipo de predio. Media = alfa / (alfa + beta).
PERFIL_RIESGO = {
    "Industrial": (4.0, 2.0),
    "Mercado Distrital": (3.5, 2.5),
    "Comercial": (2.5, 3.0),
    "Salud": (2.0, 4.0),
    "Educativo": (2.0, 4.5),
}
PERFIL_POR_DEFECTO = (2.0, 3.0)

DENSIDAD_MAX_KG_M2 = 12.0  # kg de combustible por m2 cuando r = 1
PESO_MAX_KG = 100_000  # tope por material (la columna admite hasta 999 999,99)


@dataclass(frozen=True)
class InspeccionSimulada:
    extintores: str
    fallas_electricas: bool
    rutas_despejadas: bool
    materiales: list[tuple[str, float]]  # (nombre del material, kg)
    infracciones: list[str]  # nombres del catalogo de infracciones


def riesgo_latente(tipo_predio: str, rng: random.Random) -> float:
    return rng.betavariate(*PERFIL_RIESGO.get(tipo_predio, PERFIL_POR_DEFECTO))


def riesgo_en_reinspeccion(riesgo: float, rng: random.Random) -> float:
    """Una reinspeccion suele encontrar el predio algo mejor, pero no siempre."""
    return min(1.0, max(0.0, riesgo + rng.uniform(-0.25, 0.10)))


def _extintores(r: float, rng: random.Random) -> str:
    p_no_posee = 0.05 + 0.50 * r
    p_vencido = 0.15 + 0.30 * r
    u = rng.random()
    if u < p_no_posee:
        return "No posee"
    return "Vencido" if u < p_no_posee + p_vencido else "Vigente"


def _materiales(r: float, area_m2: float, catalogo: list[str], rng: random.Random):
    cantidad = min(len(catalogo), 1 + (r > 0.35) + (r > 0.70))
    elegidos = rng.sample(catalogo, cantidad)
    densidad = 0.2 + r * DENSIDAD_MAX_KG_M2 * rng.uniform(0.4, 1.3)
    total_kg = densidad * area_m2
    return [
        (nombre, round(min(max(1.0, total_kg / cantidad * rng.uniform(0.7, 1.3)), PESO_MAX_KG), 2))
        for nombre in elegidos
    ]


def simular_inspeccion(
    riesgo: float,
    area_m2: float,
    materiales_catalogo: list[str],
    infracciones_catalogo: list[str],
    rng: random.Random,
) -> InspeccionSimulada:
    cantidad_infracciones = sum(rng.random() < 0.15 + 0.50 * riesgo for _ in infracciones_catalogo)
    return InspeccionSimulada(
        extintores=_extintores(riesgo, rng),
        fallas_electricas=rng.random() < 0.05 + 0.60 * riesgo,
        rutas_despejadas=rng.random() >= 0.05 + 0.55 * riesgo,
        materiales=_materiales(riesgo, area_m2, materiales_catalogo, rng),
        infracciones=rng.sample(infracciones_catalogo, cantidad_infracciones),
    )
