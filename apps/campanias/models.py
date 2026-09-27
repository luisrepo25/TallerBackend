from django.contrib.gis.db import models

from apps.usuarios.models import Administrador, InspectorTecnico

# Modelos mapeados 1:1 al schema de BasedeDatos.sql (managed=False).
# Sin logica de negocio aqui: eso vive en services.py.
#
# OJO: no existe FK directa Predio<->Campania (ver CLAUDE.md). Esa relacion
# se resuelve por interseccion espacial (ST_Intersects) en services.py.


class Campania(models.Model):
    ESTADO_PENDIENTE = "pendiente"
    ESTADO_EN_CURSO = "en_curso"
    ESTADO_CERRADA = "cerrada"
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_EN_CURSO, "En curso"),
        (ESTADO_CERRADA, "Cerrada"),
    ]

    nombre = models.CharField(max_length=150)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)
    geom = models.PolygonField(srid=4326, null=True, blank=True)
    creado_por = models.ForeignKey(
        Administrador, on_delete=models.PROTECT, db_column="creado_por"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "campanias"

    def __str__(self):
        return self.nombre


class CampaniaFuncionario(models.Model):
    pk = models.CompositePrimaryKey("campania", "usuario")
    campania = models.ForeignKey(Campania, on_delete=models.CASCADE, db_column="campania_id")
    usuario = models.ForeignKey(
        InspectorTecnico, on_delete=models.PROTECT, db_column="usuario_id"
    )
    fecha_asignacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "campania_funcionarios"
