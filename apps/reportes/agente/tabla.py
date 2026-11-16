# Tipado semantico de columnas, autodetecion de graficos y calculo de KPIs.
# Basado en la especificacion de guia-reportes.md adaptado al dominio de Bomberos UUBR.

METADATOS_COLUMNA = {
    # Identificadores y fechas
    "acta_id": {"etiqueta": "Nº Acta", "tipo": "numero"},
    "predio_id": {"etiqueta": "ID Predio", "tipo": "numero"},
    "infraccion_id": {"etiqueta": "ID Infracción", "tipo": "numero"},
    "campania_id": {"etiqueta": "ID Campaña", "tipo": "numero"},
    "hidrante_id": {"etiqueta": "ID Hidrante", "tipo": "numero"},
    "fecha_inspeccion": {"etiqueta": "Fecha de Inspección", "tipo": "fecha"},
    "fecha_inicio": {"etiqueta": "Fecha Inicio", "tipo": "fecha"},
    "fecha_fin": {"etiqueta": "Fecha Fin", "tipo": "fecha"},
    "ultima_inspeccion": {"etiqueta": "Última Inspección", "tipo": "fecha"},
    "mes": {"etiqueta": "Mes", "tipo": "fecha"},
    # Entidades y Nombres
    "predio": {"etiqueta": "Predio", "tipo": "texto"},
    "tipo_predio": {"etiqueta": "Tipo de Predio", "tipo": "texto"},
    "distrito": {"etiqueta": "Distrito Municipal", "tipo": "texto"},
    "campania": {"etiqueta": "Campaña de Fiscalización", "tipo": "texto"},
    "inspector": {"etiqueta": "Inspector Técnico", "tipo": "texto"},
    "direccion": {"etiqueta": "Dirección", "tipo": "texto"},
    "tipo_infraccion": {"etiqueta": "Tipo de Infracción", "tipo": "texto"},
    "descripcion": {"etiqueta": "Descripción Técnica", "tipo": "texto"},
    "codigo": {"etiqueta": "Código", "tipo": "texto"},
    "hidrante_cercano": {"etiqueta": "Hidrante más Cercano", "tipo": "texto"},
    "tipo_acople": {"etiqueta": "Tipo de Acople", "tipo": "texto"},
    # Estados y clasificaciones
    "cluster_riesgo": {"etiqueta": "Nivel de Riesgo (Cluster)", "tipo": "riesgo"},
    "nivel_predominante": {"etiqueta": "Nivel Predominante", "tipo": "riesgo"},
    "estado": {"etiqueta": "Estado", "tipo": "texto"},
    "estado_operativo": {"etiqueta": "Estado Operativo", "tipo": "texto"},
    "estado_extintores": {"etiqueta": "Extintores", "tipo": "texto"},
    "fallas_electricas": {"etiqueta": "Fallas Eléctricas", "tipo": "booleano"},
    "rutas_obstruidas": {"etiqueta": "Rutas Obstruidas", "tipo": "booleano"},
    "es_reincidencia": {"etiqueta": "Reincidente", "tipo": "booleano"},
    "campania_activa": {"etiqueta": "Campaña Activa", "tipo": "booleano"},
    # Metricas tecnicas continuas
    "scoring_riesgo": {"etiqueta": "Scoring de Riesgo (0-100)", "tipo": "numero", "unidad": "pts"},
    "scoring_promedio": {"etiqueta": "Scoring Promedio", "tipo": "numero", "unidad": "pts"},
    "carga_fuego": {"etiqueta": "Carga de Fuego (NB 58005)", "tipo": "numero", "unidad": "MJ/m²"},
    "carga_fuego_promedio": {
        "etiqueta": "Carga de Fuego Prom.",
        "tipo": "numero",
        "unidad": "MJ/m²",
    },
    "area_m2": {"etiqueta": "Área Edificada", "tipo": "numero", "unidad": "m²"},
    "aforo": {"etiqueta": "Capacidad (Aforo)", "tipo": "numero", "unidad": "pers."},
    "distancia_hidrante_m": {"etiqueta": "Dist. a Hidrante", "tipo": "numero", "unidad": "m"},
    "distancia_promedio_m": {"etiqueta": "Dist. Prom. a Hidrante", "tipo": "numero", "unidad": "m"},
    "distancia_maxima_m": {"etiqueta": "Dist. Máx. a Hidrante", "tipo": "numero", "unidad": "m"},
    "presion_nominal": {"etiqueta": "Presión Nominal", "tipo": "numero", "unidad": "bar"},
    "severidad": {"etiqueta": "Peso Severidad", "tipo": "numero"},
    # Conteos y Porcentajes
    "total": {"etiqueta": "Total", "tipo": "numero"},
    "total_predios": {"etiqueta": "Total Predios", "tipo": "numero"},
    "predios_registrados": {"etiqueta": "Predios Registrados", "tipo": "numero"},
    "predios_inspeccionados": {"etiqueta": "Predios Insp.", "tipo": "numero"},
    "predios_afectados": {"etiqueta": "Predios Afectados", "tipo": "numero"},
    "predios_cubiertos": {"etiqueta": "Predios Cubiertos", "tipo": "numero"},
    "actas_cerradas": {"etiqueta": "Actas Cerradas", "tipo": "numero"},
    "actas_criticas": {"etiqueta": "Actas Críticas", "tipo": "numero"},
    "infracciones": {"etiqueta": "Infracciones", "tipo": "numero"},
    "reincidencias": {"etiqueta": "Reincidencias", "tipo": "numero"},
    "criticos": {"etiqueta": "Riesgo Crítico", "tipo": "numero"},
    "medios": {"etiqueta": "Riesgo Medio", "tipo": "numero"},
    "bajos": {"etiqueta": "Riesgo Bajo", "tipo": "numero"},
    "inspectores": {"etiqueta": "Inspectores", "tipo": "numero"},
    "porcentaje_critico": {"etiqueta": "% Crítico", "tipo": "porcentaje"},
    "porcentaje_reincidencia": {"etiqueta": "% Reincidencia", "tipo": "porcentaje"},
    "avance_pct": {"etiqueta": "% Avance", "tipo": "porcentaje"},
}


