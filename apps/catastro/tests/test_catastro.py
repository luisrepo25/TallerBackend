import uuid
from decimal import Decimal

from django.contrib.gis.geos import Point, Polygon
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.catastro.models import (
    CatalogoTipoAcople,
    CatalogoTipoPredio,
    Hidrante,
)
from apps.catastro.services import (
    calcular_cobertura_hidrantes,
    crear_hidrante,
    crear_predio,
    obtener_hidrante_mas_cercano,
)
from apps.usuarios.models import BitacoraAuditoria, Rol
from apps.usuarios.services import crear_usuario


class BaseCatastroTestCase(TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:6]
        self.rol_admin = Rol.objects.get(nombre="Administrador")
        self.rol_inspector = Rol.objects.get(nombre="Inspector Tecnico")
        self.rol_oficial = Rol.objects.get(nombre="Oficial de Mando")

        self.admin = crear_usuario(
            nombre_completo=f"Admin Catastro {self.suffix}",
            email=f"admin.{self.suffix}@uubr.org.bo",
            password="claveSegura123",
            rol=self.rol_admin,
            subtipo="administrador",
        )
        self.inspector = crear_usuario(
            nombre_completo=f"Inspector Catastro {self.suffix}",
            email=f"inspector.{self.suffix}@uubr.org.bo",
            password="claveSegura123",
            rol=self.rol_inspector,
            subtipo="inspector_tecnico",
        )
        self.oficial = crear_usuario(
            nombre_completo=f"Oficial Catastro {self.suffix}",
            email=f"oficial.{self.suffix}@uubr.org.bo",
            password="claveSegura123",
            rol=self.rol_oficial,
            subtipo="oficial_mando",
        )

        self.tipo_predio = CatalogoTipoPredio.objects.first()
        self.tipo_acople = CatalogoTipoAcople.objects.first()
        self.client = APIClient()


class CoberturaHidrantesServiceTests(BaseCatastroTestCase):
    def setUp(self):
        super().setUp()

        # Poligono de predio en Santa Cruz
        self.poly_predio = Polygon(
            (
                (-63.1800, -17.7800),
                (-63.1800, -17.7810),
                (-63.1790, -17.7810),
                (-63.1790, -17.7800),
                (-63.1800, -17.7800),
            ),
            srid=4326,
        )
        self.predio = crear_predio(
            nombre=f"Predio Central {self.suffix}",
            direccion="Av. Las Americas",
            tipo_predio=self.tipo_predio,
            area_m2=Decimal("250.00"),
            geom=self.poly_predio,
            registrado_por=self.admin,
            calcular_cobertura=False,
        )

        # Hidrante 1: muy cercano y ACTIVO
        self.h_cercano = crear_hidrante(
            codigo=f"H-CERC-{self.suffix}",
            estado_operativo=Hidrante.ESTADO_ACTIVO,
            tipo_acople=self.tipo_acople,
            geom=Point(-63.1805, -17.7800, srid=4326),
            registrado_por=self.admin,
        )
        # Hidrante 2: mas lejano y ACTIVO
        self.h_lejano = crear_hidrante(
            codigo=f"H-LEJ-{self.suffix}",
            estado_operativo=Hidrante.ESTADO_ACTIVO,
            tipo_acople=self.tipo_acople,
            geom=Point(-63.1860, -17.7800, srid=4326),
            registrado_por=self.admin,
        )
        # Hidrante 3: cercano pero FUERA DE SERVICIO (debe ser ignorado en calculo de cobertura activa)
        self.h_inactivo = crear_hidrante(
            codigo=f"H-INAC-{self.suffix}",
            estado_operativo=Hidrante.ESTADO_FUERA_DE_SERVICIO,
            tipo_acople=self.tipo_acople,
            geom=Point(-63.1801, -17.7800, srid=4326),
            registrado_por=self.admin,
        )

    def test_calcular_cobertura_hidrantes_asigna_es_mas_cercano(self):
        coberturas = calcular_cobertura_hidrantes(self.predio)

        # Solo debe registrar los 2 hidrantes activos
        ids_hidrantes = [c.hidrante_id for c in coberturas]
        self.assertIn(self.h_cercano.id, ids_hidrantes)
        self.assertIn(self.h_lejano.id, ids_hidrantes)
        self.assertNotIn(self.h_inactivo.id, ids_hidrantes)

        # El mas cercano debe tener es_mas_cercano = True
        cobertura_cercano = next(c for c in coberturas if c.hidrante_id == self.h_cercano.id)
        cobertura_lejano = next(c for c in coberturas if c.hidrante_id == self.h_lejano.id)

        self.assertTrue(cobertura_cercano.es_mas_cercano)
        self.assertFalse(cobertura_lejano.es_mas_cercano)
        self.assertLess(cobertura_cercano.distancia_m, cobertura_lejano.distancia_m)
        self.assertGreater(cobertura_cercano.distancia_m, 0)

    def test_obtener_hidrante_mas_cercano(self):
        cobertura = obtener_hidrante_mas_cercano(self.predio)
        self.assertIsNotNone(cobertura)
        self.assertEqual(cobertura.hidrante_id, self.h_cercano.id)
        self.assertTrue(cobertura.es_mas_cercano)

    def test_predio_sin_hidrantes_activos_retorna_vacio(self):
        # Desactivar TODOS los hidrantes, incluidos los reales de la BD compartida
        # (el TestCase corre en una transaccion que se revierte al terminar).
        Hidrante.objects.update(estado_operativo=Hidrante.ESTADO_FUERA_DE_SERVICIO)
        coberturas = calcular_cobertura_hidrantes(self.predio)
        self.assertEqual(len(coberturas), 0)

        mas_cercano = obtener_hidrante_mas_cercano(self.predio)
        self.assertIsNone(mas_cercano)


