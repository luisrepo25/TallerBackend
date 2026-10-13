import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

# Cliente HTTP del microservicio de clustering. Solo transporte: no conoce reglas de negocio.
# Usa la libreria estandar (urllib) para no agregar una dependencia por una sola llamada.


class ServicioMLNoDisponible(Exception):
    """El microservicio no responde o falla por un motivo ajeno a los datos (la vista da 503)."""


class ServicioMLRechazo(Exception):
    """El microservicio rechazo los datos (422): pocas actas, actas identicas, etc."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


def ejecutar_clustering(actas: list[dict]) -> dict:
    """POST /clustering/ejecutar. Devuelve el JSON del microservicio ya decodificado."""
    peticion = urllib.request.Request(
        f"{settings.ML_SERVICE_URL.rstrip('/')}/clustering/ejecutar",
        data=json.dumps({"actas": actas}).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": settings.ML_API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=settings.ML_TIMEOUT_SEGUNDOS) as respuesta:
            return json.load(respuesta)
    except urllib.error.HTTPError as exc:  # antes que URLError: es su subclase
        if exc.code == 422:
            raise ServicioMLRechazo(_detalle(exc)) from exc
        logger.error("El microservicio ML respondio HTTP %s", exc.code)
        raise ServicioMLNoDisponible("El servicio de clustering respondio con un error.") from exc
    except (OSError, ValueError) as exc:  # red caida, timeout, conexion cortada, JSON invalido
        logger.error("No se pudo contactar al microservicio ML: %s", exc)
        raise ServicioMLNoDisponible("No se pudo contactar al servicio de clustering.") from exc


def _detalle(exc: urllib.error.HTTPError) -> str:
    """Mensaje del 422. Si es nuestro (texto) se muestra; si es de validacion de campos
    (lista de errores de pydantic) es un fallo de contrato, no algo que el usuario deba ver."""
    try:
        detalle = json.load(exc).get("detail")
    except (ValueError, AttributeError):
        detalle = None
    if isinstance(detalle, str):
        return detalle
    logger.error("El microservicio ML rechazo el contrato de datos: %s", detalle)
    raise ServicioMLNoDisponible("El servicio de clustering rechazo los datos enviados.") from exc
