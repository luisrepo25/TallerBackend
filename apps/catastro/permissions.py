from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsCatastroEditorOrReadOnly(BasePermission):
    """Permite metodos seguros (GET, HEAD, OPTIONS) a cualquier usuario
    autenticado (incluyendo Inspectores Tecnicos para consulta en campo).

    Modificaciones (POST, PUT, PATCH, DELETE) se reservan para usuarios
    con subtipo Administrador u Oficial de Mando (quienes operan la plataforma
    web de gestion catastral segun CLAUDE.md).
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(hasattr(request.user, "administrador") or hasattr(request.user, "oficialmando"))


class IsAdministradorOrReadOnly(BasePermission):
    """Permite lectura a cualquier usuario autenticado, pero edicion
    exclusiva al subtipo Administrador (para catalogos base).
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(hasattr(request.user, "administrador"))
