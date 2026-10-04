from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.usuarios.mixins import BitacoraAuditoriaMixin

from .models import (
    ActaInspeccion,
    CatalogoEstadoExtintor,
    CatalogoInfraccion,
    CatalogoMaterialCombustible,
)
from .permissions import IsAdministradorOrReadOnly, IsInspectorTecnicoOrReadOnly
from .serializers import (
    ActaInspeccionCreateSerializer,
    ActaInspeccionDetailSerializer,
    ActaInspeccionListSerializer,
    CatalogoEstadoExtintorSerializer,
    CatalogoInfraccionSerializer,
    CatalogoMaterialCombustibleSerializer,
    EvidenciaFotograficaSerializer,
    InfraccionCreateSerializer,
    InfraccionSerializer,
    MaterialItemInputSerializer,
    MaterialRegistradoSerializer,
)
from .services import (
    FiscalizacionConflicto,
    FiscalizacionError,
    cerrar_acta,
    consultar_historial,
    registrar_infraccion,
    registrar_materiales,
    subir_evidencia,
)


class CatalogoEstadoExtintorViewSet(viewsets.ModelViewSet):
    queryset = CatalogoEstadoExtintor.objects.all().order_by("id")
    serializer_class = CatalogoEstadoExtintorSerializer
    permission_classes = [IsAdministradorOrReadOnly]


class CatalogoInfraccionViewSet(viewsets.ModelViewSet):
    queryset = CatalogoInfraccion.objects.all().order_by("id")
    serializer_class = CatalogoInfraccionSerializer
    permission_classes = [IsAdministradorOrReadOnly]


class CatalogoMaterialCombustibleViewSet(viewsets.ModelViewSet):
    queryset = CatalogoMaterialCombustible.objects.all().order_by("id")
    serializer_class = CatalogoMaterialCombustibleSerializer
    permission_classes = [IsAdministradorOrReadOnly]


