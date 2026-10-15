from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import GenerarReporteView, ReporteGeneradoViewSet

app_name = "reportes"

router = DefaultRouter()
router.register("reportes", ReporteGeneradoViewSet, basename="reporte")

urlpatterns = [
    path("generar/", GenerarReporteView.as_view(), name="generar"),
] + router.urls
