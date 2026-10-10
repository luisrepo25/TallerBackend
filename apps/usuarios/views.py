from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

# Vistas/ViewSets de esta app (capa de presentacion).
# Delegan la logica de negocio a services.py, nunca al ORM directo.
from .models import Permiso, Rol, Usuario
from .permissions import IsAdministrador
from .serializers import (
    PermisoSerializer,
    RolSerializer,
    UsuarioCreateSerializer,
    UsuarioSerializer,
)


class PerfilView(APIView):
    """Usuario autenticado con sus subtipos. Lo usa el frontend tras el login."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: UsuarioSerializer})
    def get(self, request):
        return Response(UsuarioSerializer(request.user).data)


class RolViewSet(viewsets.ModelViewSet):
    queryset = Rol.objects.all()
    serializer_class = RolSerializer
    permission_classes = [IsAdministrador]


class PermisoViewSet(viewsets.ModelViewSet):
    queryset = Permiso.objects.all()
    serializer_class = PermisoSerializer
    permission_classes = [IsAdministrador]


class UsuarioViewSet(viewsets.ModelViewSet):
    # select_related de los subtipos: el listado muestra `subtipos` de cada usuario
    queryset = Usuario.objects.select_related(
        "rol", "administrador", "inspectortecnico", "oficialmando"
    ).all()
    permission_classes = [IsAdministrador]

    def get_serializer_class(self):
        if self.action == "create":
            return UsuarioCreateSerializer
        return UsuarioSerializer
