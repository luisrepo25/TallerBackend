# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.contrib.gis.db import models


class ActasInspeccion(models.Model):
    uuid_local = models.UUIDField(unique=True, blank=True, null=True)
    predio = models.ForeignKey('Predios', models.DO_NOTHING)
    campania = models.ForeignKey('Campanias', models.DO_NOTHING)
    inspector = models.ForeignKey('InspectoresTecnicos', models.DO_NOTHING)
    fecha_inspeccion = models.DateTimeField()
    carga_fuego = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    estado_extintores = models.ForeignKey('CatalogoEstadosExtintor', models.DO_NOTHING)
    fallas_electricas = models.BooleanField()
    rutas_evacuacion_despejadas = models.BooleanField()
    distancia_hidrante_m = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    scoring_riesgo = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    cluster_riesgo = models.CharField(max_length=20, blank=True, null=True)
    cerrada = models.BooleanField()
    fecha_cierre = models.DateTimeField(blank=True, null=True)
    sincronizada = models.BooleanField()
    fecha_sincronizacion = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'actas_inspeccion'


class Administradores(models.Model):
    usuario = models.OneToOneField('Usuarios', models.DB_CASCADE, primary_key=True)
    nivel_acceso = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = 'administradores'


class BitacoraAuditoria(models.Model):
    usuario = models.ForeignKey('Usuarios', models.DO_NOTHING)
    rol = models.ForeignKey('Roles', models.DO_NOTHING, blank=True, null=True)
    accion = models.CharField(max_length=150)
    entidad_afectada = models.CharField(max_length=100, blank=True, null=True)
    fecha = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'bitacora_auditoria'


class CampaniaFuncionarios(models.Model):
    pk = models.CompositePrimaryKey('campania_id', 'usuario_id')
    campania = models.ForeignKey('Campanias', models.DB_CASCADE)
    usuario = models.ForeignKey('InspectoresTecnicos', models.DO_NOTHING)
    fecha_asignacion = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'campania_funcionarios'


class Campanias(models.Model):
    nombre = models.CharField(max_length=150)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    estado = models.CharField(max_length=20)
    geom = models.PolygonField(blank=True, null=True)
    creado_por = models.ForeignKey(Administradores, models.DO_NOTHING, db_column='creado_por')
    fecha_creacion = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'campanias'


class CatalogoEstadosExtintor(models.Model):
    nombre = models.CharField(unique=True, max_length=50)

    class Meta:
        managed = False
        db_table = 'catalogo_estados_extintor'


