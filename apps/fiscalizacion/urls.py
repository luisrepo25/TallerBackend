from rest_framework.routers import DefaultRouter

from .views import (
    ActaInspeccionViewSet,
    CatalogoEstadoExtintorViewSet,
    CatalogoInfraccionViewSet,
    CatalogoMaterialCombustibleViewSet,
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

urlpatterns = router.urls