class PredioAPITests(BaseCatastroTestCase):
    def setUp(self):
        super().setUp()
        self.geojson_polygon = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-63.1812, -17.7820],
                    [-63.1812, -17.7830],
                    [-63.1800, -17.7830],
                    [-63.1800, -17.7820],
                    [-63.1812, -17.7820],
                ]
            ],
        }

    def test_administrador_puede_crear_predio_con_geojson(self):
        self.client.force_authenticate(user=self.admin)
        data = {
            "nombre": f"Edificio Corporativo {self.suffix}",
            "direccion": "Calle Rene Moreno #123",
            "tipo_predio": self.tipo_predio.id,
            "aforo": 150,
            "area_m2": 320.50,
            "atributos_extra": {"pisos": 5, "rubro": "oficinas"},
            "geom": self.geojson_polygon,
        }

        response = self.client.post(reverse("catastro:predio-list"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertEqual(response.data["geom"]["type"], "Polygon")
        self.assertEqual(response.data["registrado_por"], self.admin.id)

        # Verificar que se registro en bitacora de auditoria
        self.assertTrue(
            BitacoraAuditoria.objects.filter(
                usuario=self.admin, accion="Registrar predio", entidad_afectada="Predio"
            ).exists()
        )

    def test_oficial_mando_puede_crear_predio(self):
        self.client.force_authenticate(user=self.oficial)
        data = {
            "nombre": f"Predio Oficial {self.suffix}",
            "tipo_predio": self.tipo_predio.id,
            "geom": self.geojson_polygon,
        }
        response = self.client.post(reverse("catastro:predio-list"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_inspector_no_puede_crear_predio(self):
        self.client.force_authenticate(user=self.inspector)
        data = {
            "nombre": f"Intento Inspector {self.suffix}",
            "tipo_predio": self.tipo_predio.id,
            "geom": self.geojson_polygon,
        }
        response = self.client.post(reverse("catastro:predio-list"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_inspector_puede_listar_predios(self):
        self.client.force_authenticate(user=self.inspector)
        response = self.client.get(reverse("catastro:predio-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_geometria_invalida_es_rechazada(self):
        self.client.force_authenticate(user=self.admin)
        # Enviar Point en vez de Polygon
        data = {
            "nombre": "Predio Invalido",
            "tipo_predio": self.tipo_predio.id,
            "geom": {"type": "Point", "coordinates": [-63.18, -17.78]},
        }
        response = self.client.post(reverse("catastro:predio-list"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("geom", response.data)

    def test_endpoint_hidrante_cercano(self):
        self.client.force_authenticate(user=self.admin)
        # Crear predio y un hidrante
        predio = crear_predio(
            nombre=f"Predio Test Cercania {self.suffix}",
            tipo_predio=self.tipo_predio,
            geom=Polygon(
                (
                    (-63.18, -17.78),
                    (-63.18, -17.79),
                    (-63.17, -17.79),
                    (-63.17, -17.78),
                    (-63.18, -17.78),
                ),
                srid=4326,
            ),
            registrado_por=self.admin,
        )
        crear_hidrante(
            codigo=f"H-API-{self.suffix}",
            estado_operativo=Hidrante.ESTADO_ACTIVO,
            tipo_acople=self.tipo_acople,
            geom=Point(-63.181, -17.785, srid=4326),
            registrado_por=self.admin,
        )

        url = reverse("catastro:predio-hidrante-cercano", kwargs={"pk": predio.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("hidrante", response.data)
        self.assertIn("distancia_m", response.data)
        self.assertTrue(response.data["es_mas_cercano"])


class HidranteAPITests(BaseCatastroTestCase):
    def test_administrador_puede_crear_hidrante_con_geojson(self):
        self.client.force_authenticate(user=self.admin)
        data = {
            "codigo": f"H-TEST-{self.suffix}",
            "estado_operativo": "activo",
            "presion_nominal": 5.50,
            "tipo_acople": self.tipo_acople.id,
            "geom": {"type": "Point", "coordinates": [-63.1825, -17.7835]},
        }
        response = self.client.post(reverse("catastro:hidrante-list"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["codigo"], f"H-TEST-{self.suffix}")
        self.assertEqual(response.data["geom"]["type"], "Point")

    def test_inspector_no_puede_crear_hidrante(self):
        self.client.force_authenticate(user=self.inspector)
        data = {
            "codigo": f"H-NO-{self.suffix}",
            "tipo_acople": self.tipo_acople.id,
            "geom": {"type": "Point", "coordinates": [-63.18, -17.78]},
        }
        response = self.client.post(reverse("catastro:hidrante-list"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_filtrar_hidrantes_por_estado(self):
        self.client.force_authenticate(user=self.inspector)
        crear_hidrante(
            codigo=f"H-ACT-{self.suffix}",
            estado_operativo=Hidrante.ESTADO_ACTIVO,
            tipo_acople=self.tipo_acople,
            geom=Point(-63.18, -17.78, srid=4326),
            registrado_por=self.admin,
        )
        crear_hidrante(
            codigo=f"H-OUT-{self.suffix}",
            estado_operativo=Hidrante.ESTADO_FUERA_DE_SERVICIO,
            tipo_acople=self.tipo_acople,
            geom=Point(-63.19, -17.79, srid=4326),
            registrado_por=self.admin,
        )

        response = self.client.get(
            reverse("catastro:hidrante-list"), {"estado_operativo": "activo"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for h in response.data:
            self.assertEqual(h["estado_operativo"], "activo")


class EliminarProtegidoAPITests(BaseCatastroTestCase):
    def test_eliminar_tipo_predio_en_uso_responde_409_no_500(self):
        crear_predio(
            nombre=f"Predio en uso {self.suffix}",
            tipo_predio=self.tipo_predio,
            geom=Polygon(
                ((-63.18, -17.78), (-63.18, -17.779), (-63.179, -17.779), (-63.18, -17.78)),
                srid=4326,
            ),
            registrado_por=self.admin,
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(
            reverse("catastro:tipo-predio-detail", args=[self.tipo_predio.id])
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("Predio", response.data["dependientes"])
        self.assertTrue(CatalogoTipoPredio.objects.filter(pk=self.tipo_predio.id).exists())

    def test_eliminar_predio_sin_dependencias_responde_204(self):
        predio = crear_predio(
            nombre=f"Predio libre {self.suffix}",
            tipo_predio=self.tipo_predio,
            geom=Polygon(
                ((-63.18, -17.78), (-63.18, -17.779), (-63.179, -17.779), (-63.18, -17.78)),
                srid=4326,
            ),
            registrado_por=self.admin,
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(reverse("catastro:predio-detail", args=[predio.id]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
