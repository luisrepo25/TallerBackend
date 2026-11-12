# Interprete determinista por reglas semanticas (fallback del agente).
# Garantiza que el Agente de Reportes funcione al 100% incluso sin conexion a internet o sin API key.

import re

from . import resolutores as r

PALABRAS_COLUMNAS = {
    "predio": "predio",
    "nombre": "predio",
    "distrito": "distrito",
    "zona": "distrito",
    "tipo": "tipo_predio",
    "categoria": "tipo_predio",
    "rubro": "tipo_predio",
    "riesgo": "cluster_riesgo",
    "cluster": "cluster_riesgo",
    "scoring": "scoring_riesgo",
    "puntaje": "scoring_riesgo",
    "fuego": "carga_fuego",
    "carga": "carga_fuego",
    "extintor": "estado_extintores",
    "extintores": "estado_extintores",
    "falla": "fallas_electricas",
    "electrica": "fallas_electricas",
    "ruta": "rutas_obstruidas",
    "obstruida": "rutas_obstruidas",
    "hidrante": "distancia_hidrante_m",
    "distancia": "distancia_hidrante_m",
    "infracciones": "infracciones",
    "reincidencias": "reincidencias",
    "fecha": "fecha_inspeccion",
    "inspector": "inspector",
    "campania": "campania",
    "campana": "campania",
    "direccion": "direccion",
    "area": "area_m2",
    "aforo": "aforo",
}


def detectar_columnas_solicitadas(texto_norm: str) -> list[str] | None:
    if not any(
        frase in texto_norm
        for frase in (
            "solo quiero",
            "solo mostrar",
            "solo ver",
            "unicamente",
            "columnas:",
            "mostrando solo",
        )
    ):
        return None
    encontradas = []
    palabras = set(re.findall(r"\b[a-z_]+\b", texto_norm))
    for p in palabras:
        if p in PALABRAS_COLUMNAS and PALABRAS_COLUMNAS[p] not in encontradas:
            encontradas.append(PALABRAS_COLUMNAS[p])
    return encontradas or None


def interpretar_pregunta(pregunta: str) -> tuple[str, dict, list[str] | None, str]:
    t = r.normalizar(pregunta)

    # 1. Distritos / Comparativa territorial
    if any(
        k in t
        for k in (
            "resumen de distrito",
            "comparar distrito",
            "por distrito",
            "distritos critico",
            "ranking de distrito",
        )
    ):
        params = {"orden": "criticos"}
        if "solo critico" in t:
            params["solo_con_criticos"] = True
        cols = detectar_columnas_solicitadas(t)
        return (
            "resumen_distritos",
            params,
            cols,
            "Resumen y Clasificación de Riesgo por Distritos Municipales",
        )

    # 2. Hidrantes y cobertura
    if any(k in t for k in ("hidrante", "grifo", "acople", "red hidraulica")):
        params = {}
        if "fuera de servicio" in t or "inoperativo" in t:
            params["estado_operativo"] = "fuera_de_servicio"
        elif "activo" in t or "operativo" in t:
            params["estado_operativo"] = "activo"
        try:
            d = r.resolver_distrito(t)
            if d:
                params["distrito"] = d.nombre
        except Exception:
            pass
        cols = detectar_columnas_solicitadas(t)
        return "consultar_hidrantes", params, cols, "Estado Operativo de la Red de Hidrantes"

    # 3. Infracciones y reincidencias
    if any(
        k in t
        for k in ("infraccion", "infracciones", "reincidencia", "reincidentes", "falta", "sancion")
    ):
        params = {}
        if "reinciden" in t:
            params["solo_reincidencias"] = True
        if any(k in t for k in ("por tipo", "mas comun", "frecuente", "ranking")):
            params["agrupar_por"] = "tipo_infraccion"
        elif "por distrito" in t:
            params["agrupar_por"] = "distrito"
        elif "por mes" in t or "tendencia" in t:
            params["agrupar_por"] = "mes"
        cols = detectar_columnas_solicitadas(t)
        return (
            "consultar_infracciones",
            params,
            cols,
            "Registro y Análisis de Infracciones Técnicas",
        )

    # 4. Campañas
    if any(k in t for k in ("campana", "campania", "operativo", "avance de campana")):
        params = {}
        if "activa" in t or "en curso" in t:
            params["estado"] = "activa"
        elif "cerrada" in t:
            params["estado"] = "cerrada"
        elif "pendiente" in t or "programada" in t:
            params["estado"] = "pendiente"
        cols = detectar_columnas_solicitadas(t)
        return "consultar_campanias", params, cols, "Avance y Estado de Campañas de Fiscalización"

    # 5. Inspectores
    if any(k in t for k in ("inspector", "inspectores", "productividad", "actas por inspector")):
        cols = detectar_columnas_solicitadas(t)
        return (
            "consultar_inspectores",
            {},
            cols,
            "Rendimiento y Productividad de Inspectores Técnicos",
        )

    # 6. Rubros / Tipos de predio
    if any(k in t for k in ("por rubro", "tipo de predio", "mercados vs colegios", "rubros")):
        cols = detectar_columnas_solicitadas(t)
        return "resumen_tipos_predio", {}, cols, "Evaluación de Riesgo por Rubro de Edificación"

    # 7. Predios Catastrados
    if any(k in t for k in ("predio", "edificacion", "inmueble", "catastro", "desprotegido")):
        params = {}
        if "critico" in t:
            params["cluster_riesgo"] = "Critico"
        elif "medio" in t:
            params["cluster_riesgo"] = "Medio"
        elif "bajo" in t:
            params["cluster_riesgo"] = "Bajo"
        if "sin inspeccion" in t or "no inspeccionado" in t:
            params["sin_inspeccion"] = True
        if "reinciden" in t:
            params["con_reincidencias"] = True
        if "desprotegido" in t or "lejos de hidrante" in t:
            params["distancia_hidrante_minima"] = 150.0
        try:
            d = r.resolver_distrito(t)
            if d:
                params["distrito"] = d.nombre
        except Exception:
            pass
        try:
            tp = r.resolver_tipo_predio(t)
            if tp:
                params["tipo_predio"] = tp.nombre
        except Exception:
            pass
        cols = detectar_columnas_solicitadas(t)
        return "consultar_predios", params, cols, "Catastro de Predios y Niveles de Riesgo"

    # 8. Inspecciones técnicas (por defecto)
    params = {}
    if "critico" in t or "alto riesgo" in t:
        params["cluster_riesgo"] = "Critico"
    elif "medio" in t:
        params["cluster_riesgo"] = "Medio"
    elif "bajo" in t:
        params["cluster_riesgo"] = "Bajo"

    if "falla" in t and "electr" in t:
        params["fallas_electricas"] = True
    if "ruta" in t and ("obstru" in t or "bloque" in t):
        params["rutas_obstruidas"] = True
    if "extintor vencido" in t or "sin extintor" in t:
        params["estado_extintores"] = "Vencido"

    try:
        d = r.resolver_distrito(t)
        if d:
            params["distrito"] = d.nombre
    except Exception:
        pass
    try:
        tp = r.resolver_tipo_predio(t)
        if tp:
            params["tipo_predio"] = tp.nombre
    except Exception:
        pass

    cols = detectar_columnas_solicitadas(t)
    return "consultar_inspecciones", params, cols, "Inspecciones Técnicas y Evaluación Pericial"