def etiqueta_columna(clave: str) -> dict:
    if clave in METADATOS_COLUMNA:
        meta = METADATOS_COLUMNA[clave].copy()
        meta["clave"] = clave
        return meta
    etiqueta = clave.replace("_", " ").capitalize()
    return {"clave": clave, "etiqueta": etiqueta, "tipo": "texto"}


def conformar_columnas(
    filas: list[dict], columnas_elegidas: list[str] | None = None
) -> tuple[list[dict], list[dict]]:
    if not filas:
        return [], []
    claves_disponibles = list(filas[0].keys())
    disponibles = [etiqueta_columna(k) for k in claves_disponibles]

    if columnas_elegidas:
        validas = [c for c in columnas_elegidas if c in claves_disponibles]
        if validas:
            return [etiqueta_columna(c) for c in validas], disponibles

    return disponibles, disponibles


def autodetectar_grafico(columnas: list[dict], filas: list[dict]) -> dict | None:
    if not filas or len(filas) < 2:
        return None

    claves_cols = {c["clave"]: c for c in columnas}

    # Prioridad eje X
    candidatos_x = [
        "distrito",
        "tipo_predio",
        "campania",
        "inspector",
        "tipo_infraccion",
        "mes",
        "fecha_inspeccion",
        "predio",
    ]
    clave_x = None
    for cand in candidatos_x:
        if cand in claves_cols:
            clave_x = cand
            break
    if not clave_x:
        for c in columnas:
            if c["tipo"] in ("texto", "fecha") and not c["clave"].endswith("_id"):
                clave_x = c["clave"]
                break
    if not clave_x:
        return None

    # Prioridad eje Y
    candidatos_y = [
        "criticos",
        "porcentaje_critico",
        "total",
        "scoring_promedio",
        "scoring_riesgo",
        "infracciones",
        "reincidencias",
        "carga_fuego_promedio",
        "carga_fuego",
        "actas_cerradas",
        "avance_pct",
    ]
    clave_y = None
    for cand in candidatos_y:
        if cand in claves_cols:
            clave_y = cand
            break
    if not clave_y:
        for c in columnas:
            if (
                c["tipo"] in ("numero", "porcentaje")
                and c["clave"] != clave_x
                and not c["clave"].endswith("_id")
            ):
                clave_y = c["clave"]
                break
    if not clave_y:
        return None

    # Determinar tipo de grafico
    meta_x = claves_cols[clave_x]
    if meta_x["tipo"] == "fecha" or clave_x == "mes":
        tipo_grafico = "linea"
    elif len(filas) <= 6 and meta_x["tipo"] == "texto":
        tipo_grafico = "anillo"
    else:
        tipo_grafico = "barras"

    etiqueta_x = meta_x["etiqueta"]
    etiqueta_y = claves_cols[clave_y]["etiqueta"]
    return {
        "tipo": tipo_grafico,
        "x": clave_x,
        "y": clave_y,
        "etiqueta_x": etiqueta_x,
        "etiqueta_y": etiqueta_y,
        "titulo": f"{etiqueta_y} por {etiqueta_x}",
    }


