import hashlib
import json
import time
import urllib.error
import urllib.request
import uuid

from django.conf import settings

# Subida firmada a Cloudinary (RF-13). Usa solo la libreria estandar: es una unica llamada
# HTTP y no justifica agregar el SDK. El API Secret nunca sale del servidor.

TIMEOUT_SEGUNDOS = 30


class CloudinaryError(Exception):
    """No se pudo guardar la imagen en Cloudinary."""


def _firmar(parametros: dict) -> str:
    texto = "&".join(f"{k}={v}" for k, v in sorted(parametros.items()))
    return hashlib.sha1((texto + settings.CLOUDINARY_API_SECRET).encode()).hexdigest()  # noqa: S324


def _cuerpo_multipart(campos: dict, nombre_archivo: str, contenido: bytes, tipo: str):
    frontera = uuid.uuid4().hex
    partes = []
    for clave, valor in campos.items():
        partes.append(
            f'--{frontera}\r\nContent-Disposition: form-data; name="{clave}"\r\n\r\n{valor}\r\n'.encode()
        )
    partes.append(
        (
            f"--{frontera}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{nombre_archivo}"\r\n'
            f"Content-Type: {tipo}\r\n\r\n"
        ).encode()
        + contenido
        + b"\r\n"
    )
    partes.append(f"--{frontera}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={frontera}"


def subir_imagen(contenido: bytes, nombre_archivo: str, tipo: str) -> str:
    """Sube la imagen a la carpeta de evidencias y devuelve su URL https."""
    faltan = [
        n
        for n in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
        if not getattr(settings, n, "")
    ]
    if faltan:
        raise CloudinaryError(f"Cloudinary no esta configurado (falta {', '.join(faltan)}).")

    firmados = {
        "folder": settings.CLOUDINARY_FOLDER.strip("/"),
        "timestamp": str(int(time.time())),
    }
    campos = {
        **firmados,
        "api_key": settings.CLOUDINARY_API_KEY,
        "signature": _firmar(firmados),
    }
    cuerpo, content_type = _cuerpo_multipart(campos, nombre_archivo, contenido, tipo)
    peticion = urllib.request.Request(
        f"https://api.cloudinary.com/v1_1/{settings.CLOUDINARY_CLOUD_NAME}/image/upload",
        data=cuerpo,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_SEGUNDOS) as respuesta:  # noqa: S310
            datos = json.loads(respuesta.read())
    except urllib.error.HTTPError as error:
        raise CloudinaryError(f"Cloudinary rechazo la imagen ({error.code}).") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise CloudinaryError("No se pudo conectar con Cloudinary.") from error

    url = datos.get("secure_url")
    if not url:
        raise CloudinaryError("Cloudinary no devolvio la URL de la imagen.")
    return url
