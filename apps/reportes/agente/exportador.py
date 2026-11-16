# Exportador dinamico en PDF, Excel (.xlsx), TXT y CSV para el Agente de Reportes.
# Respeta la seleccion de columnas interactiva del usuario y genera graficos integrados.

import csv
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..aviso import AVISO_LEGAL, agregar_aviso_excel
from . import tabla

# Paleta institucional UUBR
COLOR_MARINO = colors.HexColor("#14213D")
COLOR_ROJO = colors.HexColor("#D7263D")
COLOR_BORDE = colors.HexColor("#CBD5E1")
COLOR_FONDO_CABECERA = colors.HexColor("#14213D")
COLOR_ZEBRA = colors.HexColor("#F8FAFC")
COLOR_TEXTO_SEC = colors.HexColor("#475569")

HEX_MARINO = "14213D"
HEX_BLANCO = "FFFFFF"
HEX_ZEBRA = "F8FAFC"
HEX_BORDE = "CBD5E1"


class NumberedCanvasHorizontal(canvas.Canvas):
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
        width, height = landscape(A4)
        # Pie de pagina institucional
        self.setStrokeColor(COLOR_BORDE)
        self.setLineWidth(0.5)
        self.line(1.5 * cm, 1.2 * cm, width - 1.5 * cm, 1.2 * cm)

        self.setFont("Helvetica-Oblique", 6.5)
        self.setFillColor(COLOR_TEXTO_SEC)
        self.drawCentredString(width / 2, 1.4 * cm, AVISO_LEGAL)

        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(COLOR_ROJO)
        self.drawString(1.5 * cm, 0.8 * cm, "UUBR")
        self.setFont("Helvetica", 8)
        self.setFillColor(COLOR_TEXTO_SEC)
        self.drawString(
            2.5 * cm, 0.8 * cm, "· Bomberos Voluntarios Santa Cruz · Agente de Reportes Dinámico"
        )

        pag_txt = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(width - 1.5 * cm, 0.8 * cm, pag_txt)
        self.restoreState()


def exportar_pdf(reporte: dict, columnas_seleccionadas: list[str] | None = None) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.8 * cm,
    )

    columnas, _ = tabla.conformar_columnas(
        reporte["filas"], columnas_seleccionadas or [c["clave"] for c in reporte["columnas"]]
    )
    filas = reporte["filas"]

    styles = getSampleStyleSheet()
    style_titulo = ParagraphStyle(
        "RepTit",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=17,
        textColor=COLOR_MARINO,
    )
    style_sub = ParagraphStyle(
        "RepSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=COLOR_TEXTO_SEC,
    )
    style_resumen = ParagraphStyle(
        "RepRes",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9,
        leading=13,
        textColor=COLOR_MARINO,
    )
    style_th = ParagraphStyle(
        "RepTH",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=colors.white,
        alignment=1,
    )
    style_td = ParagraphStyle(
        "RepTD",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=9,
        textColor=colors.black,
    )

    story = [
        Paragraph(
            f"<b>BOMBEROS VOLUNTARIOS UUBR SANTA CRUZ</b> — {reporte.get('titulo', 'Reporte Dinámico')}",
            style_titulo,
        ),
        Spacer(1, 4),
        Paragraph(
            f"<b>Consulta:</b> {reporte.get('pregunta', '—')} | <b>Emisión:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            style_sub,
        ),
        Spacer(1, 6),
        HRFlowable(width="100%", thickness=1, color=COLOR_ROJO, spaceBefore=2, spaceAfter=6),
    ]

    if reporte.get("respuesta_nl"):
        story.extend(
            [
                Paragraph(f"<b>Resumen Ejecutivo:</b> {reporte['respuesta_nl']}", style_resumen),
                Spacer(1, 8),
            ]
        )

    # Tabla de datos
    if columnas and filas:
        encabezados = [Paragraph(f"<b>{c['etiqueta']}</b>", style_th) for c in columnas]
        data_tabla = [encabezados]

        for f in filas[:150]:  # Limite para el PDF
            fila_celdas = []
            for c in columnas:
                val = f.get(c["clave"])
                if val is None:
                    val_str = "—"
                elif isinstance(val, bool):
                    val_str = "Sí" if val else "No"
                elif c["clave"] in ("estado", "estado_operativo") and isinstance(val, str):
                    val_str = val.replace("_", " ").capitalize()
                elif c.get("tipo") == "porcentaje" and isinstance(val, int | float):
                    val_str = f"{val:.1f}%"
                else:
                    val_str = str(val)
                fila_celdas.append(Paragraph(val_str, style_td))
            data_tabla.append(fila_celdas)

        ancho_disponible = landscape(A4)[0] - 3.0 * cm
        col_width = ancho_disponible / max(len(columnas), 1)

        t = Table(data_tabla, colWidths=[col_width] * len(columnas), repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), COLOR_FONDO_CABECERA),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDE),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_ZEBRA]),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(t)
    else:
        story.append(
            Paragraph(
                "No se encontraron registros para los criterios consultados.",
                style_sub,
            )
        )

    doc.build(story, canvasmaker=NumberedCanvasHorizontal)
    return buffer.getvalue()