def generar_sintesis_reglas(titulo: str, herramienta: str, params: dict, filas: list[dict]) -> str:
    total = len(filas)
    if total == 0:
        return f"No se encontraron registros en el sistema que coincidan con los criterios especificados ({titulo}). Se recomienda verificar los filtros de búsqueda o ampliar el rango de fechas."

    if herramienta == "consultar_inspecciones":
        criticos = sum(1 for f in filas if f.get("cluster_riesgo") == "Critico")
        fallas = sum(1 for f in filas if f.get("fallas_electricas"))
        rutas = sum(1 for f in filas if f.get("rutas_obstruidas"))
        scorings = [f["scoring_riesgo"] for f in filas if f.get("scoring_riesgo") is not None]
        prom_sc = f"{sum(scorings) / len(scorings):.1f}" if scorings else "—"
        return (
            f"Se evaluaron {total} inspecciones técnicas en Santa Cruz de la Sierra. "
            f"Se identificaron {criticos} predios en nivel de riesgo Crítico con un scoring promedio de {prom_sc} pts. "
            f"Se detectaron fallas eléctricas en {fallas} edificaciones y {rutas} predios con rutas de evacuación obstruidas, "
            f"lo que demanda notificación pericial inmediata y verificación de cumplimiento conforme a la norma NB 58005."
        )

    if herramienta == "resumen_distritos":
        tot_crit = sum(f.get("criticos", 0) for f in filas)
        top = filas[0]["distrito"] if filas else "—"
        pct_top = filas[0].get("porcentaje_critico", 0) if filas else 0
        return (
            f"El consolidado territorial abarca los distritos municipales de Santa Cruz de la Sierra, "
            f"acumulando un total de {tot_crit} edificaciones en riesgo Crítico. "
            f"El distrito con mayor concentración de riesgo pericial es '{top}' con un {pct_top}% de predios críticos. "
            f"Se sugiere priorizar este sector para la asignación de nuevas brigadas y campañas de fiscalización preventiva."
        )

    if herramienta == "consultar_infracciones":
        tot_reinc = sum(f.get("reincidencias", 0) for f in filas if "reincidencias" in f)
        return (
            f"Se registraron {total} incidencias técnicas en edificaciones de uso público, "
            f"con {tot_reinc} casos confirmados de reincidencia normativa. "
            f"La mayor severidad corresponde a deficiencias en cableado eléctrico y extintores inoperativos, "
            f"ameritando seguimiento de medidas correctivas."
        )

    if herramienta == "consultar_hidrantes":
        inoperativos = sum(1 for f in filas if f.get("estado_operativo") != "activo")
        return (
            f"El censo hidráulico comprende {total} hidrantes georreferenciados en el municipio. "
            f"Se identificaron {inoperativos} hidrantes fuera de servicio o con presión deficiente, "
            f"los cuales requieren mantenimiento preventivo para asegurar el radio de cobertura ante emergencias."
        )

    return f"Se consolidaron {total} registros operativos correspondientes a '{titulo}', listos para su análisis pericial y exportación oficial."