class CatalogoInfracciones(models.Model):
    nombre = models.CharField(unique=True, max_length=150)
    peso_severidad = models.DecimalField(max_digits=4, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'catalogo_infracciones'


class CatalogoMaterialesCombustibles(models.Model):
    nombre = models.CharField(unique=True, max_length=100)
    poder_calorifico_mj_kg = models.DecimalField(max_digits=6, decimal_places=2)
    coeficiente_peligrosidad = models.DecimalField(max_digits=4, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'catalogo_materiales_combustibles'


class CatalogoTiposAcople(models.Model):
    nombre = models.CharField(unique=True, max_length=50)

    class Meta:
        managed = False
        db_table = 'catalogo_tipos_acople'


class CatalogoTiposPredio(models.Model):
    nombre = models.CharField(unique=True, max_length=100)
    categoria_riesgo_base = models.CharField(max_length=20, blank=True, null=True)
    riesgo_activacion = models.DecimalField(max_digits=4, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'catalogo_tipos_predio'


class ClusteringEjecuciones(models.Model):
    fecha_ejecucion = models.DateTimeField()
    k_value = models.IntegerField()
    coeficiente_silueta = models.DecimalField(max_digits=4, decimal_places=3, blank=True, null=True)
    ejecutado_por = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='ejecutado_por')

    class Meta:
        managed = False
        db_table = 'clustering_ejecuciones'


class EvidenciasFotograficas(models.Model):
    acta = models.ForeignKey(ActasInspeccion, models.DB_CASCADE)
    url_imagen = models.CharField(max_length=255)
    descripcion_infraccion = models.TextField(blank=True, null=True)
    fecha_captura = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'evidencias_fotograficas'


class Hidrantes(models.Model):
    codigo = models.CharField(unique=True, max_length=50, blank=True, null=True)
    estado_operativo = models.CharField(max_length=20)
    presion_nominal = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    tipo_acople = models.ForeignKey(CatalogoTiposAcople, models.DO_NOTHING)
    geom = models.PointField()
    fecha_registro = models.DateTimeField()
    registrado_por = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='registrado_por')

    class Meta:
        managed = False
        db_table = 'hidrantes'


class Infracciones(models.Model):
    acta = models.ForeignKey(ActasInspeccion, models.DB_CASCADE)
    tipo_infraccion = models.ForeignKey(CatalogoInfracciones, models.DO_NOTHING)
    descripcion = models.TextField(blank=True, null=True)
    es_reincidencia = models.BooleanField()
    fecha_registro = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'infracciones'


class InspectoresTecnicos(models.Model):
    usuario = models.OneToOneField('Usuarios', models.DB_CASCADE, primary_key=True)
    fecha_certificacion = models.DateField(blank=True, null=True)
    curso_capacitacion_completo = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'inspectores_tecnicos'


class MaterialesRegistrados(models.Model):
    acta = models.ForeignKey(ActasInspeccion, models.DB_CASCADE)
    material = models.ForeignKey(CatalogoMaterialesCombustibles, models.DO_NOTHING)
    peso_kg = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'materiales_registrados'


class OficialesMando(models.Model):
    usuario = models.OneToOneField('Usuarios', models.DB_CASCADE, primary_key=True)
    rango = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'oficiales_mando'


class Permisos(models.Model):
    nombre = models.CharField(unique=True, max_length=100)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'permisos'


class PredioHidranteCobertura(models.Model):
    pk = models.CompositePrimaryKey('predio_id', 'hidrante_id')
    predio = models.ForeignKey('Predios', models.DB_CASCADE)
    hidrante = models.ForeignKey(Hidrantes, models.DB_CASCADE)
    distancia_m = models.DecimalField(max_digits=8, decimal_places=2)
    es_mas_cercano = models.BooleanField()
    fecha_calculo = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'predio_hidrante_cobertura'


class Predios(models.Model):
    nombre = models.CharField(max_length=150)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    tipo_predio = models.ForeignKey(CatalogoTiposPredio, models.DO_NOTHING)
    aforo = models.IntegerField(blank=True, null=True)
    area_m2 = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    atributos_extra = models.JSONField(blank=True, null=True)
    geom = models.PolygonField()
    fecha_registro = models.DateTimeField()
    registrado_por = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='registrado_por')

    class Meta:
        managed = False
        db_table = 'predios'


class ReportesGenerados(models.Model):
    tipo = models.CharField(max_length=50)
    formato = models.CharField(max_length=10)
    generado_por = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='generado_por')
    fecha_generacion = models.DateTimeField()
    parametros = models.JSONField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'reportes_generados'


class RolPermiso(models.Model):
    pk = models.CompositePrimaryKey('rol_id', 'permiso_id')
    rol = models.ForeignKey('Roles', models.DB_CASCADE)
    permiso = models.ForeignKey(Permisos, models.DB_CASCADE)

    class Meta:
        managed = False
        db_table = 'rol_permiso'


class Roles(models.Model):
    nombre = models.CharField(unique=True, max_length=50)

    class Meta:
        managed = False
        db_table = 'roles'


class Usuarios(models.Model):
    nombre_completo = models.CharField(max_length=150)
    email = models.CharField(unique=True, max_length=150)
    password_hash = models.CharField(max_length=255)
    rol = models.ForeignKey(Roles, models.DO_NOTHING)
    activo = models.BooleanField()
    fecha_registro = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'usuarios'