def exportar_excel(reporte: dict, columnas_seleccionadas: list[str] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Reporte Dinámico"
    ws.views.sheetView[0].showGridLines = True

    columnas, _ = tabla.conformar_columnas(
        reporte["filas"], columnas_seleccionadas or [c["clave"] for c in reporte["columnas"]]
    )
    filas = reporte["filas"]

    # Cabecera institucional
    ws.merge_cells("A1:G1")
    c1 = ws["A1"]
    c1.value = "CUERPO DE BOMBEROS VOLUNTARIOS UUBR - SANTA CRUZ"
    c1.font = Font(name="Calibri", size=14, bold=True, color=HEX_BLANCO)
    c1.fill = PatternFill(start_color=HEX_MARINO, end_color=HEX_MARINO, fill_type="solid")
    c1.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 26

    ws.merge_cells("A2:G2")
    c2 = ws["A2"]
    c2.value = f"REPORTE: {reporte.get('titulo', 'Informe Dinámico').upper()}"
    c2.font = Font(name="Calibri", size=11, bold=True, color=HEX_BLANCO)
    c2.fill = PatternFill(start_color="1F3357", end_color="1F3357", fill_type="solid")
    c2.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    ws["A4"] = "Consulta solicitada:"
    ws["A4"].font = Font(name="Calibri", bold=True)
    ws["B4"] = reporte.get("pregunta", "—")

    ws["A5"] = "Fecha de emisión:"
    ws["A5"].font = Font(name="Calibri", bold=True)
    ws["B5"] = datetime.now().strftime("%d/%m/%Y %H:%M")

    if reporte.get("respuesta_nl"):
        ws["A6"] = "Síntesis Ejecutiva:"
        ws["A6"].font = Font(name="Calibri", bold=True)
        ws.merge_cells("B6:G6")
        ws["B6"] = reporte["respuesta_nl"]
        ws["B6"].alignment = Alignment(wrap_text=True)
        ws.row_dimensions[6].height = 36

    fila_inicio_tabla = 8
    font_th = Font(name="Calibri", size=10, bold=True, color=HEX_BLANCO)
    fill_th = PatternFill(start_color=HEX_MARINO, end_color=HEX_MARINO, fill_type="solid")
    border_thin = Border(
        left=Side(style="thin", color=HEX_BORDE),
        right=Side(style="thin", color=HEX_BORDE),
        top=Side(style="thin", color=HEX_BORDE),
        bottom=Side(style="thin", color=HEX_BORDE),
    )

    for col_idx, col in enumerate(columnas, start=1):
        cell = ws.cell(row=fila_inicio_tabla, column=col_idx, value=col["etiqueta"])
        cell.font = font_th
        cell.fill = fill_th
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border_thin

    fill_zebra = PatternFill(start_color=HEX_ZEBRA, end_color=HEX_ZEBRA, fill_type="solid")

    for f_idx, fila in enumerate(filas, start=fila_inicio_tabla + 1):
        for c_idx, col in enumerate(columnas, start=1):
            val = fila.get(col["clave"])
            if col["clave"] in ("estado", "estado_operativo") and isinstance(val, str):
                val = val.replace("_", " ").capitalize()
            cell = ws.cell(row=f_idx, column=c_idx, value=val)
            cell.border = border_thin
            if f_idx % 2 == 0:
                cell.fill = fill_zebra

            if col["tipo"] == "numero":
                cell.alignment = Alignment(horizontal="right")
                if isinstance(val, int | float):
                    cell.number_format = "#,##0.00" if isinstance(val, float) else "#,##0"
            elif col["tipo"] == "porcentaje":
                cell.alignment = Alignment(horizontal="right")
                cell.number_format = '0.0"%"'
            else:
                cell.alignment = Alignment(horizontal="left")

    # Autoajuste de columnas
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if "\n" in val_str:
                val_str = max(val_str.split("\n"), key=len)
            max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = max(min(max_len + 3, 50), 12)

    if columnas:
        ws.freeze_panes = f"A{fila_inicio_tabla + 1}"
        ultima_col_letra = get_column_letter(len(columnas))
        ws.auto_filter.ref = (
            f"A{fila_inicio_tabla}:{ultima_col_letra}{fila_inicio_tabla + len(filas)}"
        )

    # Hoja 2 con grafico si aplica
    grafico_info = tabla.autodetectar_grafico(columnas, filas)
    if grafico_info and len(filas) <= 50:
        ws_graf = wb.create_sheet(title="Gráfico")
        chart = BarChart()
        chart.type = "col"
        chart.style = 10
        chart.title = grafico_info["titulo"]
        chart.y_axis.title = grafico_info["etiqueta_y"]
        chart.x_axis.title = grafico_info["etiqueta_x"]

        # Indice de la columna X e Y
        idx_x = next(i for i, c in enumerate(columnas, start=1) if c["clave"] == grafico_info["x"])
        idx_y = next(i for i, c in enumerate(columnas, start=1) if c["clave"] == grafico_info["y"])

        data_ref = Reference(
            ws, min_col=idx_y, min_row=fila_inicio_tabla, max_row=fila_inicio_tabla + len(filas)
        )
        cats_ref = Reference(
            ws, min_col=idx_x, min_row=fila_inicio_tabla + 1, max_row=fila_inicio_tabla + len(filas)
        )
        chart.add_data(data_ref, titles_from_data=True)
        chart.set_categories(cats_ref)
        chart.width = 20
        chart.height = 12
        ws_graf.add_chart(chart, "B2")

    agregar_aviso_excel(wb)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def exportar_txt(reporte: dict, columnas_seleccionadas: list[str] | None = None) -> str:
    columnas, _ = tabla.conformar_columnas(
        reporte["filas"], columnas_seleccionadas or [c["clave"] for c in reporte["columnas"]]
    )
    filas = reporte["filas"]

    lineas = [
        "=" * 85,
        "CUERPO DE BOMBEROS VOLUNTARIOS UUBR - SANTA CRUZ DE LA SIERRA",
        f"INFORME: {reporte.get('titulo', 'REPORTE DINÁMICO').upper()}",
        f"CONSULTA: {reporte.get('pregunta', '—')}",
        f"EMISIÓN: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "=" * 85,
        "",
    ]

    if reporte.get("respuesta_nl"):
        lineas.extend(["SÍNTESIS EJECUTIVA:", reporte["respuesta_nl"], "", "-" * 85, ""])

    if columnas and filas:
        anchos = {c["clave"]: max(len(c["etiqueta"]), 8) for c in columnas}
        for f in filas[:200]:
            for c in columnas:
                val_str = str(f.get(c["clave"], "") or "")
                anchos[c["clave"]] = min(max(anchos[c["clave"]], len(val_str)), 35)

        cabecera = " | ".join(
            c["etiqueta"][: anchos[c["clave"]]].ljust(anchos[c["clave"]]) for c in columnas
        )
        separador = "-+-".join("-" * anchos[c["clave"]] for c in columnas)
        lineas.append(cabecera)
        lineas.append(separador)

        for f in filas[:200]:
            fila_str = " | ".join(
                str(f.get(c["clave"], "") or "")[: anchos[c["clave"]]].ljust(anchos[c["clave"]])
                for c in columnas
            )
            lineas.append(fila_str)

    lineas.extend(["", f"Total de registros exportados: {len(filas)}", "", AVISO_LEGAL, "=" * 85])
    return "\n".join(lineas)


def exportar_csv(reporte: dict, columnas_seleccionadas: list[str] | None = None) -> bytes:
    """Exporta el reporte en formato CSV tabular.

    Usa codificación UTF-8 con BOM (utf-8-sig) para máxima compatibilidad con
    Microsoft Excel y LibreOffice en Windows y entornos de habla hispana.
    """
    columnas, _ = tabla.conformar_columnas(
        reporte["filas"], columnas_seleccionadas or [c["clave"] for c in reporte["columnas"]]
    )
    filas = reporte["filas"]

    output = io.StringIO()
    writer = csv.writer(output, dialect="excel")

    if columnas:
        writer.writerow([c["etiqueta"] for c in columnas])

    for fila in filas:
        valores_fila = []
        for col in columnas:
            val = fila.get(col["clave"])
            if val is None:
                val = ""
            elif isinstance(val, bool):
                val = "Sí" if val else "No"
            elif col["clave"] in ("estado", "estado_operativo") and isinstance(val, str):
                val = val.replace("_", " ").capitalize()
            valores_fila.append(val)
        writer.writerow(valores_fila)

    return output.getvalue().encode("utf-8-sig")
