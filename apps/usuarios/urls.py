from rest_framework.routers import DefaultRouter

from .views import PermisoViewSet, RolViewSet, UsuarioViewSet

app_name = "usuarios"

router = DefaultRouter()
router.register("roles", RolViewSet, basename="rol")
router.register("permisos", PermisoViewSet, basename="permiso")
router.register("usuarios", UsuarioViewSet, basename="usuario")

urlpatterns = router.urls
