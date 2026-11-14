from drf_spectacular.utils import extend_schema
from rest_framework import generics, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

# Vistas/ViewSets de esta app (capa de presentacion).
# Delegan la logica de negocio a services.py, nunca al ORM directo.
from .models import Permiso, Rol, Usuario
from .permissions import IsAdministrador
from .serializers import (
    BitacoraAuditoriaSerializer,
    BitacoraFiltrosSerializer,
    PermisoSerializer,
    RolSerializer,
    UsuarioCreateSerializer,
    UsuarioSerializer,
)
from .services import listar_acciones_bitacora, listar_bitacora


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


class BitacoraListView(generics.ListAPIView):
    """Consulta de la bitacora de auditoria (CU03). Solo Administrador, solo lectura."""

    serializer_class = BitacoraAuditoriaSerializer
    permission_classes = [IsAdministrador]
    pagination_class = None

    @extend_schema(parameters=[BitacoraFiltrosSerializer])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        filtros = BitacoraFiltrosSerializer(data=self.request.query_params)
        filtros.is_valid(raise_exception=True)
        return listar_bitacora(**filtros.validated_data)


class BitacoraAccionesView(APIView):
    """Acciones distintas registradas en la bitacora (opciones del filtro)."""

    permission_classes = [IsAdministrador]

    @extend_schema(responses={200: list[str]})
    def get(self, request):
        return Response(listar_acciones_bitacora())
