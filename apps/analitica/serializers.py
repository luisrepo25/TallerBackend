from rest_framework import serializers

from apps.common.fields import GeometryJSONField

from .models import ClusteringEjecucion

# Serializers explicitos de esta app (capa de presentacion).
# No usar fields = "__all__".


class ClusteringEjecucionSerializer(serializers.ModelSerializer):
    ejecutado_por_nombre = serializers.CharField(
        source="ejecutado_por.nombre_completo", read_only=True
    )

    class Meta:
        model = ClusteringEjecucion
        fields = [
            "id",
            "fecha_ejecucion",
            "k_value",
            "coeficiente_silueta",
            "ejecutado_por",
            "ejecutado_por_nombre",
        ]
        read_only_fields = fields


class FiltrosMapaCalorSerializer(serializers.Serializer):
    cluster = serializers.ChoiceField(choices=["Bajo", "Medio", "Critico"], required=False)
    campania_id = serializers.IntegerField(min_value=1, required=False)


class PuntoCalorSerializer(serializers.Serializer):
    predio_id = serializers.IntegerField()
    predio_nombre = serializers.CharField()
    lat = serializers.FloatField()
    lng = serializers.FloatField()
    scoring_riesgo = serializers.DecimalField(max_digits=6, decimal_places=2)
    cluster_riesgo = serializers.CharField(allow_null=True)
    intensidad = serializers.FloatField(help_text="scoring/100: peso del punto en el mapa de calor")


class ConteoClustersSerializer(serializers.Serializer):
    Bajo = serializers.IntegerField()
    Medio = serializers.IntegerField()
    Critico = serializers.IntegerField()


class DistritoResumenSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nombre = serializers.CharField()
    geom = GeometryJSONField()
    predios_registrados = serializers.IntegerField()
    predios_inspeccionados = serializers.IntegerField()
    conteo_clusters = ConteoClustersSerializer()
    nivel_predominante = serializers.CharField(allow_null=True)
    porcentaje_critico = serializers.FloatField()
    scoring_promedio = serializers.FloatField(allow_null=True)
    infracciones = serializers.IntegerField()
    reincidencias = serializers.IntegerField()


class ResumenDistritosSerializer(serializers.Serializer):
    distritos = DistritoResumenSerializer(many=True)
    inspeccionados_sin_distrito = serializers.IntegerField()


class FiltrosZonasSugeridasSerializer(serializers.Serializer):
    limite = serializers.IntegerField(min_value=1, max_value=50, default=5)


class ZonaSugeridaSerializer(DistritoResumenSerializer):
    campanias_activas = serializers.ListField(
        child=serializers.CharField(),
        help_text="Campanias pendientes o en curso que tocan el distrito",
    )


class ResumenClusterSerializer(serializers.Serializer):
    cluster_riesgo = serializers.CharField()
    cantidad_actas = serializers.IntegerField()
    scoring_promedio = serializers.FloatField()


class ResultadoClusteringSerializer(serializers.Serializer):
    ejecucion = ClusteringEjecucionSerializer()
    cantidad_actas = serializers.IntegerField()
    resumen = ResumenClusterSerializer(many=True)
