from decimal import Decimal

from rest_framework import serializers

from apps.campanias.models import Campania
from apps.catastro.models import Predio
from apps.usuarios.models import InspectorTecnico

from .models import (
    ActaInspeccion,
    CatalogoEstadoExtintor,
    CatalogoInfraccion,
    CatalogoMaterialCombustible,
    EvidenciaFotografica,
    Infraccion,
    MaterialRegistrado,
)
from .services import (
    FiscalizacionConflicto,
    FiscalizacionError,
    registrar_acta,
    registrar_materiales,
)


class CatalogoEstadoExtintorSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogoEstadoExtintor
        fields = ["id", "nombre"]


class CatalogoInfraccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogoInfraccion
        fields = ["id", "nombre", "peso_severidad"]


class CatalogoMaterialCombustibleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogoMaterialCombustible
        fields = [
            "id",
            "nombre",
            "poder_calorifico_mj_kg",
            "coeficiente_peligrosidad",
        ]


class MaterialRegistradoSerializer(serializers.ModelSerializer):
    material = CatalogoMaterialCombustibleSerializer(read_only=True)

    class Meta:
        model = MaterialRegistrado
        fields = ["id", "material", "peso_kg"]


class MaterialItemInputSerializer(serializers.Serializer):
    material_id = serializers.IntegerField()
    peso_kg = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0.00"))


class EvidenciaFotograficaSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvidenciaFotografica
        fields = [
            "id",
            "url_imagen",
            "descripcion_infraccion",
            "fecha_captura",
        ]


class InfraccionSerializer(serializers.ModelSerializer):
    tipo_infraccion = CatalogoInfraccionSerializer(read_only=True)

    class Meta:
        model = Infraccion
        fields = [
            "id",
            "tipo_infraccion",
            "descripcion",
            "es_reincidencia",
            "fecha_registro",
        ]


class InfraccionCreateSerializer(serializers.Serializer):
    tipo_infraccion_id = serializers.IntegerField()
    descripcion = serializers.CharField(required=False, allow_blank=True, default="")


class ActaInspeccionListSerializer(serializers.ModelSerializer):
    predio_nombre = serializers.ReadOnlyField(source="predio.nombre")
    campania_nombre = serializers.ReadOnlyField(source="campania.nombre")
    inspector_nombre = serializers.ReadOnlyField(source="inspector.usuario.nombre_completo")
    estado_extintores_nombre = serializers.ReadOnlyField(source="estado_extintores.nombre")

    class Meta:
        model = ActaInspeccion
        fields = [
            "id",
            "uuid_local",
            "predio",
            "predio_nombre",
            "campania",
            "campania_nombre",
            "inspector",
            "inspector_nombre",
            "fecha_inspeccion",
            "carga_fuego",
            "estado_extintores",
            "estado_extintores_nombre",
            "fallas_electricas",
            "rutas_evacuacion_despejadas",
            "distancia_hidrante_m",
            "scoring_riesgo",
            "cluster_riesgo",
            "cerrada",
            "fecha_cierre",
            "sincronizada",
            "fecha_sincronizacion",
        ]


class ActaInspeccionDetailSerializer(serializers.ModelSerializer):
    predio_nombre = serializers.ReadOnlyField(source="predio.nombre")
    campania_nombre = serializers.ReadOnlyField(source="campania.nombre")
    inspector_nombre = serializers.ReadOnlyField(source="inspector.usuario.nombre_completo")
    estado_extintores = CatalogoEstadoExtintorSerializer(read_only=True)
    materiales = MaterialRegistradoSerializer(
        source="materialregistrado_set", many=True, read_only=True
    )
    infracciones = InfraccionSerializer(source="infraccion_set", many=True, read_only=True)
    evidencias = EvidenciaFotograficaSerializer(
        source="evidenciafotografica_set", many=True, read_only=True
    )

    class Meta:
        model = ActaInspeccion
        fields = [
            "id",
            "uuid_local",
            "predio",
            "predio_nombre",
            "campania",
            "campania_nombre",
            "inspector",
            "inspector_nombre",
            "fecha_inspeccion",
            "carga_fuego",
            "estado_extintores",
            "fallas_electricas",
            "rutas_evacuacion_despejadas",
            "distancia_hidrante_m",
            "scoring_riesgo",
            "cluster_riesgo",
            "cerrada",
            "fecha_cierre",
            "sincronizada",
            "fecha_sincronizacion",
            "materiales",
            "infracciones",
            "evidencias",
        ]


class ActaInspeccionCreateSerializer(serializers.ModelSerializer):
    predio = serializers.PrimaryKeyRelatedField(queryset=Predio.objects.all())
    campania = serializers.PrimaryKeyRelatedField(queryset=Campania.objects.all())
    estado_extintores = serializers.PrimaryKeyRelatedField(
        queryset=CatalogoEstadoExtintor.objects.all()
    )
    inspector = serializers.PrimaryKeyRelatedField(
        queryset=InspectorTecnico.objects.all(), required=False
    )
    materiales = MaterialItemInputSerializer(many=True, required=False)

    class Meta:
        model = ActaInspeccion
        fields = [
            "id",
            "uuid_local",
            "predio",
            "campania",
            "inspector",
            "estado_extintores",
            "fallas_electricas",
            "rutas_evacuacion_despejadas",
            "distancia_hidrante_m",
            "materiales",
        ]

    def create(self, validated_data):
        user = self.context["request"].user
        materiales_data = validated_data.pop("materiales", [])

        # Si no se envio inspector explicito, se asume el del usuario autenticado
        inspector = validated_data.pop("inspector", None)
        if inspector is None:
            if hasattr(user, "inspectortecnico"):
                inspector = user.inspectortecnico
            else:
                raise serializers.ValidationError(
                    {"inspector": "Debe especificar un inspector tecnico."}
                )

        try:
            acta = registrar_acta(
                inspector=inspector,
                usuario_autenticado=user,
                **validated_data,
            )
            if materiales_data:
                registrar_materiales(acta, materiales_data)
            return acta
        except FiscalizacionConflicto:
            raise
        except FiscalizacionError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
