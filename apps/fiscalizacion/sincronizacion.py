"""Sincronizacion de actas hechas SIN CONEXION desde la app movil (RF-21, CU23).

Capa de negocio. Reutiliza las reglas que ya existen en `services.py` (registrar, cerrar,
calcular carga de fuego y scoring): aqui solo se orquesta una acta COMPLETA en una sola
operacion atomica. Por eso un corte de red nunca deja un acta a medias.

Garantias:
  - Idempotente: reenviar el mismo `uuid_local` no duplica nada (el celular puede reintentar).
  - Un acta mala no afecta a las demas del lote: cada una va en su propia transaccion.
  - El resultado se informa POR ACTA.
  - La fecha de inspeccion es la que capturo el dispositivo (no la de la sincronizacion).
"""

import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.campanias.models import Campania
from apps.catastro.models import Predio

from .models import (
    ActaInspeccion,
    CatalogoEstadoExtintor,
    CatalogoInfraccion,
    CatalogoMaterialCombustible,
)
from .services import (
    FiscalizacionConflicto,
    FiscalizacionError,
    cerrar_acta,
    registrar_acta,
    registrar_infraccion,
    registrar_materiales,
    subir_evidencia,
)

logger = logging.getLogger(__name__)

# Los relojes de los celulares no son exactos: se tolera un pequeno adelanto.
TOLERANCIA_RELOJ = timedelta(minutes=5)

# Estados del resultado de cada acta
SINCRONIZADA = "sincronizada"  # se guardo y se cerro ahora
YA_SINCRONIZADA = "ya_sincronizada"  # ya estaba (reintento): se devuelve lo guardado
RECHAZADA = "rechazada"  # el servidor la rechaza; reenviarla igual no sirve
ERROR_TEMPORAL = "error_temporal"  # fallo del servidor; la app debe reintentar luego


def _obtener(consulta, pk, descripcion):
    try:
        return consulta.get(pk=pk)
    except consulta.model.DoesNotExist as exc:
        raise FiscalizacionError(f"{descripcion} {pk} no existe.") from exc


def _validar_fecha(fecha):
    if fecha is not None and fecha > timezone.now() + TOLERANCIA_RELOJ:
        raise FiscalizacionError("La fecha de inspeccion no puede estar en el futuro.")
    return fecha


def _resultado(acta, estado):
    return {
        "uuid_local": str(acta.uuid_local),
        "estado": estado,
        "acta_id": acta.pk,
        "carga_fuego": acta.carga_fuego,
        "scoring_riesgo": acta.scoring_riesgo,
        "cluster_riesgo": acta.cluster_riesgo,
        "fecha_cierre": acta.fecha_cierre,
        # La reincidencia solo se conoce en el servidor (compara con actas anteriores del predio)
        "infracciones": [
            {"tipo_infraccion_id": i.tipo_infraccion_id, "es_reincidencia": i.es_reincidencia}
            for i in acta.infraccion_set.all()
        ],
    }


def _rechazo(uuid_local, codigo, detalle, estado=RECHAZADA):
    return {"uuid_local": str(uuid_local), "estado": estado, "codigo": codigo, "detalle": detalle}


def _buscar_existente(uuid_local):
    return (
        ActaInspeccion.objects.filter(uuid_local=uuid_local)
        .prefetch_related("infraccion_set")
        .first()
    )


