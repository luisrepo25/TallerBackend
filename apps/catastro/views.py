from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.usuarios.mixins import BitacoraAuditoriaMixin

from .models import (
    CatalogoTipoAcople,
    CatalogoTipoPredio,
    Hidrante,
    Predio,
    PredioHidranteCobertura,
)
from .permissions import IsAdministradorOrReadOnly, IsCatastroEditorOrReadOnly
from .serializers import (
    CatalogoTipoAcopleSerializer,
    CatalogoTipoPredioSerializer,
    HidranteCercanoResponseSerializer,
    HidranteCreateUpdateSerializer,
    HidranteSerializer,
    PredioCreateUpdateSerializer,
    PredioHidranteCoberturaSerializer,
    PredioSerializer,
)
from .services import calcular_cobertura_hidrantes, obtener_hidrante_mas_cercano


class CatalogoTipoPredioViewSet(viewsets.ModelViewSet):
    queryset = CatalogoTipoPredio.objects.all().order_by("id")
    serializer_class = CatalogoTipoPredioSerializer
    permission_classes = [IsAdministradorOrReadOnly]


class CatalogoTipoAcopleViewSet(viewsets.ModelViewSet):
    queryset = CatalogoTipoAcople.objects.all().order_by("id")
    serializer_class = CatalogoTipoAcopleSerializer
    permission_classes = [IsAdministradorOrReadOnly]


class PredioViewSet(BitacoraAuditoriaMixin, viewsets.ModelViewSet):
    queryset = Predio.objects.select_related("tipo_predio", "registrado_por").all().order_by("-id")
    permission_classes = [IsCatastroEditorOrReadOnly]
    bitacora_acciones = {
        "create": "Registrar predio",
        "update": "Actualizar predio",
        "partial_update": "Actualizar predio",
        "destroy": "Eliminar predio",
    }

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return PredioCreateUpdateSerializer
        return PredioSerializer

    @extend_schema(responses={200: HidranteCercanoResponseSerializer})
    @action(detail=True, methods=["get"], url_path="hidrante-cercano")
    def hidrante_cercano(self, request, pk=None):
        """Retorna el hidrante activo mas cercano al predio junto con la distancia en metros."""
        predio = self.get_object()
        cobertura = obtener_hidrante_mas_cercano(predio)
        if not cobertura:
            return Response(
                {"detail": "No existen hidrantes activos registrados en el sistema."},
                status=status.HTTP_404_NOT_FOUND,
            )
        data = {
            "predio_id": predio.id,
            "predio_nombre": predio.nombre,
            "hidrante": HidranteSerializer(cobertura.hidrante).data,
            "distancia_m": cobertura.distancia_m,
            "es_mas_cercano": cobertura.es_mas_cercano,
            "fecha_calculo": cobertura.fecha_calculo,
        }
        return Response(data, status=status.HTTP_200_OK)

    @extend_schema(responses={200: PredioHidranteCoberturaSerializer(many=True)})
    @action(detail=True, methods=["get"], url_path="cobertura")
    def cobertura(self, request, pk=None):
        """Lista todas las coberturas registradas para este predio ordenadas por distancia."""
        predio = self.get_object()
        coberturas = (
            PredioHidranteCobertura.objects.filter(predio=predio)
            .select_related("hidrante", "hidrante__tipo_acople")
            .order_by("distancia_m")
        )
        serializer = PredioHidranteCoberturaSerializer(coberturas, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(responses={200: PredioHidranteCoberturaSerializer(many=True)})
    @action(detail=True, methods=["post"], url_path="recalcular-cobertura")
    def recalcular_cobertura(self, request, pk=None):
        """Fuerza el recalculo espacial de distancias a todos los hidrantes activos."""
        predio = self.get_object()
        coberturas = calcular_cobertura_hidrantes(predio)
        serializer = PredioHidranteCoberturaSerializer(coberturas, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class HidranteViewSet(BitacoraAuditoriaMixin, viewsets.ModelViewSet):
    queryset = (
        Hidrante.objects.select_related("tipo_acople", "registrado_por").all().order_by("-id")
    )
    permission_classes = [IsCatastroEditorOrReadOnly]
    bitacora_acciones = {
        "create": "Registrar hidrante",
        "update": "Actualizar hidrante",
        "partial_update": "Actualizar hidrante",
        "destroy": "Eliminar hidrante",
    }

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return HidranteCreateUpdateSerializer
        return HidranteSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        estado = self.request.query_params.get("estado_operativo")
        if estado:
            qs = qs.filter(estado_operativo=estado)
        return qs
