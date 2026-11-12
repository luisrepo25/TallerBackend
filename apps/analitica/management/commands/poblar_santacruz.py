import json
import random
import uuid
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, Point, Polygon
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from apps.analitica import demo_simulacion as simulacion
from apps.analitica.models import ClusteringEjecucion, Distrito
from apps.analitica.services import ejecutar_clustering
from apps.campanias.models import Campania, CampaniaFuncionario
from apps.catastro.models import (
    CatalogoTipoAcople,
    CatalogoTipoPredio,
    Hidrante,
    Predio,
    PredioHidranteCobertura,
)
from apps.fiscalizacion.models import (
    ActaInspeccion,
    CatalogoEstadoExtintor,
    CatalogoInfraccion,
    CatalogoMaterialCombustible,
    EvidenciaFotografica,
    Infraccion,
    MaterialRegistrado,
    SolicitudMaterial,
)
from apps.fiscalizacion.services import (
    D_MAX,
    PESO_CARGA_FUEGO,
    PESO_DISTANCIA_HIDRANTE,
    PESO_ESTADO_EXTINTORES,
    PESO_FALLAS_ELECTRICAS,
    PESO_RUTAS_EVACUACION,
    Q_MAX,
    riesgo_extintores,
)
from apps.usuarios.models import Administrador, BitacoraAuditoria, Rol, Usuario
from apps.usuarios.services import crear_usuario, registrar_bitacora

MARCA_FUENTE = "OSM-SCZ-UUBR"
PREFIJO_HIDRANTE_SCZ = "HID-SCZ-"

ZONAS_DISTRITO = {
    "Distrito Urbano 1": (
        "DM-1 (Piraí / Equipetrol)",
        ["Av. San Martín", "Av. Busch", "Av. Roca y Coronado", "Av. La Salle", "3er Anillo Oeste"],
    ),
    "Distrito Urbano 2": (
        "DM-2 (Norte / Mutualista)",
        ["Av. Mutualista", "Av. Beni", "Av. Alemana", "3er Anillo Interno", "4to Anillo Norte"],
    ),
    "Distrito Urbano 3": (
        "DM-3 (Estación Argentina)",
        ["Av. Brasil", "Av. Paraguá", "Av. Virgen de Cotoca", "2do Anillo Este", "3er Anillo Este"],
    ),
    "Distrito Urbano 4": (
        "DM-4 (Pari / El Trompillo)",
        [
            "Av. Santos Dumont",
            "Av. El Trompillo",
            "Av. Grigotá",
            "Av. Las Américas",
            "2do Anillo Sur",
        ],
    ),
    "Distrito Urbano 5": (
        "DM-5 (Norte / Cristo Redentor)",
        [
            "Av. Cristo Redentor (Bánzer)",
            "Av. G77",
            "Av. Remanso",
            "5to Anillo Norte",
            "7mo Anillo Norte",
        ],
    ),
    "Distrito Urbano 6": (
        "DM-6 (Pampa de la Isla)",
        ["Av. Virgen de Cotoca", "Av. Virgen de Luján", "Carretera a Cotoca", "6to Anillo Este"],
    ),
    "Distrito Urbano 7": (
        "DM-7 (Villa 1ro de Mayo)",
        ["Av. Tres Pasos al Frente", "Av. Cumavi", "Av. 16 de Julio", "5to Anillo Sur-Este"],
    ),
    "Distrito Urbano 8": (
        "DM-8 (Plan 3000 / Andrés Ibáñez)",
        ["Av. Principal Plan 3000", "Av. El Mechero", "Av. Paurito", "Rotonda Plan 3000"],
    ),
    "Distrito Urbano 9": (
        "DM-9 (Palmasola / Sur)",
        ["Av. Moscú", "Av. Santos Dumont Sur", "5to Anillo Sur", "6to Anillo Sur"],
    ),
    "Distrito Urbano 10": (
        "DM-10 (El Bajío / Suroeste)",
        ["Doble Vía La Guardia", "Av. Radial 17 y Medio", "Av. Pirai Sur", "6to Anillo Suroeste"],
    ),
    "Distrito Urbano 11": (
        "DM-11 (Centro / Casco Viejo)",
        ["Calle René Moreno", "Av. Cañoto", "Av. Irala", "Calle Junín", "1er Anillo Centro"],
    ),
    "Distrito Urbano 12": (
        "DM-12 (Nuevo Palmar / Sur)",
        ["Av. Bolivia", "Av. Olímpica", "Prolongación Santos Dumont", "8vo Anillo Sur"],
    ),
    "Distrito 13": (
        "DM-13 (Palmar del Oratorio)",
        ["Av. Palmar del Oratorio", "Zona Sur Industrial"],
    ),
    "Distrito 14": (
        "DM-14 (Paurito)",
        ["Camino a Paurito", "Plaza Principal Paurito"],
    ),
    "Distrito 15 Montero Hoyos": (
        "DM-15 (Montero Hoyos)",
        ["Sector Montero Hoyos", "Camino Vecinal Este"],
    ),
    "Distrito Industrial": (
        "Distrito Industrial (Parque Industrial)",
        [
            "Parque Industrial Ramón Darío Gutiérrez",
            "Av. Parque Industrial PI-1",
            "Av. Parque Industrial PI-2",
            "4to Anillo Parque Industrial",
        ],
    ),
}

