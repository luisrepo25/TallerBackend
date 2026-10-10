from django.db import models

from apps.common.model_fields import UtcDateTimeField
from apps.usuarios.models import Usuario

# Modelos mapeados 1:1 al schema de BasedeDatos.sql (managed=False).
# Sin logica de negocio aqui: eso vive en services.py.


class ClusteringEjecucion(models.Model):
    fecha_ejecucion = UtcDateTimeField(auto_now_add=True)
    k_value = models.IntegerField(default=3)
    coeficiente_silueta = models.DecimalField(
        max_digits=4, decimal_places=3, null=True, blank=True
    )
    ejecutado_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, db_column="ejecutado_por"
    )

    class Meta:
        managed = False
        db_table = "clustering_ejecuciones"
