# Consultas parametrizadas del Agente de Reportes (capa de negocio, SOLO LECTURA).
#
# Son las unicas "herramientas" de datos que puede invocar el LLM: el modelo elige cual y con
# que filtros, pero nunca escribe SQL. Cada consulta devuelve filas planas (dict) con valores
# serializables a JSON; los nombres de columna estan descritos en `tabla.METADATOS`.
#
# El distrito de un predio se obtiene igual que en la zonificacion (RF-18): por el distrito
# que contiene su centroide.

from django.contrib.gis.db.models.functions import Centroid
from django.db.models import Avg, Count, Max, OuterRef, Q, Subquery
from django.db.models.functions import TruncMonth

from apps.analitica.models import Distrito
from apps.analitica.zonificacion import resumen_distritos as resumen_zonificacion
from apps.analitica.zonificacion import ultimas_actas_cerradas
from apps.campanias.models import Campania, CampaniaFuncionario
from apps.campanias.services import calcular_avance
from apps.catastro.models import Hidrante, Predio, PredioHidranteCobertura
from apps.fiscalizacion.models import ActaInspeccion, Infraccion

from . import resolutores as r

LIMITE_POR_DEFECTO = 200


def _num(valor, decimales: int = 2):
    return None if valor is None else round(float(valor), decimales)


def _con_distrito(qs, campo_geom: str):
    """Anota `distrito_nombre` (distrito que contiene el centroide de `campo_geom`)."""
    distrito = Distrito.objects.filter(geom__contains=OuterRef("centro_geom")).order_by("pk")
    return qs.annotate(centro_geom=Centroid(campo_geom)).annotate(
        distrito_nombre=Subquery(distrito.values("nombre")[:1])
    )


def _filtrar_distrito(qs, distrito):
    return qs.filter(centro_geom__within=distrito.geom) if distrito else qs


def _filtrar_fechas(qs, campo: str, desde, hasta):
    limites = r.rango_datetime(r.a_fecha(desde, "desde"), r.a_fecha(hasta, "hasta"))
    return qs.filter(**{f"{campo}__{op}": valor for op, valor in limites.items()})


def _resolver_campania(valor):
    if r.vacio(valor):
        return None
    texto = str(valor).strip()
    campania = (
        Campania.objects.filter(pk=int(texto)).first()
        if texto.isdigit()
        else Campania.objects.filter(nombre__icontains=texto).order_by("-pk").first()
    )
    if campania is None:
        raise r.ParametroInvalido(f"No existe la campania '{valor}'.")
    return campania


