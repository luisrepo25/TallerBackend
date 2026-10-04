import uuid

from django.db import models

from apps.campanias.models import Campania
from apps.catastro.models import Predio
from apps.usuarios.models import InspectorTecnico

# Modelos mapeados 1:1 al schema de BasedeDatos.sql (managed=False).
# Sin logica de negocio aqui: eso vive en services.py. En particular,
# `carga_fuego`, `scoring_riesgo` y `cluster_riesgo` son campos derivados
# calculados y guardados por services.py (nunca calculados en el modelo
# ni recalculados retroactivamente, ver CLAUDE.md).


class CatalogoEstadoExtintor(models.Model):
    nombre = models.CharField(max_length=50, unique=True)

    class Meta:
        managed = False
        db_table = "catalogo_estados_extintor"

    def __str__(self):
        return self.nombre


class CatalogoInfraccion(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    peso_severidad = models.DecimalField(max_digits=4, decimal_places=2, default=1.0)

    class Meta:
        managed = False
        db_table = "catalogo_infracciones"

    def __str__(self):
        return self.nombre


class CatalogoMaterialCombustible(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    poder_calorifico_mj_kg = models.DecimalField(max_digits=6, decimal_places=2)
    coeficiente_peligrosidad = models.DecimalField(max_digits=4, decimal_places=2)

    class Meta:
        managed = False
        db_table = "catalogo_materiales_combustibles"

    def __str__(self):
        return self.nombre


class ActaInspeccion(models.Model):
    CLUSTER_BAJO = "Bajo"
    CLUSTER_MEDIO = "Medio"
    CLUSTER_CRITICO = "Critico"
    CLUSTER_CHOICES = [
        (CLUSTER_BAJO, "Bajo"),
        (CLUSTER_MEDIO, "Medio"),
        (CLUSTER_CRITICO, "Critico"),
    ]

    uuid_local = models.UUIDField(unique=True, null=True, blank=True, default=uuid.uuid4)
    predio = models.ForeignKey(Predio, on_delete=models.PROTECT, db_column="predio_id")
    campania = models.ForeignKey(Campania, on_delete=models.PROTECT, db_column="campania_id")
    inspector = models.ForeignKey(
        InspectorTecnico, on_delete=models.PROTECT, db_column="inspector_id"
    )
    fecha_inspeccion = models.DateTimeField(auto_now_add=True)
    carga_fuego = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    estado_extintores = models.ForeignKey(
        CatalogoEstadoExtintor, on_delete=models.PROTECT, db_column="estado_extintores_id"
    )
    fallas_electricas = models.BooleanField(default=False)
    rutas_evacuacion_despejadas = models.BooleanField(default=True)
    distancia_hidrante_m = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    scoring_riesgo = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    cluster_riesgo = models.CharField(max_length=20, choices=CLUSTER_CHOICES, null=True, blank=True)
    cerrada = models.BooleanField(default=False)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    sincronizada = models.BooleanField(default=True)
    fecha_sincronizacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "actas_inspeccion"

    def __str__(self):
        return f"Acta {self.pk} - {self.predio_id}"


class MaterialRegistrado(models.Model):
    acta = models.ForeignKey(ActaInspeccion, on_delete=models.CASCADE, db_column="acta_id")
    material = models.ForeignKey(
        CatalogoMaterialCombustible, on_delete=models.PROTECT, db_column="material_id"
    )
    peso_kg = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        managed = False
        db_table = "materiales_registrados"


class EvidenciaFotografica(models.Model):
    acta = models.ForeignKey(ActaInspeccion, on_delete=models.CASCADE, db_column="acta_id")
    url_imagen = models.CharField(max_length=255)
    descripcion_infraccion = models.TextField(null=True, blank=True)
    fecha_captura = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "evidencias_fotograficas"


class Infraccion(models.Model):
    acta = models.ForeignKey(ActaInspeccion, on_delete=models.CASCADE, db_column="acta_id")
    tipo_infraccion = models.ForeignKey(
        CatalogoInfraccion, on_delete=models.PROTECT, db_column="tipo_infraccion_id"
    )
    descripcion = models.TextField(null=True, blank=True)
    es_reincidencia = models.BooleanField(default=False)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "infracciones"
