from rest_framework.permissions import SAFE_METHODS, BasePermission


class ConsultaAnaliticaPermission(BasePermission):
    """Consultar la analitica (mapa de calor, distritos, zonas sugeridas, historial del
    clustering) es para Administrador y Oficial de Mando. El Inspector no entra."""

    def has_permission(self, request, view):
        usuario = request.user
        if not (usuario and usuario.is_authenticated):
            return False
        return hasattr(usuario, "administrador") or hasattr(usuario, "oficialmando")


class ClusteringPermission(ConsultaAnaliticaPermission):
    """Ejecutar el clustering es exclusivo del Administrador; consultar, como la analitica."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return super().has_permission(request, view)
        usuario = request.user
        return bool(usuario and usuario.is_authenticated and hasattr(usuario, "administrador"))
