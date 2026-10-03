from rest_framework import serializers

from apps.common.fields import GeometryJSONField

from .models import Campania
from .services import actualizar_campania, crear_campania

# Serializers explicitos de esta app (capa de presentacion).
# No usar fields = "__all__".


class InspectorAsignadoSerializer(serializers.Serializer):
    usuario_id = serializers.IntegerField(source="usuario.pk")
    nombre_completo = serializers.CharField(source="usuario.usuario.nombre_completo")
    fecha_asignacion = serializers.DateTimeField()


class CampaniaSerializer(serializers.ModelSerializer):
    geom = GeometryJSONField(expected_type="Polygon", read_only=True)
    creado_por = serializers.IntegerField(source="creado_por_id", read_only=True)
    creado_por_nombre = serializers.ReadOnlyField(source="creado_por.usuario.nombre_completo")
    inspectores = InspectorAsignadoSerializer(
        source="campaniafuncionario_set", many=True, read_only=True
    )

    class Meta:
        model = Campania
        fields = [
            "id",
            "nombre",
            "fecha_inicio",
            "fecha_fin",
            "estado",
            "geom",
            "creado_por",
            "creado_por_nombre",
            "fecha_creacion",
            "inspectores",
        ]


class CampaniaCreateUpdateSerializer(serializers.ModelSerializer):
    geom = GeometryJSONField(expected_type="Polygon", required=False, allow_null=True)

    class Meta:
        model = Campania
        fields = ["id", "nombre", "fecha_inicio", "fecha_fin", "estado", "geom"]
        read_only_fields = ["id", "estado"]

    def create(self, validated_data):
        return crear_campania(
            creado_por=self.context["request"].user.administrador, **validated_data
        )

    def update(self, instance, validated_data):
        return actualizar_campania(instance, validated_data)


class ZonaCampaniaSerializer(serializers.Serializer):
    geom = GeometryJSONField(expected_type="Polygon")


class AsignarInspectoresSerializer(serializers.Serializer):
    usuarios_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False
    )


class AvanceCampaniaSerializer(serializers.Serializer):
    total_predios = serializers.IntegerField()
    predios_inspeccionados = serializers.IntegerField()
    predios_pendientes = serializers.IntegerField()
    porcentaje = serializers.DecimalField(max_digits=5, decimal_places=2)


class CerrarCampaniaSerializer(serializers.Serializer):
    forzar = serializers.BooleanField(default=False)


class CierreCampaniaResponseSerializer(AvanceCampaniaSerializer):
    campania = CampaniaSerializer()
    forzado = serializers.BooleanField()
    actas_abiertas = serializers.IntegerField()
