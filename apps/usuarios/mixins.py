from .services import registrar_bitacora

# Mixin reutilizable para que los ViewSets de CUALQUIER app registren
# automaticamente sus acciones criticas en BitacoraAuditoria (crear campania,
# cerrar acta, generar/descargar reporte, etc. - ver PLANBACKEND.md Fase 1).


class BitacoraAuditoriaMixin:
    """Registra en BitacoraAuditoria las acciones marcadas como criticas.

    El ViewSet que use este mixin debe definir `bitacora_acciones`, un dict
    {nombre_de_action: "descripcion de la accion"}, ej.:

        class CampaniaViewSet(BitacoraAuditoriaMixin, viewsets.ModelViewSet):
            bitacora_acciones = {"create": "Crear campania"}
    """

    bitacora_acciones: dict[str, str] = {}

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        accion = self.bitacora_acciones.get(getattr(self, "action", None))
        usuario = getattr(request, "user", None)
        if accion and response.status_code < 400 and usuario and usuario.is_authenticated:
            registrar_bitacora(
                usuario=usuario,
                accion=accion,
                entidad_afectada=self.get_queryset().model.__name__,
            )
        return response
