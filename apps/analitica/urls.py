from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ClusteringViewSet, DistritosView, MapaCalorView, ZonasSugeridasView

app_name = "analitica"

router = DefaultRouter()
router.register("clustering", ClusteringViewSet, basename="clustering")

urlpatterns = [
    path("mapa-calor/", MapaCalorView.as_view(), name="mapa-calor"),
    path("distritos/", DistritosView.as_view(), name="distritos"),
    path("zonas-sugeridas/", ZonasSugeridasView.as_view(), name="zonas-sugeridas"),
    *router.urls,
]
