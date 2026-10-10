import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import models, transaction
from django.db.models import F
from django.utils import timezone

from apps.campanias.models import Campania, CampaniaFuncionario
from apps.catastro.services import obtener_hidrante_mas_cercano
from apps.common import cloudinary_storage
from apps.usuarios.services import registrar_bitacora

from .models import (
    ActaInspeccion,
    CatalogoMaterialCombustible,
    EvidenciaFotografica,
    Infraccion,
    MaterialRegistrado,
    SolicitudMaterial,
)

logger = logging.getLogger(__name__)

# ============================================================
# Constantes de scoring de riesgo (especificación PLANBACKEND.md)
# ============================================================
PESO_CARGA_FUEGO = Decimal("0.30")
PESO_ESTADO_EXTINTORES = Decimal("0.20")
PESO_FALLAS_ELECTRICAS = Decimal("0.20")
PESO_RUTAS_EVACUACION = Decimal("0.20")
PESO_DISTANCIA_HIDRANTE = Decimal("0.10")

# Topes de normalización
Q_MAX = Decimal("1000.00")  # Carga de fuego máxima para escala (MJ/m2)
D_MAX = Decimal("500.00")  # Distancia a hidrante máxima para escala (metros)


class FiscalizacionError(Exception):
    """Regla de negocio violada por datos invalidos (la vista responde 400)."""

    def __init__(self, mensaje, **extra):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.extra = extra


class FiscalizacionConflicto(FiscalizacionError):
    """Operacion incompatible con el estado actual (la vista responde 409)."""


def calcular_carga_fuego(acta: ActaInspeccion) -> Decimal:
    """RF-23. Calcula la carga de fuego ponderada segun norma boliviana NB 58005:
    Q_s = ( sum(P_i * H_i * C_i) * R_a ) / A

    Donde:
      P_i: peso_kg del material combustible registrado
      H_i: poder_calorifico_mj_kg tabulado en catalogo_materiales_combustibles
      C_i: coeficiente_peligrosidad tabulado en catalogo_materiales_combustibles
      R_a: riesgo_activacion del tipo de predio (catalogo_tipos_predio)
      A:   area_m2 del predio inspeccionado

    Se calcula en Django mediante agregaciones del ORM (aggregate / F()),
    sin traer filas a un loop en Python ni recurrir a triggers SQL (ver CLAUDE.md).
    """
    resultado = (
        MaterialRegistrado.objects.filter(acta=acta)
        .annotate(
            energia=F("peso_kg")
            * F("material__poder_calorifico_mj_kg")
            * F("material__coeficiente_peligrosidad")
        )
        .aggregate(total_energia=models.Sum("energia"))
    )

    total_energia = resultado["total_energia"] or Decimal("0.00")

    predio = acta.predio
    tipo_predio = predio.tipo_predio
    riesgo_activacion = Decimal(str(tipo_predio.riesgo_activacion or "1.00"))

    area = Decimal(str(predio.area_m2 or "1.00"))
    if area <= Decimal("0.00"):
        area = Decimal("1.00")

    carga = (total_energia * riesgo_activacion) / area
    return carga.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calcular_scoring_riesgo(acta: ActaInspeccion) -> Decimal:
    """RF-14. Combina las 5 variables de inspeccion en un puntaje continuo de 0 a 100:
    scoring = 100 * sum(peso * valor_normalizado)

    Variables normalizadas de 0 (sin riesgo) a 1 (riesgo maximo):
      1. Carga de fuego: min(Q / Q_max, 1.0)                      -> peso 0.30
      2. Estado extintores: Vigente=0.0 / Vencido=0.5 / No posee=1.0 -> peso 0.20
      3. Fallas electricas: No=0.0 / Si=1.0                      -> peso 0.20
      4. Rutas evacuacion:  Despejadas=0.0 / Obstruidas=1.0      -> peso 0.20
      5. Distancia hidrante: min(d / d_max, 1.0); sin hidrantes=1.0 -> peso 0.10
    """
    # 1. Carga de fuego
    carga = acta.carga_fuego or Decimal("0.00")
    if carga < Decimal("0.00"):
        carga = Decimal("0.00")
    v_carga = min(carga / Q_MAX, Decimal("1.00"))

    # 2. Estado extintores
    estado_nombre = (acta.estado_extintores.nombre if acta.estado_extintores else "").lower()
    if "vigente" in estado_nombre:
        v_extintores = Decimal("0.00")
    elif "vencido" in estado_nombre:
        v_extintores = Decimal("0.50")
    else:
        # 'No posee' u otros estados deficientes
        v_extintores = Decimal("1.00")

    # 3. Fallas electricas
    v_fallas = Decimal("1.00") if acta.fallas_electricas else Decimal("0.00")

    # 4. Rutas de evacuacion
    v_rutas = Decimal("0.00") if acta.rutas_evacuacion_despejadas else Decimal("1.00")

    # 5. Distancia a hidrante
    if acta.distancia_hidrante_m is None:
        v_distancia = Decimal("1.00")
    else:
        dist_m = Decimal(str(acta.distancia_hidrante_m))
        if dist_m < Decimal("0.00"):
            dist_m = Decimal("0.00")
        v_distancia = min(dist_m / D_MAX, Decimal("1.00"))

    scoring = Decimal("100.00") * (
        (PESO_CARGA_FUEGO * v_carga)
        + (PESO_ESTADO_EXTINTORES * v_extintores)
        + (PESO_FALLAS_ELECTRICAS * v_fallas)
        + (PESO_RUTAS_EVACUACION * v_rutas)
        + (PESO_DISTANCIA_HIDRANTE * v_distancia)
    )

    return scoring.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@transaction.atomic
