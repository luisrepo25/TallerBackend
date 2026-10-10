from decimal import Decimal

from rest_framework import serializers

# Serializers del endpoint de sincronizacion (capa de presentacion). Solo validan el FORMATO;
# las reglas de negocio las aplica `sincronizacion.py`.

MAX_ACTAS_POR_LOTE = 50


class SyncMaterialSerializer(serializers.Serializer):
    material_id = serializers.IntegerField(min_value=1)
    peso_kg = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0.00"))


class SyncInfraccionSerializer(serializers.Serializer):
    tipo_infraccion_id = serializers.IntegerField(min_value=1)
    descripcion = serializers.CharField(required=False, allow_blank=True, default="")


class SyncEvidenciaSerializer(serializers.Serializer):
    url_imagen = serializers.CharField(max_length=255)
    descripcion_infraccion = serializers.CharField(required=False, allow_blank=True, default="")


class SyncActaSerializer(serializers.Serializer):
    uuid_local = serializers.UUIDField()
    predio_id = serializers.IntegerField(min_value=1)
    campania_id = serializers.IntegerField(min_value=1)
    estado_extintores_id = serializers.IntegerField(min_value=1)
    fallas_electricas = serializers.BooleanField(default=False)
    rutas_evacuacion_despejadas = serializers.BooleanField(default=True)
    # Momento real de la inspeccion, capturado en el dispositivo (ISO 8601 con zona horaria)
    fecha_inspeccion = serializers.DateTimeField(required=False)
    distancia_hidrante_m = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        allow_null=True,
    )
    materiales = SyncMaterialSerializer(many=True, required=False)
    infracciones = SyncInfraccionSerializer(many=True, required=False)
    evidencias = SyncEvidenciaSerializer(many=True, required=False)


class SyncLoteSerializer(serializers.Serializer):
    # Cada acta se valida por separado en la vista: una mal formada no tumba el lote
    actas = serializers.ListField(
        child=serializers.DictField(), allow_empty=False, max_length=MAX_ACTAS_POR_LOTE
    )


# --- Solo para documentar la respuesta en Swagger ---


class SyncInfraccionResultadoSerializer(serializers.Serializer):
    tipo_infraccion_id = serializers.IntegerField()
    es_reincidencia = serializers.BooleanField()


class SyncResultadoSerializer(serializers.Serializer):
    uuid_local = serializers.CharField(allow_null=True)
    estado = serializers.ChoiceField(
        choices=["sincronizada", "ya_sincronizada", "rechazada", "error_temporal"]
    )
    acta_id = serializers.IntegerField(required=False)
    carga_fuego = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)
    scoring_riesgo = serializers.DecimalField(max_digits=6, decimal_places=2, required=False)
    cluster_riesgo = serializers.CharField(required=False, allow_null=True)
    fecha_cierre = serializers.DateTimeField(required=False)
    infracciones = SyncInfraccionResultadoSerializer(many=True, required=False)
    codigo = serializers.CharField(required=False)
    detalle = serializers.JSONField(required=False)


class SyncRespuestaSerializer(serializers.Serializer):
    resultados = SyncResultadoSerializer(many=True)
