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
    tipo = serializers.ChoiceField(choices=ReporteGenerado.TIPO_CHOICES)
    formato = serializers.ChoiceField(choices=ReporteGenerado.FORMATO_CHOICES)
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
