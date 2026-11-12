# Resolutores de parametros del Agente de Reportes (capa de negocio).
#
# El LLM (o el interprete de reglas) entrega los filtros tal como los dice una persona:
# "distrito 8", "plan 3000"... no el nombre exacto de la BD. Aqui se traducen a valores
# validos del dominio o se rechazan con un mensaje que el LLM puede usar para corregirse.

import re
import unicodedata
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from apps.analitica.models import Distrito
from apps.catastro.models import CatalogoTipoPredio
from apps.fiscalizacion.models import CatalogoEstadoExtintor, CatalogoInfraccion

NIVELES_RIESGO = ["Bajo", "Medio", "Critico"]

SINONIMOS_TIPO_PREDIO = {
    "mercado": "Mercado Distrital",
    "feria": "Mercado Distrital",
    "salud": "Salud",
    "hospital": "Salud",
    "clinica": "Salud",
    "educ": "Educativo",
    "colegio": "Educativo",
    "escuela": "Educativo",
    "universidad": "Educativo",
    "unidad educativa": "Educativo",
    "comerci": "Comercial",
    "mall": "Comercial",
    "supermercado": "Comercial",
    "tienda": "Comercial",
    "industr": "Industrial",
    "fabrica": "Industrial",
    "planta": "Industrial",
    "deposito": "Industrial",
}


class ParametroInvalido(Exception):
    """Un filtro no corresponde a ningun valor del dominio (se devuelve al LLM)."""

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


def normalizar(texto) -> str:
    """Minusculas, sin tildes ni espacios repetidos."""
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().lower()


def vacio(valor) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def a_bool(valor) -> bool | None:
    if vacio(valor):
        return None
    if isinstance(valor, bool):
        return valor
    return normalizar(valor) in ("true", "si", "1", "verdadero", "yes")


def a_numero(valor, nombre: str) -> float | None:
    if vacio(valor):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        raise ParametroInvalido(f"'{nombre}' debe ser numerico (recibido: {valor}).") from None


def a_entero(valor, nombre: str, *, defecto: int, minimo: int = 1, maximo: int = 500) -> int:
    numero = a_numero(valor, nombre)
    if numero is None:
        return defecto
    return max(minimo, min(int(numero), maximo))


def a_fecha(valor, nombre: str) -> date | None:
    if vacio(valor):
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        raise ParametroInvalido(
            f"'{nombre}' debe tener formato YYYY-MM-DD (recibido: {valor})."
        ) from None


def rango_datetime(desde: date | None, hasta: date | None) -> dict:
    """Limites aware (hora local) para filtrar columnas timestamp: [desde 00:00, hasta+1 00:00)."""
    tz = timezone.get_current_timezone()
    limites = {}
    if desde:
        limites["gte"] = timezone.make_aware(datetime.combine(desde, time.min), tz)
    if hasta:
        limites["lt"] = timezone.make_aware(
            datetime.combine(hasta + timedelta(days=1), time.min), tz
        )
    return limites


def fecha_local(valor) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        if timezone.is_naive(valor):
            valor = timezone.make_aware(valor, timezone.get_current_timezone())
        return timezone.localtime(valor).strftime("%Y-%m-%d")
    return valor.isoformat()


def resolver_cluster(valor) -> str | None:
    if vacio(valor):
        return None
    texto = normalizar(valor)
    for nivel in NIVELES_RIESGO:
        if texto.startswith(normalizar(nivel)[:4]):
            return nivel
    if "alto" in texto:
        return "Critico"
    raise ParametroInvalido(f"Nivel de riesgo '{valor}' invalido. Usa: Bajo, Medio o Critico.")


def resolver_distrito(valor) -> Distrito | None:
    if vacio(valor):
        return None
    texto = normalizar(valor)
    distritos = list(Distrito.objects.order_by("pk"))
    if "industrial" in texto:
        return next((d for d in distritos if "industrial" in normalizar(d.nombre)), None)
    if "montero" in texto or "hoyos" in texto:
        texto = "15"
    numero = re.search(r"\d+", texto)
    if numero:
        patron = rf"(?<!\d){numero.group()}(?!\d)"
        encontrado = next((d for d in distritos if re.search(patron, d.nombre)), None)
        if encontrado:
            return encontrado
    encontrado = next((d for d in distritos if texto in normalizar(d.nombre)), None)
    if encontrado:
        return encontrado
    nombres = ", ".join(d.nombre for d in distritos)
    raise ParametroInvalido(f"No existe el distrito '{valor}'. Distritos validos: {nombres}.")


def resolver_tipo_predio(valor) -> CatalogoTipoPredio | None:
    if vacio(valor):
        return None
    texto = normalizar(valor)
    tipos = list(CatalogoTipoPredio.objects.all())
    exacto = next((t for t in tipos if normalizar(t.nombre) == texto), None)
    if exacto:
        return exacto
    for clave, nombre in SINONIMOS_TIPO_PREDIO.items():
        if clave in texto:
            return next((t for t in tipos if t.nombre == nombre), None)
    parcial = next((t for t in tipos if texto in normalizar(t.nombre)), None)
    if parcial:
        return parcial
    nombres = ", ".join(t.nombre for t in tipos)
    raise ParametroInvalido(f"Tipo de predio '{valor}' invalido. Tipos validos: {nombres}.")


def resolver_catalogo(valor, modelo, etiqueta: str):
    """Busca por nombre aproximado en un catalogo (infracciones, estados de extintor)."""
    if vacio(valor):
        return None
    texto = normalizar(valor)
    items = list(modelo.objects.all())
    for item in items:
        nombre = normalizar(item.nombre)
        if texto == nombre or texto in nombre or nombre in texto:
            return item
    palabras = [p for p in texto.split() if len(p) > 3]
    for item in items:
        if any(p[:5] in normalizar(item.nombre) for p in palabras):
            return item
    nombres = ", ".join(i.nombre for i in items)
    raise ParametroInvalido(f"{etiqueta} '{valor}' invalido. Valores validos: {nombres}.")


def resolver_infraccion(valor):
    return resolver_catalogo(valor, CatalogoInfraccion, "Tipo de infraccion")


def resolver_estado_extintor(valor):
    return resolver_catalogo(valor, CatalogoEstadoExtintor, "Estado de extintor")