DESCRIPCIONES_INFRACCION = {
    "Cableado expuesto": [
        "Conductores eléctricos sin entubar en sector de depósito y tableros sin tapa de protección.",
        "Empalmes improvisados con cinta aislante y sobrecarga térmica en térmica principal.",
        "Tendido eléctrico aéreo en contacto con estructura metálica de cubierta sin puesta a tierra.",
    ],
    "Falta de senalizacion": [
        "Ausencia de señalética fotoluminiscente NB 55001 en cambios de dirección y salidas de emergencia.",
        "Falta señalización de ubicación y altura reglamentaria en extintores portátiles.",
        "Rutas de evacuación y punto de encuentro sin cartelería visible desde nave principal.",
    ],
    "Almacenamiento indebido de inflamables": [
        "Acopio de envases con solventes y GLP a menos de 3 metros de tableros seccionales.",
        "Almacenamiento de líquidos inflamables sin bandeja de contención ni ventilación cruzada.",
        "Depósito de materiales combustibles adyacente a fuente de calor sin muro cortafuego.",
    ],
    "Extintores con carga vencida": [
        "Manómetros en zona roja (despresurizados) y tarjetas de mantenimiento vencidas hace más de 6 meses.",
        "Extintores PQS ABC de 6 kg con fecha de prueba hidrostática y recarga anual vencida.",
        "Dotación insuficiente y extintores existentes con sello de seguridad roto y carga vencida.",
    ],
    "Obstruccion de salida de emergencia": [
        "Puerta de evacuación bloqueada con mercadería estibada y apertura hacia el interior.",
        "Pasillo de evacuación reducido a menos de 0.80 m por vitrinas y cajas apiladas.",
        "Salida secundaria asegurada con candado durante horario de atención al público.",
    ],
}

FOTOS_EVIDENCIA = [
    (
        "https://images.unsplash.com/photo-1581092160607-ee22621dd758?auto=format&fit=crop&w=800&q=80",
        "Tablero eléctrico secundario con conductores expuestos y sin disyuntor diferencial.",
    ),
    (
        "https://images.unsplash.com/photo-1581092335397-9583fe92d232?auto=format&fit=crop&w=800&q=80",
        "Verificación de presión manométrica y tarjeta de control en gabinete contra incendios.",
    ),
    (
        "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?auto=format&fit=crop&w=800&q=80",
        "Almacenamiento de carga combustible sólida en estanterías metálicas de depósito.",
    ),
    (
        "https://images.unsplash.com/photo-1504328345606-18bbc8c9d7d1?auto=format&fit=crop&w=800&q=80",
        "Inspección técnica de instalaciones y corredor de evacuación en nave principal.",
    ),
]


def _area_m2(geom) -> float:
    return round(geom.transform(32720, clone=True).area, 2)


def _aforo_estimado(tipo_predio: str, area_m2: float, rng: random.Random) -> int:
    factores = {
        "Salud": 0.12,
        "Educativo": 0.22,
        "Mercado Distrital": 0.35,
        "Comercial": 0.25,
        "Industrial": 0.06,
    }
    base = int(area_m2 * factores.get(tipo_predio, 0.15) * rng.uniform(0.75, 1.25))
    return max(25, min(base, 4500))