def consultar_inspecciones(
    cluster_riesgo=None,
    distrito=None,
    tipo_predio=None,
    campania=None,
    inspector=None,
    estado_extintores=None,
    fallas_electricas=None,
    rutas_obstruidas=None,
    desde=None,
    hasta=None,
    scoring_minimo=None,
    scoring_maximo=None,
    estado="cerrada",
    solo_ultima_por_predio=None,
    orden="scoring_desc",
    limite=None,
) -> list[dict]:
    qs = ActaInspeccion.objects.all()
    if r.a_bool(solo_ultima_por_predio):
        qs = ultimas_actas_cerradas()
    elif r.normalizar(estado) in ("abierta", "abiertas"):
        qs = qs.filter(cerrada=False)
    elif r.normalizar(estado) not in ("todas", "todos"):
        qs = qs.filter(cerrada=True)

    qs = _con_distrito(qs, "predio__geom")
    qs = _filtrar_distrito(qs, r.resolver_distrito(distrito))
    qs = _filtrar_fechas(qs, "fecha_inspeccion", desde, hasta)
    if nivel := r.resolver_cluster(cluster_riesgo):
        qs = qs.filter(cluster_riesgo=nivel)
    if tipo := r.resolver_tipo_predio(tipo_predio):
        qs = qs.filter(predio__tipo_predio=tipo)
    if camp := _resolver_campania(campania):
        qs = qs.filter(campania=camp)
    if not r.vacio(inspector):
        qs = qs.filter(inspector__usuario__nombre_completo__icontains=str(inspector).strip())
    if ext := r.resolver_estado_extintor(estado_extintores):
        qs = qs.filter(estado_extintores=ext)
    if (fallas := r.a_bool(fallas_electricas)) is not None:
        qs = qs.filter(fallas_electricas=fallas)
    if (obstruidas := r.a_bool(rutas_obstruidas)) is not None:
        qs = qs.filter(rutas_evacuacion_despejadas=not obstruidas)
    if (minimo := r.a_numero(scoring_minimo, "scoring_minimo")) is not None:
        qs = qs.filter(scoring_riesgo__gte=minimo)
    if (maximo := r.a_numero(scoring_maximo, "scoring_maximo")) is not None:
        qs = qs.filter(scoring_riesgo__lte=maximo)

    ordenes = {
        "scoring_desc": ["-scoring_riesgo", "-pk"],
        "carga_fuego_desc": ["-carga_fuego", "-pk"],
        "fecha_desc": ["-fecha_inspeccion", "-pk"],
        "fecha_asc": ["fecha_inspeccion", "pk"],
    }
    qs = qs.annotate(
        n_infracciones=Count("infraccion", distinct=True),
        n_reincidencias=Count("infraccion", filter=Q(infraccion__es_reincidencia=True)),
    ).order_by(*ordenes.get(r.normalizar(orden), ordenes["scoring_desc"]))

    limite = r.a_entero(limite, "limite", defecto=LIMITE_POR_DEFECTO)
    filas = qs.values(
        "pk",
        "fecha_inspeccion",
        "predio__nombre",
        "predio__tipo_predio__nombre",
        "distrito_nombre",
        "campania__nombre",
        "inspector__usuario__nombre_completo",
        "cluster_riesgo",
        "scoring_riesgo",
        "carga_fuego",
        "estado_extintores__nombre",
        "fallas_electricas",
        "rutas_evacuacion_despejadas",
        "distancia_hidrante_m",
        "cerrada",
        "n_infracciones",
        "n_reincidencias",
    )[:limite]
    return [
        {
            "acta_id": f["pk"],
            "fecha_inspeccion": r.fecha_local(f["fecha_inspeccion"]),
            "predio": f["predio__nombre"],
            "tipo_predio": f["predio__tipo_predio__nombre"],
            "distrito": f["distrito_nombre"] or "Fuera de distritos",
            "campania": f["campania__nombre"],
            "inspector": f["inspector__usuario__nombre_completo"],
            "cluster_riesgo": f["cluster_riesgo"]
            or ("Sin clasificar" if f["cerrada"] else "Abierta"),
            "scoring_riesgo": _num(f["scoring_riesgo"]),
            "carga_fuego": _num(f["carga_fuego"]),
            "estado_extintores": f["estado_extintores__nombre"],
            "fallas_electricas": f["fallas_electricas"],
            "rutas_obstruidas": not f["rutas_evacuacion_despejadas"],
            "distancia_hidrante_m": _num(f["distancia_hidrante_m"], 1),
            "infracciones": f["n_infracciones"],
            "reincidencias": f["n_reincidencias"],
        }
        for f in filas
    ]


def consultar_predios(
    distrito=None,
    tipo_predio=None,
    cluster_riesgo=None,
    con_reincidencias=None,
    sin_inspeccion=None,
    distancia_hidrante_minima=None,
    nombre=None,
    orden="scoring_desc",
    limite=None,
) -> list[dict]:
    qs = _con_distrito(Predio.objects.all(), "geom")
    qs = _filtrar_distrito(qs, r.resolver_distrito(distrito))
    if tipo := r.resolver_tipo_predio(tipo_predio):
        qs = qs.filter(tipo_predio=tipo)
    if not r.vacio(nombre):
        qs = qs.filter(nombre__icontains=str(nombre).strip())
    base = qs.values(
        "pk", "nombre", "direccion", "tipo_predio__nombre", "area_m2", "aforo", "distrito_nombre"
    )

    ultimas = {
        a["predio_id"]: a
        for a in ultimas_actas_cerradas().values(
            "predio_id", "cluster_riesgo", "scoring_riesgo", "carga_fuego", "fecha_inspeccion"
        )
    }
    reincidencias = dict(
        Infraccion.objects.filter(es_reincidencia=True)
        .values("acta__predio_id")
        .annotate(n=Count("pk"))
        .values_list("acta__predio_id", "n")
    )
    cobertura = {
        c[0]: (c[1], c[2])
        for c in PredioHidranteCobertura.objects.filter(es_mas_cercano=True).values_list(
            "predio_id", "hidrante__codigo", "distancia_m"
        )
    }

    nivel = r.resolver_cluster(cluster_riesgo)
    distancia_min = r.a_numero(distancia_hidrante_minima, "distancia_hidrante_minima")
    filas = []
    for p in base:
        acta = ultimas.get(p["pk"], {})
        hidrante, distancia = cobertura.get(p["pk"], (None, None))
        fila = {
            "predio_id": p["pk"],
            "predio": p["nombre"],
            "tipo_predio": p["tipo_predio__nombre"],
            "distrito": p["distrito_nombre"] or "Fuera de distritos",
            "direccion": p["direccion"],
            "area_m2": _num(p["area_m2"], 1),
            "aforo": p["aforo"],
            "cluster_riesgo": acta.get("cluster_riesgo")
            or ("Sin clasificar" if acta else "Sin inspeccion"),
            "scoring_riesgo": _num(acta.get("scoring_riesgo")),
            "carga_fuego": _num(acta.get("carga_fuego")),
            "ultima_inspeccion": r.fecha_local(acta.get("fecha_inspeccion")),
            "hidrante_cercano": hidrante,
            "distancia_hidrante_m": _num(distancia, 1),
            "reincidencias": reincidencias.get(p["pk"], 0),
        }
        if nivel and fila["cluster_riesgo"] != nivel:
            continue
        if r.a_bool(con_reincidencias) and not fila["reincidencias"]:
            continue
        if r.a_bool(sin_inspeccion) and acta:
            continue
        if distancia_min is not None and (distancia is None or float(distancia) < distancia_min):
            continue
        filas.append(fila)

    claves = {
        "scoring_desc": (lambda f: -(f["scoring_riesgo"] or -1)),
        "distancia_desc": (lambda f: -(f["distancia_hidrante_m"] or 0)),
        "area_desc": (lambda f: -(f["area_m2"] or 0)),
        "nombre": (lambda f: f["predio"]),
    }
    filas.sort(key=claves.get(r.normalizar(orden), claves["scoring_desc"]))
    return filas[: r.a_entero(limite, "limite", defecto=LIMITE_POR_DEFECTO)]


