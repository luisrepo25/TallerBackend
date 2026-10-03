from rest_framework.routers import DefaultRouter

from .views import CampaniaViewSet

app_name = "campanias"

router = DefaultRouter()
router.register("campanias", CampaniaViewSet, basename="campania")

urlpatterns = router.urls