class ActaInspeccionViewSet(BitacoraAuditoriaMixin, viewsets.ModelViewSet):
    queryset = (
        ActaInspeccion.objects.select_related(
            "predio", "campania", "inspector__usuario", "estado_extintores"
        )
        .all()
        .order_by("-fecha_inspeccion")
    )
    permission_classes = [IsInspectorTecnicoOrReadOnly]
    bitacora_acciones = {
        "create": "Registrar acta de inspeccion",
        "cerrar": "Cerrar acta de inspeccion",
        "materiales": "Registrar materiales combustibles",
        "infracciones": "Registrar infraccion",
        "evidencias": "Subir evidencia fotografica",
    }

    def get_serializer_class(self):
        if self.action == "create":
            return ActaInspeccionCreateSerializer
        if self.action in ["retrieve", "cerrar"]:
            return ActaInspeccionDetailSerializer
        return ActaInspeccionListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        predio_id = self.request.query_params.get("predio_id")
        campania_id = self.request.query_params.get("campania_id")
        cerrada = self.request.query_params.get("cerrada")

        if predio_id:
            qs = qs.filter(predio_id=predio_id)
        if campania_id:
            qs = qs.filter(campania_id=campania_id)
        if cerrada is not None:
            es_cerrada = cerrada.lower() in ["true", "1"]
            qs = qs.filter(cerrada=es_cerrada)

        # Si el usuario es Inspector (sin admin ni oficial), filtrar solo sus actas asignadas
        user = self.request.user
        if (
            hasattr(user, "inspectortecnico")
            and not hasattr(user, "administrador")
            and not hasattr(user, "oficialmando")
        ):
            qs = qs.filter(inspector_id=user.pk)

        return qs

    def handle_exception(self, exc):
        if isinstance(exc, FiscalizacionError):
            codigo = (
                status.HTTP_409_CONFLICT
                if isinstance(exc, FiscalizacionConflicto)
                else status.HTTP_400_BAD_REQUEST
            )
            return self.finalize_response(
                self.request,
                Response(
                    {"detail": exc.mensaje, **getattr(exc, "extra", {})},
                    status=codigo,
                ),
                *self.args,
                **self.kwargs,
            )
        return super().handle_exception(exc)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            instance = serializer.save()
            detail_serializer = ActaInspeccionDetailSerializer(instance)
            return Response(detail_serializer.data, status=status.HTTP_201_CREATED)
        except FiscalizacionConflicto as exc:
            return Response({"detail": exc.mensaje}, status=status.HTTP_409_CONFLICT)
        except FiscalizacionError as exc:
            return Response({"detail": exc.mensaje}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=MaterialItemInputSerializer(many=True),
        responses={200: MaterialRegistradoSerializer(many=True)},
    )
    @action(detail=True, methods=["post"], url_path="materiales")
    def materiales(self, request, pk=None):
        """RF-22. Registra o agrega materiales combustibles a una acta abierta."""
        acta = self.get_object()
        serializer = MaterialItemInputSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        try:
            creados = registrar_materiales(acta, serializer.validated_data)
            out_serializer = MaterialRegistradoSerializer(creados, many=True)
            return Response(out_serializer.data, status=status.HTTP_200_OK)
        except FiscalizacionConflicto as exc:
            return Response({"detail": exc.mensaje}, status=status.HTTP_409_CONFLICT)
        except FiscalizacionError as exc:
            return Response({"detail": exc.mensaje}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=InfraccionCreateSerializer,
        responses={201: InfraccionSerializer},
    )
    @action(detail=True, methods=["post"], url_path="infracciones")
    def infracciones(self, request, pk=None):
        """RF-16. Registra una infraccion detectada con verificacion automatica de reincidencia."""
        acta = self.get_object()
        serializer = InfraccionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tipo_infraccion_id = serializer.validated_data["tipo_infraccion_id"]
        descripcion = serializer.validated_data.get("descripcion", "")

        try:
            tipo_infraccion = CatalogoInfraccion.objects.get(pk=tipo_infraccion_id)
            infraccion = registrar_infraccion(
                acta=acta,
                tipo_infraccion=tipo_infraccion,
                descripcion=descripcion,
                usuario_autenticado=request.user,
            )
            out_serializer = InfraccionSerializer(infraccion)
            return Response(out_serializer.data, status=status.HTTP_201_CREATED)
        except CatalogoInfraccion.DoesNotExist:
            return Response(
                {"detail": "El tipo de infraccion especificado no existe."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except FiscalizacionConflicto as exc:
            return Response({"detail": exc.mensaje}, status=status.HTTP_409_CONFLICT)
        except FiscalizacionError as exc:
            return Response({"detail": exc.mensaje}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        request=EvidenciaFotograficaSerializer,
        responses={201: EvidenciaFotograficaSerializer},
    )
    @action(detail=True, methods=["post"], url_path="evidencias")
    def evidencias(self, request, pk=None):
        """RF-13. Sube y asocia una evidencia fotografica al acta de inspeccion."""
        acta = self.get_object()
        url_imagen = request.data.get("url_imagen")
        descripcion = request.data.get("descripcion_infraccion", "")

        try:
            evidencia = subir_evidencia(
                acta=acta,
                url_imagen=url_imagen,
                descripcion_infraccion=descripcion,
                usuario_autenticado=request.user,
            )
            out_serializer = EvidenciaFotograficaSerializer(evidencia)
            return Response(out_serializer.data, status=status.HTTP_201_CREATED)
        except FiscalizacionConflicto as exc:
            return Response({"detail": exc.mensaje}, status=status.HTTP_409_CONFLICT)
        except FiscalizacionError as exc:
            return Response({"detail": exc.mensaje}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(responses={200: ActaInspeccionDetailSerializer})
    @action(detail=True, methods=["post"], url_path="cerrar")
    def cerrar(self, request, pk=None):
        """RF-14. Cierra formalmente el acta y ejecuta el calculo automatizado de
        carga de fuego (NB 58005) y scoring de riesgo."""
        acta = self.get_object()
        try:
            acta_cerrada = cerrar_acta(acta, usuario_autenticado=request.user)
            out_serializer = ActaInspeccionDetailSerializer(acta_cerrada)
            return Response(out_serializer.data, status=status.HTTP_200_OK)
        except FiscalizacionConflicto as exc:
            return Response({"detail": exc.mensaje}, status=status.HTTP_409_CONFLICT)
        except FiscalizacionError as exc:
            return Response({"detail": exc.mensaje}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(responses={200: ActaInspeccionDetailSerializer(many=True)})
    @action(detail=False, methods=["get"], url_path="historial")
    def historial(self, request):
        """RF-15. Consulta el historial de inspecciones con detalle completo."""
        predio_id = request.query_params.get("predio_id")
        campania_id = request.query_params.get("campania_id")
        inspector_id = request.query_params.get("inspector_id")
        solo_cerradas = request.query_params.get("solo_cerradas", "false").lower() == "true"

        qs = consultar_historial(
            predio_id=predio_id,
            campania_id=campania_id,
            inspector_id=inspector_id,
            solo_cerradas=solo_cerradas,
        )
        serializer = ActaInspeccionDetailSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
