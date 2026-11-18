from django.urls import path
from rest_framework.routers import DefaultRouter

from .sync_views import SincronizarActasView
from .views import (
    ActaInspeccionViewSet,
    CatalogoEstadoExtintorViewSet,
    CatalogoInfraccionViewSet,
    CatalogoMaterialCombustibleViewSet,
    MisActasView,
    SolicitudMaterialViewSet,
    SubirImagenEvidenciaView,
)

app_name = "fiscalizacion"

router = DefaultRouter()
router.register("actas", ActaInspeccionViewSet, basename="acta")
router.register(
    "estados-extintor",
    CatalogoEstadoExtintorViewSet,
    basename="estado-extintor",
)
router.register(
    "infracciones-catalogo",
    CatalogoInfraccionViewSet,
    basename="infraccion-catalogo",
)
router.register(
    "materiales-combustibles",
    CatalogoMaterialCombustibleViewSet,
    basename="material-combustible",
)
router.register(
    "solicitudes-material",
    SolicitudMaterialViewSet,
    basename="solicitud-material",
)

urlpatterns = [
    # La app movil envia aqui las actas hechas sin conexion (un lote por llamada)
    path("sync/actas/", SincronizarActasView.as_view(), name="sync-actas"),
    # Historial del propio inspector: lo ya inspeccionado, para recuperarlo en un telefono nuevo
    path("mis-actas/", MisActasView.as_view(), name="mis-actas"),
    # ...y sube antes cada foto de evidencia (devuelve la URL que va dentro del acta)
    path("evidencias/subir/", SubirImagenEvidenciaView.as_view(), name="subir-evidencia"),
] + router.urls
