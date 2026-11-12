from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AgenteReporteView,
    DetalleReporteDinamicoView,
    ExportarReporteDinamicoView,
    GenerarReporteView,
    ReporteGeneradoViewSet,
)

app_name = "reportes"

router = DefaultRouter()
router.register("reportes", ReporteGeneradoViewSet, basename="reporte")

urlpatterns = [
    path("generar/", GenerarReporteView.as_view(), name="generar"),
    path("agente/", AgenteReporteView.as_view(), name="agente"),
    path("agente/<uuid:id>/", DetalleReporteDinamicoView.as_view(), name="agente_detalle"),
    path(
        "agente/<uuid:id>/exportar/", ExportarReporteDinamicoView.as_view(), name="agente_exportar"
    ),
] + router.urls