def _calcular_carga_y_scoring(
    *,
    materiales_tuplas: list[tuple[CatalogoMaterialCombustible, Decimal]],
    riesgo_activacion: Decimal,
    area_m2: Decimal,
    estado_extintores_nombre: str,
    fallas_electricas: bool,
    rutas_despejadas: bool,
    distancia_hidrante_m: Decimal | None,
) -> tuple[Decimal, Decimal]:
    total_energia = Decimal("0.00")
    for mat, peso_kg in materiales_tuplas:
        total_energia += peso_kg * mat.poder_calorifico_mj_kg * mat.coeficiente_peligrosidad

    area = area_m2 if area_m2 > Decimal("0.00") else Decimal("1.00")
    carga_fuego = ((total_energia * riesgo_activacion) / area).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    v_carga = min(max(carga_fuego, Decimal("0.00")) / Q_MAX, Decimal("1.00"))
    v_extintores = riesgo_extintores(estado_extintores_nombre)
    v_fallas = Decimal("1.00") if fallas_electricas else Decimal("0.00")
    v_rutas = Decimal("0.00") if rutas_despejadas else Decimal("1.00")
    if distancia_hidrante_m is None:
        v_distancia = Decimal("1.00")
    else:
        v_distancia = min(max(distancia_hidrante_m, Decimal("0.00")) / D_MAX, Decimal("1.00"))

    scoring = Decimal("100.00") * (
        (PESO_CARGA_FUEGO * v_carga)
        + (PESO_ESTADO_EXTINTORES * v_extintores)
        + (PESO_FALLAS_ELECTRICAS * v_fallas)
        + (PESO_RUTAS_EVACUACION * v_rutas)
        + (PESO_DISTANCIA_HIDRANTE * v_distancia)
    )
    return carga_fuego, scoring.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Command(BaseCommand):
    help = (
        "Puebla la base de datos con datos realistas y abundantes de Santa Cruz de la Sierra "
        "(personal UUBR, 35 hidrantes, ~330 predios reales OSM con direccion y distrito, "
        "7 campanias por zonas, ~460 actas de inspeccion y ejecucion real de K-Means)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limpiar",
            action="store_true",
            help="Elimina previamente los datos poblados antes de recargar.",
        )
        parser.add_argument(
            "--solo-limpiar",
            action="store_true",
            help="Solo elimina los datos poblados sin volver a cargar.",
        )

    def handle(self, *args, **options):
        if options["limpiar"] or options["solo_limpiar"]:
            self._limpiar()
            if options["solo_limpiar"]:
                return

        self._poblar()

    @transaction.atomic
    def _limpiar(self):
        self.stdout.write("Limpiando datos previos de poblar_santacruz / demo...")
        SolicitudMaterial.objects.all().delete()
        ActaInspeccion.objects.all().delete()
        CampaniaFuncionario.objects.all().delete()
        Campania.objects.all().delete()
        PredioHidranteCobertura.objects.all().delete()
        Predio.objects.all().delete()
        Hidrante.objects.all().delete()
        ClusteringEjecucion.objects.all().delete()
        BitacoraAuditoria.objects.all().delete()
        Usuario.objects.exclude(email="roly.hernandez@uubr.org.bo").delete()
        self.stdout.write(
            self.style.SUCCESS("Base limpia (conservando distritos, catalogos y admin Roly).")
        )

    def _poblar(self):
        rng = random.Random(202610)

        # 1. Administrador principal (Roly)
        admin_user = Usuario.objects.filter(email="roly.hernandez@uubr.org.bo").first()
        if not admin_user:
            rol_admin = Rol.objects.get(nombre="Administrador")
            admin_user = crear_usuario(
                nombre_completo="Cap. Roly Hernández Lijerón",
                email="roly.hernandez@uubr.org.bo",
                password="adminRoly",
                rol=rol_admin,
                subtipo="administrador",
                datos_subtipo={"nivel_acceso": "total"},
            )
        admin_obj = Administrador.objects.get(usuario=admin_user)

        # 2. Personal UUBR Santa Cruz (Oficiales de Mando e Inspectores Técnicos)
        rol_oficial = Rol.objects.get(nombre="Oficial de Mando")
        rol_inspector = Rol.objects.get(nombre="Inspector Tecnico")

        oficiales_data = [
            ("Cap. Carlos Alberto Méndez Roca", "carlos.mendez@uubr.org.bo", "Capitán UUBR"),
            ("Tte. Javier Mauricio Suárez Dorado", "javier.suarez@uubr.org.bo", "Teniente UUBR"),
        ]
        for nombre, email, rango in oficiales_data:
            if not Usuario.objects.filter(email=email).exists():
                crear_usuario(
                    nombre_completo=nombre,
                    email=email,
                    password="uubr2026",
                    rol=rol_oficial,
                    subtipo="oficial_mando",
                    datos_subtipo={"rango": rango},
                )

        inspectores_data = [
            (
                "Subtte. Marco Antonio Justiniano Vaca",
                "marco.justiniano@uubr.org.bo",
                date(2024, 3, 15),
            ),
            (
                "Subtte. Valeria Fernanda Coimbra Paz",
                "valeria.coimbra@uubr.org.bo",
                date(2024, 6, 10),
            ),
            (
                "Sgto. 1ro. Diego Alejandro Salvatierra",
                "diego.salvatierra@uubr.org.bo",
                date(2025, 1, 20),
            ),
            (
                "Sgto. 2do. Luis Fernando Cuéllar Ribera",
                "luis.cuellar@uubr.org.bo",
                date(2025, 5, 12),
            ),
        ]
        inspectores = []
        for nombre, email, fecha_cert in inspectores_data:
            u = Usuario.objects.filter(email=email).first()
            if not u:
                u = crear_usuario(
                    nombre_completo=nombre,
                    email=email,
                    password="uubr2026",
                    rol=rol_inspector,
                    subtipo="inspector_tecnico",
                    datos_subtipo={
                        "fecha_certificacion": fecha_cert,
                        "curso_capacitacion_completo": True,
                    },
                )
            inspectores.append(u.inspectortecnico)
        self.stdout.write(
            f"Personal UUBR listo: 1 Admin, 2 Oficiales de Mando, {len(inspectores)} Inspectores Técnicos."
        )

        # 3. Hidrantes en Santa Cruz de la Sierra (7 reales OSM + 28 estratégicos = 35 hidrantes)
        acoples = list(CatalogoTipoAcople.objects.order_by("id"))
        acople_storz = CatalogoTipoAcople.objects.get(nombre="Storz")
        ruta_hidrantes = settings.BASE_DIR / "datos" / "hidrantes_osm_santacruz.geojson"
        with open(ruta_hidrantes, encoding="utf-8") as f:
            features_hid = json.load(f)["features"]

        hidrantes_a_crear = []
        idx_hid = 1
        for feat in features_hid:
            lon, lat = feat["geometry"]["coordinates"]
            hidrantes_a_crear.append(
                Hidrante(
                    codigo=f"{PREFIJO_HIDRANTE_SCZ}{idx_hid:03d}",
                    estado_operativo=Hidrante.ESTADO_ACTIVO,
                    presion_nominal=Decimal(str(round(rng.uniform(3.8, 5.5), 2))),
                    tipo_acople=acople_storz,
                    geom=Point(lon, lat, srid=4326),
                    registrado_por=admin_user,
                )
            )
            idx_hid += 1

        # Puntos estrategicos reales en anillos, mercados, parque industrial y hospitales de SCZ
        puntos_estrategicos_scz = [
            (-63.1821, -17.7833),  # Plaza 24 de Septiembre / Casco Viejo
            (-63.1776, -17.7785),  # Mercado Los Pozos
            (-63.1878, -17.7815),  # Mercado Florida
            (-63.1912, -17.7892),  # Mercado Siete Calles / La Ramada Antigua
            (-63.1995, -17.7545),  # Ventura Mall / 4to Anillo Norte
            (-63.1765, -17.7492),  # Las Brisas / Av. Cristo Redentor
            (-63.1618, -17.7632),  # Mercado Mutualista / 3er Anillo
            (-63.1528, -17.7898),  # Feria Barrio Lindo
            (-63.1551, -17.7732),  # Hospital Japonés / 3er Anillo
            (-63.1578, -17.7672),  # Hospital Obrero Nro 3
            (-63.1515, -17.7582),  # Parque Industrial PI-1 (Ferrotodo/Belcorp)
            (-63.1468, -17.7575),  # Parque Industrial PI-2 (Enabolco/Faboce)
            (-63.1412, -17.7598),  # Parque Industrial PI-3 (Tigre)
            (-63.1475, -17.7621),  # UPSA / Parque Industrial Sur
            (-63.1921, -17.7768),  # Campus UAGRM / 2do Anillo
            (-63.1965, -17.7755),  # Módulos UAGRM / Av. Busch
            (-63.2015, -17.7678),  # Equipetrol / UTEPSA - UDABOL
            (-63.1975, -17.7968),  # Clínica Urbarí / Av. Irala
            (-63.1791, -17.7983),  # Cine Center / El Trompillo
            (-63.2056, -17.7906),  # Centro Comercial Chiriguano / Doble Vía La Guardia
            (-63.1802, -17.8158),  # La Morita / 4to Anillo Sur
            (-63.1472, -17.8212),  # Mercado Modelo Plan 3000 (DM-8)
            (-63.1368, -17.7911),  # Villa 1ro de Mayo (DM-7)
            (-63.1245, -17.7725),  # Pampa de la Isla / Av. Virgen de Cotoca (DM-6)
            (-63.1778, -17.8296),  # Palmasola / Centro Salud DM-9
            (-63.2148, -17.7768),  # Multicenter Oeste / 4to Anillo Roca y Coronado
            (-63.1655, -17.7288),  # Av. Banzer 6to Anillo Norte (DM-5)
            (-63.1742, -17.8328),  # Nuevo Palmar / Zona Sur (DM-12)
        ]
        for lon, lat in puntos_estrategicos_scz:
            es_inoperativo = idx_hid in (12, 19, 27, 33)
            hidrantes_a_crear.append(
                Hidrante(
                    codigo=f"{PREFIJO_HIDRANTE_SCZ}{idx_hid:03d}",
                    estado_operativo=(
                        Hidrante.ESTADO_FUERA_DE_SERVICIO
                        if es_inoperativo
                        else Hidrante.ESTADO_ACTIVO
                    ),
                    presion_nominal=Decimal(
                        str(
                            round(
                                rng.uniform(1.1, 1.8) if es_inoperativo else rng.uniform(3.5, 5.8),
                                2,
                            )
                        )
                    ),
                    tipo_acople=rng.choice(acoples),
                    geom=Point(lon, lat, srid=4326),
                    registrado_por=admin_user,
                )
            )
            idx_hid += 1

        Hidrante.objects.bulk_create(hidrantes_a_crear)
        self.stdout.write(
            f"Hidrantes creados: {len(hidrantes_a_crear)} (31 activos, 4 fuera de servicio)."
        )

        # 4. Selección de 330 Predios Reales de Santa Cruz desde OpenStreetMap
        distritos = list(Distrito.objects.order_by("id"))
        tipos_predio = {t.nombre: t for t in CatalogoTipoPredio.objects.all()}

        ruta_predios = settings.BASE_DIR / "datos" / "predios_osm_santacruz.geojson"
        with open(ruta_predios, encoding="utf-8") as f:
            seleccionados = json.load(f)["features"]

        predios_objs = []
        meta_predios = []
        for feat in seleccionados:
            props = feat["properties"]
            geom = GEOSGeometry(json.dumps(feat["geometry"]), srid=4326)
            centro = geom.centroid
            distrito_nombre = "Distrito Urbano 11"
            for d in distritos:
                if d.geom.contains(centro):
                    distrito_nombre = d.nombre
                    break

            zona_label, avenidas = ZONAS_DISTRITO.get(
                distrito_nombre,
                (distrito_nombre, ["Av. Circunvalación", "Av. Principal"]),
            )
            avenida = rng.choice(avenidas)
            uv = rng.randint(1, 210)
            mz = rng.randint(1, 65)
            direccion = f"{zona_label}, {avenida} (UV-{uv:03d}, Mz-{mz:02d})"

            area = _area_m2(geom)
            tipo_str = props["tipo_predio"]
            aforo = _aforo_estimado(tipo_str, area, rng)
            niveles = (
                rng.randint(1, 2)
                if tipo_str in ("Industrial", "Mercado Distrital")
                else rng.randint(2, 6)
            )

            predios_objs.append(
                Predio(
                    nombre=props["nombre"][:150],
                    direccion=direccion[:255],
                    tipo_predio=tipos_predio[tipo_str],
                    aforo=aforo,
                    area_m2=Decimal(str(area)),
                    atributos_extra={
                        "fuente": MARCA_FUENTE,
                        "osm_id": props["osm_id"],
                        "tipo_osm": props.get("tipo_osm", ""),
                        "distrito": distrito_nombre,
                        "niveles": niveles,
                        "tiene_sotano": tipo_str == "Comercial" and area > 2500,
                    },
                    geom=geom,
                    registrado_por=admin_user,
                )
            )
            meta_predios.append((tipo_str, distrito_nombre, centro))

        Predio.objects.bulk_create(predios_objs)
        self.stdout.write(f"Predios reales de Santa Cruz creados: {len(predios_objs)}.")

        # 5. Calcular cobertura PostGIS Predio <-> Hidrante en lote (RF-6)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO predio_hidrante_cobertura (
                    predio_id, hidrante_id, distancia_m, es_mas_cercano, fecha_calculo
                )
                SELECT
                    p.id,
                    h.id,
                    ROUND(ST_Distance(p.geom::geography, h.geom::geography)::numeric, 2),
                    (ROW_NUMBER() OVER (
                        PARTITION BY p.id
                        ORDER BY ST_Distance(p.geom::geography, h.geom::geography) ASC, h.id ASC
                    ) = 1),
                    NOW()
                FROM predios p
                CROSS JOIN hidrantes h
                WHERE h.estado_operativo = 'activo';
                """
            )
        distancias_mas_cercanas = dict(
            PredioHidranteCobertura.objects.filter(es_mas_cercano=True).values_list(
                "predio_id", "distancia_m"
            )
        )
        self.stdout.write(
            f"Cobertura espacial calculada para {len(distancias_mas_cercanas)} predios con hidrante cercano."
        )

        # 6. Crear 7 Campañas de Fiscalización en Santa Cruz de la Sierra
        hoy = timezone.localdate()

        def _bbox_de(lista_predios: list[Predio], margen: float = 0.0025) -> Polygon:
            extents = [p.geom.extent for p in lista_predios]
            poly = Polygon.from_bbox(
                (
                    min(e[0] for e in extents) - margen,
                    min(e[1] for e in extents) - margen,
                    max(e[2] for e in extents) + margen,
                    max(e[3] for e in extents) + margen,
                )
            )
            poly.srid = 4326
            return poly

        # Agrupar predios por sector para las 4 campañas históricas cerradas
        grupo_industrial_este = []
        grupo_mercados_centro = []
        grupo_norte_oeste = []
        grupo_sur_populosos = []

        for predio, (tipo_str, dist_nombre, centro) in zip(predios_objs, meta_predios, strict=True):
            if dist_nombre in (
                "Distrito Industrial",
                "Distrito Urbano 3",
                "Distrito Urbano 6",
                "Distrito 15 Montero Hoyos",
            ):
                grupo_industrial_este.append((predio, tipo_str))
            elif tipo_str == "Mercado Distrital" or dist_nombre in (
                "Distrito Urbano 11",
                "Distrito Urbano 2",
            ):
                grupo_mercados_centro.append((predio, tipo_str))
            elif (
                dist_nombre in ("Distrito Urbano 1", "Distrito Urbano 5", "Distrito Urbano 10")
                or centro.y > -17.780
            ):
                grupo_norte_oeste.append((predio, tipo_str))
            else:
                grupo_sur_populosos.append((predio, tipo_str))

        campania_1 = Campania.objects.create(
            nombre="Campaña I-2026: Fiscalización Parque Industrial y Sector Este",
            fecha_inicio=hoy - timedelta(days=120),
            fecha_fin=hoy - timedelta(days=90),
            estado=Campania.ESTADO_CERRADA,
            geom=_bbox_de([p for p, _ in grupo_industrial_este]),
            creado_por=admin_obj,
        )
        campania_2 = Campania.objects.create(
            nombre="Campaña II-2026: Operativo Mercados Municipales y Abastecimiento SCZ",
            fecha_inicio=hoy - timedelta(days=89),
            fecha_fin=hoy - timedelta(days=60),
            estado=Campania.ESTADO_CERRADA,
            geom=_bbox_de([p for p, _ in grupo_mercados_centro]),
            creado_por=admin_obj,
        )
        campania_3 = Campania.objects.create(
            nombre="Campaña III-2026: Inspección Comercios, Salud y Educación Norte-Oeste",
            fecha_inicio=hoy - timedelta(days=59),
            fecha_fin=hoy - timedelta(days=30),
            estado=Campania.ESTADO_CERRADA,
            geom=_bbox_de([p for p, _ in grupo_norte_oeste]),
            creado_por=admin_obj,
        )
        campania_4 = Campania.objects.create(
            nombre="Campaña IV-2026: Control Preventivo Zona Sur, Plan 3000 y Villa 1ro de Mayo",
            fecha_inicio=hoy - timedelta(days=29),
            fecha_fin=hoy - timedelta(days=5),
            estado=Campania.ESTADO_CERRADA,
            geom=_bbox_de([p for p, _ in grupo_sur_populosos]),
            creado_por=admin_obj,
        )

        # 2 campañas EN CURSO con polígonos acotados dentro de DM-11 (Casco Viejo) y DM-1 (Equipetrol)
        poly_casco_viejo = Polygon.from_bbox((-63.1865, -17.7885, -63.1755, -17.7770))
        poly_casco_viejo.srid = 4326
        campania_en_curso_1 = Campania.objects.create(
            nombre="Operativo En Curso: Control Preventivo Casco Viejo (DM-11)",
            fecha_inicio=hoy - timedelta(days=10),
            fecha_fin=hoy + timedelta(days=20),
            estado=Campania.ESTADO_EN_CURSO,
            geom=poly_casco_viejo,
            creado_por=admin_obj,
        )

        poly_equipetrol = Polygon.from_bbox((-63.2045, -17.7760, -63.1910, -17.7520))
        poly_equipetrol.srid = 4326
        campania_en_curso_2 = Campania.objects.create(
            nombre="Operativo En Curso: Fiscalización Corredor Equipetrol y UAGRM (DM-1)",
            fecha_inicio=hoy - timedelta(days=7),
            fecha_fin=hoy + timedelta(days=23),
            estado=Campania.ESTADO_EN_CURSO,
            geom=poly_equipetrol,
            creado_por=admin_obj,
        )

        # 1 campaña PENDIENTE programada en zona norte (DM-5)
        poly_pendiente_norte = Polygon.from_bbox((-63.1790, -17.7530, -63.1640, -17.7270))
        poly_pendiente_norte.srid = 4326
        Campania.objects.create(
            nombre="Operativo Programado: Verificación Preventiva Eje Norte Banzer (DM-5)",
            fecha_inicio=hoy + timedelta(days=4),
            fecha_fin=hoy + timedelta(days=34),
            estado=Campania.ESTADO_PENDIENTE,
            geom=poly_pendiente_norte,
            creado_por=admin_obj,
        )

        # Asignar inspectores a las campañas cerradas y en curso
        asignaciones = []
        for camp in (
            campania_1,
            campania_2,
            campania_3,
            campania_4,
            campania_en_curso_1,
            campania_en_curso_2,
        ):
            for insp in inspectores:
                asignaciones.append(CampaniaFuncionario(campania=camp, usuario=insp))
        CampaniaFuncionario.objects.bulk_create(asignaciones)
        self.stdout.write(
            "7 campañas creadas (4 cerradas, 2 en curso, 1 pendiente) y brigadas asignadas."
        )

        # 7. Generar ~465 Actas de Inspección con cálculo exacto NB 58005 y Scoring
        estados_ext = {e.nombre: e for e in CatalogoEstadoExtintor.objects.all()}
        materiales_cat = {m.nombre: m for m in CatalogoMaterialCombustible.objects.all()}
        infracciones_cat = {i.nombre: i for i in CatalogoInfraccion.objects.all()}
        nombres_mat = sorted(materiales_cat.keys())
        nombres_inf = sorted(infracciones_cat.keys())

        actas_a_crear: list[ActaInspeccion] = []
        detalle_actas: list[dict] = []

        grupos_campanias = [
            (campania_1, grupo_industrial_este, 115, 92),
            (campania_2, grupo_mercados_centro, 88, 62),
            (campania_3, grupo_norte_oeste, 58, 32),
            (campania_4, grupo_sur_populosos, 28, 7),
        ]

        for campania, lista_predios, dias_inicio_atras, dias_fin_atras in grupos_campanias:
            for predio, tipo_str in lista_predios:
                riesgo_base = simulacion.riesgo_latente(tipo_str, rng)
                # 36% de los predios reciben una reinspección dentro del periodo
                es_reinspeccionado = rng.random() < 0.36
                niveles = [riesgo_base]
                if es_reinspeccionado:
                    niveles.append(simulacion.riesgo_en_reinspeccion(riesgo_base, rng))

                infracciones_previas_predio: set[str] = set()
                for idx_visita, r_nivel in enumerate(niveles):
                    sim = simulacion.simular_inspeccion(
                        r_nivel, float(predio.area_m2), nombres_mat, nombres_inf, rng
                    )
                    mat_tuplas = [
                        (materiales_cat[nombre_m], Decimal(str(kg)))
                        for nombre_m, kg in sim.materiales
                    ]
                    dist_m = distancias_mas_cercanas.get(predio.pk)
                    carga_fuego, scoring_riesgo = _calcular_carga_y_scoring(
                        materiales_tuplas=mat_tuplas,
                        riesgo_activacion=predio.tipo_predio.riesgo_activacion,
                        area_m2=predio.area_m2,
                        estado_extintores_nombre=sim.extintores,
                        fallas_electricas=sim.fallas_electricas,
                        rutas_despejadas=sim.rutas_despejadas,
                        distancia_hidrante_m=dist_m,
                    )

                    dias_atras = (
                        rng.randint(dias_fin_atras + 10, dias_inicio_atras)
                        if idx_visita == 0
                        else rng.randint(dias_fin_atras, dias_fin_atras + 9)
                    )
                    fecha_insp = timezone.make_aware(
                        datetime.combine(
                            hoy - timedelta(days=dias_atras),
                            time(rng.randint(8, 17), rng.randint(0, 59)),
                        )
                    )
                    fecha_cierre = fecha_insp + timedelta(minutes=rng.randint(25, 95))

                    acta = ActaInspeccion(
                        uuid_local=uuid.uuid4(),
                        predio=predio,
                        campania=campania,
                        inspector=rng.choice(inspectores),
                        fecha_inspeccion=fecha_insp,
                        carga_fuego=carga_fuego,
                        estado_extintores=estados_ext[sim.extintores],
                        fallas_electricas=sim.fallas_electricas,
                        rutas_evacuacion_despejadas=sim.rutas_despejadas,
                        distancia_hidrante_m=dist_m,
                        scoring_riesgo=scoring_riesgo,
                        cluster_riesgo=None,
                        cerrada=True,
                        fecha_cierre=fecha_cierre,
                        sincronizada=True,
                        fecha_sincronizacion=fecha_cierre + timedelta(minutes=5),
                    )
                    actas_a_crear.append(acta)

                    infracciones_visita = []
                    for inf_nombre in sim.infracciones:
                        es_reinc = inf_nombre in infracciones_previas_predio
                        infracciones_previas_predio.add(inf_nombre)
                        infracciones_visita.append((inf_nombre, es_reinc))

                    detalle_actas.append(
                        {
                            "materiales": mat_tuplas,
                            "infracciones": infracciones_visita,
                            "fecha": fecha_insp,
                            "con_evidencia": bool(infracciones_visita) and rng.random() < 0.48,
                        }
                    )

        # Además, agregar actas en las 2 campañas EN CURSO (65% cerradas + 3 abiertas en campo)
        for camp_activa, dias_atras_max in ((campania_en_curso_1, 9), (campania_en_curso_2, 6)):
            predios_en_zona = [p for p in predios_objs if p.geom.intersects(camp_activa.geom)]
            cantidad_inspeccionar = max(1, int(len(predios_en_zona) * 0.68))
            elegidos_zona = predios_en_zona[:cantidad_inspeccionar]
            for idx_z, predio in enumerate(elegidos_zona):
                tipo_str = predio.tipo_predio.nombre
                r_nivel = simulacion.riesgo_latente(tipo_str, rng)
                sim = simulacion.simular_inspeccion(
                    r_nivel, float(predio.area_m2), nombres_mat, nombres_inf, rng
                )
                mat_tuplas = [
                    (materiales_cat[nombre_m], Decimal(str(kg))) for nombre_m, kg in sim.materiales
                ]
                dist_m = distancias_mas_cercanas.get(predio.pk)
                es_abierta = (
                    idx_z == len(elegidos_zona) - 1
                )  # 1 acta en borrador por campaña activa

                if es_abierta:
                    carga_fuego, scoring_riesgo = None, None
                    fecha_cierre = None
                else:
                    carga_fuego, scoring_riesgo = _calcular_carga_y_scoring(
                        materiales_tuplas=mat_tuplas,
                        riesgo_activacion=predio.tipo_predio.riesgo_activacion,
                        area_m2=predio.area_m2,
                        estado_extintores_nombre=sim.extintores,
                        fallas_electricas=sim.fallas_electricas,
                        rutas_despejadas=sim.rutas_despejadas,
                        distancia_hidrante_m=dist_m,
                    )

                fecha_insp = timezone.make_aware(
                    datetime.combine(
                        hoy - timedelta(days=rng.randint(1, dias_atras_max)),
                        time(rng.randint(8, 16), rng.randint(0, 59)),
                    )
                )
                if not es_abierta:
                    fecha_cierre = fecha_insp + timedelta(minutes=rng.randint(30, 80))

                acta = ActaInspeccion(
                    uuid_local=uuid.uuid4(),
                    predio=predio,
                    campania=camp_activa,
                    inspector=rng.choice(inspectores),
                    fecha_inspeccion=fecha_insp,
                    carga_fuego=carga_fuego,
                    estado_extintores=estados_ext[sim.extintores],
                    fallas_electricas=sim.fallas_electricas,
                    rutas_evacuacion_despejadas=sim.rutas_despejadas,
                    distancia_hidrante_m=dist_m,
                    scoring_riesgo=scoring_riesgo,
                    cluster_riesgo=None,
                    cerrada=not es_abierta,
                    fecha_cierre=fecha_cierre,
                    sincronizada=True,
                    fecha_sincronizacion=fecha_cierre if fecha_cierre else fecha_insp,
                )
                actas_a_crear.append(acta)
                detalle_actas.append(
                    {
                        "materiales": mat_tuplas,
                        "infracciones": [(inf_n, True) for inf_n in sim.infracciones],
                        "fecha": fecha_insp,
                        "con_evidencia": bool(sim.infracciones) and rng.random() < 0.60,
                    }
                )

        ActaInspeccion.objects.bulk_create(actas_a_crear)
        # Restaurar las fechas históricas exactas (auto_now_add las pisa al hacer bulk_create)
        ActaInspeccion.objects.bulk_update(actas_a_crear, ["fecha_inspeccion"])

        # 8. Insertar Materiales Registrados, Infracciones y Evidencias Fotográficas en lote
        materiales_objs = []
        infracciones_objs = []
        evidencias_objs = []

        for acta, det in zip(actas_a_crear, detalle_actas, strict=True):
            for mat, peso_kg in det["materiales"]:
                materiales_objs.append(MaterialRegistrado(acta=acta, material=mat, peso_kg=peso_kg))
            for inf_nombre, es_reinc in det["infracciones"]:
                textos = DESCRIPCIONES_INFRACCION.get(
                    inf_nombre, ["Observación técnica registrada durante la inspección de campo."]
                )
                infracciones_objs.append(
                    Infraccion(
                        acta=acta,
                        tipo_infraccion=infracciones_cat[inf_nombre],
                        descripcion=rng.choice(textos),
                        es_reincidencia=es_reinc,
                        fecha_registro=det["fecha"],
                    )
                )
            if det["con_evidencia"]:
                url_img, desc_img = rng.choice(FOTOS_EVIDENCIA)
                evidencias_objs.append(
                    EvidenciaFotografica(
                        acta=acta,
                        url_imagen=url_img,
                        descripcion_infraccion=desc_img,
                        fecha_captura=det["fecha"],
                    )
                )

        MaterialRegistrado.objects.bulk_create(materiales_objs)
        Infraccion.objects.bulk_create(infracciones_objs)
        EvidenciaFotografica.objects.bulk_create(evidencias_objs)

        cerradas_count = sum(1 for a in actas_a_crear if a.cerrada)
        abiertas_count = sum(1 for a in actas_a_crear if not a.cerrada)
        reincidencias_count = sum(1 for i in infracciones_objs if i.es_reincidencia)
        self.stdout.write(
            f"Actas creadas: {len(actas_a_crear)} ({cerradas_count} cerradas, {abiertas_count} abiertas). "
            f"Materiales: {len(materiales_objs)}, Infracciones: {len(infracciones_objs)} "
            f"({reincidencias_count} reincidencias), Evidencias: {len(evidencias_objs)}."
        )

        # 9. Crear Solicitudes de Material Móvil (Fase 7) para pruebas en el frontend
        solicitudes_data = [
            (
                "Espuma de Poliuretano Expandido",
                "Aislante acústico y relleno en galpones comerciales y tapicerías del Parque Industrial.",
                Decimal("450.00"),
                inspectores[0],
                SolicitudMaterial.ESTADO_PENDIENTE,
                None,
                None,
                None,
            ),
            (
                "Aceite Dielectrico para Transformadores",
                "Detectado en subestaciones internas de plantas industriales en DM-Industrial.",
                Decimal("1200.00"),
                inspectores[1],
                SolicitudMaterial.ESTADO_PENDIENTE,
                None,
                None,
                None,
            ),
            (
                "Baterías de Litio (Almacenamiento Comercial)",
                "Importadoras de repuestos electrónicos en Mercado Los Pozos y Barrio Lindo.",
                Decimal("320.00"),
                inspectores[2],
                SolicitudMaterial.ESTADO_RECHAZADA,
                None,
                admin_obj,
                "Clasificar bajo Plásticos (polietileno/PVC) o químicos existentes según ficha técnica NB 58005.",
            ),
        ]
        for (
            nom_sol,
            desc_sol,
            peso_est,
            solicitante,
            est_sol,
            mat_asoc,
            res_por,
            motivo,
        ) in solicitudes_data:
            SolicitudMaterial.objects.create(
                uuid_local=uuid.uuid4(),
                nombre=nom_sol,
                descripcion=desc_sol,
                peso_kg_estimado=peso_est,
                solicitante=solicitante,
                estado=est_sol,
                material=mat_asoc,
                resuelta_por=res_por,
                motivo_rechazo=motivo,
                fecha_resolucion=timezone.now() if res_por else None,
            )

        # 10. Registrar Bitácora de Auditoría representativa
        acciones_bitacora = [
            (admin_user, "Importar distritos municipales GAMSC (16 distritos)", "Distrito"),
            (admin_user, "Registrar red de hidrantes Santa Cruz de la Sierra", "Hidrante"),
            (admin_user, "Crear campania de fiscalizacion", "Campania"),
            (admin_user, "Asignar brigada de inspectores tecnicos", "CampaniaFuncionario"),
            (
                inspectores[0].usuario,
                "Sincronizar lote de actas de inspeccion desde app movil",
                "ActaInspeccion",
            ),
            (inspectores[1].usuario, "Registrar acta de inspeccion", "ActaInspeccion"),
            (inspectores[2].usuario, "Cerrar acta de inspeccion", "ActaInspeccion"),
        ]
        for usr, accion, entidad in acciones_bitacora:
            registrar_bitacora(usuario=usr, accion=accion, entidad_afectada=entidad)

        # 11. Entrenar y ejecutar Clustering K-Means real contra el Microservicio ML
        self.stdout.write(
            "Entrenando modelo K-Means en el Microservicio ML con todas las actas cerradas..."
        )
        resultado_ml = ejecutar_clustering(usuario=admin_user)
        ejecucion = resultado_ml["ejecucion"]
        self.stdout.write(
            self.style.SUCCESS(
                f"Clustering K-Means completado: {resultado_ml['cantidad_actas']} actas clasificadas | "
                f"k={ejecucion.k_value} | Coeficiente de Silueta={ejecucion.coeficiente_silueta:.4f} | "
                f"Resumen={resultado_ml['resumen']}"
            )
        )
