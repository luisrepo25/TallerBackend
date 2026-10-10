from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.usuarios.permissions import IsInspectorTecnico

from .sincronizacion import RECHAZADA, sincronizar_actas
from .sync_serializers import (
    SyncActaSerializer,
    SyncLoteSerializer,
    SyncRespuestaSerializer,
)

# Vista (capa de presentacion) del endpoint que usa la app movil. Delega TODA la logica a
# `sincronizacion.py`.


class SincronizarActasView(APIView):
    """RF-21. Recibe un lote de actas COMPLETAS hechas sin conexion, las guarda, las cierra
    y calcula carga de fuego y scoring. Responde 200 con el resultado de CADA acta:
    una acta rechazada no impide que las demas se guarden."""

    permission_classes = [IsInspectorTecnico]

    @extend_schema(request=SyncLoteSerializer, responses={200: SyncRespuestaSerializer})
    def post(self, request):
        lote = SyncLoteSerializer(data=request.data)
        lote.is_valid(raise_exception=True)

        resultados = [None] * len(lote.validated_data["actas"])
        validas = []  # (posicion, datos validados)
        for posicion, crudo in enumerate(lote.validated_data["actas"]):
            serializer = SyncActaSerializer(data=crudo)
            if serializer.is_valid():
                validas.append((posicion, serializer.validated_data))
            else:
                resultados[posicion] = {
                    "uuid_local": crudo.get("uuid_local"),
                    "estado": RECHAZADA,
                    "codigo": "datos_invalidos",
                    "detalle": serializer.errors,
                }

        procesadas = sincronizar_actas([datos for _, datos in validas], request.user)
        for (posicion, _), resultado in zip(validas, procesadas, strict=True):
            resultados[posicion] = resultado

        return Response({"resultados": resultados})
