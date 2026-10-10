from datetime import UTC

from django.db import models
from django.utils import timezone

# Campos de modelo compartidos (capa de datos). Sin logica de negocio.


class UtcDateTimeField(models.DateTimeField):
    """Para las columnas `timestamp without time zone` de BasedeDatos.sql.

    Django guarda en ellas la hora en UTC, pero al leerlas devuelve datetimes SIN zona
    horaria. La API los enviaba como `2026-10-10T00:56:06` (sin indicador) y cada cliente
    (web, movil) los tomaba como hora local: se veian corridos 4 horas (Bolivia = UTC-4).

    Aqui se marcan como UTC al leer, asi la API responde ISO 8601 con zona
    (`2026-10-10T00:56:06Z`) y el cliente la convierte a su hora local.
    """

    def from_db_value(self, value, expression, connection):
        if value is not None and timezone.is_naive(value):
            return value.replace(tzinfo=UTC)
        return value