def resumen_distritos(orden="criticos", solo_con_criticos=None) -> list[dict]:
    activas = Campania.objects.exclude(estado=Campania.ESTADO_CERRADA)
    filas = []
    for d in resumen_zonificacion()["distritos"]:
        conteo = d["conteo_clusters"]
        if r.a_bool(solo_con_criticos) and not conteo["Critico"]:
            continue
        filas.append(
            {
                "distrito": d["nombre"],
                "predios_registrados": d["predios_registrados"],
                "predios_inspeccionados": d["predios_inspeccionados"],
                "criticos": conteo["Critico"],
                "medios": conteo["Medio"],
                "bajos": conteo["Bajo"],
                "porcentaje_critico": d["porcentaje_critico"],
                "scoring_promedio": d["scoring_promedio"],
                "infracciones": d["infracciones"],
                "reincidencias": d["reincidencias"],
                "nivel_predominante": d["nivel_predominante"] or "Sin datos",
                "campania_activa": activas.filter(geom__intersects=d["geom"]).exists(),
            }
        )
    claves = {
        "criticos": (lambda f: (-f["criticos"], -f["porcentaje_critico"])),
        "porcentaje_critico": (lambda f: (-f["porcentaje_critico"], -f["criticos"])),
        "scoring": (lambda f: -(f["scoring_promedio"] or 0)),
        "infracciones": (lambda f: -f["infracciones"]),
        "nombre": (lambda f: f["distrito"]),
    }
    filas.sort(key=claves.get(r.normalizar(orden), claves["criticos"]))
    return filas


