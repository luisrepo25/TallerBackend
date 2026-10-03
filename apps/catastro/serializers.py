from rest_framework import serializers

from apps.common.fields import GeometryJSONField

from .models import (
    CatalogoTipoAcople,
    CatalogoTipoPredio,
    Hidrante,
    Predio,
    PredioHidranteCobertura,
)
from .services import (
    actualizar_hidrante,
    actualizar_predio,
    crear_hidrante,
    crear_predio,
)


class CatalogoTipoPredioSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogoTipoPredio
        fields = ["id", "nombre", "categoria_riesgo_base", "riesgo_activacion"]


class CatalogoTipoAcopleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogoTipoAcople
        fields = ["id", "nombre"]


class PredioSerializer(serializers.ModelSerializer):
    tipo_predio = CatalogoTipoPredioSerializer(read_only=True)
    geom = GeometryJSONField(expected_type="Polygon")
    registrado_por_nombre = serializers.ReadOnlyField(source="registrado_por.nombre_completo")

    class Meta:
        model = Predio
        fields = [
            "id",
            "nombre",
            "direccion",
            "tipo_predio",
            "aforo",
            "area_m2",
            "atributos_extra",
            "geom",
            "fecha_registro",
            "registrado_por",
            "registrado_por_nombre",
        ]


class PredioCreateUpdateSerializer(serializers.ModelSerializer):
    tipo_predio = serializers.PrimaryKeyRelatedField(
        queryset=CatalogoTipoPredio.objects.all(),
        source="tipo_predio_id",
    )
    geom = GeometryJSONField(expected_type="Polygon")
    registrado_por = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Predio
        fields = [
            "id",
            "nombre",
            "direccion",
            "tipo_predio",
            "aforo",
            "area_m2",
            "atributos_extra",
            "geom",
            "registrado_por",
        ]

    def create(self, validated_data):
        user = self.context["request"].user
        tipo_predio_id = validated_data.pop("tipo_predio_id")
        return crear_predio(
            tipo_predio=tipo_predio_id,
            registrado_por=user,
            **validated_data,
        )

    def update(self, instance, validated_data):
        if "tipo_predio_id" in validated_data:
            validated_data["tipo_predio"] = validated_data.pop("tipo_predio_id")
        return actualizar_predio(instance, validated_data)


class HidranteSerializer(serializers.ModelSerializer):
    tipo_acople = CatalogoTipoAcopleSerializer(read_only=True)
    geom = GeometryJSONField(expected_type="Point")
    registrado_por_nombre = serializers.ReadOnlyField(source="registrado_por.nombre_completo")

    class Meta:
        model = Hidrante
        fields = [
            "id",
            "codigo",
            "estado_operativo",
            "presion_nominal",
            "tipo_acople",
            "geom",
            "fecha_registro",
            "registrado_por",
            "registrado_por_nombre",
        ]


class HidranteCreateUpdateSerializer(serializers.ModelSerializer):
    tipo_acople = serializers.PrimaryKeyRelatedField(
        queryset=CatalogoTipoAcople.objects.all(),
        source="tipo_acople_id",
    )
    geom = GeometryJSONField(expected_type="Point")
    registrado_por = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Hidrante
        fields = [
            "id",
            "codigo",
            "estado_operativo",
            "presion_nominal",
            "tipo_acople",
            "geom",
            "registrado_por",
        ]

    def create(self, validated_data):
        user = self.context["request"].user
        tipo_acople_id = validated_data.pop("tipo_acople_id")
        return crear_hidrante(
            tipo_acople=tipo_acople_id,
            registrado_por=user,
            **validated_data,
        )

    def update(self, instance, validated_data):
        if "tipo_acople_id" in validated_data:
            validated_data["tipo_acople"] = validated_data.pop("tipo_acople_id")
        return actualizar_hidrante(instance, validated_data)


class PredioHidranteCoberturaSerializer(serializers.ModelSerializer):
    hidrante = HidranteSerializer(read_only=True)

    class Meta:
        model = PredioHidranteCobertura
        fields = [
            "predio_id",
            "hidrante",
            "distancia_m",
            "es_mas_cercano",
            "fecha_calculo",
        ]


class HidranteCercanoResponseSerializer(serializers.Serializer):
    predio_id = serializers.IntegerField()
    predio_nombre = serializers.CharField()
    hidrante = HidranteSerializer()
    distancia_m = serializers.DecimalField(max_digits=8, decimal_places=2)
    es_mas_cercano = serializers.BooleanField()
    fecha_calculo = serializers.DateTimeField()
