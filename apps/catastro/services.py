from decimal import Decimal

from django.contrib.gis.db.models.functions import Distance
from django.db import transaction

from .models import Hidrante, Predio, PredioHidranteCobertura


@transaction.atomic
def calcular_cobertura_hidrantes(predio: Predio) -> list[PredioHidranteCobertura]:
    """Calcula la distancia esferica exacta (en metros) desde el poligono del predio
    a todos los hidrantes con estado_operativo='activo' (RF-6).

    Puebla la tabla N:M `predio_hidrante_cobertura` y marca con `es_mas_cercano=True`
    al hidrante con menor distancia. Si no existen hidrantes activos, limpia
    los registros de cobertura previos del predio y retorna lista vacia.
    """
    PredioHidranteCobertura.objects.filter(predio=predio).delete()

    hidrantes_activos = (
        Hidrante.objects.filter(estado_operativo=Hidrante.ESTADO_ACTIVO)
        .annotate(distancia=Distance("geom", predio.geom))
        .order_by("distancia")
    )

    coberturas = []
    for idx, hidrante in enumerate(hidrantes_activos):
        distancia_m = round(Decimal(str(hidrante.distancia.m)), 2)
        coberturas.append(
            PredioHidranteCobertura(
                predio=predio,
                hidrante=hidrante,
                distancia_m=distancia_m,
                es_mas_cercano=(idx == 0),
            )
        )

    if coberturas:
        PredioHidranteCobertura.objects.bulk_create(coberturas)

    return coberturas


def obtener_hidrante_mas_cercano(predio: Predio) -> PredioHidranteCobertura | None:
    """Retorna el registro de cobertura del hidrante activo mas cercano al predio.
    Si la cobertura aun no ha sido calculada, la genera bajo demanda."""
    cobertura = (
        PredioHidranteCobertura.objects.filter(
            predio=predio,
            es_mas_cercano=True,
            hidrante__estado_operativo=Hidrante.ESTADO_ACTIVO,
        )
        .select_related("hidrante", "hidrante__tipo_acople")
        .first()
    )
    if cobertura:
        return cobertura

    # Generar calculo si no existia
    calcular_cobertura_hidrantes(predio)
    return (
        PredioHidranteCobertura.objects.filter(
            predio=predio,
            es_mas_cercano=True,
            hidrante__estado_operativo=Hidrante.ESTADO_ACTIVO,
        )
        .select_related("hidrante", "hidrante__tipo_acople")
        .first()
    )


@transaction.atomic
def crear_predio(
    *,
    nombre: str,
    direccion: str | None = None,
    tipo_predio,
    aforo: int | None = None,
    area_m2: Decimal | float | None = None,
    atributos_extra: dict | None = None,
    geom,
    registrado_por,
    calcular_cobertura: bool = True,
) -> Predio:
    """Crea un nuevo predio y opcionalmente calcula su cobertura de hidrantes inicial."""
    predio = Predio.objects.create(
        nombre=nombre,
        direccion=direccion,
        tipo_predio=tipo_predio,
        aforo=aforo,
        area_m2=area_m2,
        atributos_extra=atributos_extra,
        geom=geom,
        registrado_por=registrado_por,
    )
    if calcular_cobertura:
        calcular_cobertura_hidrantes(predio)
    return predio


@transaction.atomic
def actualizar_predio(predio: Predio, datos: dict, recalcular_cobertura: bool = True) -> Predio:
    """Actualiza atributos del predio y recalcula cobertura si cambio la geometria."""
    geom_cambio = "geom" in datos and datos["geom"] != predio.geom
    for campo, valor in datos.items():
        setattr(predio, campo, valor)
    predio.save()

    if recalcular_cobertura and geom_cambio:
        calcular_cobertura_hidrantes(predio)

    return predio


def crear_hidrante(
    *,
    codigo: str | None = None,
    estado_operativo: str = Hidrante.ESTADO_ACTIVO,
    presion_nominal: Decimal | float | None = None,
    tipo_acople,
    geom,
    registrado_por,
) -> Hidrante:
    """Crea un nuevo hidrante con ubicacion puntual."""
    return Hidrante.objects.create(
        codigo=codigo,
        estado_operativo=estado_operativo,
        presion_nominal=presion_nominal,
        tipo_acople=tipo_acople,
        geom=geom,
        registrado_por=registrado_por,
    )


def actualizar_hidrante(hidrante: Hidrante, datos: dict) -> Hidrante:
    """Actualiza los atributos de un hidrante."""
    for campo, valor in datos.items():
        setattr(hidrante, campo, valor)
    hidrante.save()
    return hidrante
