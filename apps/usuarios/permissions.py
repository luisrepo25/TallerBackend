from rest_framework.permissions import BasePermission

# Permisos basados en pertenencia a un subtipo funcional (administradores/
# inspectores_tecnicos/oficiales_mando), NUNCA en el campo `rol` (ver CLAUDE.md:
# subtipos son independientes del rol RBAC y pueden solaparse).


class IsAdministrador(BasePermission):
    def has_permission(self, request, view):
        usuario = request.user
        return bool(usuario and usuario.is_authenticated and hasattr(usuario, "administrador"))


class IsInspectorTecnico(BasePermission):
    def has_permission(self, request, view):
        usuario = request.user
        return bool(usuario and usuario.is_authenticated and hasattr(usuario, "inspectortecnico"))


class IsOficialMando(BasePermission):
    def has_permission(self, request, view):
        usuario = request.user
        return bool(usuario and usuario.is_authenticated and hasattr(usuario, "oficialmando"))
