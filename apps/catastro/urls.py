from rest_framework.routers import DefaultRouter

from .views import (
    CatalogoTipoAcopleViewSet,
    CatalogoTipoPredioViewSet,
    HidranteViewSet,
    PredioViewSet,
)

app_name = "catastro"

router = DefaultRouter()
router.register("tipos-predio", CatalogoTipoPredioViewSet, basename="tipo-predio")
router.register("tipos-acople", CatalogoTipoAcopleViewSet, basename="tipo-acople")
router.register("predios", PredioViewSet, basename="predio")
router.register("hidrantes", HidranteViewSet, basename="hidrante")

urlpatterns = router.urls
