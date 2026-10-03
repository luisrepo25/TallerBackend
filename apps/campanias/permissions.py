from rest_framework.permissions import SAFE_METHODS, BasePermission


class CampaniaPermission(BasePermission):
    """Escritura exclusiva del Administrador. Lectura para Administrador, Oficial de Mando
    e Inspector Tecnico (este ultimo solo ve sus campanias, ver `campanias_visibles`).
    El avance de campania es informacion de gestion: solo Administrador y Oficial de Mando.
    """

    def has_permission(self, request, view):
        usuario = request.user
        if not (usuario and usuario.is_authenticated):
            return False

        es_admin = hasattr(usuario, "administrador")
        if request.method not in SAFE_METHODS:
            return es_admin

        es_oficial = hasattr(usuario, "oficialmando")
        if getattr(view, "action", None) == "avance":
            return es_admin or es_oficial
        return es_admin or es_oficial or hasattr(usuario, "inspectortecnico")
