import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.catastro.models import Predio
from apps.usuarios.models import InspectorTecnico
from apps.usuarios.services import registrar_bitacora

from .models import Campania, CampaniaFuncionario

# Logica de negocio de esta app (capa de servicios).
# Las vistas delegan aqui: nunca hacen calculos ni orquestacion directo con el ORM.
#
# OJO: no existe FK directa Predio<->Campania (ver CLAUDE.md). Los "predios de una
# campania" se resuelven SIEMPRE por interseccion espacial en `predios_en_zona`.

logger = logging.getLogger(__name__)


class CampaniaError(Exception):
    """Regla de negocio violada por datos invalidos (la vista responde 400)."""

    def __init__(self, mensaje, **extra):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.extra = extra


class CampaniaConflicto(CampaniaError):
    """Operacion incompatible con el estado actual (la vista responde 409)."""


def _importar_acta():
    # Import diferido: fiscalizacion.models importa Campania (evita ciclo).
    from apps.fiscalizacion.models import ActaInspeccion

    return ActaInspeccion


def _validar_fechas(fecha_inicio, fecha_fin):
    if fecha_fin < fecha_inicio:
        raise CampaniaError("La fecha de fin no puede ser anterior a la fecha de inicio.")


def _validar_poligono(geom):
    if geom is None:
        return
    if not geom.valid:
        raise CampaniaError(f"El poligono de la zona es invalido: {geom.valid_reason}.")


def _bloquear(campania: Campania) -> Campania:
    """Re-lee la campania con lock de fila para serializar cierre/asignacion/edicion."""
    return Campania.objects.select_for_update().get(pk=campania.pk)


def _exigir_no_cerrada(campania: Campania):
    if campania.estado == Campania.ESTADO_CERRADA:
        raise CampaniaConflicto("La campania esta cerrada y no admite modificaciones.")


def campanias_visibles(usuario):
    """Campanias que el usuario puede consultar: Administrador y Oficial de Mando ven
    todas; un Inspector Tecnico (sin esos subtipos) solo las que tiene asignadas."""
    qs = Campania.objects.select_related("creado_por__usuario").prefetch_related(
        "campaniafuncionario_set__usuario__usuario"
    )
    if hasattr(usuario, "administrador") or hasattr(usuario, "oficialmando"):
        return qs.order_by("-id")
    return qs.filter(campaniafuncionario__usuario_id=usuario.pk).order_by("-id")


@transaction.atomic
def crear_campania(*, nombre, fecha_inicio, fecha_fin, creado_por, geom=None) -> Campania:
    """RF-7. `creado_por` es el Administrador autenticado; la campania nace 'pendiente'."""
    _validar_fechas(fecha_inicio, fecha_fin)
    _validar_poligono(geom)
    return Campania.objects.create(
        nombre=nombre,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        geom=geom,
        creado_por=creado_por,
        estado=Campania.ESTADO_PENDIENTE,
    )


@transaction.atomic
def actualizar_campania(campania: Campania, datos: dict) -> Campania:
    campania = _bloquear(campania)
    _exigir_no_cerrada(campania)

    nuevo = {**datos}
    _validar_fechas(
        nuevo.get("fecha_inicio", campania.fecha_inicio),
        nuevo.get("fecha_fin", campania.fecha_fin),
    )
    if "geom" in nuevo:
        _validar_poligono(nuevo["geom"])

    for campo, valor in nuevo.items():
        setattr(campania, campo, valor)
    if nuevo:
        # update_fields: no reescribir fecha_creacion (se lee naive de la columna TIMESTAMP).
        campania.save(update_fields=list(nuevo))
    return campania


@transaction.atomic
def actualizar_zona(campania: Campania, geom) -> Campania:
    """RF-8. Delimita/reemplaza el poligono de la zona de la campania."""
    if geom is None:
        raise CampaniaError("El poligono de la zona es obligatorio.")
    return actualizar_campania(campania, {"geom": geom})


@transaction.atomic
def asignar_inspectores(campania: Campania, usuarios_ids: list[int]) -> Campania:
    """RF-9. Idempotente: reasignar un inspector ya asignado no falla ni duplica.
    Al asignar el primer inspector una campania 'pendiente' pasa a 'en_curso'."""
    campania = _bloquear(campania)
    _exigir_no_cerrada(campania)

    ids = set(usuarios_ids)
    validos = set(
        InspectorTecnico.objects.filter(usuario_id__in=ids).values_list("usuario_id", flat=True)
    )
    if validos != ids:
        raise CampaniaError(
            "Solo se pueden asignar Inspectores Tecnicos existentes.",
            ids_invalidos=sorted(ids - validos),
        )

    ya_asignados = set(
        CampaniaFuncionario.objects.filter(campania=campania).values_list("usuario_id", flat=True)
    )
    for usuario_id in sorted(ids - ya_asignados):
        CampaniaFuncionario.objects.create(campania=campania, usuario_id=usuario_id)

    if campania.estado == Campania.ESTADO_PENDIENTE and (ids or ya_asignados):
        campania.estado = Campania.ESTADO_EN_CURSO
        campania.save(update_fields=["estado"])
    return campania


