from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.campanias.models import Campania
from apps.catastro.models import Predio, PredioHidranteCobertura
from apps.fiscalizacion.models import ActaInspeccion, Infraccion
from apps.usuarios.services import registrar_bitacora

from .excel_generator import generar_excel_dictamen, generar_excel_ejecutivo
from .models import ReporteGenerado
from .pdf_generator import generar_pdf_dictamen, generar_pdf_ejecutivo


class ReportesError(Exception):
    """Error base de la capa de servicios de reportes."""

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


class ReportesNoEncontrado(ReportesError):
    """El recurso requerido para el reporte (campaña, predio, acta) no existe."""

    pass


def obtener_datos_ejecutivo(campania_id: int) -> dict:
    """Extrae y estructura todos los datos estadísticos y operacionales de una campaña
    para la generación de reportes ejecutivos (PDF / Excel)."""
    try:
        campania = Campania.objects.select_related("creado_por__usuario").get(id=campania_id)
    except Campania.DoesNotExist:
        raise ReportesNoEncontrado(f"No existe la campaña con ID {campania_id}.") from None

    # Inspectores asignados
    inspectores = [
        cf.usuario.usuario.nombre_completo
        for cf in campania.campaniafuncionario_set.select_related("usuario__usuario").all()
    ]

    # Predios dentro de la zona de la campaña
    if campania.geom:
        total_predios = Predio.objects.filter(geom__intersects=campania.geom).count()
    else:
        total_predios = (
            ActaInspeccion.objects.filter(campania=campania).values("predio_id").distinct().count()
        )

    # Actas de la campaña
    actas_qs = (
        ActaInspeccion.objects.filter(campania=campania)
        .select_related("predio__tipo_predio", "inspector__usuario", "estado_extintores")
        .prefetch_related("infraccion_set")
        .order_by("-fecha_inspeccion")
    )

    actas_list = list(actas_qs)
    actas_cerradas = [a for a in actas_list if a.cerrada]
    actas_abiertas = [a for a in actas_list if not a.cerrada]
    predios_inspeccionados = len({a.predio_id for a in actas_list})

    avance_pct = round((len(actas_cerradas) / total_predios) * 100, 1) if total_predios > 0 else 0.0

    # Distribución por Cluster de Riesgo (K-Means)
    conteo_critico = sum(1 for a in actas_cerradas if a.cluster_riesgo == "Critico")
    conteo_medio = sum(1 for a in actas_cerradas if a.cluster_riesgo == "Medio")
    conteo_bajo = sum(1 for a in actas_cerradas if a.cluster_riesgo == "Bajo")
    conteo_sin_cluster = sum(1 for a in actas_cerradas if not a.cluster_riesgo)

    total_cerradas_n = len(actas_cerradas) or 1
    pct_critico = round((conteo_critico / total_cerradas_n) * 100, 1)
    pct_medio = round((conteo_medio / total_cerradas_n) * 100, 1)
    pct_bajo = round((conteo_bajo / total_cerradas_n) * 100, 1)
    pct_sin_cluster = round((conteo_sin_cluster / total_cerradas_n) * 100, 1)

    # Promedios cuantitativos
    scorings = [float(a.scoring_riesgo) for a in actas_cerradas if a.scoring_riesgo is not None]
    scoring_prom = round(sum(scorings) / len(scorings), 1) if scorings else 0.0

    cargas = [float(a.carga_fuego) for a in actas_cerradas if a.carga_fuego is not None]
    carga_prom = round(sum(cargas) / len(cargas), 2) if cargas else 0.0
    carga_max = round(max(cargas), 2) if cargas else 0.0

    distancias = [
        float(a.distancia_hidrante_m) for a in actas_cerradas if a.distancia_hidrante_m is not None
    ]
    distancia_prom = round(sum(distancias) / len(distancias), 1) if distancias else 0.0

    # Infracciones detectadas en la campaña
    infracciones_agg = (
        Infraccion.objects.filter(acta__campania=campania)
        .values("tipo_infraccion__nombre")
        .annotate(
            total=Count("id"),
            reincidentes=Count("id", filter=Q(es_reincidencia=True)),
        )
        .order_by("-total")
    )
    infracciones_lista = [
        {
            "nombre": inf["tipo_infraccion__nombre"],
            "total": inf["total"],
            "reincidentes": inf["reincidentes"],
        }
        for inf in infracciones_agg
    ]

    # Lista detallada de inspecciones
    detalles_actas = []
    for a in actas_list:
        detalles_actas.append(
            {
                "acta_id": a.id,
                "predio_nombre": a.predio.nombre if a.predio else "—",
                "direccion": a.predio.direccion if a.predio else "—",
                "tipo_predio": (
                    a.predio.tipo_predio.nombre if a.predio and a.predio.tipo_predio else "—"
                ),
                "inspector_nombre": (a.inspector.usuario.nombre_completo if a.inspector else "—"),
                "fecha_inspeccion": (
                    a.fecha_inspeccion.strftime("%d/%m/%Y %H:%M") if a.fecha_inspeccion else "—"
                ),
                "carga_fuego": float(a.carga_fuego) if a.carga_fuego is not None else None,
                "scoring_riesgo": (
                    float(a.scoring_riesgo) if a.scoring_riesgo is not None else None
                ),
                "cluster_riesgo": a.cluster_riesgo or "—",
                "estado_extintores": (a.estado_extintores.nombre if a.estado_extintores else "—"),
                "rutas_obstruidas": not a.rutas_evacuacion_despejadas,
                "fallas_electricas": a.fallas_electricas,
                "infracciones_conteo": a.infraccion_set.count(),
                "cerrada": a.cerrada,
            }
        )

    return {
        "campania": {
            "id": campania.id,
            "nombre": campania.nombre,
            "estado": campania.estado,
            "fecha_inicio": (
                campania.fecha_inicio.strftime("%d/%m/%Y") if campania.fecha_inicio else "—"
            ),
            "fecha_fin": (campania.fecha_fin.strftime("%d/%m/%Y") if campania.fecha_fin else "—"),
            "creado_por": (
                campania.creado_por.usuario.nombre_completo if campania.creado_por else "Sistema"
            ),
            "inspectores": inspectores,
        },
        "avance": {
            "total_predios": total_predios,
            "total_inspeccionados": predios_inspeccionados,
            "actas_cerradas": len(actas_cerradas),
            "actas_abiertas": len(actas_abiertas),
            "porcentaje_avance": avance_pct,
        },
        "riesgo": {
            "critico": conteo_critico,
            "medio": conteo_medio,
            "bajo": conteo_bajo,
            "sin_clasificar": conteo_sin_cluster,
            "pct_critico": pct_critico,
            "pct_medio": pct_medio,
            "pct_bajo": pct_bajo,
            "pct_sin_clasificar": pct_sin_cluster,
            "scoring_promedio": scoring_prom,
            "carga_fuego_promedio": carga_prom,
            "carga_fuego_max": carga_max,
            "distancia_hidrante_promedio": distancia_prom,
        },
        "infracciones": infracciones_lista,
        "detalles_actas": detalles_actas,
        "fecha_emision": timezone.now().strftime("%d/%m/%Y %H:%M"),
    }


