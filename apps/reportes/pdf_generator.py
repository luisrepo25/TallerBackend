import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Paleta institucional
COLOR_MARINO = colors.HexColor("#14213D")
COLOR_MARINO_SEC = colors.HexColor("#1F3357")
COLOR_ROJO = colors.HexColor("#D7263D")
COLOR_BORDE = colors.HexColor("#E2E8F0")
COLOR_FONDO_TABLA = colors.HexColor("#F8FAFC")
COLOR_TEXTO_SEC = colors.HexColor("#5C6773")
COLOR_BAJO = colors.HexColor("#2E7D32")
COLOR_MEDIO = colors.HexColor("#F9A825")
COLOR_CRITICO = colors.HexColor("#D7263D")


class NumberedCanvas(canvas.Canvas):
    """Canvas de dos pasadas que dibuja pie de pagina con 'Pagina X de Y' y membrete
    inferior."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_decorations(self, page_count):
        self.saveState()
        width, height = A4

        # Encabezado fino en paginas > 1
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(COLOR_MARINO)
            self.drawString(1.8 * cm, height - 1.2 * cm, "BOMBEROS VOLUNTARIOS UUBR")
            self.setFont("Helvetica", 8)
            self.setFillColor(COLOR_TEXTO_SEC)
            self.drawRightString(
                width - 1.8 * cm,
                height - 1.2 * cm,
                "SIG Riesgo de Incendios · Santa Cruz de la Sierra",
            )
            self.setStrokeColor(COLOR_BORDE)
            self.setLineWidth(0.5)
            self.line(1.8 * cm, height - 1.35 * cm, width - 1.8 * cm, height - 1.35 * cm)

        # Pie de pagina institucional
        self.setStrokeColor(COLOR_BORDE)
        self.setLineWidth(0.5)
        self.line(1.8 * cm, 1.5 * cm, width - 1.8 * cm, 1.5 * cm)

        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(COLOR_ROJO)
        self.drawString(1.8 * cm, 1.1 * cm, "UUBR")
        self.setFont("Helvetica", 8)
        self.setFillColor(COLOR_TEXTO_SEC)
        self.drawString(
            2.8 * cm,
            1.1 * cm,
            "· Prevención y Respuesta a Emergencias · Santa Cruz de la Sierra, Bolivia",
        )

        pag_txt = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(width - 1.8 * cm, 1.1 * cm, pag_txt)
        self.restoreState()


def _crear_estilos():
    base = getSampleStyleSheet()
    estilos = {
        "Titulo": ParagraphStyle(
            "ReporteTitulo",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=COLOR_MARINO,
            alignment=1,  # Centro
        ),
        "Subtitulo": ParagraphStyle(
            "ReporteSubtitulo",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=COLOR_ROJO,
            alignment=1,
        ),
        "Seccion": ParagraphStyle(
            "ReporteSeccion",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=COLOR_MARINO,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "Texto": ParagraphStyle(
            "ReporteTexto",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=COLOR_MARINO,
        ),
        "TextoBold": ParagraphStyle(
            "ReporteTextoBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=COLOR_MARINO,
        ),
        "TablaHead": ParagraphStyle(
            "ReporteTablaHead",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.white,
            alignment=1,
        ),
        "TablaCell": ParagraphStyle(
            "ReporteTablaCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=COLOR_MARINO,
        ),
        "TablaCellBold": ParagraphStyle(
            "ReporteTablaCellBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=COLOR_MARINO,
        ),
        "TablaCellCenter": ParagraphStyle(
            "ReporteTablaCellCenter",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=COLOR_MARINO,
            alignment=1,
        ),
        "TablaCellNum": ParagraphStyle(
            "ReporteTablaCellNum",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=COLOR_MARINO,
            alignment=2,  # Derecha
        ),
        "DictamenBox": ParagraphStyle(
            "DictamenBox",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.white,
            alignment=1,
        ),
    }
    return estilos


def generar_pdf_ejecutivo(datos: dict) -> bytes:
    """Genera el PDF del Reporte Ejecutivo de una campaña de fiscalización."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=2.0 * cm,
    )
    est = _crear_estilos()
    story = []
    ancho_util = A4[0] - 3.6 * cm

    # Encabezado Institucional
    story.append(Paragraph("BOMBEROS VOLUNTARIOS UUBR", est["Titulo"]))
    story.append(
        Paragraph("SISTEMA DE EVALUACIÓN Y ZONIFICACIÓN DE RIESGO DE INCENDIOS", est["TextoBold"])
    )
    story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            f"REPORTE EJECUTIVO DE CAMPAÑA: {datos['campania']['nombre'].upper()}",
            est["Subtitulo"],
        )
    )
    story.append(Spacer(1, 8))
    story.append(
        HRFlowable(width="100%", thickness=1.5, color=COLOR_ROJO, spaceBefore=2, spaceAfter=8)
    )

    # 1. Informacion General
    story.append(Paragraph("1. INFORMACIÓN DE LA CAMPAÑA", est["Seccion"]))
    tabla_info_data = [
        [
            Paragraph("<b>Campaña:</b>", est["TextoBold"]),
            Paragraph(datos["campania"]["nombre"], est["Texto"]),
            Paragraph("<b>Estado:</b>", est["TextoBold"]),
            Paragraph(datos["campania"]["estado"].capitalize(), est["Texto"]),
        ],
        [
            Paragraph("<b>Vigencia:</b>", est["TextoBold"]),
            Paragraph(
                f"{datos['campania']['fecha_inicio']} al {datos['campania']['fecha_fin']}",
                est["Texto"],
            ),
            Paragraph("<b>Creada por:</b>", est["TextoBold"]),
            Paragraph(datos["campania"]["creado_por"], est["Texto"]),
        ],
        [
            Paragraph("<b>Inspectores:</b>", est["TextoBold"]),
            Paragraph(
                ", ".join(datos["campania"]["inspectores"]) or "Sin inspectores asignados",
                est["Texto"],
            ),
            Paragraph("<b>Emisión:</b>", est["TextoBold"]),
            Paragraph(datos.get("fecha_emision", "—"), est["Texto"]),
        ],
    ]
    t_info = Table(tabla_info_data, colWidths=[3 * cm, 5.5 * cm, 3 * cm, 5.9 * cm])
    t_info.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_FONDO_TABLA),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t_info)
    story.append(Spacer(1, 8))

    # 2. Avance Territorial
    story.append(Paragraph("2. AVANCE TERRITORIAL DE INSPECCIONES", est["Seccion"]))
    tabla_avance_data = [
        [
            Paragraph("Predios en Polígono", est["TablaHead"]),
            Paragraph("Predios Inspeccionados", est["TablaHead"]),
            Paragraph("Actas Cerradas", est["TablaHead"]),
            Paragraph("Actas en Curso", est["TablaHead"]),
            Paragraph("% Cumplimiento", est["TablaHead"]),
        ],
        [
            Paragraph(str(datos["avance"]["total_predios"]), est["TablaCellCenter"]),
            Paragraph(str(datos["avance"]["total_inspeccionados"]), est["TablaCellCenter"]),
            Paragraph(str(datos["avance"]["actas_cerradas"]), est["TablaCellCenter"]),
            Paragraph(str(datos["avance"]["actas_abiertas"]), est["TablaCellCenter"]),
            Paragraph(f"<b>{datos['avance']['porcentaje_avance']}%</b>", est["TablaCellCenter"]),
        ],
    ]
    t_avance = Table(tabla_avance_data, colWidths=[ancho_util / 5] * 5)
    t_avance.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_MARINO),
                ("BACKGROUND", (0, 1), (-1, 1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t_avance)
    story.append(Spacer(1, 8))

    # 3. Evaluacion y Distribucion de Riesgo
    story.append(
        Paragraph("3. EVALUACIÓN Y DISTRIBUCIÓN DE RIESGO (K-MEANS / NB 58005)", est["Seccion"])
    )
    r = datos["riesgo"]
    tabla_riesgo_data = [
        [
            Paragraph("Nivel de Riesgo (Cluster)", est["TablaHead"]),
            Paragraph("Predios Clasificados", est["TablaHead"]),
            Paragraph("Proporción territorial (%)", est["TablaHead"]),
        ],
        [
            Paragraph("<font color='#D7263D'><b>● Riesgo Crítico</b></font>", est["TablaCellBold"]),
            Paragraph(str(r["critico"]), est["TablaCellNum"]),
            Paragraph(f"{r['pct_critico']}%", est["TablaCellNum"]),
        ],
        [
            Paragraph("<font color='#F9A825'><b>● Riesgo Medio</b></font>", est["TablaCellBold"]),
            Paragraph(str(r["medio"]), est["TablaCellNum"]),
            Paragraph(f"{r['pct_medio']}%", est["TablaCellNum"]),
        ],
        [
            Paragraph("<font color='#2E7D32'><b>● Riesgo Bajo</b></font>", est["TablaCellBold"]),
            Paragraph(str(r["bajo"]), est["TablaCellNum"]),
            Paragraph(f"{r['pct_bajo']}%", est["TablaCellNum"]),
        ],
        [
            Paragraph("Sin clasificar (Pendientes)", est["TablaCell"]),
            Paragraph(str(r["sin_clasificar"]), est["TablaCellNum"]),
            Paragraph(f"{r['pct_sin_clasificar']}%", est["TablaCellNum"]),
        ],
    ]
    t_riesgo = Table(
        tabla_riesgo_data,
        colWidths=[ancho_util * 0.45, ancho_util * 0.27, ancho_util * 0.28],
    )
    t_riesgo.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_MARINO),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_FONDO_TABLA]),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(t_riesgo)
    story.append(Spacer(1, 6))

    # Indicadores globales
    indicadores_data = [
        [
            Paragraph(
                f"<b>Scoring de Riesgo Promedio:</b> {r['scoring_promedio']} / 100 pts",
                est["Texto"],
            ),
            Paragraph(
                f"<b>Carga de Fuego Promedio:</b> {r['carga_fuego_promedio']} MJ/m²", est["Texto"]
            ),
            Paragraph(
                f"<b>Distancia Media a Hidrante:</b> {r['distancia_hidrante_promedio']} m",
                est["Texto"],
            ),
        ]
    ]
    t_ind = Table(indicadores_data, colWidths=[ancho_util / 3] * 3)
    t_ind.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_FONDO_TABLA),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(t_ind)
    story.append(Spacer(1, 8))

    # 4. Infracciones
    if datos["infracciones"]:
        story.append(Paragraph("4. INFRACCIONES MÁS COMUNES EN CAMPAÑA", est["Seccion"]))
        inf_data = [
            [
                Paragraph("Infracción detectada", est["TablaHead"]),
                Paragraph("Casos", est["TablaHead"]),
                Paragraph("Reincidencias", est["TablaHead"]),
            ]
        ]
        for inf in datos["infracciones"][:6]:
            inf_data.append(
                [
                    Paragraph(inf["nombre"], est["TablaCell"]),
                    Paragraph(str(inf["total"]), est["TablaCellNum"]),
                    Paragraph(str(inf["reincidentes"]), est["TablaCellNum"]),
                ]
            )
        t_inf = Table(inf_data, colWidths=[ancho_util * 0.6, ancho_util * 0.2, ancho_util * 0.2])
        t_inf.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), COLOR_MARINO_SEC),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_FONDO_TABLA]),
                    ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(t_inf)
        story.append(Spacer(1, 10))

    # 5. Listado detallado de inspecciones (anexo)
    if datos["detalles_actas"]:
        story.append(
            KeepTogether(
                [
                    Paragraph("5. DETALLE DE INSPECCIONES REALIZADAS", est["Seccion"]),
                    Spacer(1, 3),
                ]
            )
        )
        det_data = [
            [
                Paragraph("Predio", est["TablaHead"]),
                Paragraph("Tipo", est["TablaHead"]),
                Paragraph("Inspector", est["TablaHead"]),
                Paragraph("Carga Fuego", est["TablaHead"]),
                Paragraph("Scoring", est["TablaHead"]),
                Paragraph("Riesgo", est["TablaHead"]),
            ]
        ]
        for d in datos["detalles_actas"]:
            det_data.append(
                [
                    Paragraph(f"<b>{d['predio_nombre']}</b>", est["TablaCell"]),
                    Paragraph(d["tipo_predio"], est["TablaCell"]),
                    Paragraph(d["inspector_nombre"], est["TablaCell"]),
                    Paragraph(
                        f"{d['carga_fuego']} MJ/m²" if d["carga_fuego"] else "—",
                        est["TablaCellNum"],
                    ),
                    Paragraph(str(d["scoring_riesgo"] or "—"), est["TablaCellCenter"]),
                    Paragraph(f"<b>{d['cluster_riesgo'] or '—'}</b>", est["TablaCellCenter"]),
                ]
            )
        t_det = Table(
            det_data,
            colWidths=[
                ancho_util * 0.27,
                ancho_util * 0.19,
                ancho_util * 0.16,
                ancho_util * 0.14,
                ancho_util * 0.12,
                ancho_util * 0.12,
            ],
        )
        t_det.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), COLOR_MARINO),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_FONDO_TABLA]),
                    ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(t_det)

    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()


