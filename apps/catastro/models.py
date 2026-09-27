from django.contrib.gis.db import models

from apps.usuarios.models import Usuario

# Modelos mapeados 1:1 al schema de BasedeDatos.sql (managed=False).
# Sin logica de negocio aqui: eso vive en services.py.


class CatalogoTipoPredio(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    categoria_riesgo_base = models.CharField(max_length=20, null=True, blank=True)
    riesgo_activacion = models.DecimalField(max_digits=4, decimal_places=2, default=1.0)

    class Meta:
        managed = False
        db_table = "catalogo_tipos_predio"

    def __str__(self):
        return self.nombre


class CatalogoTipoAcople(models.Model):
    nombre = models.CharField(max_length=50, unique=True)

    class Meta:
        managed = False
        db_table = "catalogo_tipos_acople"

    def __str__(self):
        return self.nombre


class Predio(models.Model):
    nombre = models.CharField(max_length=150)
    direccion = models.CharField(max_length=255, null=True, blank=True)
    tipo_predio = models.ForeignKey(
        CatalogoTipoPredio, on_delete=models.PROTECT, db_column="tipo_predio_id"
    )
    aforo = models.IntegerField(null=True, blank=True)
    area_m2 = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    atributos_extra = models.JSONField(null=True, blank=True)
    geom = models.PolygonField(srid=4326)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, db_column="registrado_por"
    )

    class Meta:
        managed = False
        db_table = "predios"

    def __str__(self):
        return self.nombre


class Hidrante(models.Model):
    ESTADO_ACTIVO = "activo"
    ESTADO_FUERA_DE_SERVICIO = "fuera_de_servicio"
    ESTADO_OPERATIVO_CHOICES = [
        (ESTADO_ACTIVO, "Activo"),
        (ESTADO_FUERA_DE_SERVICIO, "Fuera de servicio"),
    ]

    codigo = models.CharField(max_length=50, unique=True, null=True, blank=True)
    estado_operativo = models.CharField(
        max_length=20, choices=ESTADO_OPERATIVO_CHOICES, default=ESTADO_ACTIVO
    )
    presion_nominal = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    tipo_acople = models.ForeignKey(
        CatalogoTipoAcople, on_delete=models.PROTECT, db_column="tipo_acople_id"
    )
    geom = models.PointField(srid=4326)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, db_column="registrado_por"
    )

    class Meta:
        managed = False
        db_table = "hidrantes"

    def __str__(self):
        return self.codigo or f"Hidrante {self.pk}"


class PredioHidranteCobertura(models.Model):
    pk = models.CompositePrimaryKey("predio", "hidrante")
    predio = models.ForeignKey(Predio, on_delete=models.CASCADE, db_column="predio_id")
    hidrante = models.ForeignKey(Hidrante, on_delete=models.CASCADE, db_column="hidrante_id")
    distancia_m = models.DecimalField(max_digits=8, decimal_places=2)
    es_mas_cercano = models.BooleanField(default=False)
    fecha_calculo = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "predio_hidrante_cobertura"
