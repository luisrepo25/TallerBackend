from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.usuarios.mixins import BitacoraAuditoriaMixin

from .permissions import CampaniaPermission
from .serializers import (
    AsignarInspectoresSerializer,
    AvanceCampaniaSerializer,
    CampaniaCreateUpdateSerializer,
    CampaniaSerializer,
    CerrarCampaniaSerializer,
    CierreCampaniaResponseSerializer,
    InspectorAsignadoSerializer,
    ZonaCampaniaSerializer,
)
from .services import (
    CampaniaConflicto,
    CampaniaError,
    actualizar_zona,
    asignar_inspectores,
    calcular_avance,
    campanias_visibles,
    cerrar_campania,
    quitar_inspector,
)

# Vistas/ViewSets de esta app (capa de presentacion).
# Delegan la logica de negocio a services.py, nunca al ORM directo.


class CampaniaViewSet(
    BitacoraAuditoriaMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Una campania con actas no se elimina: se cierra (ver accion `cerrar`)."""

    permission_classes = [CampaniaPermission]
    # El cierre se audita dentro del servicio (distingue cierre normal de forzado).
    bitacora_acciones = {
        "create": "Crear campania",
        "update": "Actualizar campania",
        "partial_update": "Actualizar campania",
        "zona": "Actualizar zona de campania",
        "asignar_inspectores": "Asignar inspectores a campania",
        "quitar_inspector": "Quitar inspector de campania",
    }

    def get_queryset(self):
        return campanias_visibles(self.request.user)

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return CampaniaCreateUpdateSerializer
        return CampaniaSerializer

    def handle_exception(self, exc):
        if isinstance(exc, CampaniaError):
            codigo = (
                status.HTTP_409_CONFLICT
                if isinstance(exc, CampaniaConflicto)
                else status.HTTP_400_BAD_REQUEST
            )
            return self.finalize_response(
                self.request,
                Response({"detail": exc.mensaje, **exc.extra}, status=codigo),
                *self.args,
                **self.kwargs,
            )
        return super().handle_exception(exc)

    @extend_schema(request=ZonaCampaniaSerializer, responses={200: CampaniaSerializer})
    @action(detail=True, methods=["put"], url_path="zona")
    def zona(self, request, pk=None):
        """RF-8. Delimita o reemplaza el poligono de la zona de la campania."""
        serializer = ZonaCampaniaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campania = actualizar_zona(self.get_object(), serializer.validated_data["geom"])
        return Response(CampaniaSerializer(campania).data)

    @extend_schema(responses={200: InspectorAsignadoSerializer(many=True)})
    @action(detail=True, methods=["get"], url_path="inspectores")
    def inspectores(self, request, pk=None):
        """Inspectores asignados a la campania."""
        campania = self.get_object()
        asignados = campania.campaniafuncionario_set.all()
        return Response(InspectorAsignadoSerializer(asignados, many=True).data)

    @extend_schema(request=AsignarInspectoresSerializer, responses={200: CampaniaSerializer})
    @action(detail=True, methods=["post"], url_path="asignar-inspectores")
    def asignar_inspectores(self, request, pk=None):
        """RF-9. Asigna inspectores (idempotente). La primera asignacion pone la campania
        'pendiente' en 'en_curso'."""
        serializer = AsignarInspectoresSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campania = asignar_inspectores(self.get_object(), serializer.validated_data["usuarios_ids"])
        return Response(CampaniaSerializer(self.get_queryset().get(pk=campania.pk)).data)

    @extend_schema(responses={204: None})
    @action(
        detail=True,
        methods=["delete"],
        url_path=r"inspectores/(?P<usuario_id>\d+)",
    )
    def quitar_inspector(self, request, pk=None, usuario_id=None):
        """RF-9. Quita a un inspector que aun no registro actas en la campania."""
        quitar_inspector(self.get_object(), int(usuario_id))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses={200: AvanceCampaniaSerializer})
    @action(detail=True, methods=["get"], url_path="avance")
    def avance(self, request, pk=None):
        """RF-10. Avance = predios dentro del poligono con acta cerrada / total de predios."""
        return Response(AvanceCampaniaSerializer(calcular_avance(self.get_object())).data)

    @extend_schema(
        request=CerrarCampaniaSerializer, responses={200: CierreCampaniaResponseSerializer}
    )
    @action(detail=True, methods=["post"], url_path="cerrar")
    def cerrar(self, request, pk=None):
        """RF-11. Cierra la campania. Responde 409 si hay inspecciones pendientes, salvo
        que se envie `forzar=true`."""
        serializer = CerrarCampaniaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resultado = cerrar_campania(
            self.get_object(), usuario=request.user, forzar=serializer.validated_data["forzar"]
        )
        return Response(CierreCampaniaResponseSerializer(resultado).data)