def generar_pdf_dictamen(datos: dict) -> bytes:
    """Genera el PDF del Dictamen Técnico Oficial de Inspección y Carga de Fuego (NB
    58005)."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=2.0 * cm,
    )
    est = _crear_estilos()
    story = []
    ancho_util = A4[0] - 3.6 * cm

    # Encabezado Oficial
    story.append(Paragraph("BOMBEROS VOLUNTARIOS UUBR", est["Titulo"]))
    story.append(Paragraph("COMANDANCIA DE FISCALIZACIÓN Y PREVENCIÓN", est["TextoBold"]))
    story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            f"DICTAMEN TÉCNICO DE INSPECCIÓN CONTRA INCENDIOS · ACTA #{datos['acta']['id']}",
            est["Subtitulo"],
        )
    )
    story.append(
        HRFlowable(width="100%", thickness=1.5, color=COLOR_ROJO, spaceBefore=4, spaceAfter=8)
    )

    # 1. Datos del Predio
    story.append(Paragraph("1. IDENTIFICACIÓN DEL INMUEBLE EVALUADO", est["Seccion"]))
    p = datos["predio"]
    t_predio_data = [
        [
            Paragraph("<b>Nombre / Razón Social:</b>", est["TextoBold"]),
            Paragraph(p["nombre"], est["Texto"]),
            Paragraph("<b>Tipo de Predio:</b>", est["TextoBold"]),
            Paragraph(p["tipo"], est["Texto"]),
        ],
        [
            Paragraph("<b>Dirección:</b>", est["TextoBold"]),
            Paragraph(p["direccion"], est["Texto"]),
            Paragraph("<b>Área Construida:</b>", est["TextoBold"]),
            Paragraph(f"{p['area_m2']} m²", est["Texto"]),
        ],
        [
            Paragraph("<b>Aforo Máximo:</b>", est["TextoBold"]),
            Paragraph(str(p["aforo"] or "No especificado"), est["Texto"]),
            Paragraph("<b>Hidrante más cercano:</b>", est["TextoBold"]),
            Paragraph(f"{p['hidrante_codigo']} a {p['distancia_hidrante_m']} m", est["Texto"]),
        ],
    ]
    t_p = Table(t_predio_data, colWidths=[3.2 * cm, 5.5 * cm, 3.2 * cm, 5.5 * cm])
    t_p.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_FONDO_TABLA),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(t_p)
    story.append(Spacer(1, 8))

    # 2. Datos de la Inspección
    story.append(Paragraph("2. REGISTRO OFICIAL DE INSPECCIÓN", est["Seccion"]))
    a = datos["acta"]
    t_acta_data = [
        [
            Paragraph("<b>Campaña:</b>", est["TextoBold"]),
            Paragraph(a["campania_nombre"], est["Texto"]),
            Paragraph("<b>Inspector:</b>", est["TextoBold"]),
            Paragraph(a["inspector_nombre"], est["Texto"]),
        ],
        [
            Paragraph("<b>Fecha y Hora:</b>", est["TextoBold"]),
            Paragraph(a["fecha_inspeccion"], est["Texto"]),
            Paragraph("<b>Estado Acta:</b>", est["TextoBold"]),
            Paragraph(
                "Cerrada (Definitiva)" if a["cerrada"] else "En curso (Preliminar)", est["Texto"]
            ),
        ],
    ]
    t_a = Table(t_acta_data, colWidths=[3.2 * cm, 5.5 * cm, 3.2 * cm, 5.5 * cm])
    t_a.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_FONDO_TABLA),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(t_a)
    story.append(Spacer(1, 8))

    # 3. Carga de Fuego NB 58005
    story.append(
        Paragraph(
            "3. CÁLCULO DE CARGA DE FUEGO PONDERADA (NORMA BOLIVIANA NB 58005)", est["Seccion"]
        )
    )
    mat_data = [
        [
            Paragraph("Material Combustible", est["TablaHead"]),
            Paragraph("Masa (kg)", est["TablaHead"]),
            Paragraph("Poder Calorífico Hi (MJ/kg)", est["TablaHead"]),
            Paragraph("Peligrosidad (Ci)", est["TablaHead"]),
            Paragraph("Aporte Térmico (MJ)", est["TablaHead"]),
        ]
    ]
    if datos["materiales"]:
        for m in datos["materiales"]:
            mat_data.append(
                [
                    Paragraph(m["nombre"], est["TablaCellBold"]),
                    Paragraph(str(m["peso_kg"]), est["TablaCellNum"]),
                    Paragraph(str(m["poder_calorifico"]), est["TablaCellNum"]),
                    Paragraph(str(m["coeficiente_peligrosidad"]), est["TablaCellNum"]),
                    Paragraph(f"{m['calor_total_mj']} MJ", est["TablaCellNum"]),
                ]
            )
    else:
        mat_data.append(
            [Paragraph("Sin materiales específicos inventariados", est["TablaCell"])] * 5
        )

    t_mat = Table(
        mat_data,
        colWidths=[
            ancho_util * 0.35,
            ancho_util * 0.15,
            ancho_util * 0.20,
            ancho_util * 0.15,
            ancho_util * 0.15,
        ],
    )
    t_mat.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_MARINO),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_FONDO_TABLA]),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(t_mat)
    story.append(Spacer(1, 4))

    # Carga de Fuego calculada
    cf_box_data = [
        [
            Paragraph(
                f"<b>Carga de Fuego Total (Qp): {a['carga_fuego'] or '—'} MJ/m²</b> (Ra aplicado: {p.get('riesgo_activacion', 1.0)})",
                est["TextoBold"],
            )
        ]
    ]
    t_cf = Table(cf_box_data, colWidths=[ancho_util])
    t_cf.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_FONDO_TABLA),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t_cf)
    story.append(Spacer(1, 8))

    # 4. Seguridad e Infracciones
    story.append(Paragraph("4. CONDICIONES DE SEGURIDAD E INFRACCIONES DETECTADAS", est["Seccion"]))
    cond_data = [
        [
            Paragraph("<b>Estado Extintores:</b>", est["TextoBold"]),
            Paragraph(a["estado_extintores"], est["Texto"]),
            Paragraph("<b>Rutas de Evacuación:</b>", est["TextoBold"]),
            Paragraph(
                (
                    "<font color='#D7263D'><b>OBSTRUIDAS</b></font>"
                    if a["rutas_obstruidas"]
                    else "Despejadas"
                ),
                est["Texto"],
            ),
        ],
        [
            Paragraph("<b>Fallas Eléctricas:</b>", est["TextoBold"]),
            Paragraph(
                (
                    "<font color='#D7263D'><b>DEFICIENCIAS GRAVES</b></font>"
                    if a["fallas_electricas"]
                    else "Normales"
                ),
                est["Texto"],
            ),
            Paragraph("<b>Evidencias Fotos:</b>", est["TextoBold"]),
            Paragraph(f"{datos.get('total_evidencias', 0)} capturas", est["Texto"]),
        ],
    ]
    t_cond = Table(cond_data, colWidths=[3.2 * cm, 5.5 * cm, 3.2 * cm, 5.5 * cm])
    t_cond.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_FONDO_TABLA),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(t_cond)

    if datos["infracciones"]:
        story.append(Spacer(1, 5))
        inf_data = [
            [
                Paragraph("Infracción", est["TablaHead"]),
                Paragraph("Severidad", est["TablaHead"]),
                Paragraph("Reincidencia", est["TablaHead"]),
                Paragraph("Observaciones de campo", est["TablaHead"]),
            ]
        ]
        for inf in datos["infracciones"]:
            inf_data.append(
                [
                    Paragraph(inf["nombre"], est["TablaCellBold"]),
                    Paragraph(str(inf["severidad"]), est["TablaCellCenter"]),
                    Paragraph(
                        (
                            "<font color='#D7263D'><b>REINCIDENTE</b></font>"
                            if inf["reincidente"]
                            else "No"
                        ),
                        est["TablaCellCenter"],
                    ),
                    Paragraph(inf["descripcion"] or "—", est["TablaCell"]),
                ]
            )
        t_inf = Table(
            inf_data,
            colWidths=[ancho_util * 0.35, ancho_util * 0.12, ancho_util * 0.15, ancho_util * 0.38],
        )
        t_inf.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), COLOR_MARINO_SEC),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_FONDO_TABLA]),
                    ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(t_inf)

    story.append(Spacer(1, 10))

    # 5. Dictamen Final y Conclusión
    color_dictamen = COLOR_MARINO
    if a["cluster_riesgo"] == "Critico":
        color_dictamen = COLOR_CRITICO
    elif a["cluster_riesgo"] == "Bajo":
        color_dictamen = COLOR_BAJO
    elif a["cluster_riesgo"] == "Medio":
        color_dictamen = COLOR_MEDIO

    story.append(
        KeepTogether(
            [
                Paragraph("5. DICTAMEN FINAL DE EVALUACIÓN DE RIESGO", est["Seccion"]),
                Spacer(1, 4),
                Table(
                    [
                        [
                            Paragraph(
                                f"PUNTAJE DE SCORING: {a['scoring_riesgo'] or '—'} / 100 PTS<br/>"
                                f"CLASIFICACIÓN DE RIESGO: {a['cluster_riesgo'].upper() if a['cluster_riesgo'] else 'PENDIENTE'}",
                                est["DictamenBox"],
                            )
                        ]
                    ],
                    colWidths=[ancho_util],
                    style=[
                        ("BACKGROUND", (0, 0), (-1, -1), color_dictamen),
                        ("BOX", (0, 0), (-1, -1), 1, color_dictamen),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ],
                ),
                Spacer(1, 15),
                # Bloque de Firmas
                Table(
                    [
                        [
                            Paragraph(
                                "__________________________________<br/>"
                                f"<b>{a['inspector_nombre']}</b><br/>"
                                "Inspector Técnico Actuante",
                                est["TablaCellCenter"],
                            ),
                            Paragraph(
                                "__________________________________<br/>"
                                "<b>Oficial de Mando / Comandancia</b><br/>"
                                "Cuerpo de Bomberos Voluntarios UUBR",
                                est["TablaCellCenter"],
                            ),
                        ]
                    ],
                    colWidths=[ancho_util / 2, ancho_util / 2],
                    style=[
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ],
                ),
            ]
        )
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
