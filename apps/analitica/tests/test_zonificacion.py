from datetime import date, timedelta

from rest_framework import status

from apps.analitica import zonificacion
from apps.analitica.models import Distrito
from apps.analitica.tests.base import BaseAnaliticaTestCase, cuadrado
from apps.campanias.services import cerrar_campania, crear_campania
from apps.fiscalizacion.models import CatalogoInfraccion, Infraccion


def geojson_cuadrado(nombre, x, y, lado=0.05, tipo="Polygon", campo="nombre"):
    anillo = [[x, y], [x + lado, y], [x + lado, y + lado], [x, y + lado], [x, y]]
    coordenadas = [anillo] if tipo == "Polygon" else [[anillo]]
    return {
        "type": "Feature",
        "properties": {campo: nombre},
        "geometry": {"type": tipo, "coordinates": coordenadas},
    }


class MapaCalorTests(BaseAnaliticaTestCase):
    def punto_de(self, predio):
        puntos = zonificacion.mapa_calor()
        return [p for p in puntos if p["predio_id"] == predio.pk]

    def test_usa_solo_la_ultima_acta_cerrada_del_predio(self):
        self.crear_acta(scoring="80.00", cluster_riesgo="Critico")
        self.crear_acta(scoring="30.00", cluster_riesgo="Bajo")
        puntos = self.punto_de(self.predio)
        self.assertEqual(len(puntos), 1)
        self.assertEqual(puntos[0]["scoring_riesgo"], 30)
        self.assertEqual(puntos[0]["intensidad"], 0.3)

    def test_el_punto_es_el_centroide_del_predio(self):
        self.crear_acta()
        punto = self.punto_de(self.predio)[0]
        self.assertAlmostEqual(punto["lng"], -63.2 + 0.0005, places=6)
        self.assertAlmostEqual(punto["lat"], -17.8 + 0.0005, places=6)

    def test_ignora_actas_abiertas(self):
        self.crear_acta(cerrada=False)
        self.assertEqual(self.punto_de(self.predio), [])

    def test_filtra_por_cluster(self):
        self.crear_acta(scoring="90.00", cluster_riesgo="Critico")
        criticos = zonificacion.mapa_calor(cluster="Critico")
        bajos = zonificacion.mapa_calor(cluster="Bajo")
        self.assertIn(self.predio.pk, [p["predio_id"] for p in criticos])
        self.assertNotIn(self.predio.pk, [p["predio_id"] for p in bajos])


class ResumenDistritosTests(BaseAnaliticaTestCase):
    def resumen_de(self, distrito):
        todos = zonificacion.resumen_distritos()["distritos"]
        return next(d for d in todos if d["id"] == distrito.pk)

    def acta_en(self, predio, scoring, cluster):
        return self.crear_acta(predio=predio, scoring=scoring, cluster_riesgo=cluster)

    def test_resume_clusters_scoring_e_infracciones(self):
        distrito = self.crear_distrito("Norte")
        p1, p2, p3, p4 = (self.predio_en(0, 0, desplazamiento=0.01 * i) for i in range(1, 5))
        self.acta_en(p1, "10.00", "Bajo")
        critica = self.acta_en(p2, "90.00", "Critico")
        self.acta_en(p3, "80.00", "Critico")
        tipo = CatalogoInfraccion.objects.first()
        Infraccion.objects.create(acta=critica, tipo_infraccion=tipo, es_reincidencia=True)
        Infraccion.objects.create(acta=critica, tipo_infraccion=tipo, es_reincidencia=False)

        r = self.resumen_de(distrito)
        self.assertEqual(r["conteo_clusters"], {"Bajo": 1, "Medio": 0, "Critico": 2})
        self.assertEqual(r["nivel_predominante"], "Critico")
        self.assertEqual(r["porcentaje_critico"], 66.7)
        self.assertEqual(r["scoring_promedio"], 60.0)
        self.assertEqual(r["predios_inspeccionados"], 3)
        self.assertEqual(r["predios_registrados"], 4)  # p4 existe pero no fue inspeccionado
        self.assertEqual((r["infracciones"], r["reincidencias"]), (2, 1))
        self.assertIsNotNone(p4)

    def test_distrito_sin_actas_aparece_en_ceros(self):
        r = self.resumen_de(self.crear_distrito("Vacio"))
        self.assertIsNone(r["nivel_predominante"])
        self.assertEqual(r["predios_inspeccionados"], 0)
        self.assertEqual(r["porcentaje_critico"], 0.0)
        self.assertIsNone(r["scoring_promedio"])

    def test_empate_gana_el_nivel_mas_severo(self):
        distrito = self.crear_distrito("Empate")
        self.acta_en(self.predio_en(0, 0, desplazamiento=0.01), "10.00", "Bajo")
        self.acta_en(self.predio_en(0, 0, desplazamiento=0.02), "90.00", "Critico")
        self.assertEqual(self.resumen_de(distrito)["nivel_predominante"], "Critico")

    def test_predio_en_el_limite_cuenta_solo_en_el_distrito_de_su_centroide(self):
        a = self.crear_distrito("A", dx=0.0)
        b = self.crear_distrito("B", dx=0.1)  # contiguo a la derecha de A
        x, y = self.ORIGEN
        # Ocupa x de +0.0985 a +0.1005 del origen: cruza el limite con B (en +0.1), pero su
        # centroide (+0.0995) esta dentro de A.
        cruza = self.crear_predio(x + 0.0985, y + 0.01, lado=0.002)
        self.acta_en(cruza, "85.00", "Critico")
        self.assertEqual(self.resumen_de(a)["predios_inspeccionados"], 1)
        self.assertEqual(self.resumen_de(b)["predios_inspeccionados"], 0)


