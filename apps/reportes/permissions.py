from rest_framework.permissions import BasePermission


class ReportesPermission(BasePermission):
    """Generar y consultar reportes es exclusivo de Administrador y Oficial de Mando.
    El Inspector Técnico puro no tiene acceso a reportes en la web."""

    def has_permission(self, request, view):
        usuario = request.user
        if not (usuario and usuario.is_authenticated):
            return False
        return hasattr(usuario, "administrador") or hasattr(usuario, "oficialmando")