@transaction.atomic
def quitar_inspector(campania: Campania, usuario_id: int) -> None:
    """RF-9. No se puede quitar a un inspector que ya registro actas en la campania."""
    campania = _bloquear(campania)
    _exigir_no_cerrada(campania)

    asignacion = CampaniaFuncionario.objects.filter(campania=campania, usuario_id=usuario_id)
    if not asignacion.exists():
        raise CampaniaError("El inspector no esta asignado a esta campania.")
    ActaInspeccion = _importar_acta()
    if ActaInspeccion.objects.filter(campania=campania, inspector_id=usuario_id).exists():
        raise CampaniaConflicto(
            "El inspector ya registro actas en esta campania y no puede ser removido."
        )
    asignacion.delete()


def predios_en_zona(campania: Campania):
    """Unica definicion de 'predios de la campania': interseccion espacial (ST_Intersects)
    con el poligono de la zona. Un predio en el borde de dos zonas cuenta en ambas."""
    if campania.geom is None:
        return Predio.objects.none()
    return Predio.objects.filter(geom__intersects=campania.geom)


def calcular_avance(campania: Campania) -> dict:
    """RF-10. porcentaje = predios con acta cerrada / predios dentro del poligono."""
    ActaInspeccion = _importar_acta()
    predios = predios_en_zona(campania)
    total = predios.count()
    inspeccionados = (
        ActaInspeccion.objects.filter(campania=campania, cerrada=True, predio__in=predios)
        .values("predio_id")
        .distinct()
        .count()
    )
    porcentaje = (
        (Decimal(inspeccionados) * 100 / Decimal(total)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if total
        else Decimal("0.00")
    )
    return {
        "total_predios": total,
        "predios_inspeccionados": inspeccionados,
        "predios_pendientes": total - inspeccionados,
        "porcentaje": porcentaje,
    }


def _cerrar(campania: Campania, *, forzar: bool) -> dict:
    ActaInspeccion = _importar_acta()
    avance = calcular_avance(campania)
    actas_abiertas = ActaInspeccion.objects.filter(campania=campania, cerrada=False).count()

    if not forzar and (avance["predios_pendientes"] or actas_abiertas):
        raise CampaniaConflicto(
            "No se puede cerrar: quedan inspecciones pendientes.",
            predios_pendientes=avance["predios_pendientes"],
            actas_abiertas=actas_abiertas,
        )

    campania.estado = Campania.ESTADO_CERRADA
    campania.save(update_fields=["estado"])
    return {**avance, "actas_abiertas": actas_abiertas}


@transaction.atomic
def cerrar_campania(campania: Campania, *, usuario, forzar: bool = False) -> dict:
    """RF-11. Cierra la campania solo si no quedan inspecciones pendientes (predios de la
    zona sin acta cerrada o actas abiertas). `forzar=True` permite al Administrador cerrar
    de todos modos; el cierre forzado queda marcado en la bitacora."""
    campania = _bloquear(campania)
    _exigir_no_cerrada(campania)
    resumen = _cerrar(campania, forzar=forzar)
    registrar_bitacora(
        usuario=usuario,
        accion="Cerrar campania (forzado)" if forzar else "Cerrar campania",
        entidad_afectada="Campania",
    )
    return {"campania": campania, "forzado": forzar, **resumen}


def cerrar_campanias_vencidas(hoy=None) -> list[int]:
    """Cierre automatico por vencimiento: toda campania no cerrada cuya `fecha_fin` ya
    paso se cierra (equivale a un cierre forzado, no exige inspecciones completas).
    Pensado para ejecutarse periodicamente (management command `cerrar_campanias_vencidas`).
    No registra bitacora: no hay usuario que realice la accion (usuario_id es NOT NULL)."""
    hoy = hoy or timezone.localdate()
    vencidas = Campania.objects.exclude(estado=Campania.ESTADO_CERRADA).filter(fecha_fin__lt=hoy)
    cerradas = []
    for campania_id in list(vencidas.values_list("id", flat=True)):
        with transaction.atomic():
            campania = Campania.objects.select_for_update().get(pk=campania_id)
            if campania.estado == Campania.ESTADO_CERRADA:
                continue
            resumen = _cerrar(campania, forzar=True)
        cerradas.append(campania_id)
        logger.info("Campania %s cerrada por vencimiento: %s", campania_id, resumen)
    return cerradas
