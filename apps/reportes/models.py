from django.db import models

from apps.common.model_fields import UtcDateTimeField
from apps.usuarios.models import Usuario

# Modelos mapeados 1:1 al schema de BasedeDatos.sql (managed=False).
# Sin logica de negocio aqui: eso vive en services.py.


class ReporteGenerado(models.Model):
    TIPO_DICTAMEN = "dictamen"
    TIPO_EJECUTIVO = "ejecutivo"
    TIPO_DINAMICO = "dinamico"
    TIPO_CHOICES = [
        (TIPO_DICTAMEN, "Dictamen"),
        (TIPO_EJECUTIVO, "Ejecutivo"),
        (TIPO_DINAMICO, "Dinamico (Agente)"),
    ]
    # Tipos que se generan por POST /generar/ (el dinamico se exporta desde el agente).
    TIPO_OFICIAL_CHOICES = [(TIPO_DICTAMEN, "Dictamen"), (TIPO_EJECUTIVO, "Ejecutivo")]

    FORMATO_PDF = "PDF"
    FORMATO_EXCEL = "Excel"
    FORMATO_TXT = "TXT"
    FORMATO_CSV = "CSV"
    FORMATO_CHOICES = [
        (FORMATO_PDF, "PDF"),
        (FORMATO_EXCEL, "Excel"),
        (FORMATO_TXT, "TXT"),
        (FORMATO_CSV, "CSV"),
    ]
    FORMATO_OFICIAL_CHOICES = [(FORMATO_PDF, "PDF"), (FORMATO_EXCEL, "Excel")]

    tipo = models.CharField(max_length=50, choices=TIPO_CHOICES)
    formato = models.CharField(max_length=10, choices=FORMATO_CHOICES)
    generado_por = models.ForeignKey(Usuario, on_delete=models.PROTECT, db_column="generado_por")
    fecha_generacion = UtcDateTimeField(auto_now_add=True)
    parametros = models.JSONField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "reportes_generados"


class ReporteDinamico(models.Model):
    """Resultado completo de una consulta al Agente de Reportes (se re-exporta sin recalcular)."""

    MOTOR_LLM = "llm"
    MOTOR_REGLAS = "reglas"

    id = models.UUIDField(primary_key=True)
    pregunta = models.TextField()
    titulo = models.CharField(max_length=150)
    interpretacion = models.JSONField()
    columnas = models.JSONField()
    columnas_disponibles = models.JSONField()
    filas = models.JSONField()
    grafico = models.JSONField(null=True, blank=True)
    kpis = models.JSONField(null=True, blank=True)
    respuesta_nl = models.TextField(null=True, blank=True)
    motor = models.CharField(max_length=20)
    idempotency_key = models.CharField(max_length=100, unique=True, null=True, blank=True)
    generado_por = models.ForeignKey(Usuario, on_delete=models.PROTECT, db_column="generado_por")
    fecha_generacion = UtcDateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "reportes_dinamicos"
