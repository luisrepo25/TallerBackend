from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ReporteDinamico, ReporteGenerado
from .permissions import ReportesPermission
from .serializers import (
    ExportarReporteDinamicoQuerySerializer,
    GenerarReporteDinamicoInputSerializer,
    GenerarReporteInputSerializer,
    ReporteDinamicoResponseSerializer,
    ReporteGeneradoSerializer,
)
from .services import (
    ReportesError,
    ReportesNoEncontrado,
    exportar_reporte_dinamico,
    generar_reporte,
    generar_reporte_dinamico,
)


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


class AgenteReporteView(APIView):
    """Agente de Reportes Dinámico con IA (Fase 6 extendido / F7).

    Recibe preguntas en lenguaje natural (por voz, texto o filtros visuales),
    ejecuta consultas parametrizadas, detecta gráficos y genera síntesis pericial.
    """

    permission_classes = [IsAuthenticated, ReportesPermission]

    @extend_schema(
        summary="Consultar al Agente Inteligente de Reportes",
        request=GenerarReporteDinamicoInputSerializer,
        responses={200: ReporteDinamicoResponseSerializer, 400: dict},
        description="Genera un reporte interactivo dinámico con tabla, gráficos, KPIs y síntesis ejecutiva a partir de una instrucción en lenguaje natural.",
    )
    def post(self, request):
        serializer = GenerarReporteDinamicoInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pregunta = serializer.validated_data["pregunta"]
        idempotency_key = request.headers.get("Idempotency-Key") or request.data.get(
            "idempotency_key"
        )

        try:
            reporte = generar_reporte_dinamico(
                pregunta=pregunta, usuario=request.user, idempotency_key=idempotency_key
            )
        except ReportesError as exc:
            return Response({"detail": exc.mensaje}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"Error al procesar el reporte: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(reporte, status=status.HTTP_200_OK)


class ExportarReporteDinamicoView(APIView):
    """Descarga un reporte dinámico en PDF, Excel (.xlsx) o TXT con las columnas seleccionadas."""

    permission_classes = [IsAuthenticated, ReportesPermission]

    @extend_schema(
        summary="Exportar reporte dinámico generado",
        parameters=[
            OpenApiParameter(
                name="formato",
                description="Formato de exportación: 'PDF', 'Excel' o 'TXT'",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="columnas",
                description="Claves de columnas separadas por coma",
                required=False,
                type=str,
            ),
        ],
        responses={200: bytes, 400: dict, 404: dict},
    )
    def get(self, request, id):
        query_serializer = ExportarReporteDinamicoQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        formato = query_serializer.validated_data.get("formato", "PDF")
        columnas_raw = query_serializer.validated_data.get("columnas")
        columnas = (
            [c.strip() for c in columnas_raw.split(",") if c.strip()] if columnas_raw else None
        )

        try:
            contenido, content_type, filename, reporte_audit = exportar_reporte_dinamico(
                id_reporte=id, formato=formato, columnas=columnas, usuario=request.user
            )
        except ReportesNoEncontrado as exc:
            return Response({"detail": exc.mensaje}, status=status.HTTP_404_NOT_FOUND)
        except ReportesError as exc:
            return Response({"detail": exc.mensaje}, status=status.HTTP_400_BAD_REQUEST)

        response = HttpResponse(contenido, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["X-Reporte-Id"] = str(reporte_audit.id)
        response["Access-Control-Expose-Headers"] = "Content-Disposition, X-Reporte-Id"
        return response


class DetalleReporteDinamicoView(APIView):
    """Consulta los datos JSON completos de un reporte dinámico generado."""

    permission_classes = [IsAuthenticated, ReportesPermission]

    @extend_schema(
        summary="Consultar detalle JSON de un reporte dinámico",
        responses={200: ReporteDinamicoResponseSerializer, 404: dict},
    )
    def get(self, request, id):
        try:
            reporte_obj = ReporteDinamico.objects.get(id=id)
        except (ReporteDinamico.DoesNotExist, ValueError):
            return Response(
                {"detail": "Reporte dinámico no encontrado."}, status=status.HTTP_404_NOT_FOUND
            )

        data = {
            "id": str(reporte_obj.id),
            "pregunta": reporte_obj.pregunta,
            "titulo": reporte_obj.titulo,
            "generado_en": reporte_obj.fecha_generacion.isoformat(),
            "interpretacion": reporte_obj.interpretacion,
            "columnas": reporte_obj.columnas,
            "columnas_disponibles": reporte_obj.columnas_disponibles,
            "filas": reporte_obj.filas,
            "grafico": reporte_obj.grafico,
            "kpis": reporte_obj.kpis,
            "respuesta_nl": reporte_obj.respuesta_nl,
            "motor": reporte_obj.motor,
            "presentacion_ia": len(reporte_obj.columnas) < len(reporte_obj.columnas_disponibles),
            "total_filas": len(reporte_obj.filas),
        }
        return Response(data, status=status.HTTP_200_OK)
