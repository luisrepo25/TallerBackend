import base64
import json
import urllib.error
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# Crea en Cloudinary la carpeta donde se guardan las evidencias fotograficas
# (CLOUDINARY_FOLDER). Usa la Admin API con autenticacion basica key:secret, asi que
# necesita CLOUDINARY_API_SECRET en el .env. Es idempotente: si ya existe, no falla.
#
#   docker compose run --rm web python manage.py crear_carpeta_cloudinary


class Command(BaseCommand):
    help = "Crea la carpeta de evidencias fotograficas en Cloudinary."

    def handle(self, *args, **options):
        faltantes = [
            nombre
            for nombre in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
            if not getattr(settings, nombre)
        ]
        if faltantes:
            raise CommandError(
                f"Falta configurar en el .env: {', '.join(faltantes)}. "
                "El API Secret se obtiene en Cloudinary -> Settings -> API Keys."
            )

        carpeta = settings.CLOUDINARY_FOLDER.strip("/")
        url = f"https://api.cloudinary.com/v1_1/{settings.CLOUDINARY_CLOUD_NAME}/folders/{carpeta}"
        credenciales = f"{settings.CLOUDINARY_API_KEY}:{settings.CLOUDINARY_API_SECRET}"
        token = base64.b64encode(credenciales.encode()).decode()
        peticion = urllib.request.Request(
            url, method="POST", headers={"Authorization": f"Basic {token}"}
        )

        try:
            with urllib.request.urlopen(peticion, timeout=20) as respuesta:
                datos = json.load(respuesta)
        except urllib.error.HTTPError as error:
            detalle = error.read().decode(errors="replace")
            if error.code == 401:
                raise CommandError(
                    "Cloudinary rechazo las credenciales (revisa key y secret)."
                ) from error
            if "already exists" in detalle.lower():
                self.stdout.write(self.style.WARNING(f"La carpeta '{carpeta}' ya existe."))
                return
            raise CommandError(f"Cloudinary respondio {error.code}: {detalle}") from error
        except urllib.error.URLError as error:
            raise CommandError(f"No se pudo conectar con Cloudinary: {error.reason}") from error

        self.stdout.write(
            self.style.SUCCESS(f"Carpeta creada en Cloudinary: {datos.get('path', carpeta)}")
        )
