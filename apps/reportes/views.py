from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ReporteGenerado
from .permissions import ReportesPermission
from .serializers import GenerarReporteInputSerializer, ReporteGeneradoSerializer
from .services import ReportesError, ReportesNoEncontrado, generar_reporte


class GenerarReporteView(APIView):
    """RF-20 / CU20: Genera y devuelve un reporte descargable (PDF o Excel).

    Admite tipo 'ejecutivo' (requiere campania_id) o 'dictamen' (requiere acta_id o
    predio_id).
    """

    permission_classes = [IsAuthenticated, ReportesPermission]

    @extend_schema(
        summary="Generar y descargar reporte",
        request=GenerarReporteInputSerializer,
        responses={
            200: bytes,
            400: dict,
            404: dict,
        },
        description="Genera y descarga un reporte ejecutivo de campaña o dictamen técnico en PDF o Excel.",
    )
    def post(self, request):
        serializer = GenerarReporteInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            contenido, content_type, filename, reporte = generar_reporte(
                tipo=data["tipo"],
                formato=data["formato"],
                usuario=request.user,
                campania_id=data.get("campania_id"),
                acta_id=data.get("acta_id"),
                predio_id=data.get("predio_id"),
            )
        except ReportesNoEncontrado as exc:
            return Response({"detail": exc.mensaje}, status=status.HTTP_404_NOT_FOUND)
        except ReportesError as exc:
            return Response({"detail": exc.mensaje}, status=status.HTTP_400_BAD_REQUEST)

        response = HttpResponse(contenido, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["X-Reporte-Id"] = str(reporte.id)
        response["Access-Control-Expose-Headers"] = "Content-Disposition, X-Reporte-Id"
        return response


@extend_schema_view(
    list=extend_schema(
        summary="Listar historial de reportes generados",
        description="Retorna el historial de reportes generados con ordenamiento cronológico inverso.",
        parameters=[
            OpenApiParameter(
                name="tipo",
                description="Filtrar por tipo de reporte ('ejecutivo' o 'dictamen')",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="formato",
                description="Filtrar por formato ('PDF' o 'Excel')",
                required=False,
                type=str,
            ),
        ],
    ),
    retrieve=extend_schema(
        summary="Detalle de un reporte generado",
        description="Retorna los metadatos y parámetros con los que fue generado un reporte.",
    ),
)
class ReporteGeneradoViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta el historial de reportes generados en el sistema (auditoría / registro
    histórico)."""

    queryset = (
        ReporteGenerado.objects.select_related("generado_por").all().order_by("-fecha_generacion")
    )
    serializer_class = ReporteGeneradoSerializer
    permission_classes = [IsAuthenticated, ReportesPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        tipo = self.request.query_params.get("tipo")
        formato = self.request.query_params.get("formato")
        if tipo:
            qs = qs.filter(tipo=tipo)
        if formato:
            qs = qs.filter(formato=formato)
        return qs
