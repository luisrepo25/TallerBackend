# Logica de negocio de esta app (capa de servicios).
# Las vistas delegan aqui: nunca hacen calculos ni orquestacion directo con el ORM.

from collections import defaultdict

from django.db import transaction

from apps.fiscalizacion.models import ActaInspeccion
from apps.fiscalizacion.services import D_MAX, Q_MAX, riesgo_extintores
from apps.usuarios.models import Administrador
from apps.usuarios.services import registrar_bitacora

from . import cliente_ml
from .models import ClusteringEjecucion

NIVELES_VALIDOS = {valor for valor, _ in ActaInspeccion.CLUSTER_CHOICES}


class AnaliticaConflicto(Exception):
    """No hay datos suficientes para agrupar (la vista responde 409)."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


def actas_para_clustering():
    """Actas cerradas con sus valores calculados (carga de fuego y scoring ya guardados)."""
    return (
        ActaInspeccion.objects.filter(
            cerrada=True, carga_fuego__isnull=False, scoring_riesgo__isnull=False
        )
        .order_by("pk")
        .values_list(
            "pk",
            "carga_fuego",
            "estado_extintores__nombre",
            "fallas_electricas",
            "rutas_evacuacion_despejadas",
            "distancia_hidrante_m",
            "scoring_riesgo",
        )
    )


def construir_payload(filas) -> list[dict]:
    """Contrato del microservicio (ver MicroservicioML/README.md). El ML no deriva nada:
    recibe los valores ya calculados, incluido el riesgo de extintores del scoring.

    La carga de fuego y la distancia al hidrante se recortan a los mismos topes del scoring
    (Q_MAX y D_MAX): para el scoring cualquier valor por encima es riesgo maximo, y sin el
    recorte K-Means los trataria como distintos (65 % de los predios estan a mas de 500 m)."""
    return [
        {
            "acta_id": pk,
            "carga_fuego": min(float(carga), float(Q_MAX)),
            "riesgo_extintores": float(riesgo_extintores(extintores)),
            "fallas_electricas": fallas,
            "rutas_obstruidas": not rutas_despejadas,
            "distancia_hidrante_m": (
                None if distancia is None else min(float(distancia), float(D_MAX))
            ),
            "scoring_riesgo": float(scoring),
        }
        for pk, carga, extintores, fallas, rutas_despejadas, distancia, scoring in filas
    ]


class SinAdministrador(Exception):
    """No hay un Administrador activo al que atribuir la ejecucion automatica."""


def administrador_para_ejecucion_automatica():
    """Administrador activo al que se atribuye la corrida programada (el primero por id).
    La columna ejecutado_por de clustering_ejecuciones y la bitacora exigen un usuario real."""
    admin = (
        Administrador.objects.select_related("usuario")
        .filter(usuario__activo=True)
        .order_by("usuario_id")
        .first()
    )
    if admin is None:
        raise SinAdministrador("No hay un Administrador activo para registrar la ejecucion.")
    return admin.usuario


def ejecutar_clustering(*, usuario, automatico=False) -> dict:
    """RF-17. Envia las actas cerradas al microservicio, guarda el cluster de cada una en
    `ActaInspeccion.cluster_riesgo` y registra la ejecucion.

    La llamada de red va fuera de la transaccion: si el microservicio falla no se escribe
    nada. Cada ejecucion reasigna el cluster de TODAS las actas cerradas (K-Means depende
    del conjunto completo), a diferencia de carga de fuego y scoring, que no se recalculan.
    """
    payload = construir_payload(actas_para_clustering())
    try:
        resultado = cliente_ml.ejecutar_clustering(payload)
    except cliente_ml.ServicioMLRechazo as exc:
        raise AnaliticaConflicto(exc.mensaje) from exc
    return _guardar_resultado(resultado, usuario, automatico)


@transaction.atomic
def _guardar_resultado(resultado: dict, usuario, automatico=False) -> dict:
    por_nivel = defaultdict(list)
    for item in resultado["clusters"]:
        if item["cluster_riesgo"] not in NIVELES_VALIDOS:
            raise cliente_ml.ServicioMLNoDisponible("El servicio devolvio un nivel desconocido.")
        por_nivel[item["cluster_riesgo"]].append(item["acta_id"])

    for nivel, ids in por_nivel.items():
        ActaInspeccion.objects.filter(pk__in=ids).update(cluster_riesgo=nivel)

    ejecucion = ClusteringEjecucion.objects.create(
        k_value=resultado["k"],
        coeficiente_silueta=resultado["coeficiente_silueta"],
        ejecutado_por=usuario,
    )
    registrar_bitacora(
        usuario=usuario,
        accion=(
            "Ejecutar clustering de riesgo (automatico)"
            if automatico
            else "Ejecutar clustering de riesgo"
        ),
        entidad_afectada="ClusteringEjecucion",
    )
    return {
        "ejecucion": ejecucion,
        "cantidad_actas": resultado["cantidad_actas"],
        "resumen": resultado["resumen"],
    }