class ZonasSugeridasTests(BaseAnaliticaTestCase):
    def critico_en(self, dx, cantidad):
        for i in range(cantidad):
            predio = self.predio_en(dx, 0, desplazamiento=0.01 * (i + 1))
            self.crear_acta(predio=predio, scoring="90.00", cluster_riesgo="Critico")

    def campania_en(self, dx, cerrar=False):
        x, y = self.ORIGEN
        campania = crear_campania(
            nombre=f"Camp {dx} {self.suffix}",
            fecha_inicio=date.today(),
            fecha_fin=date.today() + timedelta(days=30),
            creado_por=self.admin.administrador,
            geom=cuadrado(x + dx + 0.02, y + 0.02, 0.01),
        )
        if cerrar:
            cerrar_campania(campania, usuario=self.admin, forzar=True)
        return campania

    def mis_zonas(self):
        zonas = zonificacion.zonas_sugeridas(limite=50)
        return [z for z in zonas if z["nombre"].endswith(self.suffix)]

    def test_los_distritos_sin_campania_activa_van_primero(self):
        sin_campania = self.crear_distrito("Libre", dx=0.0)
        con_campania = self.crear_distrito("Cubierto", dx=0.2)
        self.critico_en(0.0, 1)
        self.critico_en(0.2, 3)  # tiene mas criticos, pero ya hay campania activa
        self.campania_en(0.2)

        zonas = self.mis_zonas()
        self.assertEqual([z["id"] for z in zonas], [sin_campania.pk, con_campania.pk])
        self.assertEqual(zonas[0]["campanias_activas"], [])
        self.assertEqual(len(zonas[1]["campanias_activas"]), 1)

    def test_una_campania_cerrada_no_cubre_el_distrito(self):
        self.crear_distrito("Cerrada", dx=0.0)
        self.critico_en(0.0, 1)
        self.campania_en(0.0, cerrar=True)
        self.assertEqual(self.mis_zonas()[0]["campanias_activas"], [])

    def test_sin_predios_criticos_no_se_sugiere(self):
        self.crear_distrito("Tranquilo", dx=0.0)
        self.crear_acta(predio=self.predio_en(0.0, 0), scoring="5.00", cluster_riesgo="Bajo")
        self.assertEqual(self.mis_zonas(), [])

    def test_respeta_el_limite(self):
        for dx in (0.0, 0.2, 0.4):
            self.crear_distrito(f"D{dx}", dx=dx)
            self.critico_en(dx, 1)
        self.assertEqual(len(zonificacion.zonas_sugeridas(limite=1)), 1)