def registrar_acta(
    *,
    predio,
    campania,
    inspector,
    estado_extintores,
    fallas_electricas: bool = False,
    rutas_evacuacion_despejadas: bool = True,
    uuid_local=None,
    distancia_hidrante_m=None,
    usuario_autenticado=None,
) -> ActaInspeccion:
    """RF-12. Registra una nueva acta de inspeccion en campo.

    Reglas de negocio validadas:
      1. La campania no debe estar cerrada (409 Conflicto).
      2. El inspector debe estar asignado a la campania en campania_funcionarios.
      3. El predio debe pertenecer a la zona geografica de la campania (ST_Intersects).
      4. Si no se provee distancia_hidrante_m, se toma la fotografia historica
         del hidrante activo mas cercano mediante el servicio de catastro.
    """
    # 1. Validar campania no cerrada
    if campania.estado == Campania.ESTADO_CERRADA:
        raise FiscalizacionConflicto("No se pueden registrar actas en una campania cerrada.")

    # 2. Validar que el inspector este asignado a la campania
    asignado = CampaniaFuncionario.objects.filter(campania=campania, usuario=inspector).exists()
    if not asignado:
        raise FiscalizacionError("El inspector tecnico no esta asignado a esta campania.")

    # 3. Validar interseccion espacial Predio <-> Campania
    if campania.geom is not None and not predio.geom.intersects(campania.geom):
        raise FiscalizacionError(
            "El predio no pertenece al poligono territorial delimitado para la campania."
        )

    # 4. Fotografia historica de distancia a hidrante activo
    if distancia_hidrante_m is None:
        cobertura = obtener_hidrante_mas_cercano(predio)
        if cobertura:
            distancia_hidrante_m = cobertura.distancia_m

    acta = ActaInspeccion.objects.create(
        uuid_local=uuid_local,
        predio=predio,
        campania=campania,
        inspector=inspector,
        estado_extintores=estado_extintores,
        fallas_electricas=fallas_electricas,
        rutas_evacuacion_despejadas=rutas_evacuacion_despejadas,
        distancia_hidrante_m=distancia_hidrante_m,
        cerrada=False,
    )

    if usuario_autenticado:
        registrar_bitacora(
            usuario=usuario_autenticado,
            accion="Registrar acta de inspeccion",
            entidad_afectada="ActaInspeccion",
        )

    return acta


@transaction.atomic
def registrar_materiales(acta: ActaInspeccion, materiales: list[dict]) -> list[MaterialRegistrado]:
    """RF-22. Registra o actualiza materiales combustibles para un acta de inspeccion.
    El inspector solo ingresa tipo_material_id y peso_kg."""
    if acta.cerrada:
        raise FiscalizacionConflicto(
            "No se pueden registrar materiales en una acta que ya esta cerrada."
        )

    creados = []
    for item in materiales:
        material_id = item["material_id"]
        peso_kg = Decimal(str(item["peso_kg"]))
        if peso_kg < Decimal("0.00"):
            raise FiscalizacionError("El peso en kg no puede ser negativo.")

        material = CatalogoMaterialCombustible.objects.get(pk=material_id)
        registro = MaterialRegistrado.objects.create(
            acta=acta,
            material=material,
            peso_kg=peso_kg,
        )
        creados.append(registro)

    return creados


@transaction.atomic
def registrar_infraccion(
    acta: ActaInspeccion,
    tipo_infraccion,
    descripcion: str = "",
    usuario_autenticado=None,
) -> Infraccion:
    """RF-16. Registra una infraccion detectada en el acta.

    Deteccion automatica de reincidencia:
      Verifica si en actas anteriores del mismo predio ya se registro
      una infraccion con el mismo tipo_infraccion_id.
    """
    if acta.cerrada:
        raise FiscalizacionConflicto("No se pueden registrar infracciones en una acta cerrada.")

    es_reincidencia = (
        Infraccion.objects.filter(acta__predio=acta.predio, tipo_infraccion=tipo_infraccion)
        .exclude(acta=acta)
        .exists()
    )

    infraccion = Infraccion.objects.create(
        acta=acta,
        tipo_infraccion=tipo_infraccion,
        descripcion=descripcion,
        es_reincidencia=es_reincidencia,
    )

    if usuario_autenticado:
        registrar_bitacora(
            usuario=usuario_autenticado,
            accion="Registrar infraccion",
            entidad_afectada="Infraccion",
        )

    return infraccion


