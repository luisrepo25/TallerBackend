# Capa de negocio de la zonificacion (RF-18, RF-19): mapa de calor, resumen por distrito y
# zonas sugeridas para nuevas campanias. Solo LECTURA de lo ya calculado (scoring y cluster
# guardados en las actas); nada se recalcula aqui.
#
# "Situacion actual" = la ultima acta cerrada de cada predio (una reinspeccion reemplaza a
# la anterior para el mapa). El distrito de un predio se obtiene por interseccion espacial de
# su centroide, asi cada predio cae en un solo distrito aunque cruce un limite.

import json

from django.contrib.gis.db.models.functions import Centroid
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.db import transaction
from django.db.models import Avg, Count, OuterRef, Q, Subquery

from apps.campanias.models import Campania
from apps.catastro.models import Predio
from apps.fiscalizacion.models import ActaInspeccion, Infraccion

from .models import Distrito

# De menor a mayor severidad: sirve para desempatar el nivel predominante de un distrito.
NIVELES = ["Bajo", "Medio", "Critico"]


class AnaliticaError(Exception):
    """Datos invalidos (la vista responde 400)."""

    def __init__(self, mensaje, **extra):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.extra = extra


def ultimas_actas_cerradas():
    """Una acta por predio: la ultima cerrada (con scoring). Su cluster puede ser nulo si el
    clustering aun no se ejecuto despues de cerrarla."""
    ids = (
        ActaInspeccion.objects.filter(cerrada=True, scoring_riesgo__isnull=False)
        .order_by("predio_id", "-fecha_inspeccion", "-pk")
        .distinct("predio_id")
        .values("pk")
    )
    return ActaInspeccion.objects.filter(pk__in=ids)


def _distrito_de(campo_centroide):
    """Subconsulta: id del distrito que contiene el centroide (el de menor id si se solapan)."""
    return Subquery(
        Distrito.objects.filter(geom__contains=OuterRef(campo_centroide))
        .order_by("pk")
        .values("pk")[:1]
    )


def mapa_calor(*, cluster=None, campania_id=None) -> list[dict]:
    """RF-18. Un punto por predio inspeccionado: centroide + scoring (intensidad 0 a 1)."""
    actas = ultimas_actas_cerradas().annotate(centro=Centroid("predio__geom"))
    if cluster:
        actas = actas.filter(cluster_riesgo=cluster)
    if campania_id:
        actas = actas.filter(campania_id=campania_id)

    filas = actas.order_by("predio_id").values_list(
        "predio_id", "predio__nombre", "centro", "scoring_riesgo", "cluster_riesgo"
    )
    return [
        {
            "predio_id": predio_id,
            "predio_nombre": nombre,
            "lat": centro.y,
            "lng": centro.x,
            "scoring_riesgo": scoring,
            "cluster_riesgo": cluster_riesgo,
            "intensidad": round(float(scoring) / 100, 4),
        }
        for predio_id, nombre, centro, scoring, cluster_riesgo in filas
    ]


def _nivel_predominante(conteos: dict[str, int]) -> str | None:
    """Nivel con mas predios; en empate gana el mas severo. None si nada esta clasificado."""
    if not any(conteos.values()):
        return None
    return max(NIVELES, key=lambda nivel: (conteos[nivel], NIVELES.index(nivel)))


def _agregados_actas() -> dict:
    actas = (
        ultimas_actas_cerradas()
        .annotate(centro=Centroid("predio__geom"))
        .annotate(distrito_id=_distrito_de("centro"))
    )
    filas = actas.values("distrito_id").annotate(
        inspeccionados=Count("pk"),
        bajo=Count("pk", filter=Q(cluster_riesgo="Bajo")),
        medio=Count("pk", filter=Q(cluster_riesgo="Medio")),
        critico=Count("pk", filter=Q(cluster_riesgo="Critico")),
        scoring_promedio=Avg("scoring_riesgo"),
    )
    return {fila["distrito_id"]: fila for fila in filas}


def _agregados_infracciones() -> dict:
    filas = (
        Infraccion.objects.filter(acta__in=ultimas_actas_cerradas())
        .annotate(centro=Centroid("acta__predio__geom"))
        .annotate(distrito_id=_distrito_de("centro"))
        .values("distrito_id")
        .annotate(total=Count("pk"), reincidencias=Count("pk", filter=Q(es_reincidencia=True)))
    )
    return {fila["distrito_id"]: fila for fila in filas}


def _predios_por_distrito() -> dict:
    filas = (
        Predio.objects.annotate(centro=Centroid("geom"))
        .annotate(distrito_id=_distrito_de("centro"))
        .values("distrito_id")
        .annotate(total=Count("pk"))
    )
    return {fila["distrito_id"]: fila["total"] for fila in filas}