class ImportarDistritosTests(BaseAnaliticaTestCase):
    def coleccion(self, *features):
        return {"type": "FeatureCollection", "features": list(features)}

    def nombre(self, base):
        return f"{base} {self.suffix}"

    def test_crea_y_luego_actualiza_sin_duplicar(self):
        a, b = self.nombre("Imp A"), self.nombre("Imp B")
        datos = self.coleccion(
            geojson_cuadrado(a, 100.0, 10.0), geojson_cuadrado(b, 100.1, 10.0, tipo="MultiPolygon")
        )
        primera = zonificacion.importar_distritos(datos)
        segunda = zonificacion.importar_distritos(datos)
        self.assertEqual((primera["creados"], primera["actualizados"]), (2, 0))
        self.assertEqual((segunda["creados"], segunda["actualizados"]), (0, 2))
        self.assertEqual(primera["reparados"], [])
        self.assertEqual(Distrito.objects.filter(nombre__in=[a, b]).count(), 2)
        self.assertEqual(Distrito.objects.get(nombre=a).geom.geom_type, "MultiPolygon")
        self.assertEqual(Distrito.objects.get(nombre=a).geom.srid, 4326)

    def test_usa_el_campo_de_nombre_indicado(self):
        nombre = self.nombre("Campo")
        datos = self.coleccion(geojson_cuadrado(nombre, 100.0, 10.0, campo="NOMBRE"))
        zonificacion.importar_distritos(datos, campo_nombre="NOMBRE")
        self.assertTrue(Distrito.objects.filter(nombre=nombre).exists())

    def corbata(self, nombre):
        """Poligono invalido: el contorno se cruza a si mismo (dos triangulos unidos)."""
        return {
            "type": "Feature",
            "properties": {"nombre": nombre},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
            },
        }

    def test_si_uno_es_invalido_no_se_guarda_ninguno(self):
        bueno = self.nombre("Bueno")
        datos = self.coleccion(
            geojson_cuadrado(bueno, 100.0, 10.0), self.corbata(self.nombre("Malo"))
        )
        with self.assertRaisesMessage(zonificacion.AnaliticaError, "reparar"):
            zonificacion.importar_distritos(datos)
        self.assertFalse(Distrito.objects.filter(nombre=bueno).exists())

    def test_reparar_corrige_el_poligono_invalido_y_lo_informa(self):
        malo = self.nombre("Reparado")
        resultado = zonificacion.importar_distritos(
            self.coleccion(self.corbata(malo)), reparar=True
        )
        self.assertEqual(resultado["reparados"], [malo])
        guardado = Distrito.objects.get(nombre=malo).geom
        self.assertTrue(guardado.valid)
        self.assertEqual(guardado.geom_type, "MultiPolygon")
        self.assertEqual(guardado.num_geom, 2)  # los dos triangulos de la corbata

    def test_excluir_omite_elementos_que_no_son_distritos(self):
        distrito, limite = self.nombre("Es distrito"), self.nombre("Limite municipal")
        datos = self.coleccion(
            geojson_cuadrado(distrito, 100.0, 10.0), geojson_cuadrado(limite, 100.2, 10.0)
        )
        resultado = zonificacion.importar_distritos(datos, excluir=[f"  {limite.upper()} "])
        self.assertEqual(resultado["creados"], 1)
        self.assertFalse(Distrito.objects.filter(nombre=limite).exists())

    def test_rechaza_nombre_faltante_geometria_no_poligonal_y_repetidos(self):
        sin_nombre = geojson_cuadrado("", 100.0, 10.0)
        linea = {
            "type": "Feature",
            "properties": {"nombre": self.nombre("Linea")},
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
        }
        repetido = geojson_cuadrado(self.nombre("Rep"), 100.0, 10.0)
        for datos in (
            self.coleccion(sin_nombre),
            self.coleccion(linea),
            self.coleccion(repetido, repetido),
            self.coleccion(),
        ):
            with self.assertRaises(zonificacion.AnaliticaError):
                zonificacion.importar_distritos(datos)


class ZonificacionApiTests(BaseAnaliticaTestCase):
    URLS = [
        "/api/analitica/mapa-calor/",
        "/api/analitica/distritos/",
        "/api/analitica/zonas-sugeridas/",
    ]

    def test_admin_y_oficial_consultan(self):
        for usuario in (self.admin, self.oficial):
            self.client.force_authenticate(usuario)
            for url in self.URLS:
                self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK, url)

    def test_inspector_no_entra_y_anonimo_es_401(self):
        self.client.force_authenticate(self.inspector)
        for url in self.URLS:
            self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN, url)
        self.client.force_authenticate(None)
        for url in self.URLS:
            self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED, url)

    def test_distritos_devuelve_la_geometria_geojson(self):
        distrito = self.crear_distrito("Api")
        self.client.force_authenticate(self.oficial)
        datos = self.client.get("/api/analitica/distritos/").data["distritos"]
        propio = next(d for d in datos if d["id"] == distrito.pk)
        self.assertEqual(propio["geom"]["type"], "MultiPolygon")

    def test_mapa_calor_valida_el_filtro_de_cluster(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/analitica/mapa-calor/", {"cluster": "Alto"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_zonas_sugeridas_valida_el_limite(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/analitica/zonas-sugeridas/", {"limite": 0})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
