# Logica de negocio de esta app (capa de servicios).
# Las vistas delegan aqui: nunca hacen calculos ni orquestacion directo con el ORM.

from django.db import transaction

from .models import Administrador, BitacoraAuditoria, InspectorTecnico, OficialMando, Usuario

SUBTIPOS_MODELOS = {
    "administrador": Administrador,
    "inspector_tecnico": InspectorTecnico,
    "oficial_mando": OficialMando,
}


@transaction.atomic
def crear_usuario(*, nombre_completo, email, password, rol, subtipo, datos_subtipo=None):
    """Crea un Usuario y su registro de subtipo funcional en una sola transaccion.

    `subtipo` es una clave de SUBTIPOS_MODELOS ("administrador", "inspector_tecnico"
    u "oficial_mando"). Un usuario puede tener mas de un subtipo asignado con
    llamadas separadas (los subtipos se solapan, no son el `rol`).
    """
    usuario = Usuario.objects.create_user(
        email=email, password=password, nombre_completo=nombre_completo, rol=rol
    )
    modelo_subtipo = SUBTIPOS_MODELOS[subtipo]
    modelo_subtipo.objects.create(usuario=usuario, **(datos_subtipo or {}))
    return usuario


def registrar_bitacora(*, usuario, accion, entidad_afectada=None):
    """Registra una accion critica en BitacoraAuditoria con el snapshot del rol
    ACTUAL del usuario al momento de la accion (no se actualiza retroactivamente
    si el rol del usuario cambia despues, ver CLAUDE.md)."""
    BitacoraAuditoria.objects.create(
        usuario=usuario,
        rol=usuario.rol,
        accion=accion,
        entidad_afectada=entidad_afectada,
    )