def obtener_datos_dictamen(acta_id: int | None = None, predio_id: int | None = None) -> dict:
    """Extrae y estructura los datos técnicos detallados de un predio y su acta de
    inspección para generar un dictamen técnico oficial (NB 58005)."""
    if not acta_id and not predio_id:
        raise ReportesError("Se debe especificar acta_id o predio_id.")

    if predio_id and not acta_id:
        acta = (
            ActaInspeccion.objects.filter(predio_id=predio_id)
            .select_related(
                "predio__tipo_predio", "campania", "inspector__usuario", "estado_extintores"
            )
            .order_by("-cerrada", "-fecha_inspeccion")
            .first()
        )
        if not acta:
            raise ReportesNoEncontrado(
                f"No existen actas de inspección para el predio con ID {predio_id}."
            )
    else:
        try:
            acta = ActaInspeccion.objects.select_related(
                "predio__tipo_predio",
                "campania",
                "inspector__usuario",
                "estado_extintores",
            ).get(id=acta_id)
        except ActaInspeccion.DoesNotExist:
            raise ReportesNoEncontrado(
                f"No existe el acta de inspección con ID {acta_id}."
            ) from None

    predio = acta.predio
    if not predio:
        raise ReportesNoEncontrado("El acta no tiene un predio asociado.")

    # Hidrante más cercano registrado
    cobertura = (
        PredioHidranteCobertura.objects.filter(predio=predio, es_mas_cercano=True)
        .select_related("hidrante")
        .first()
    )
    hidrante_codigo = (
        cobertura.hidrante.codigo
        if cobertura and cobertura.hidrante
        else (f"Hidrante #{cobertura.hidrante_id}" if cobertura else "Ninguno cercano")
    )
    distancia_m = (
        float(cobertura.distancia_m)
        if cobertura and cobertura.distancia_m is not None
        else (float(acta.distancia_hidrante_m) if acta.distancia_hidrante_m else 0.0)
    )

    # Materiales registrados
    materiales_db = acta.materialregistrado_set.select_related("material").all()
    ra = float(predio.tipo_predio.riesgo_activacion) if predio.tipo_predio else 1.0

    materiales = []
    for mr in materiales_db:
        p = float(mr.peso_kg)
        hi = float(mr.material.poder_calorifico_mj_kg)
        ci = float(mr.material.coeficiente_peligrosidad)
        calor_total = round(p * hi * ci, 2)
        materiales.append(
            {
                "nombre": mr.material.nombre,
                "peso_kg": p,
                "poder_calorifico": hi,
                "coeficiente_peligrosidad": ci,
                "calor_total_mj": calor_total,
            }
        )

    # Infracciones registradas
    infracciones_db = acta.infraccion_set.select_related("tipo_infraccion").all()
    infracciones = [
        {
            "nombre": inf.tipo_infraccion.nombre,
            "severidad": float(inf.tipo_infraccion.peso_severidad),
            "reincidente": inf.es_reincidencia,
            "descripcion": inf.descripcion,
        }
        for inf in infracciones_db
    ]

    total_evidencias = acta.evidenciafotografica_set.count()

    return {
        "acta": {
            "id": acta.id,
            "uuid_local": str(acta.uuid_local) if acta.uuid_local else "—",
            "campania_nombre": acta.campania.nombre if acta.campania else "Inspección General",
            "inspector_nombre": (acta.inspector.usuario.nombre_completo if acta.inspector else "—"),
            "fecha_inspeccion": (
                acta.fecha_inspeccion.strftime("%d/%m/%Y %H:%M") if acta.fecha_inspeccion else "—"
            ),
            "cerrada": acta.cerrada,
            "fecha_cierre": (
                acta.fecha_cierre.strftime("%d/%m/%Y %H:%M") if acta.fecha_cierre else "—"
            ),
            "carga_fuego": float(acta.carga_fuego) if acta.carga_fuego is not None else None,
            "scoring_riesgo": (
                float(acta.scoring_riesgo) if acta.scoring_riesgo is not None else None
            ),
            "cluster_riesgo": acta.cluster_riesgo or "Sin clasificar",
            "estado_extintores": (
                acta.estado_extintores.nombre if acta.estado_extintores else "No registrado"
            ),
            "rutas_obstruidas": not acta.rutas_evacuacion_despejadas,
            "fallas_electricas": acta.fallas_electricas,
        },
        "predio": {
            "id": predio.id,
            "nombre": predio.nombre,
            "direccion": predio.direccion or "Sin dirección especificada",
            "tipo": (predio.tipo_predio.nombre if predio.tipo_predio else "No especificado"),
            "area_m2": float(predio.area_m2) if predio.area_m2 else 0.0,
            "aforo": predio.aforo,
            "riesgo_activacion": ra,
            "hidrante_codigo": hidrante_codigo,
            "distancia_hidrante_m": round(distancia_m, 1),
        },
        "materiales": materiales,
        "infracciones": infracciones,
        "total_evidencias": total_evidencias,
        "fecha_emision": timezone.now().strftime("%d/%m/%Y %H:%M"),
    }


