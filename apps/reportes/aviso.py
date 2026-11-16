"""Aviso que acompaña a todo reporte generado por el Sistema.

El Sistema es una herramienta de apoyo a la prevención: sus reportes y dictámenes no
equivalen a la certificación de prevención y protección contra incendios que emite la
Dirección Nacional de Bomberos (Ley N.º 449). Ver el Capítulo 5, sección 5.1.4.
"""

from openpyxl.styles import Font

AVISO_LEGAL = (
    "Documento de apoyo a la prevención; no equivale a la certificación de la "
    "Dirección Nacional de Bomberos (Ley N.º 449)."
)


def agregar_aviso_excel(wb):
    """Pone el aviso como pie de impresión en todas las hojas y como nota visible al final
    de la primera. Se llama después de ajustar el ancho de las columnas."""
    for hoja in wb.worksheets:
        hoja.oddFooter.center.text = AVISO_LEGAL
        hoja.oddFooter.center.size = 8
    primera = wb.worksheets[0]
    celda = primera.cell(row=primera.max_row + 2, column=1, value=AVISO_LEGAL)
    celda.font = Font(name="Calibri", size=9, italic=True, color="5C6773")
