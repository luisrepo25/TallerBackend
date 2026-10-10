from rest_framework import serializers

# Serializers explicitos de esta app (capa de presentacion).
# No usar fields = "__all__".
from .models import Permiso, Rol, Usuario
from .services import SUBTIPOS_MODELOS, crear_usuario, obtener_subtipos


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
        fields = ["id", "nombre_completo", "email", "rol", "activo", "fecha_registro", "subtipos"]

    def get_subtipos(self, usuario):
        return obtener_subtipos(usuario)


class UsuarioCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    subtipo = serializers.ChoiceField(choices=list(SUBTIPOS_MODELOS), write_only=True)
    datos_subtipo = serializers.DictField(required=False, write_only=True)

    class Meta:
        model = Usuario
        fields = ["id", "nombre_completo", "email", "password", "rol", "subtipo", "datos_subtipo"]

    def create(self, validated_data):
        return crear_usuario(
            nombre_completo=validated_data["nombre_completo"],
            email=validated_data["email"],
            password=validated_data["password"],
            rol=validated_data["rol"],
            subtipo=validated_data["subtipo"],
            datos_subtipo=validated_data.get("datos_subtipo"),
        )
