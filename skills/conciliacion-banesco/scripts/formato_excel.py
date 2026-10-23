"""
Formato de lectura para el libro de trabajo de la conciliación.

Se aplica después de escribir los datos y no cambia ningún valor ni nombre de
columna: solo encabezados, anchos, ajuste de texto, formatos de número y fecha,
colores de flags, paneles fijos, filtros y configuración de impresión.

Convenciones (workpaper-standards): negativos entre paréntesis, fechas
AAAA-MM-DD, rojo = revisar.
"""
from __future__ import annotations

import math
from datetime import date, datetime

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

NUM_FMT = "#,##0.00;(#,##0.00)"
# en tablas de detalle el cero se muestra vacío para que cargo/abono se lean de un vistazo
NUM_FMT_TABLA = "#,##0.00;(#,##0.00);\"\""
PCT_FMT = "0.00%"
DATE_FMT = "yyyy-mm-dd"

AZUL = "1F3864"
GRIS_BANDA = "F2F2F2"
BORDE = Side(style="thin", color="BFBFBF")

FILL_FLAG = {
    "MANUAL_REVIEW_REQUIRED": "F8CBAD",
    "REJECT": "F8CBAD",
    "UNKNOWN": "F8CBAD",
    "NEEDS_CLARIFICATION": "FFE699",
    "BANK_FEE_NOT_BOOKED": "FFE699",
    "READY_FOR_REVIEW": "C6EFCE",
    "READY_TO_POST": "C6EFCE",
    "CONCILIADA": "C6EFCE",
}

# columnas de texto largo: se permiten más anchas antes de ajustar en varias líneas
TEXTO_LARGO = {"detalle", "tratamiento", "nota", "memo", "calculo", "fuente", "partida", "description",
               "book_description", "bank_description", "concepto", "support reference"}
ANCHO_MAX = 45
ANCHO_MAX_LARGO = 70
ANCHO_MIN = 9
ALTO_LINEA = 15

TAB_COLOR = {
    "Cover": AZUL, "Summary": "548235", "Evidence": "548235",
    "Validacion": "C55A11", "Review_Notes": "C55A11",
    "JEs_Proposed": "2E75B6", "Reconciling_Items": "2E75B6",
}

ETIQUETA_COVER = {
    "campo": "Campo", "valor": "Valor",
}


def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, (datetime, date)):
        return "0000-00-00"
    return str(v)


def _tipo_columna(ws: Worksheet, col: int, nombre: str) -> str:
    valores = [ws.cell(row=r, column=col).value for r in range(2, min(ws.max_row, 400) + 1)]
    valores = [v for v in valores if v not in (None, "")]
    if not valores:
        return "texto"
    if "tasa" in nombre.lower() and all(isinstance(v, (int, float)) for v in valores):
        return "pct"
    if all(isinstance(v, (datetime, date)) for v in valores):
        return "fecha"
    if all(isinstance(v, bool) for v in valores):
        return "bool"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in valores):
        return "num" if any(isinstance(v, float) for v in valores) else "entero"
    return "texto"


def _encabezado(ws: Worksheet, fila: int = 1) -> None:
    for c in ws[fila]:
        if c.value is None:
            continue
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=AZUL)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = Border(bottom=BORDE)
    ws.row_dimensions[fila].height = 30


def formatear_tabla(ws: Worksheet) -> None:
    """Hoja con encabezado en la fila 1 y una fila por registro."""
    if ws.max_row < 1 or ws.max_column < 1 or ws.cell(row=1, column=1).value is None:
        return
    _encabezado(ws)
    anchos: dict[int, float] = {}
    for col in range(1, ws.max_column + 1):
        nombre = str(ws.cell(row=1, column=col).value or "")
        tipo = _tipo_columna(ws, col, nombre)
        largo = nombre.lower() in TEXTO_LARGO
        tope = ANCHO_MAX_LARGO if largo else ANCHO_MAX
        contenido = max((len(_texto(ws.cell(row=r, column=col).value)) for r in range(2, ws.max_row + 1)), default=0)
        # números y flags (en negrita) necesitan aire extra para no pegarse a la columna vecina
        extra = 5 if tipo in ("num", "pct") else 2
        if any(ws.cell(row=r, column=col).value in FILL_FLAG for r in range(2, ws.max_row + 1)):
            extra = 5
        ancho = max(ANCHO_MIN, min(tope, max(contenido, len(nombre)) + extra))
        anchos[col] = ancho
        ws.column_dimensions[get_column_letter(col)].width = ancho
        horizontal = {"num": "right", "pct": "right", "entero": "center", "fecha": "center", "bool": "center"}.get(tipo, "left")
        for r in range(2, ws.max_row + 1):
            c = ws.cell(row=r, column=col)
            if tipo == "num":
                c.number_format = NUM_FMT_TABLA
            elif tipo == "pct":
                c.number_format = PCT_FMT
            elif tipo == "fecha":
                c.number_format = DATE_FMT
            elif tipo == "texto" and isinstance(c.value, str) and c.value.isdigit():
                c.number_format = "@"  # referencias con ceros a la izquierda
            c.alignment = Alignment(horizontal=horizontal, vertical="top", wrap_text=(tipo == "texto"),
                                    indent=1 if tipo in ("num", "pct") else 0)

    for r in range(2, ws.max_row + 1):
        lineas = 1
        banda = PatternFill("solid", fgColor=GRIS_BANDA) if r % 2 == 0 else None
        for col in range(1, ws.max_column + 1):
            c = ws.cell(row=r, column=col)
            if isinstance(c.value, str):
                lineas = max(lineas, math.ceil(len(c.value) / max(anchos[col] - 1, 1)))
                if c.value in FILL_FLAG:
                    c.fill = PatternFill("solid", fgColor=FILL_FLAG[c.value])
                    c.font = Font(bold=True)
                    continue
            if banda is not None:
                c.fill = banda
            c.border = Border(bottom=BORDE)
        if lineas > 1:
            ws.row_dimensions[r].height = ALTO_LINEA * lineas + 2

    ws.freeze_panes = "B2" if ws.max_column > 6 else "A2"
    ws.auto_filter.ref = ws.dimensions
    _impresion(ws)