@transaction.atomic
def subir_evidencia(
    acta: ActaInspeccion,
    url_imagen: str,
    descripcion_infraccion: str = "",
    usuario_autenticado=None,
) -> EvidenciaFotografica:
    """RF-13. Registra una evidencia fotografica vinculada a un acta de inspeccion."""
    if acta.cerrada:
        raise FiscalizacionConflicto("No se pueden agregar evidencias a una acta cerrada.")

    if not url_imagen or not url_imagen.strip():
        raise FiscalizacionError("La URL de la imagen es obligatoria.")

    evidencia = EvidenciaFotografica.objects.create(
        acta=acta,
        url_imagen=url_imagen.strip(),
        descripcion_infraccion=descripcion_infraccion,
    )

    if usuario_autenticado:
        registrar_bitacora(
            usuario=usuario_autenticado,
            accion="Subir evidencia fotografica",
            entidad_afectada="EvidenciaFotografica",
        )

    return evidencia


TIPOS_IMAGEN_PERMITIDOS = {"image/jpeg", "image/png", "image/webp"}
TAMANO_MAX_IMAGEN = 10 * 1024 * 1024  # 10 MB


def subir_imagen_evidencia(archivo) -> str:
    """RF-13. Valida la foto y la guarda en Cloudinary. Devuelve su URL.

    No toca ningun acta: la app movil sube las fotos antes de sincronizar el acta (que en
    campo puede no existir todavia en el servidor) y luego envia las URLs dentro del acta."""
    if archivo is None:
        raise FiscalizacionError("Falta la imagen (campo 'imagen').")
    if archivo.content_type not in TIPOS_IMAGEN_PERMITIDOS:
        raise FiscalizacionError("La evidencia debe ser una imagen JPG, PNG o WEBP.")
    if archivo.size > TAMANO_MAX_IMAGEN:
        raise FiscalizacionError("La imagen supera el maximo de 10 MB.")
    try:
        return cloudinary_storage.subir_imagen(
            archivo.read(), archivo.name or "evidencia.jpg", archivo.content_type
        )
    except cloudinary_storage.CloudinaryError as exc:
        raise FiscalizacionError(str(exc)) from exc


@transaction.atomic
def solicitar_material(
    *, inspector, nombre, descripcion="", peso_kg_estimado=None, uuid_local=None
) -> SolicitudMaterial:
    """El Inspector pide dar de alta un material combustible que no esta en el catalogo.
    Idempotente por `uuid_local` (el celular puede reenviar la misma solicitud)."""
    nombre = (nombre or "").strip()
    if not nombre:
        raise FiscalizacionError("El nombre del material es obligatorio.")

    if uuid_local is not None:
        existente = SolicitudMaterial.objects.filter(uuid_local=uuid_local).first()
        if existente is not None:
            if existente.solicitante_id != inspector.pk:
                raise FiscalizacionError("Ese identificador ya fue usado por otro inspector.")
            return existente

    if CatalogoMaterialCombustible.objects.filter(nombre__iexact=nombre).exists():
        raise FiscalizacionConflicto(f"'{nombre}' ya existe en el catalogo de materiales.")
    if SolicitudMaterial.objects.filter(
        nombre__iexact=nombre, estado=SolicitudMaterial.ESTADO_PENDIENTE
    ).exists():
        raise FiscalizacionConflicto(f"Ya hay una solicitud pendiente para '{nombre}'.")

    return SolicitudMaterial.objects.create(
        uuid_local=uuid_local,
        nombre=nombre,
        descripcion=(descripcion or "").strip() or None,
        peso_kg_estimado=peso_kg_estimado,
        solicitante=inspector,
    )


def _solicitud_pendiente(solicitud_id):
    solicitud = SolicitudMaterial.objects.select_for_update().get(pk=solicitud_id)
    if solicitud.estado != SolicitudMaterial.ESTADO_PENDIENTE:
        raise FiscalizacionConflicto(f"La solicitud ya fue {solicitud.estado}.")
    return solicitud


