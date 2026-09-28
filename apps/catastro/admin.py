from django.contrib import admin

from .models import (
    CatalogoTipoAcople,
    CatalogoTipoPredio,
    Hidrante,
    Predio,
)


@admin.register(CatalogoTipoPredio)
class CatalogoTipoPredioAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "categoria_riesgo_base", "riesgo_activacion")
    search_fields = ("nombre",)


@admin.register(CatalogoTipoAcople)
class CatalogoTipoAcopleAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre")
    search_fields = ("nombre",)


@admin.register(Predio)
class PredioAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "tipo_predio", "aforo", "area_m2", "fecha_registro")
    list_filter = ("tipo_predio",)
    search_fields = ("nombre", "direccion")


@admin.register(Hidrante)
class HidranteAdmin(admin.ModelAdmin):
    list_display = ("id", "codigo", "estado_operativo", "tipo_acople", "presion_nominal")
    list_filter = ("estado_operativo", "tipo_acople")
    search_fields = ("codigo",)
