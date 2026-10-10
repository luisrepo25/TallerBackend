from django.db import models

from apps.common.model_fields import UtcDateTimeField
from apps.usuarios.models import Usuario

# Modelos mapeados 1:1 al schema de BasedeDatos.sql (managed=False).
# Sin logica de negocio aqui: eso vive en services.py.


class ReporteGenerado(models.Model):
    TIPO_DICTAMEN = "dictamen"
    TIPO_EJECUTIVO = "ejecutivo"
    TIPO_CHOICES = [
        (TIPO_DICTAMEN, "Dictamen"),
        (TIPO_EJECUTIVO, "Ejecutivo"),
    ]

    FORMATO_PDF = "PDF"
    FORMATO_EXCEL = "Excel"
    FORMATO_CHOICES = [
        (FORMATO_PDF, "PDF"),
        (FORMATO_EXCEL, "Excel"),
    ]

    tipo = models.CharField(max_length=50, choices=TIPO_CHOICES)
    formato = models.CharField(max_length=10, choices=FORMATO_CHOICES)
    generado_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, db_column="generado_por"
    )
    fecha_generacion = UtcDateTimeField(auto_now_add=True)
    parametros = models.JSONField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "reportes_generados"