def consultar_infracciones(
    agrupar_por=None,
    distrito=None,
    tipo_predio=None,
    tipo_infraccion=None,
    solo_reincidencias=None,
    desde=None,
    hasta=None,
    limite=None,
) -> list[dict]:
    qs = _con_distrito(Infraccion.objects.all(), "acta__predio__geom")
    qs = _filtrar_distrito(qs, r.resolver_distrito(distrito))
    qs = _filtrar_fechas(qs, "acta__fecha_inspeccion", desde, hasta)
    if tipo := r.resolver_tipo_predio(tipo_predio):
        qs = qs.filter(acta__predio__tipo_predio=tipo)
    if inf := r.resolver_infraccion(tipo_infraccion):
        qs = qs.filter(tipo_infraccion=inf)
    if r.a_bool(solo_reincidencias):
        qs = qs.filter(es_reincidencia=True)
    limite = r.a_entero(limite, "limite", defecto=LIMITE_POR_DEFECTO)

    grupos = {
        "tipo_infraccion": "tipo_infraccion__nombre",
        "distrito": "distrito_nombre",
        "tipo_predio": "acta__predio__tipo_predio__nombre",
        "mes": "mes",
    }
    clave = r.normalizar(agrupar_por).replace(" ", "_")
    if clave in grupos:
        if clave == "mes":
            qs = qs.annotate(mes=TruncMonth("acta__fecha_inspeccion"))
        filas = (
            qs.values(grupos[clave])
            .annotate(
                total=Count("pk"),
                n_reinc=Count("pk", filter=Q(es_reincidencia=True)),
                predios=Count("acta__predio", distinct=True),
            )
            .order_by(grupos[clave] if clave == "mes" else "-total")[:limite]
        )
        return [
            {
                clave: (
                    f[grupos[clave]].strftime("%Y-%m")
                    if clave == "mes" and f[grupos[clave]]
                    else f[grupos[clave]] or "Fuera de distritos"
                ),
                "total": f["total"],
                "reincidencias": f["n_reinc"],
                "porcentaje_reincidencia": round(100 * f["n_reinc"] / f["total"], 1),
                "predios_afectados": f["predios"],
            }
            for f in filas
        ]

    filas = qs.order_by("-acta__fecha_inspeccion", "-pk").values(
        "pk",
        "acta__fecha_inspeccion",
        "acta__predio__nombre",
        "acta__predio__tipo_predio__nombre",
        "distrito_nombre",
        "tipo_infraccion__nombre",
        "tipo_infraccion__peso_severidad",
        "es_reincidencia",
        "descripcion",
        "acta__inspector__usuario__nombre_completo",
    )[:limite]
    return [
        {
            "infraccion_id": f["pk"],
            "fecha_inspeccion": r.fecha_local(f["acta__fecha_inspeccion"]),
            "predio": f["acta__predio__nombre"],
            "tipo_predio": f["acta__predio__tipo_predio__nombre"],
            "distrito": f["distrito_nombre"] or "Fuera de distritos",
            "tipo_infraccion": f["tipo_infraccion__nombre"],
            "severidad": _num(f["tipo_infraccion__peso_severidad"]),
            "es_reincidencia": f["es_reincidencia"],
            "descripcion": f["descripcion"],
            "inspector": f["acta__inspector__usuario__nombre_completo"],
        }
        for f in filas
    ]


def consultar_campanias(estado=None, desde=None, hasta=None) -> list[dict]:
    qs = Campania.objects.all().order_by("-fecha_inicio", "-pk")
    estado_norm = r.normalizar(estado).replace(" ", "_")
    if estado_norm in ("activa", "activas", "en_curso"):
        qs = qs.filter(estado=Campania.ESTADO_EN_CURSO)
    elif estado_norm in ("pendiente", "pendientes", "programada", "programadas"):
        qs = qs.filter(estado=Campania.ESTADO_PENDIENTE)
    elif estado_norm in ("cerrada", "cerradas", "finalizada", "finalizadas"):
        qs = qs.filter(estado=Campania.ESTADO_CERRADA)
    if d := r.a_fecha(desde, "desde"):
        qs = qs.filter(fecha_fin__gte=d)
    if h := r.a_fecha(hasta, "hasta"):
        qs = qs.filter(fecha_inicio__lte=h)

    actas = {
        a["campania_id"]: a
        for a in ActaInspeccion.objects.filter(cerrada=True)
        .values("campania_id")
        .annotate(
            cerradas=Count("pk"),
            criticos=Count("pk", filter=Q(cluster_riesgo="Critico")),
            scoring=Avg("scoring_riesgo"),
        )
    }
    inspectores_map = {
        cf["campania_id"]: cf["conteo"]
        for cf in CampaniaFuncionario.objects.values("campania_id").annotate(
            conteo=Count("usuario_id")
        )
    }
    filas = []
    for c in qs:
        avance = calcular_avance(c)
        a = actas.get(c.pk, {})
        filas.append(
            {
                "campania_id": c.pk,
                "campania": c.nombre,
                "estado": c.estado,
                "fecha_inicio": c.fecha_inicio.isoformat(),
                "fecha_fin": c.fecha_fin.isoformat(),
                "inspectores": inspectores_map.get(c.pk, 0),
                "total_predios": avance["total_predios"],
                "predios_inspeccionados": avance["predios_inspeccionados"],
                "avance_pct": float(avance["porcentaje"]),
                "actas_cerradas": a.get("cerradas", 0),
                "criticos": a.get("criticos", 0),
                "scoring_promedio": _num(a.get("scoring")),
            }
        )
    return filas


