# Datos de demostracion: predios reales de OpenStreetMap (Santa Cruz de la Sierra) con
# inspecciones SIMULADAS, para probar el mapa de calor, las zonas sugeridas y el clustering
# sin esperar a tener inspecciones reales.
#
# Todo se crea con los servicios reales (catastro, campanias, fiscalizacion), asi la carga de
# fuego y el scoring salen del calculo oficial. Y todo queda marcado para poder borrarlo:
#   predios    -> atributos_extra {"demo": true}
#   campania   -> nombre que empieza con "[DEMO]"
#   hidrantes  -> codigo "DEMO-OSM-<id>"
#   inspector  -> email demo.inspector@uubr.invalid (sin contrasena: no puede iniciar sesion)
# Las actas son inspecciones ficticias: NO deben usarse para decisiones reales ni presentarse
# como tales. Borrar con `manage.py cargar_datos_demo --borrar` antes de la puesta en produccion.

import json
import random
from datetime import timedelta

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, Point, Polygon
from django.db.models import Q
from django.utils import timezone

from apps.campanias.models import Campania
from apps.campanias.services import asignar_inspectores, crear_campania
from apps.catastro.models import (
    CatalogoTipoAcople,
    CatalogoTipoPredio,
    Hidrante,
    Predio,
)
from apps.catastro.services import crear_hidrante, crear_predio
from apps.fiscalizacion import services as fiscalizacion
from apps.fiscalizacion.models import (
    ActaInspeccion,
    CatalogoEstadoExtintor,
    CatalogoInfraccion,
    CatalogoMaterialCombustible,
)
from apps.usuarios.models import Administrador, Rol, Usuario
from apps.usuarios.services import crear_usuario

from . import demo_simulacion as simulacion

PREFIJO_CAMPANIA = "[DEMO]"
PREFIJO_HIDRANTE = "DEMO-OSM-"
EMAIL_INSPECTOR = "demo.inspector@uubr.invalid"
PROBABILIDAD_REINSPECCION = 0.15


class DemoError(Exception):
    pass


def _leer(archivo: str) -> list[dict]:
    ruta = settings.BASE_DIR / "datos" / archivo
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)["features"]


def _area_m2(geom) -> float:
    """Area en m2 (el sistema no la calcula solo: se proyecta a UTM 20S, metros)."""
    return round(geom.transform(32720, clone=True).area, 2)


def _seleccionar(features: list[dict], por_tipo: int, rng: random.Random) -> list[dict]:
    por_categoria: dict[str, list[dict]] = {}
    for f in features:
        por_categoria.setdefault(f["properties"]["tipo_predio"], []).append(f)
    elegidos = []
    for tipo in sorted(por_categoria):
        elegidos += rng.sample(por_categoria[tipo], min(por_tipo, len(por_categoria[tipo])))
    return elegidos


def _cargar_hidrantes(admin: Usuario) -> int:
    acople = CatalogoTipoAcople.objects.get(nombre="Storz")
    existentes = set(
        Hidrante.objects.filter(codigo__startswith=PREFIJO_HIDRANTE).values_list(
            "codigo", flat=True
        )
    )
    creados = 0
    for f in _leer("hidrantes_osm_santacruz.geojson"):
        codigo = f"{PREFIJO_HIDRANTE}{f['properties']['osm_id']}"
        if codigo not in existentes:
            lon, lat = f["geometry"]["coordinates"]
            crear_hidrante(
                codigo=codigo,
                tipo_acople=acople,
                geom=Point(lon, lat, srid=4326),
                registrado_por=admin,
            )
            creados += 1
    return creados


def _zona(predios: list[Predio]) -> Polygon:
    """Rectangulo que contiene a todos los predios (con un pequeno margen)."""
    extents = [p.geom.extent for p in predios]
    margen = 0.002
    zona = Polygon.from_bbox(
        (
            min(e[0] for e in extents) - margen,
            min(e[1] for e in extents) - margen,
            max(e[2] for e in extents) + margen,
            max(e[3] for e in extents) + margen,
        )
    )
    zona.srid = 4326
    return zona


def _inspeccionar(predio, campania, inspector, sim, catalogos) -> ActaInspeccion:
    """Una inspeccion completa por el camino real: registrar, materiales, infracciones, cerrar."""
    acta = fiscalizacion.registrar_acta(
        predio=predio,
        campania=campania,
        inspector=inspector,
        estado_extintores=catalogos["estados"][sim.extintores],
        fallas_electricas=sim.fallas_electricas,
        rutas_evacuacion_despejadas=sim.rutas_despejadas,
    )
    fiscalizacion.registrar_materiales(
        acta,
        [{"material_id": catalogos["materiales"][n].pk, "peso_kg": kg} for n, kg in sim.materiales],
    )
    for nombre in sim.infracciones:
        fiscalizacion.registrar_infraccion(acta, catalogos["infracciones"][nombre])
    return fiscalizacion.cerrar_acta(acta)


