import json

from django.contrib.gis.geos import GEOSGeometry
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


@extend_schema_field(OpenApiTypes.OBJECT)
class GeometryJSONField(serializers.Field):
    """Campo DRF para serializar y deserializar geometrias PostGIS (SRID 4326)
    desde y hacia estructuras GeoJSON estandar (dict o string JSON)."""

    def __init__(self, expected_type: str | None = None, **kwargs):
        self.expected_type = expected_type
        super().__init__(**kwargs)

    def to_representation(self, value):
        if value is None:
            return None
        if hasattr(value, "geojson"):
            return json.loads(value.geojson)
        return json.loads(value.json)

    def to_internal_value(self, data):
        if data is None:
            return None
        if isinstance(data, dict):
            geom_str = json.dumps(data)
        elif isinstance(data, str):
            geom_str = data
        else:
            raise serializers.ValidationError(
                "Formato de geometria invalido; debe ser dict GeoJSON o string."
            )

        try:
            geom = GEOSGeometry(geom_str)
        except Exception as exc:
            raise serializers.ValidationError(
                f"Error al interpretar la geometria GeoJSON: {exc}"
            ) from exc

        if geom.srid != 4326:
            geom.srid = 4326

        if self.expected_type and geom.geom_type.lower() != self.expected_type.lower():
            raise serializers.ValidationError(
                f"Se esperaba geometria de tipo '{self.expected_type}', pero se recibio '{geom.geom_type}'."
            )
        return geom
