from rest_framework import serializers

from .models import ReporteGenerado


class ReporteGeneradoSerializer(serializers.ModelSerializer):
    generado_por_nombre = serializers.CharField(
        source="generado_por.nombre_completo", read_only=True
    )

    class Meta:
        model = ReporteGenerado
        fields = [
            "id",
            "tipo",
            "formato",
            "generado_por",
            "generado_por_nombre",
            "fecha_generacion",
            "parametros",
        ]
        read_only_fields = fields


class GenerarReporteInputSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=ReporteGenerado.TIPO_OFICIAL_CHOICES)
    formato = serializers.ChoiceField(choices=ReporteGenerado.FORMATO_OFICIAL_CHOICES)
    campania_id = serializers.IntegerField(required=False, allow_null=True)
    acta_id = serializers.IntegerField(required=False, allow_null=True)
    predio_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        tipo = attrs.get("tipo")
        campania_id = attrs.get("campania_id")
        acta_id = attrs.get("acta_id")
        predio_id = attrs.get("predio_id")

        if tipo == ReporteGenerado.TIPO_EJECUTIVO and not campania_id:
            raise serializers.ValidationError(
                {"campania_id": "Se requiere campania_id para generar un reporte ejecutivo."}
            )

        if tipo == ReporteGenerado.TIPO_DICTAMEN and not acta_id and not predio_id:
            raise serializers.ValidationError(
                {"acta_id": "Se requiere acta_id o predio_id para generar un dictamen técnico."}
            )

        return attrs


class GenerarReporteDinamicoInputSerializer(serializers.Serializer):
    pregunta = serializers.CharField(
        max_length=1000,
        help_text="Pregunta, instrucción pericial o filtros en lenguaje natural (ej: 'Predios en riesgo Crítico en el Parque Industrial').",
    )


class ExportarReporteDinamicoQuerySerializer(serializers.Serializer):
    formato = serializers.ChoiceField(
        choices=["PDF", "Excel", "TXT", "pdf", "excel", "txt", "xlsx"],
        default="PDF",
        help_text="Formato de exportación (PDF, Excel o TXT)",
    )
    columnas = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Claves de columnas separadas por coma para exportar únicamente esas columnas.",
    )


class ReporteDinamicoResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    pregunta = serializers.CharField()
    titulo = serializers.CharField()
    generado_en = serializers.CharField()
    interpretacion = serializers.DictField()
    columnas = serializers.ListField(child=serializers.DictField())
    columnas_disponibles = serializers.ListField(child=serializers.DictField())
    filas = serializers.ListField(child=serializers.DictField())
    grafico = serializers.DictField(allow_null=True)
    kpis = serializers.ListField(child=serializers.DictField(), allow_null=True)
    respuesta_nl = serializers.CharField(allow_null=True)
    motor = serializers.CharField()
    presentacion_ia = serializers.BooleanField()
    total_filas = serializers.IntegerField()
