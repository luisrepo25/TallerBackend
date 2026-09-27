from django.db import models

# Modelos mapeados 1:1 al schema de BasedeDatos.sql (managed=False: el SQL
# es la fuente de verdad del esquema, no las migraciones de Django).
# Sin logica de negocio aqui: eso vive en services.py.


class Rol(models.Model):
    nombre = models.CharField(max_length=50, unique=True)

    class Meta:
        managed = False
        db_table = "roles"

    def __str__(self):
        return self.nombre


class Permiso(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "permisos"

    def __str__(self):
        return self.nombre


class RolPermiso(models.Model):
    pk = models.CompositePrimaryKey("rol", "permiso")
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, db_column="rol_id")
    permiso = models.ForeignKey(Permiso, on_delete=models.CASCADE, db_column="permiso_id")

    class Meta:
        managed = False
        db_table = "rol_permiso"


class Usuario(models.Model):
    nombre_completo = models.CharField(max_length=150)
    email = models.CharField(max_length=150, unique=True)
    password_hash = models.CharField(max_length=255)
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, db_column="rol_id")
    activo = models.BooleanField(default=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "usuarios"

    def __str__(self):
        return self.nombre_completo


class Administrador(models.Model):
    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, primary_key=True, db_column="usuario_id"
    )
    nivel_acceso = models.CharField(max_length=20, default="total")

    class Meta:
        managed = False
        db_table = "administradores"


class InspectorTecnico(models.Model):
    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, primary_key=True, db_column="usuario_id"
    )
    fecha_certificacion = models.DateField(null=True, blank=True)
    curso_capacitacion_completo = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = "inspectores_tecnicos"


class OficialMando(models.Model):
    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, primary_key=True, db_column="usuario_id"
    )
    rango = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "oficiales_mando"


class BitacoraAuditoria(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, db_column="usuario_id")
    rol = models.ForeignKey(
        Rol, on_delete=models.PROTECT, db_column="rol_id", null=True, blank=True
    )
    accion = models.CharField(max_length=150)
    entidad_afectada = models.CharField(max_length=100, null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "bitacora_auditoria"