def resumen_distritos() -> dict:
    """RF-18. Resumen de riesgo por distrito (con su geometria, para pintar la capa
    semaforica) y la cantidad de predios inspeccionados que no caen en ningun distrito."""
    actas = _agregados_actas()
    infracciones = _agregados_infracciones()
    predios = _predios_por_distrito()
    vacio = {"inspeccionados": 0, "bajo": 0, "medio": 0, "critico": 0, "scoring_promedio": None}

    distritos = []
    for distrito in Distrito.objects.order_by("nombre"):
        a = actas.get(distrito.pk, vacio)
        i = infracciones.get(distrito.pk, {"total": 0, "reincidencias": 0})
        conteos = {"Bajo": a["bajo"], "Medio": a["medio"], "Critico": a["critico"]}
        clasificados = sum(conteos.values())
        distritos.append(
            {
                "id": distrito.pk,
                "nombre": distrito.nombre,
                "geom": distrito.geom,
                "predios_registrados": predios.get(distrito.pk, 0),
                "predios_inspeccionados": a["inspeccionados"],
                "conteo_clusters": conteos,
                "nivel_predominante": _nivel_predominante(conteos),
                "porcentaje_critico": (
                    round(100 * a["critico"] / clasificados, 1) if clasificados else 0.0
                ),
                "scoring_promedio": (
                    None
                    if a["scoring_promedio"] is None
                    else round(float(a["scoring_promedio"]), 2)
                ),
                "infracciones": i["total"],
                "reincidencias": i["reincidencias"],
            }
        )
    return {
        "distritos": distritos,
        "inspeccionados_sin_distrito": actas.get(None, vacio)["inspeccionados"],
    }


def zonas_sugeridas(*, limite=5) -> list[dict]:
    """RF-19. Distritos con predios en riesgo Critico, para proponer como nuevas campanias.

    Orden: primero los que NO tienen una campania activa (pendiente o en curso) tocando su
    territorio; luego mas predios Criticos y mayor porcentaje de Criticos. No hay umbral
    inventado: basta 1 predio Critico, y `limite` acota la lista."""
    candidatos = [d for d in resumen_distritos()["distritos"] if d["conteo_clusters"]["Critico"]]
    for d in candidatos:
        d["campanias_activas"] = list(
            Campania.objects.exclude(estado=Campania.ESTADO_CERRADA)
            .filter(geom__intersects=d["geom"])
            .order_by("nombre")
            .values_list("nombre", flat=True)
        )
    candidatos.sort(
        key=lambda d: (
            bool(d["campanias_activas"]),
            -d["conteo_clusters"]["Critico"],
            -d["porcentaje_critico"],
            d["nombre"],
        )
    )
    return candidatos[:limite]


def _nombre_de(feature: dict, campo_nombre: str) -> str:
    return str((feature.get("properties") or {}).get(campo_nombre) or "").strip()


def _poligonos_de(geom) -> list[Polygon]:
    """Poligonos que contiene una geometria (make_valid puede devolver una coleccion
    mezclada con lineas o puntos sueltos, que se descartan)."""
    if isinstance(geom, Polygon):
        return [geom]
    if geom.geom_type in ("MultiPolygon", "GeometryCollection"):
        return [poligono for parte in geom for poligono in _poligonos_de(parte)]
    return []


def _a_multipoligono(
    feature: dict, campo_nombre: str, *, reparar: bool
) -> tuple[str, MultiPolygon, bool]:
    """Devuelve (nombre, geometria, fue_reparada)."""
    nombre = _nombre_de(feature, campo_nombre)
    if not nombre:
        raise AnaliticaError(f"Un distrito no tiene la propiedad '{campo_nombre}'.")
    try:
        geom = GEOSGeometry(json.dumps(feature["geometry"]), srid=4326)
    except Exception as exc:
        raise AnaliticaError(f"'{nombre}': geometria ilegible.") from exc
    if isinstance(geom, Polygon):
        geom = MultiPolygon(geom, srid=4326)
    if not isinstance(geom, MultiPolygon):
        raise AnaliticaError(f"'{nombre}': debe ser Polygon o MultiPolygon, no {geom.geom_type}.")

    reparada = False
    if not geom.valid:
        if not reparar:
            raise AnaliticaError(
                f"'{nombre}': el poligono es invalido ({geom.valid_reason}). "
                "Usa reparar=True (--reparar) para corregirlo automaticamente."
            )
        poligonos = _poligonos_de(geom.make_valid())
        if not poligonos:
            raise AnaliticaError(f"'{nombre}': no se pudo reparar el poligono.")
        geom, reparada = MultiPolygon(*poligonos, srid=4326), True
    return nombre, geom, reparada


@transaction.atomic
def importar_distritos(geojson: dict, *, campo_nombre="nombre", reparar=False, excluir=()) -> dict:
    """Carga o actualiza distritos desde un GeoJSON (FeatureCollection o Feature). Todo o
    nada: si un distrito es invalido no se guarda ninguno. Idempotente por nombre.

    `excluir`: nombres de elementos que no son distritos y se omiten (ej. el limite del
    municipio). `reparar`: corrige con GEOS los poligonos invalidos (ej. un contorno que se
    cruza a si mismo) en vez de rechazarlos; los nombres reparados vuelven en `reparados`."""
    features = geojson.get("features") if geojson.get("type") == "FeatureCollection" else [geojson]
    omitidos = {e.strip().lower() for e in excluir}
    features = [f for f in features or [] if _nombre_de(f, campo_nombre).lower() not in omitidos]
    if not features:
        raise AnaliticaError("El archivo no contiene distritos.")

    leidos = [_a_multipoligono(f, campo_nombre, reparar=reparar) for f in features]
    nombres = [nombre for nombre, _, _ in leidos]
    if len(set(nombres)) != len(nombres):
        raise AnaliticaError("Hay distritos con el mismo nombre en el archivo.")

    creados = 0
    for nombre, geom, _ in leidos:
        _, creado = Distrito.objects.update_or_create(nombre=nombre, defaults={"geom": geom})
        creados += creado
    return {
        "creados": creados,
        "actualizados": len(leidos) - creados,
        "reparados": [nombre for nombre, _, reparada in leidos if reparada],
    }