def calcular_kpis(columnas: list[dict], filas: list[dict]) -> list[dict]:
    if not filas:
        return []

    total_registros = len(filas)
    kpis = [{"etiqueta": "Total de Registros", "valor": str(total_registros), "tipo": "conteo"}]

    claves_presentes = {c["clave"]: c for c in columnas}

    # Casos especificos de interes operativo
    if "criticos" in claves_presentes:
        total_crit = sum(f.get("criticos", 0) for f in filas)
        kpis.append({"etiqueta": "Predios Críticos", "valor": str(total_crit), "tipo": "alerta"})
    elif "actas_criticas" in claves_presentes:
        total_crit = sum(f.get("actas_criticas", 0) for f in filas)
        kpis.append({"etiqueta": "Actas Críticas", "valor": str(total_crit), "tipo": "alerta"})
    elif "cluster_riesgo" in claves_presentes:
        criticos = sum(1 for f in filas if f.get("cluster_riesgo") == "Critico")
        kpis.append({"etiqueta": "Predios Críticos", "valor": str(criticos), "tipo": "alerta"})

    if "actas_cerradas" in claves_presentes:
        total_actas = sum(f.get("actas_cerradas", 0) for f in filas)
        kpis.append({"etiqueta": "Actas Cerradas", "valor": str(total_actas), "tipo": "conteo"})

    if "scoring_riesgo" in claves_presentes:
        vals = [f["scoring_riesgo"] for f in filas if f.get("scoring_riesgo") is not None]
        if vals:
            kpis.append(
                {
                    "etiqueta": "Scoring Promedio",
                    "valor": f"{sum(vals) / len(vals):.1f} pts",
                    "tipo": "promedio",
                }
            )
    elif "scoring_promedio" in claves_presentes:
        vals = [f["scoring_promedio"] for f in filas if f.get("scoring_promedio") is not None]
        if vals:
            kpis.append(
                {
                    "etiqueta": "Scoring Promedio",
                    "valor": f"{sum(vals) / len(vals):.1f} pts",
                    "tipo": "promedio",
                }
            )

    if "carga_fuego" in claves_presentes:
        vals = [f["carga_fuego"] for f in filas if f.get("carga_fuego") is not None]
        if vals:
            kpis.append(
                {
                    "etiqueta": "Carga de Fuego Prom.",
                    "valor": f"{sum(vals) / len(vals):.1f} MJ/m²",
                    "tipo": "promedio",
                }
            )
    elif "carga_fuego_promedio" in claves_presentes:
        vals = [
            f["carga_fuego_promedio"] for f in filas if f.get("carga_fuego_promedio") is not None
        ]
        if vals:
            kpis.append(
                {
                    "etiqueta": "Carga de Fuego Prom.",
                    "valor": f"{sum(vals) / len(vals):.1f} MJ/m²",
                    "tipo": "promedio",
                }
            )

    if "reincidencias" in claves_presentes:
        total_reinc = sum(f.get("reincidencias", 0) for f in filas)
        kpis.append({"etiqueta": "Reincidencias", "valor": str(total_reinc), "tipo": "alerta"})
    elif "es_reincidencia" in claves_presentes:
        total_reinc = sum(1 for f in filas if f.get("es_reincidencia"))
        kpis.append({"etiqueta": "Reincidencias", "valor": str(total_reinc), "tipo": "alerta"})

    if "severidad" in claves_presentes:
        vals = [f["severidad"] for f in filas if f.get("severidad") is not None]
        if vals:
            kpis.append(
                {
                    "etiqueta": "Severidad Promedio",
                    "valor": f"{sum(vals) / len(vals):.2f}",
                    "tipo": "promedio",
                }
            )

    if "estado_operativo" in claves_presentes:
        activos = sum(1 for f in filas if f.get("estado_operativo") == "activo")
        inoperativos = total_registros - activos
        kpis.append({"etiqueta": "Hidrantes Activos", "valor": str(activos), "tipo": "progreso"})
        kpis.append({"etiqueta": "Fuera de Servicio", "valor": str(inoperativos), "tipo": "alerta"})

    if "presion_nominal" in claves_presentes:
        vals = [f["presion_nominal"] for f in filas if f.get("presion_nominal") is not None]
        if vals:
            kpis.append(
                {
                    "etiqueta": "Presión Promedio",
                    "valor": f"{sum(vals) / len(vals):.1f} bar",
                    "tipo": "promedio",
                }
            )

    if "avance_pct" in claves_presentes:
        vals = [f["avance_pct"] for f in filas if f.get("avance_pct") is not None]
        if vals:
            kpis.append(
                {
                    "etiqueta": "Avance Promedio",
                    "valor": f"{sum(vals) / len(vals):.1f}%",
                    "tipo": "progreso",
                }
            )

    return kpis[:4]
