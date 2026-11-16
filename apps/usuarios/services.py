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
def crear_usuario(
    *, nombre_completo, email, password, rol, subtipo, datos_subtipo=None, telefono=None
):
    """Crea un Usuario y su registro de subtipo funcional en una sola transaccion.

    `subtipo` es una clave de SUBTIPOS_MODELOS ("administrador", "inspector_tecnico"
    u "oficial_mando"). Un usuario puede tener mas de un subtipo asignado con
    llamadas separadas (los subtipos se solapan, no son el `rol`).
    """
    usuario = Usuario.objects.create_user(
        email=email,
        password=password,
        nombre_completo=nombre_completo,
        rol=rol,
        telefono=telefono,
    )
    modelo_subtipo = SUBTIPOS_MODELOS[subtipo]
    modelo_subtipo.objects.create(usuario=usuario, **(datos_subtipo or {}))
    return usuario


# Nombre de la relacion inversa 1:1 de cada subtipo en Usuario
_RELACION_SUBTIPO = {
    "administrador": "administrador",
    "inspector_tecnico": "inspectortecnico",
    "oficial_mando": "oficialmando",
}

_SUBTIPO_POR_ROL = {
    "Administrador": "administrador",
    "Oficial de Mando": "oficial_mando",
    "Inspector Tecnico": "inspector_tecnico",
}


@transaction.atomic
def actualizar_usuario(
    *,
    usuario: Usuario,
    nombre_completo=None,
    email=None,
    telefono=None,
    rol=None,
    password=None,
    activo=None,
):
    """Actualiza datos de un Usuario y mantiene sincronizados sus subtipos."""
    if nombre_completo is not None:
        usuario.nombre_completo = nombre_completo
    if email is not None:
        usuario.email = email
    if telefono is not None:
        usuario.telefono = (
            telefono.strip() if isinstance(telefono, str) and telefono.strip() else None
        )
    if password:
        usuario.set_password(password)
    if activo is not None:
        usuario.activo = activo

    if rol is not None:
        usuario.rol = rol
        subtipo_clave = _SUBTIPO_POR_ROL.get(rol.nombre)
        if subtipo_clave and not hasattr(usuario, _RELACION_SUBTIPO[subtipo_clave]):
            modelo_subtipo = SUBTIPOS_MODELOS[subtipo_clave]
            modelo_subtipo.objects.create(usuario=usuario)

    usuario.save()
    return usuario


def obtener_subtipos(usuario):
    """Claves de SUBTIPOS_MODELOS a las que pertenece el usuario (pueden ser varias).

    Usa la relacion inversa 1:1: si el usuario se cargo con select_related (como hace la
    autenticacion JWT) no genera consultas; si no, hace una por subtipo.
    """
    return [clave for clave, relacion in _RELACION_SUBTIPO.items() if hasattr(usuario, relacion)]


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


LIMITE_BITACORA = 200
LIMITE_BITACORA_MAXIMO = 1000


def listar_bitacora(
    *, usuario_id=None, accion=None, desde=None, hasta=None, limite=LIMITE_BITACORA
):
    """Registros de auditoria mas recientes primero, con filtros opcionales.

    La bitacora solo crece, asi que se acota con `limite` (tope LIMITE_BITACORA_MAXIMO)
    en vez de devolver todo. Las fechas se comparan en UTC (zona horaria del proyecto).
    """
    registros = BitacoraAuditoria.objects.select_related("usuario", "rol").order_by("-fecha", "-id")
    if usuario_id:
        registros = registros.filter(usuario_id=usuario_id)
    if accion:
        registros = registros.filter(accion=accion)
    if desde:
        registros = registros.filter(fecha__date__gte=desde)
    if hasta:
        registros = registros.filter(fecha__date__lte=hasta)
    return registros[: max(1, min(limite, LIMITE_BITACORA_MAXIMO))]


def listar_acciones_bitacora():
    """Acciones distintas ya registradas, para poblar el filtro de la pantalla."""
    return list(
        BitacoraAuditoria.objects.order_by("accion").values_list("accion", flat=True).distinct()
    )