@transaction.atomic
def aprobar_solicitud_material(
    solicitud_id, *, administrador, poder_calorifico_mj_kg, coeficiente_peligrosidad, usuario
) -> SolicitudMaterial:
    """El Administrador da de alta el material con sus Hi y Ci tabulados (NB 58005)."""
    solicitud = _solicitud_pendiente(solicitud_id)
    if CatalogoMaterialCombustible.objects.filter(nombre__iexact=solicitud.nombre).exists():
        raise FiscalizacionConflicto(f"'{solicitud.nombre}' ya existe en el catalogo.")

    material = CatalogoMaterialCombustible.objects.create(
        nombre=solicitud.nombre,
        poder_calorifico_mj_kg=poder_calorifico_mj_kg,
        coeficiente_peligrosidad=coeficiente_peligrosidad,
    )
    solicitud.estado = SolicitudMaterial.ESTADO_APROBADA
    solicitud.material = material
    solicitud.resuelta_por = administrador
    solicitud.fecha_resolucion = timezone.now()
    solicitud.save()
    registrar_bitacora(
        usuario=usuario,
        accion="Aprobar solicitud de material combustible",
        entidad_afectada="SolicitudMaterial",
    )
    return solicitud


@transaction.atomic
def rechazar_solicitud_material(
    solicitud_id, *, administrador, motivo, usuario
) -> SolicitudMaterial:
    motivo = (motivo or "").strip()
    if not motivo:
        raise FiscalizacionError("Indica el motivo del rechazo.")
    solicitud = _solicitud_pendiente(solicitud_id)
    solicitud.estado = SolicitudMaterial.ESTADO_RECHAZADA
    solicitud.motivo_rechazo = motivo
    solicitud.resuelta_por = administrador
    solicitud.fecha_resolucion = timezone.now()
    solicitud.save()
    registrar_bitacora(
        usuario=usuario,
        accion="Rechazar solicitud de material combustible",
        entidad_afectada="SolicitudMaterial",
    )
    return solicitud


@transaction.atomic
def cerrar_acta(acta: ActaInspeccion, usuario_autenticado=None) -> ActaInspeccion:
    """RF-14. Cierra formalmente un acta de inspeccion.

    Orquesta las reglas de negocio de cierre:
      1. Valida que el acta no este cerrada previamente (409).
      2. Bloquea la fila del acta con select_for_update().
      3. Ejecuta calcular_carga_fuego(acta) y la persiste.
      4. Ejecuta calcular_scoring_riesgo(acta) y lo persiste.
      5. Marca cerrada=True y fecha_cierre=now().
      6. Registra en bitacora de auditoria el snapshot del rol.
    """
    acta_db = (
        ActaInspeccion.objects.select_for_update()
        .select_related(
            "predio",
            "predio__tipo_predio",
            "estado_extintores",
            "campania",
            "inspector",
        )
        .get(pk=acta.pk)
    )

    if acta_db.cerrada:
        raise FiscalizacionConflicto("El acta de inspeccion ya se encuentra cerrada.")

    # 1. Calcular carga de fuego
    carga = calcular_carga_fuego(acta_db)
    acta_db.carga_fuego = carga

    # 2. Calcular scoring de riesgo
    scoring = calcular_scoring_riesgo(acta_db)
    acta_db.scoring_riesgo = scoring

    # 3. Marcar cierre
    now = timezone.now()
    acta_db.cerrada = True
    acta_db.fecha_cierre = now
    acta_db.save(
        update_fields=[
            "carga_fuego",
            "scoring_riesgo",
            "cerrada",
            "fecha_cierre",
        ]
    )

    # Mantener el objeto original en memoria sincronizado
    acta.carga_fuego = carga
    acta.scoring_riesgo = scoring
    acta.cerrada = True
    acta.fecha_cierre = now

    if usuario_autenticado:
        registrar_bitacora(
            usuario=usuario_autenticado,
            accion="Cerrar acta de inspeccion",
            entidad_afectada="ActaInspeccion",
        )

    return acta_db


def consultar_historial(
    *,
    predio_id=None,
    campania_id=None,
    inspector_id=None,
    solo_cerradas: bool = False,
):
    """RF-15. Consulta el historial de inspecciones con filtros opcionales por predio,
    campania o inspector, precargando materiales, infracciones y evidencias."""
    qs = (
        ActaInspeccion.objects.select_related(
            "predio",
            "predio__tipo_predio",
            "campania",
            "inspector__usuario",
            "estado_extintores",
        )
        .prefetch_related(
            "materialregistrado_set__material",
            "infraccion_set__tipo_infraccion",
            "evidenciafotografica_set",
        )
        .order_by("-fecha_inspeccion")
    )

    if predio_id:
        qs = qs.filter(predio_id=predio_id)
    if campania_id:
        qs = qs.filter(campania_id=campania_id)
    if inspector_id:
        qs = qs.filter(inspector_id=inspector_id)
    if solo_cerradas:
        qs = qs.filter(cerrada=True)

    return qs
