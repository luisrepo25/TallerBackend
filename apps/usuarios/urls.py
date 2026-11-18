from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BitacoraAccionesView,
    BitacoraListView,
    DispositivosView,
    PerfilView,
    PermisoViewSet,
    RolViewSet,
    UsuarioViewSet,
)

app_name = "usuarios"

router = DefaultRouter()
router.register("roles", RolViewSet, basename="rol")
router.register("permisos", PermisoViewSet, basename="permiso")
router.register("usuarios", UsuarioViewSet, basename="usuario")

urlpatterns = [
    path("me/", PerfilView.as_view(), name="perfil"),
    path("dispositivos/", DispositivosView.as_view(), name="dispositivos"),
    path("bitacora/", BitacoraListView.as_view(), name="bitacora"),
    path("bitacora/acciones/", BitacoraAccionesView.as_view(), name="bitacora-acciones"),
] + router.urls
