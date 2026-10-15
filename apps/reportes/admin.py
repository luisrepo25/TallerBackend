from django.contrib import admin

from .models import ReporteGenerado


@admin.register(ReporteGenerado)
class ReporteGeneradoAdmin(admin.ModelAdmin):
    list_display = ("id", "tipo", "formato", "generado_por", "fecha_generacion")
    list_filter = ("tipo", "formato", "fecha_generacion")
    search_fields = ("generado_por__email", "generado_por__nombre_completo")
    readonly_fields = ("tipo", "formato", "generado_por", "fecha_generacion", "parametros")
