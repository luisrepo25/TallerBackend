from rest_framework import viewsets

# Vistas/ViewSets de esta app (capa de presentacion).
# Delegan la logica de negocio a services.py, nunca al ORM directo.

from .models import Permiso, Rol, Usuario
from .permissions import IsAdministrador
from .serializers import PermisoSerializer, RolSerializer, UsuarioCreateSerializer, UsuarioSerializer


class RolViewSet(viewsets.ModelViewSet):
    queryset = Rol.objects.all()
    serializer_class = RolSerializer
    permission_classes = [IsAdministrador]


class PermisoViewSet(viewsets.ModelViewSet):
    queryset = Permiso.objects.all()
    serializer_class = PermisoSerializer
    permission_classes = [IsAdministrador]


class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.select_related("rol").all()
    permission_classes = [IsAdministrador]

    def get_serializer_class(self):
        if self.action == "create":
            return UsuarioCreateSerializer
        return UsuarioSerializer