def cargar(*, por_tipo=15, semilla=42, log=lambda mensaje: None) -> dict:
    if Campania.objects.filter(nombre__startswith=PREFIJO_CAMPANIA).exists():
        raise DemoError("Ya hay datos de demostracion. Ejecuta primero con --borrar.")
    admin = Administrador.objects.select_related("usuario").first()
    if admin is None:
        raise DemoError("No hay ningun Administrador en el sistema.")
    rng = random.Random(semilla)

    log(f"Hidrantes de OpenStreetMap: {_cargar_hidrantes(admin.usuario)} creados")
    inspector = crear_usuario(
        nombre_completo="[DEMO] Inspector de prueba",
        email=EMAIL_INSPECTOR,
        password=None,
        rol=Rol.objects.get(nombre="Inspector Tecnico"),
        subtipo="inspector_tecnico",
    )

    tipos = {t.nombre: t for t in CatalogoTipoPredio.objects.all()}
    seleccion = _seleccionar(_leer("predios_osm_santacruz.geojson"), por_tipo, rng)
    predios = []
    for f in seleccion:
        p, geom = f["properties"], GEOSGeometry(json.dumps(f["geometry"]), srid=4326)
        predios.append(
            (
                crear_predio(
                    nombre=p["nombre"],
                    tipo_predio=tipos[p["tipo_predio"]],
                    area_m2=_area_m2(geom),
                    atributos_extra={
                        "demo": True,
                        "fuente": "OpenStreetMap",
                        "osm_id": p["osm_id"],
                    },
                    geom=geom,
                    registrado_por=admin.usuario,
                ),
                p["tipo_predio"],
            )
        )
    log(f"Predios creados: {len(predios)}")

    hoy = timezone.localdate()
    campania = crear_campania(
        nombre=f"{PREFIJO_CAMPANIA} Campana de prueba (OpenStreetMap)",
        fecha_inicio=hoy,
        fecha_fin=hoy + timedelta(days=30),
        creado_por=admin,
        geom=_zona([p for p, _ in predios]),
    )
    asignar_inspectores(campania, [inspector.pk])

    catalogos = {
        "estados": {e.nombre: e for e in CatalogoEstadoExtintor.objects.all()},
        "materiales": {m.nombre: m for m in CatalogoMaterialCombustible.objects.all()},
        "infracciones": {i.nombre: i for i in CatalogoInfraccion.objects.all()},
    }
    nombres = {k: sorted(v) for k, v in catalogos.items()}
    actas = 0
    for predio, tipo in predios:
        riesgo = simulacion.riesgo_latente(tipo, rng)
        niveles = [riesgo]
        if rng.random() < PROBABILIDAD_REINSPECCION:
            niveles.append(simulacion.riesgo_en_reinspeccion(riesgo, rng))
        for nivel in niveles:
            sim = simulacion.simular_inspeccion(
                nivel, float(predio.area_m2), nombres["materiales"], nombres["infracciones"], rng
            )
            _inspeccionar(predio, campania, inspector.inspectortecnico, sim, catalogos)
            actas += 1
        if actas % 10 == 0:
            log(f"  {actas} actas cerradas...")

    # La campana de demostracion se deja CERRADA: una activa cubriria toda la ciudad y haria que
    # las zonas sugeridas marquen todos los distritos como "ya tienen campana". Se cierra sin
    # pasar por cerrar_campania para no dejar una entrada de bitacora a nombre de un usuario real.
    Campania.objects.filter(pk=campania.pk).update(estado=Campania.ESTADO_CERRADA)
    return {"predios": len(predios), "actas": actas, "campania_id": campania.pk}


def borrar() -> dict:
    campanias = Campania.objects.filter(nombre__startswith=PREFIJO_CAMPANIA)
    actas = ActaInspeccion.objects.filter(
        Q(campania__in=campanias) | Q(predio__atributos_extra__demo=True)
    )
    resultado = {"actas": actas.count()}
    actas.delete()  # materiales, infracciones y evidencias se borran en cascada
    resultado["campanias"] = campanias.count()
    campanias.delete()
    predios = Predio.objects.filter(atributos_extra__demo=True)
    resultado["predios"] = predios.count()
    predios.delete()  # la cobertura de hidrantes se borra en cascada
    resultado["hidrantes"] = Hidrante.objects.filter(codigo__startswith=PREFIJO_HIDRANTE).count()
    Hidrante.objects.filter(codigo__startswith=PREFIJO_HIDRANTE).delete()
    Usuario.objects.filter(email=EMAIL_INSPECTOR).delete()
    return resultado
