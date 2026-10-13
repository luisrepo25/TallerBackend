from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .cliente_ml import ServicioMLNoDisponible
from .models import ClusteringEjecucion
from .permissions import ClusteringPermission, ConsultaAnaliticaPermission
from .serializers import (
    ClusteringEjecucionSerializer,
    FiltrosMapaCalorSerializer,
    FiltrosZonasSugeridasSerializer,
    PuntoCalorSerializer,
    ResultadoClusteringSerializer,
    ResumenDistritosSerializer,
    ZonaSugeridaSerializer,
)
from .services import AnaliticaConflicto, ejecutar_clustering
from .zonificacion import mapa_calor, resumen_distritos, zonas_sugeridas

# Vistas/ViewSets de esta app (capa de presentacion).
# Delegan la logica de negocio a services.py, nunca al ORM directo.


class ClusteringViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Historial de ejecuciones del clustering y accion para lanzar una nueva."""

    permission_classes = [ClusteringPermission]
    serializer_class = ClusteringEjecucionSerializer
    queryset = ClusteringEjecucion.objects.select_related("ejecutado_por").order_by(
        "-fecha_ejecucion"
    )

    def handle_exception(self, exc):
        if isinstance(exc, AnaliticaConflicto):
            codigo, mensaje = status.HTTP_409_CONFLICT, exc.mensaje
        elif isinstance(exc, ServicioMLNoDisponible):
            codigo, mensaje = status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)
        else:
            return super().handle_exception(exc)
        return self.finalize_response(
            self.request, Response({"detail": mensaje}, status=codigo), *self.args, **self.kwargs
        )

    @extend_schema(request=None, responses={201: ResultadoClusteringSerializer})
    def create(self, request):
        """RF-17. Agrupa las actas cerradas en Bajo/Medio/Critico (K-Means, k=3) y guarda el
        cluster de cada una. Solo Administrador. 409 si hay pocas actas; 503 si el
        microservicio no responde."""
        resultado = ejecutar_clustering(usuario=request.user)
        return Response(
            ResultadoClusteringSerializer(resultado).data, status=status.HTTP_201_CREATED
        )


class MapaCalorView(APIView):
    permission_classes = [ConsultaAnaliticaPermission]

    @extend_schema(
        parameters=[FiltrosMapaCalorSerializer], responses={200: PuntoCalorSerializer(many=True)}
    )
    def get(self, request):
        """RF-18. Un punto por predio inspeccionado (centroide + scoring de su ultima acta
        cerrada) para la capa de calor. Filtros opcionales: `cluster`, `campania_id`."""
        filtros = FiltrosMapaCalorSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        return Response(PuntoCalorSerializer(mapa_calor(**filtros.validated_data), many=True).data)


class DistritosView(APIView):
    permission_classes = [ConsultaAnaliticaPermission]

    @extend_schema(responses={200: ResumenDistritosSerializer})
    def get(self, request):
        """RF-18. Resumen de riesgo por distrito municipal, con su poligono, para la capa
        semaforica y el tablero (clusters, scoring promedio, infracciones y reincidencias)."""
        return Response(ResumenDistritosSerializer(resumen_distritos()).data)


class ZonasSugeridasView(APIView):
    permission_classes = [ConsultaAnaliticaPermission]

    @extend_schema(
        parameters=[FiltrosZonasSugeridasSerializer],
        responses={200: ZonaSugeridaSerializer(many=True)},
    )
    def get(self, request):
        """RF-19. Distritos con predios Criticos, para proponer como nuevas campanias. Primero
        los que no tienen una campania activa; luego por cantidad y porcentaje de Criticos."""
        filtros = FiltrosZonasSugeridasSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        zonas = zonas_sugeridas(limite=filtros.validated_data["limite"])
        return Response(ZonaSugeridaSerializer(zonas, many=True).data)
