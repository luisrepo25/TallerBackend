from django.contrib.gis.db import models

from apps.common.model_fields import UtcDateTimeField
from apps.usuarios.models import Usuario

# Modelos mapeados 1:1 al schema de BasedeDatos.sql (managed=False).
# Sin logica de negocio aqui: eso vive en services.py.


class Distrito(models.Model):
    """Distrito municipal: zona de analisis (mapa de calor, zonas sugeridas). Sin FK con
    predios: se relacionan por interseccion espacial del centroide del predio."""

    nombre = models.CharField(max_length=100, unique=True)
    geom = models.MultiPolygonField(srid=4326)
    fecha_registro = UtcDateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "distritos"

    def __str__(self):
        return self.nombre


class ClusteringEjecucion(models.Model):
    fecha_ejecucion = UtcDateTimeField(auto_now_add=True)
    k_value = models.IntegerField(default=3)
    coeficiente_silueta = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    ejecutado_por = models.ForeignKey(Usuario, on_delete=models.PROTECT, db_column="ejecutado_por")

    class Meta:
        managed = False
        db_table = "clustering_ejecuciones"