@transaction.atomic
def generar_reporte(
    *,
    tipo: str,
    formato: str,
    usuario,
    campania_id: int | None = None,
    acta_id: int | None = None,
    predio_id: int | None = None,
) -> tuple[bytes, str, str, ReporteGenerado]:
    """Orquesta la extracción de datos, renderizado en formato PDF o Excel, registro
    en auditoría y bitácora, devolviendo los bytes del archivo y metadatos HTTP."""
    parametros = {}
    timestamp = timezone.now().strftime("%Y%m%d_%H%M")

    if tipo == ReporteGenerado.TIPO_EJECUTIVO:
        if not campania_id:
            raise ReportesError("campania_id es requerido para reporte ejecutivo.")
        parametros["campania_id"] = campania_id
        datos = obtener_datos_ejecutivo(campania_id)
        slug_campania = datos["campania"]["nombre"].lower().replace(" ", "_").replace("/", "_")[:30]

        if formato == ReporteGenerado.FORMATO_PDF:
            contenido = generar_pdf_ejecutivo(datos)
            content_type = "application/pdf"
            filename = f"reporte_ejecutivo_{slug_campania}_{timestamp}.pdf"
        elif formato == ReporteGenerado.FORMATO_EXCEL:
            contenido = generar_excel_ejecutivo(datos)
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"reporte_ejecutivo_{slug_campania}_{timestamp}.xlsx"
        else:
            raise ReportesError(f"Formato no soportado: {formato}")

    elif tipo == ReporteGenerado.TIPO_DICTAMEN:
        if not acta_id and not predio_id:
            raise ReportesError("acta_id o predio_id es requerido para dictamen técnico.")
        if acta_id:
            parametros["acta_id"] = acta_id
        if predio_id:
            parametros["predio_id"] = predio_id

        datos = obtener_datos_dictamen(acta_id=acta_id, predio_id=predio_id)
        slug_predio = datos["predio"]["nombre"].lower().replace(" ", "_").replace("/", "_")[:30]
        id_acta = datos["acta"]["id"]

        if formato == ReporteGenerado.FORMATO_PDF:
            contenido = generar_pdf_dictamen(datos)
            content_type = "application/pdf"
            filename = f"dictamen_acta_{id_acta}_{slug_predio}_{timestamp}.pdf"
        elif formato == ReporteGenerado.FORMATO_EXCEL:
            contenido = generar_excel_dictamen(datos)
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"dictamen_acta_{id_acta}_{slug_predio}_{timestamp}.xlsx"
        else:
            raise ReportesError(f"Formato no soportado: {formato}")
    else:
        raise ReportesError(f"Tipo de reporte no soportado: {tipo}")

    # Persistencia del registro de reporte generado
    reporte_generado = ReporteGenerado.objects.create(
        tipo=tipo,
        formato=formato,
        generado_por=usuario,
        parametros=parametros,
    )

    # Auditoria de bitacora
    registrar_bitacora(
        usuario=usuario,
        accion=f"Generar reporte {tipo} ({formato})",
        entidad_afectada="ReporteGenerado",
    )

    return contenido, content_type, filename, reporte_generado
