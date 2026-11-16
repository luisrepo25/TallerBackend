from rest_framework import serializers

# Serializers explicitos de esta app (capa de presentacion).
# No usar fields = "__all__".
from .models import Permiso, Rol, Usuario
from .services import SUBTIPOS_MODELOS, actualizar_usuario, crear_usuario, obtener_subtipos


class RolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rol
        fields = ["id", "nombre"]


class PermisoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permiso
        fields = ["id", "nombre", "descripcion"]


class UsuarioSerializer(serializers.ModelSerializer):
    """Usuario con su rol y sus subtipos funcionales (que pueden solaparse)."""

    rol = RolSerializer(read_only=True)
    subtipos = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = [
            "id",
            "nombre_completo",
            "email",
            "telefono",
            "rol",
            "activo",
            "fecha_registro",
            "subtipos",
        ]

    def get_subtipos(self, usuario) -> list[str]:
        return obtener_subtipos(usuario)


class UsuarioCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    subtipo = serializers.ChoiceField(choices=list(SUBTIPOS_MODELOS), write_only=True)
    datos_subtipo = serializers.DictField(required=False, write_only=True)
    telefono = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = Usuario
        fields = [
            "id",
            "nombre_completo",
            "email",
            "telefono",
            "password",
            "rol",
            "subtipo",
            "datos_subtipo",
        ]

    def create(self, validated_data):
        return crear_usuario(
            nombre_completo=validated_data["nombre_completo"],
            email=validated_data["email"],
            password=validated_data["password"],
            rol=validated_data["rol"],
            subtipo=validated_data["subtipo"],
            datos_subtipo=validated_data.get("datos_subtipo"),
            telefono=validated_data.get("telefono"),
        )


class UsuarioUpdateSerializer(serializers.ModelSerializer):
    rol = serializers.PrimaryKeyRelatedField(queryset=Rol.objects.all(), required=False)
    password = serializers.CharField(
        write_only=True, min_length=8, required=False, allow_blank=True
    )
    telefono = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = Usuario
        fields = [
            "id",
            "nombre_completo",
            "email",
            "telefono",
            "rol",
            "password",
            "activo",
        ]

    def to_representation(self, instance):
        return UsuarioSerializer(instance, context=self.context).data

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            password = None
        return actualizar_usuario(
            usuario=instance,
            nombre_completo=validated_data.get("nombre_completo"),
            email=validated_data.get("email"),
            telefono=validated_data.get("telefono"),
            rol=validated_data.get("rol"),
            password=password,
            activo=validated_data.get("activo"),
        )
