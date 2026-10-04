from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsInspectorTecnicoOrReadOnly(BasePermission):
    """Permite lectura a cualquier usuario autenticado (Oficial de Mando,
    Administrador e Inspector Técnico).

    Las acciones de creación, registro de materiales, evidencias, infracciones
    y cierre de acta están reservadas para Inspectores Técnicos o Administradores.
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(
            hasattr(request.user, "inspectortecnico") or hasattr(request.user, "administrador")
        )


class IsAdministradorOrReadOnly(BasePermission):
    """Permite lectura a cualquier usuario autenticado, pero edición
    exclusiva al subtipo Administrador (para catálogos base).
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(hasattr(request.user, "administrador"))