def _crear_acta_completa(datos, usuario, inspector):
    """Registra, completa y cierra el acta. Debe correr dentro de una transaccion."""
    predio = _obtener(Predio.objects, datos["predio_id"], "El predio")
    campania = _obtener(Campania.objects, datos["campania_id"], "La campania")
    estado_extintores = _obtener(
        CatalogoEstadoExtintor.objects, datos["estado_extintores_id"], "El estado de extintores"
    )
    fecha = _validar_fecha(datos.get("fecha_inspeccion"))

    # Referencias de los catalogos: se validan antes de escribir nada
    materiales = [
        {
            "material_id": _obtener(
                CatalogoMaterialCombustible.objects, m["material_id"], "El material"
            ).pk,
            "peso_kg": m["peso_kg"],
        }
        for m in datos.get("materiales", [])
    ]
    infracciones = [
        (
            _obtener(CatalogoInfraccion.objects, i["tipo_infraccion_id"], "La infraccion"),
            i.get("descripcion", ""),
        )
        for i in datos.get("infracciones", [])
    ]

    # Reglas de registro (campania abierta, inspector asignado, predio dentro de la zona)
    acta = registrar_acta(
        predio=predio,
        campania=campania,
        inspector=inspector,
        estado_extintores=estado_extintores,
        fallas_electricas=datos.get("fallas_electricas", False),
        rutas_evacuacion_despejadas=datos.get("rutas_evacuacion_despejadas", True),
        uuid_local=datos["uuid_local"],
        distancia_hidrante_m=datos.get("distancia_hidrante_m"),
        usuario_autenticado=usuario,
    )
    if materiales:
        registrar_materiales(acta, materiales)
    for tipo, descripcion in infracciones:
        registrar_infraccion(acta, tipo, descripcion, usuario)
    for evidencia in datos.get("evidencias", []):
        subir_evidencia(
            acta,
            evidencia["url_imagen"],
            evidencia.get("descripcion_infraccion", ""),
            usuario,
        )

    # Calcula carga de fuego y scoring en el servidor y deja el acta cerrada
    acta = cerrar_acta(acta, usuario)

    # `update` (no `save`): fecha_inspeccion es auto_now_add y se sobrescribiria con la
    # hora de la sincronizacion en lugar de la de la inspeccion real
    cambios = {"sincronizada": True, "fecha_sincronizacion": timezone.now()}
    if fecha is not None:
        cambios["fecha_inspeccion"] = fecha
    ActaInspeccion.objects.filter(pk=acta.pk).update(**cambios)
    return _buscar_existente(datos["uuid_local"])


def sincronizar_acta(datos, usuario):
    """Sincroniza UNA acta completa. Devuelve un diccionario con el resultado (nunca lanza
    por errores de negocio). `datos` ya viene validado por el serializador."""
    inspector = usuario.inspectortecnico
    uuid_local = datos["uuid_local"]

    existente = _buscar_existente(uuid_local)
    if existente is not None:
        return _resultado_existente(existente, inspector)

    try:
        with transaction.atomic():
            acta = _crear_acta_completa(datos, usuario, inspector)
    except IntegrityError:
        # Otra peticion con el mismo uuid_local se nos adelanto: es un reintento
        existente = _buscar_existente(uuid_local)
        if existente is not None:
            return _resultado_existente(existente, inspector)
        raise
    except FiscalizacionConflicto as exc:
        return _rechazo(uuid_local, "conflicto", exc.mensaje)
    except FiscalizacionError as exc:
        return _rechazo(uuid_local, "validacion", exc.mensaje)
    return _resultado(acta, SINCRONIZADA)


def _resultado_existente(acta, inspector):
    if acta.inspector_id != inspector.pk:
        # No se revela nada del acta ajena
        return _rechazo(
            acta.uuid_local, "uuid_en_uso", "Ese identificador ya fue usado por otro inspector."
        )
    return _resultado(acta, YA_SINCRONIZADA)


def sincronizar_actas(lista_datos, usuario):
    """Sincroniza un lote. Cada acta es independiente de las demas."""
    resultados = []
    for datos in lista_datos:
        try:
            resultados.append(sincronizar_acta(datos, usuario))
        except Exception:  # noqa: BLE001 - un fallo inesperado no debe frenar el lote
            logger.exception("Error inesperado sincronizando el acta %s", datos.get("uuid_local"))
            resultados.append(
                _rechazo(
                    datos.get("uuid_local"),
                    "servidor",
                    "El servidor no pudo procesar el acta. Reintenta mas tarde.",
                    estado=ERROR_TEMPORAL,
                )
            )
    return resultados