def formatear_cover(ws: Worksheet) -> None:
    ws.insert_rows(1, amount=2)
    ws["A1"] = "Conciliación bancaria Banesco"
    ws["A1"].font = Font(bold=True, size=16, color=AZUL)
    ws.merge_cells("A1:B1")
    ws.row_dimensions[1].height = 26
    for c in ws[3]:
        if c.value in ETIQUETA_COVER:
            c.value = ETIQUETA_COVER[c.value]
    _encabezado(ws, 3)
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 80
    for r in range(4, ws.max_row + 1):
        a, b = ws.cell(row=r, column=1), ws.cell(row=r, column=2)
        a.font = Font(bold=True)
        a.alignment = Alignment(vertical="top")
        b.alignment = Alignment(vertical="top", wrap_text=True)
        a.border = b.border = Border(bottom=BORDE)
        if a.value == "Estado":
            rojo = isinstance(b.value, str) and not b.value.startswith("CONCILIADA")
            b.fill = PatternFill("solid", fgColor="F8CBAD" if rojo else "C6EFCE")
            b.font = Font(bold=True)
        if isinstance(b.value, str) and len(b.value) > 78:
            ws.row_dimensions[r].height = ALTO_LINEA * math.ceil(len(b.value) / 78) + 2
    r = ws.max_row + 2
    for etiqueta in ("Preparado por:", "Revisado por:", "Fecha de revisión:"):
        ws.cell(row=r, column=1, value=etiqueta).font = Font(bold=True)
        ws.cell(row=r, column=2).border = Border(bottom=Side(style="thin", color="000000"))
        r += 1
    _impresion(ws, horizontal=False)


def formatear_summary(ws: Worksheet, n_periodos: int) -> None:
    ws["A1"].font = Font(bold=True, size=16, color=AZUL)
    ws.row_dimensions[1].height = 26
    _encabezado(ws, 2)
    ws.column_dimensions["A"].width = 44
    for j in range(2, n_periodos + 2):
        ws.column_dimensions[get_column_letter(j)].width = 22
    subtotales = {6, 10}
    for r in range(3, ws.max_row + 1):
        etiqueta = ws.cell(row=r, column=1)
        etiqueta.alignment = Alignment(indent=0 if r in subtotales or r >= 11 else 1)
        for j in range(1, n_periodos + 2):
            c = ws.cell(row=r, column=j)
            c.border = Border(bottom=BORDE)
            if j > 1:
                c.alignment = Alignment(horizontal="right" if r < 12 else "center", vertical="center", wrap_text=True)
            if r in subtotales:
                c.font = Font(bold=True)
                c.border = Border(top=Side(style="thin", color="000000"), bottom=BORDE)
            if r == 11:
                c.font = Font(bold=True)
                c.border = Border(top=Side(style="thin", color="000000"), bottom=Side(style="double", color="000000"))
            if r == 12 and j > 1:
                texto = str(c.value or "")
                verde = "CONCILIADA" in texto and "NO" not in texto and "SIN" not in texto
                c.fill = PatternFill("solid", fgColor="C6EFCE" if verde else "F8CBAD")
                c.font = Font(bold=True)
    ws.row_dimensions[12].height = 50
    ws.cell(row=14, column=1, value="Azul: dato del estado de cuenta o del libro. Negro: fórmula.").font = Font(italic=True, color="7F7F7F")
    ws.freeze_panes = "B3"
    _impresion(ws, horizontal=n_periodos > 3)


def _impresion(ws: Worksheet, horizontal: bool = True) -> None:
    ws.page_setup.orientation = "landscape" if horizontal else "portrait"
    ancho_total = sum((ws.column_dimensions[get_column_letter(c)].width or 10) for c in range(1, ws.max_column + 1))
    # solo se fuerza a una página de ancho si la letra sigue siendo legible; si no, se reparte en varias
    if ancho_total <= 220:
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
    else:
        ws.page_setup.scale = 70
        ws.print_title_cols = "A:A"
    ws.print_title_rows = "1:1"


def formatear_libro(wb: Workbook, n_periodos: int) -> None:
    for ws in wb.worksheets:
        if ws.title in TAB_COLOR:
            ws.sheet_properties.tabColor = TAB_COLOR[ws.title]
        if ws.title == "Cover":
            formatear_cover(ws)
        elif ws.title == "Summary":
            formatear_summary(ws, n_periodos)
        else:
            formatear_tabla(ws)