def consultar_hidrantes(estado_operativo=None, distrito=None, tipo_acople=None) -> list[dict]:
    qs = _con_distrito(Hidrante.objects.all(), "geom")
    qs = _filtrar_distrito(qs, r.resolver_distrito(distrito))
    estado = r.normalizar(estado_operativo)
    if estado.startswith("activ") or estado.startswith("operativ"):
        qs = qs.filter(estado_operativo=Hidrante.ESTADO_ACTIVO)
    elif estado and ("fuera" in estado or "inoper" in estado or "servicio" in estado):
        qs = qs.filter(estado_operativo=Hidrante.ESTADO_FUERA_DE_SERVICIO)
    if not r.vacio(tipo_acople):
        qs = qs.filter(tipo_acople__nombre__iexact=str(tipo_acople).strip())

    cobertura = {
        c["hidrante_id"]: c
        for c in PredioHidranteCobertura.objects.filter(es_mas_cercano=True)
        .values("hidrante_id")
        .annotate(n=Count("predio_id"), prom=Avg("distancia_m"), maxima=Max("distancia_m"))
    }
    filas = []
    for h in qs.order_by("codigo").values(
        "pk",
        "codigo",
        "estado_operativo",
        "presion_nominal",
        "tipo_acople__nombre",
        "distrito_nombre",
    ):
        c = cobertura.get(h["pk"], {})
        filas.append(
            {
                "hidrante_id": h["pk"],
                "codigo": h["codigo"],
                "estado_operativo": h["estado_operativo"],
                "presion_nominal": _num(h["presion_nominal"]),
                "tipo_acople": h["tipo_acople__nombre"],
                "distrito": h["distrito_nombre"] or "Fuera de distritos",
                "predios_cubiertos": c.get("n", 0),
                "distancia_promedio_m": _num(c.get("prom"), 1),
                "distancia_maxima_m": _num(c.get("maxima"), 1),
            }
        )
    return filas


def resumen_tipos_predio(distrito=None) -> list[dict]:
    distrito_obj = r.resolver_distrito(distrito)
    predios = _filtrar_distrito(_con_distrito(Predio.objects.all(), "geom"), distrito_obj)
    registrados = dict(
        predios.values("tipo_predio__nombre")
        .annotate(n=Count("pk"))
        .values_list("tipo_predio__nombre", "n")
    )
    actas = _filtrar_distrito(_con_distrito(ultimas_actas_cerradas(), "predio__geom"), distrito_obj)
    filas = []
    for a in actas.values("predio__tipo_predio__nombre").annotate(
        n=Count("pk"),
        criticos=Count("pk", filter=Q(cluster_riesgo="Critico")),
        medios=Count("pk", filter=Q(cluster_riesgo="Medio")),
        bajos=Count("pk", filter=Q(cluster_riesgo="Bajo")),
        carga=Avg("carga_fuego"),
        scoring=Avg("scoring_riesgo"),
    ):
        filas.append(
            {
                "tipo_predio": a["predio__tipo_predio__nombre"],
                "predios_registrados": registrados.get(a["predio__tipo_predio__nombre"], 0),
                "predios_inspeccionados": a["n"],
                "criticos": a["criticos"],
                "medios": a["medios"],
                "bajos": a["bajos"],
                "porcentaje_critico": round(100 * a["criticos"] / a["n"], 1) if a["n"] else 0.0,
                "carga_fuego_promedio": _num(a["carga"]),
                "scoring_promedio": _num(a["scoring"]),
            }
        )
    filas.sort(key=lambda f: (-f["porcentaje_critico"], f["tipo_predio"]))
    return filas


def consultar_inspectores(desde=None, hasta=None) -> list[dict]:
    qs = _filtrar_fechas(
        ActaInspeccion.objects.filter(cerrada=True), "fecha_inspeccion", desde, hasta
    )
    # Las infracciones se cuentan aparte: unirlas aqui duplicaria filas y sesgaria el promedio.
    infracciones = dict(
        Infraccion.objects.filter(acta__in=qs)
        .values("acta__inspector_id")
        .annotate(n=Count("pk"))
        .values_list("acta__inspector_id", "n")
    )
    filas = (
        qs.values("inspector_id", "inspector__usuario__nombre_completo")
        .annotate(
            actas=Count("pk"),
            predios=Count("predio", distinct=True),
            criticas=Count("pk", filter=Q(cluster_riesgo="Critico")),
            scoring=Avg("scoring_riesgo"),
            ultima=Max("fecha_inspeccion"),
        )
        .order_by("-actas")
    )
    return [
        {
            "inspector": f["inspector__usuario__nombre_completo"],
            "actas_cerradas": f["actas"],
            "predios_inspeccionados": f["predios"],
            "actas_criticas": f["criticas"],
            "scoring_promedio": _num(f["scoring"]),
            "infracciones": infracciones.get(f["inspector_id"], 0),
            "ultima_inspeccion": r.fecha_local(f["ultima"]),
        }
        for f in filas
    ]
