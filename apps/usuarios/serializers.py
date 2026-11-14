from rest_framework import serializers

# Serializers explicitos de esta app (capa de presentacion).
# No usar fields = "__all__".
from .models import BitacoraAuditoria, Permiso, Rol, Usuario
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


class BitacoraAuditoriaSerializer(serializers.ModelSerializer):
    """Registro de auditoria. `rol` es el snapshot del rol al momento de la accion."""

    usuario_nombre = serializers.CharField(source="usuario.nombre_completo", read_only=True)
    usuario_email = serializers.CharField(source="usuario.email", read_only=True)
    rol = serializers.CharField(source="rol.nombre", read_only=True, default=None)

    class Meta:
        model = BitacoraAuditoria
        fields = [
            "id",
            "usuario_id",
            "usuario_nombre",
            "usuario_email",
            "rol",
            "accion",
            "entidad_afectada",
            "fecha",
        ]


class BitacoraFiltrosSerializer(serializers.Serializer):
    """Valida los parametros de consulta de la bitacora (400 con detalle por campo)."""

    usuario_id = serializers.IntegerField(required=False, min_value=1)
    accion = serializers.CharField(required=False, max_length=150)
    desde = serializers.DateField(required=False)
    hasta = serializers.DateField(required=False)
    limite = serializers.IntegerField(required=False, min_value=1)

    def validate(self, datos):
        desde, hasta = datos.get("desde"), datos.get("hasta")
        if desde and hasta and desde > hasta:
            raise serializers.ValidationError(
                {"hasta": "Debe ser igual o posterior a la fecha inicial."}
            )
        return datos
