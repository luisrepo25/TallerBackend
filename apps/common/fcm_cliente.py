"""Cliente de Firebase Cloud Messaging (API HTTP v1). Solo transporte: no conoce reglas de
negocio ni a quien se notifica (eso vive en `apps/usuarios/services.py`).

Las credenciales son la cuenta de servicio de Firebase, en JSON. Llegan por la variable de
entorno FIREBASE_CREDENTIALS_JSON (en la nube, desde Secret Manager) y jamas se versionan.
Sin esa variable las notificaciones quedan desactivadas y el resto del sistema funciona igual.
"""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

ALCANCE = "https://www.googleapis.com/auth/firebase.messaging"
URL_ENVIO = "https://fcm.googleapis.com/v1/projects/{proyecto}/messages:send"


class FcmError(Exception):
    """FCM no pudo entregar el mensaje (red, credenciales, servicio caido)."""


class TokenInvalido(FcmError):
    """El token ya no existe (app desinstalada o datos borrados): hay que olvidarlo."""


_credenciales = None


def habilitado() -> bool:
    return bool(settings.FIREBASE_CREDENTIALS_JSON)


def _acceso():
    """Devuelve (token de acceso OAuth, id del proyecto), renovandolo cuando vence."""
    global _credenciales
    if _credenciales is None:
        try:
            info = json.loads(settings.FIREBASE_CREDENTIALS_JSON)
            _credenciales = service_account.Credentials.from_service_account_info(
                info, scopes=[ALCANCE]
            )
        except (ValueError, KeyError) as exc:
            raise FcmError("Las credenciales de Firebase no son validas.") from exc
    if not _credenciales.valid:
        try:
            _credenciales.refresh(Request())
        except Exception as exc:  # noqa: BLE001 - la libreria lanza varios tipos de error
            raise FcmError("No se pudo autenticar con Firebase.") from exc
    return _credenciales.token, _credenciales.project_id


def _es_token_desconocido(cuerpo: bytes) -> bool:
    try:
        detalles = json.loads(cuerpo).get("error", {}).get("details", [])
    except ValueError:
        return False
    return any(d.get("errorCode") == "UNREGISTERED" for d in detalles)


def enviar(token: str, *, titulo: str, cuerpo: str, datos: dict | None = None) -> None:
    """Envia una notificacion a un dispositivo. Levanta TokenInvalido o FcmError."""
    acceso, proyecto = _acceso()
    mensaje = {
        "message": {
            "token": token,
            "notification": {"title": titulo, "body": cuerpo},
            "data": {clave: str(valor) for clave, valor in (datos or {}).items()},
            "android": {"priority": "HIGH"},
        }
    }
    peticion = urllib.request.Request(
        URL_ENVIO.format(proyecto=proyecto),
        data=json.dumps(mensaje).encode(),
        headers={"Authorization": f"Bearer {acceso}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=settings.FCM_TIMEOUT_SEGUNDOS):
            return
    except urllib.error.HTTPError as exc:  # antes que URLError: es su subclase
        if exc.code == 404 and _es_token_desconocido(exc.read()):
            raise TokenInvalido("El token del dispositivo ya no es valido.") from exc
        logger.error("FCM respondio HTTP %s", exc.code)
        raise FcmError("Firebase rechazo el mensaje.") from exc
    except OSError as exc:  # red caida, timeout, conexion cortada
        logger.error("No se pudo contactar a FCM: %s", exc)
        raise FcmError("No se pudo contactar a Firebase.") from exc
