from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

# Manejador de excepciones de DRF (capa de presentacion): traduce errores de integridad
# del ORM a respuestas HTTP legibles en vez de un 500.


def manejar_excepciones(exc, context):
    if isinstance(exc, ProtectedError):
        dependientes = sorted({type(obj).__name__ for obj in exc.protected_objects})
        return Response(
            {
                "detail": "No se puede eliminar: otros registros dependen de este.",
                "dependientes": dependientes,
            },
            status=status.HTTP_409_CONFLICT,
        )
    return exception_handler(exc, context)
