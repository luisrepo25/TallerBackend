# Migracion state-only: los 8 modelos de esta app son managed=False
# (BasedeDatos.sql es la fuente de verdad del esquema, no se ejecuta ningun
# CREATE TABLE real al aplicar esta migracion). Existe porque
# AUTH_USER_MODEL="usuarios.Usuario" y Django exige que la app dueña del
# modelo de usuario tenga historial de migraciones para resolver el
# swappable_dependency que usan admin/auth.
#
# Escrita a mano (no generada con makemigrations): el autodetector de
# Django 6.1 dropea silenciosamente ForeignKeys al mezclar dependencias
# cruzadas entre modelos con CompositePrimaryKey (RolPermiso) en la misma
# migracion - se verifico comparando contra models.py.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Rol",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("nombre", models.CharField(max_length=50, unique=True)),
            ],
            options={
                "db_table": "roles",
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="Permiso",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("nombre", models.CharField(max_length=100, unique=True)),
                ("descripcion", models.TextField(blank=True, null=True)),
            ],
            options={
                "db_table": "permisos",
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="RolPermiso",
            fields=[
                (
                    "pk",
                    models.CompositePrimaryKey(
                        "rol",
                        "permiso",
                        blank=True,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "rol",
                    models.ForeignKey(
                        db_column="rol_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        to="usuarios.rol",
                    ),
                ),
                (
                    "permiso",
                    models.ForeignKey(
                        db_column="permiso_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        to="usuarios.permiso",
                    ),
                ),
            ],
            options={
                "db_table": "rol_permiso",
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="Usuario",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("nombre_completo", models.CharField(max_length=150)),
                ("email", models.CharField(max_length=150, unique=True)),
                ("password", models.CharField(db_column="password_hash", max_length=255)),
                ("activo", models.BooleanField(default=True)),
                ("fecha_registro", models.DateTimeField(auto_now_add=True)),
                (
                    "rol",
                    models.ForeignKey(
                        db_column="rol_id",
                        on_delete=django.db.models.deletion.PROTECT,
                        to="usuarios.rol",
                    ),
                ),
            ],
            options={
                "db_table": "usuarios",
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="Administrador",
            fields=[
                (
                    "usuario",
                    models.OneToOneField(
                        db_column="usuario_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        serialize=False,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("nivel_acceso", models.CharField(default="total", max_length=20)),
            ],
            options={
                "db_table": "administradores",
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="InspectorTecnico",
            fields=[
                (
                    "usuario",
                    models.OneToOneField(
                        db_column="usuario_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        serialize=False,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("fecha_certificacion", models.DateField(blank=True, null=True)),
                ("curso_capacitacion_completo", models.BooleanField(default=False)),
            ],
            options={
                "db_table": "inspectores_tecnicos",
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="OficialMando",
            fields=[
                (
                    "usuario",
                    models.OneToOneField(
                        db_column="usuario_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        serialize=False,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("rango", models.CharField(blank=True, max_length=50, null=True)),
            ],
            options={
                "db_table": "oficiales_mando",
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="BitacoraAuditoria",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        db_column="usuario_id",
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "rol",
                    models.ForeignKey(
                        blank=True,
                        db_column="rol_id",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="usuarios.rol",
                    ),
                ),
                ("accion", models.CharField(max_length=150)),
                ("entidad_afectada", models.CharField(blank=True, max_length=100, null=True)),
                ("fecha", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "bitacora_auditoria",
                "managed": False,
            },
        ),
    ]
