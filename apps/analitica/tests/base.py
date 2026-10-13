import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import TestCase
from rest_framework.test import APIClient

from apps.analitica.models import Distrito
from apps.campanias.services import crear_campania
from apps.catastro.models import CatalogoTipoPredio
from apps.catastro.services import crear_predio
from apps.fiscalizacion.models import ActaInspeccion, CatalogoEstadoExtintor
from apps.usuarios.models import Rol
from apps.usuarios.services import crear_usuario


def cuadrado(x, y, lado):
    """Poligono cuadrado (lon/lat, SRID 4326) con esquina inferior izquierda en (x, y)."""
    return Polygon(((x, y), (x + lado, y), (x + lado, y + lado), (x, y + lado), (x, y)), srid=4326)


class BaseAnaliticaTestCase(TestCase):
    # Los tests corren sobre la BD real compartida: los distritos y predios de prueba se crean
    # en una zona despoblada del oriente boliviano, a ~300 km de Santa Cruz, para no mezclarse
    # con datos reales. No puede estar mas lejos: la distancia al hidrante mas cercano se
    # guarda en NUMERIC(8,2) y debe ser menor a 1 000 000 m.
    ORIGEN = (-63.0, -20.0)

    def setUp(self):
        self.suffix = uuid.uuid4().hex[:6]
        self.admin = self._usuario("Administrador", "administrador", "admin")
        self.oficial = self._usuario("Oficial de Mando", "oficial_mando", "oficial")
        self.inspector = self._usuario("Inspector Tecnico", "inspector_tecnico", "insp")
        self.campania = crear_campania(
            nombre=f"Campania {self.suffix}",
            fecha_inicio=date.today(),
            fecha_fin=date.today() + timedelta(days=30),
            creado_por=self.admin.administrador,
            geom=None,
        )
        self.predio = self.crear_predio(-63.2, -17.8)
        self.client = APIClient()

    def _usuario(self, rol, subtipo, prefijo):
        return crear_usuario(
            nombre_completo=f"{prefijo} {self.suffix}",
            email=f"{prefijo}.{self.suffix}@uubr.org.bo",
            password="claveSegura123",
            rol=Rol.objects.get(nombre=rol),
            subtipo=subtipo,
        )

    def crear_predio(self, x, y, lado=0.001):
        return crear_predio(
            nombre=f"Predio {uuid.uuid4().hex[:5]}",
            tipo_predio=CatalogoTipoPredio.objects.first(),
            geom=cuadrado(x, y, lado),
            registrado_por=self.admin,
        )

    def crear_distrito(self, nombre, dx=0.0, dy=0.0, lado=0.1):
        """Distrito cuadrado cerca de ORIGEN, desplazado (dx, dy) grados."""
        x, y = self.ORIGEN
        return Distrito.objects.create(
            nombre=f"{nombre} {self.suffix}",
            geom=MultiPolygon(cuadrado(x + dx, y + dy, lado), srid=4326),
        )

    def predio_en(self, distrito_dx, distrito_dy, lado=0.001, desplazamiento=0.01):
        """Predio chico dentro del distrito creado con crear_distrito(dx, dy)."""
        x, y = self.ORIGEN
        return self.crear_predio(x + distrito_dx + desplazamiento, y + distrito_dy + 0.01, lado)

    def crear_acta(
        self, *, scoring="20.00", carga="50.00", cerrada=True, extintores="Vigente", **kw
    ):
        datos = {
            "predio": self.predio,
            "campania": self.campania,
            "inspector": self.inspector.inspectortecnico,
            "estado_extintores": CatalogoEstadoExtintor.objects.get(nombre=extintores),
            "cerrada": cerrada,
            "carga_fuego": Decimal(carga) if cerrada else None,
            "scoring_riesgo": Decimal(scoring) if cerrada else None,
        }
        datos.update(kw)
        return ActaInspeccion.objects.create(**datos)
