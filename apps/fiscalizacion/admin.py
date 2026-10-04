from django.contrib import admin

from .models import (
    ActaInspeccion,
    CatalogoEstadoExtintor,
    CatalogoInfraccion,
    CatalogoMaterialCombustible,
    EvidenciaFotografica,
    Infraccion,
    MaterialRegistrado,
)


class MaterialRegistradoInline(admin.TabularInline):
    model = MaterialRegistrado
    extra = 0


class InfraccionInline(admin.TabularInline):
    model = Infraccion
    extra = 0


class EvidenciaFotograficaInline(admin.TabularInline):
    model = EvidenciaFotografica
    extra = 0


@admin.register(CatalogoEstadoExtintor)
class CatalogoEstadoExtintorAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre")
    search_fields = ("nombre",)


@admin.register(CatalogoInfraccion)
class CatalogoInfraccionAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "peso_severidad")
    search_fields = ("nombre",)


@admin.register(CatalogoMaterialCombustible)
class CatalogoMaterialCombustibleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "nombre",
        "poder_calorifico_mj_kg",
        "coeficiente_peligrosidad",
    )
    search_fields = ("nombre",)


@admin.register(ActaInspeccion)
class ActaInspeccionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "predio",
        "campania",
        "inspector",
        "fecha_inspeccion",
        "carga_fuego",
        "scoring_riesgo",
        "cluster_riesgo",
        "cerrada",
    )
    list_filter = ("cerrada", "campania", "cluster_riesgo")
    search_fields = ("predio__nombre", "inspector__usuario__nombre_completo")
    readonly_fields = (
        "carga_fuego",
        "scoring_riesgo",
        "fecha_inspeccion",
        "fecha_cierre",
    )
    inlines = [
        MaterialRegistradoInline,
        InfraccionInline,
        EvidenciaFotograficaInline,
    ]


@admin.register(MaterialRegistrado)
class MaterialRegistradoAdmin(admin.ModelAdmin):
    list_display = ("id", "acta", "material", "peso_kg")
    list_filter = ("material",)


@admin.register(Infraccion)
class InfraccionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "acta",
        "tipo_infraccion",
        "es_reincidencia",
        "fecha_registro",
    )
    list_filter = ("tipo_infraccion", "es_reincidencia")


@admin.register(EvidenciaFotografica)
class EvidenciaFotograficaAdmin(admin.ModelAdmin):
    list_display = ("id", "acta", "url_imagen", "fecha_captura")
