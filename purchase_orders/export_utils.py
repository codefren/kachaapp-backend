"""Utilities to export purchase orders to Excel and PDF."""

from io import BytesIO
from collections import defaultdict
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)


def _safe_text(value, default=""):
    return str(value if value is not None else default)


def _order_market_name(order):
    return _safe_text(getattr(getattr(order, "market", None), "name", None), "Sin tienda")


def _provider_name(order):
    return _safe_text(getattr(getattr(order, "provider", None), "name", None), "Proveedor")


def _grouped_rows_from_orders(orders):
    """
    Devuelve:
    - rows_by_order: filas detalladas por pedido
    - consolidated_rows: filas agrupadas por producto con cantidades por tienda
    - market_names: lista ordenada de tiendas
    """
    rows_by_order = []
    consolidated = defaultdict(lambda: {"product_name": "", "markets": defaultdict(int), "total_units": 0})
    market_names = []

    seen_markets = set()

    for order in orders:
        market_name = _order_market_name(order)
        if market_name not in seen_markets:
            seen_markets.add(market_name)
            market_names.append(market_name)

        order_items = list(order.items.select_related("product").all().order_by("product__name"))
        detail_items = []

        for item in order_items:
            product_name = _safe_text(getattr(getattr(item, "product", None), "name", None), "Producto")
            qty = int(item.quantity_units or 0)
            notes = _safe_text(getattr(item, "notes", ""), "")
            purchase_unit = _safe_text(getattr(item, "purchase_unit", "boxes"), "boxes")

            detail_items.append(
                {
                    "product_name": product_name,
                    "quantity_units": qty,
                    "purchase_unit": purchase_unit,
                    "notes": notes,
                }
            )

            key = item.product_id
            consolidated[key]["product_name"] = product_name
            consolidated[key]["markets"][market_name] += qty
            consolidated[key]["total_units"] += qty

        rows_by_order.append(
            {
                "order_id": order.id,
                "market_name": market_name,
                "provider_name": _provider_name(order),
                "notes": _safe_text(getattr(order, "notes", ""), ""),
                "items": detail_items,
            }
        )

    consolidated_rows = []
    for _, row in consolidated.items():
        consolidated_rows.append(
            {
                "product_name": row["product_name"],
                "markets": dict(row["markets"]),
                "total_units": row["total_units"],
            }
        )

    consolidated_rows.sort(key=lambda x: x["product_name"].lower())
    market_names.sort(key=lambda x: x.lower())

    return rows_by_order, consolidated_rows, market_names


def build_purchase_order_excel(order):
    """Genera Excel individual de un pedido."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Pedido"

    bold = Font(bold=True)
    header_fill = PatternFill(fill_type="solid", fgColor="D9EAF7")

    ws["A1"] = "Pedido de compra"
    ws["A1"].font = Font(bold=True, size=16)

    ws["A3"] = "Pedido #"
    ws["B3"] = order.id
    ws["A4"] = "Proveedor"
    ws["B4"] = _provider_name(order)
    ws["A5"] = "Tienda"
    ws["B5"] = _order_market_name(order)
    ws["A6"] = "Estado"
    ws["B6"] = _safe_text(getattr(order, "status", ""), "")
    ws["A7"] = "Notas"
    ws["B7"] = _safe_text(getattr(order, "notes", ""), "")

    headers = ["Producto", "Cantidad", "Unidad", "Notas"]
    start_row = 10

    for col_idx, value in enumerate(headers, start=1):
        cell = ws.cell(row=start_row, column=col_idx, value=value)
        cell.font = bold
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    row = start_row + 1
    for item in order.items.select_related("product").all().order_by("product__name"):
        ws.cell(row=row, column=1, value=_safe_text(getattr(getattr(item, "product", None), "name", None), "Producto"))
        ws.cell(row=row, column=2, value=int(item.quantity_units or 0))
        ws.cell(row=row, column=3, value=_safe_text(getattr(item, "purchase_unit", "boxes"), "boxes"))
        ws.cell(row=row, column=4, value=_safe_text(getattr(item, "notes", ""), ""))
        row += 1

    widths = [35, 14, 14, 40]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out


def build_grouped_purchase_order_excel(orders):
    """Genera un Excel consolidado premium con resumen y detalle por pedido."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Consolidado"

    bold = Font(bold=True)
    title_font = Font(bold=True, size=16)
    header_fill = PatternFill(fill_type="solid", fgColor="D9EAF7")
    yellow_fill = PatternFill(fill_type="solid", fgColor="FFF3CD")

    rows_by_order, consolidated_rows, market_names = _grouped_rows_from_orders(orders)
    provider_name = _provider_name(orders[0]) if orders else "Proveedor"

    ws["A1"] = "Consolidado de pedidos"
    ws["A1"].font = title_font
    ws["A3"] = "Proveedor"
    ws["B3"] = provider_name
    ws["A4"] = "Generado"
    ws["B4"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    ws["A5"] = "Pedidos"
    ws["B5"] = len(orders)

    summary_row = 8
    summary_headers = ["Producto"] + market_names + ["TOTAL"]
    for col_idx, value in enumerate(summary_headers, start=1):
        cell = ws.cell(row=summary_row, column=col_idx, value=value)
        cell.font = bold
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    row = summary_row + 1
    for item in consolidated_rows:
        ws.cell(row=row, column=1, value=item["product_name"])
        for idx, market_name in enumerate(market_names, start=2):
            ws.cell(row=row, column=idx, value=int(item["markets"].get(market_name, 0)))
        ws.cell(row=row, column=len(market_names) + 2, value=int(item["total_units"]))
        row += 1

    row += 2
    ws.cell(row=row, column=1, value="Detalle por pedido").font = title_font
    row += 2

    for order_data in rows_by_order:
        ws.cell(row=row, column=1, value=f"Pedido #{order_data['order_id']}").font = bold
        ws.cell(row=row, column=2, value=order_data["market_name"]).font = bold
        row += 1

        detail_headers = ["Producto", "Cantidad", "Unidad", "Notas"]
        for col_idx, value in enumerate(detail_headers, start=1):
            cell = ws.cell(row=row, column=col_idx, value=value)
            cell.font = bold
            cell.fill = yellow_fill
            cell.alignment = Alignment(horizontal="center")
        row += 1

        for item in order_data["items"]:
            ws.cell(row=row, column=1, value=item["product_name"])
            ws.cell(row=row, column=2, value=int(item["quantity_units"]))
            ws.cell(row=row, column=3, value=item["purchase_unit"])
            ws.cell(row=row, column=4, value=item["notes"])
            row += 1

        if order_data["notes"]:
            ws.cell(row=row, column=1, value="Notas pedido").font = bold
            ws.cell(row=row, column=2, value=order_data["notes"])
            row += 1

        row += 2

    for idx in range(1, max(6, len(market_names) + 3)):
        ws.column_dimensions[get_column_letter(idx)].width = 24

    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out


def build_purchase_order_pdf(order):
    """Genera PDF individual de un pedido."""
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(f"Pedido de compra #{order.id}", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Proveedor: {_provider_name(order)}", styles["Normal"]))
    elements.append(Paragraph(f"Tienda: {_order_market_name(order)}", styles["Normal"]))
    elements.append(Paragraph(f"Estado: {_safe_text(getattr(order, 'status', ''), '')}", styles["Normal"]))
    elements.append(Paragraph(f"Notas: {_safe_text(getattr(order, 'notes', ''), '')}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    data = [["Producto", "Cantidad", "Unidad", "Notas"]]
    for item in order.items.select_related("product").all().order_by("product__name"):
        data.append([
            _safe_text(getattr(getattr(item, "product", None), "name", None), "Producto"),
            int(item.quantity_units or 0),
            _safe_text(getattr(item, "purchase_unit", "boxes"), "boxes"),
            _safe_text(getattr(item, "notes", ""), ""),
        ])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(table)

    doc.build(elements)
    out.seek(0)
    return out


def build_grouped_purchase_order_pdf(orders):
    """Genera PDF consolidado premium."""
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    elements = []

    rows_by_order, consolidated_rows, market_names = _grouped_rows_from_orders(orders)
    provider_name = _provider_name(orders[0]) if orders else "Proveedor"

    elements.append(Paragraph("Consolidado de pedidos", styles["Title"]))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f"Proveedor: {provider_name}", styles["Normal"]))
    elements.append(Paragraph(f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Normal"]))
    elements.append(Paragraph(f"Pedidos incluidos: {len(orders)}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    summary_table = [["Producto"] + market_names + ["TOTAL"]]
    for item in consolidated_rows:
        summary_table.append(
            [item["product_name"]]
            + [int(item["markets"].get(market_name, 0)) for market_name in market_names]
            + [int(item["total_units"])]
        )

    table = Table(summary_table, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 20))

    for order_data in rows_by_order:
        elements.append(Paragraph(
            f"Pedido #{order_data['order_id']} · {order_data['market_name']}",
            styles["Heading3"]
        ))

        detail_data = [["Producto", "Cantidad", "Unidad", "Notas"]]
        for item in order_data["items"]:
            detail_data.append([
                item["product_name"],
                int(item["quantity_units"]),
                item["purchase_unit"],
                item["notes"],
            ])

        detail_table = Table(detail_data, repeatRows=1)
        detail_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FFF3CD")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elements.append(detail_table)

        if order_data["notes"]:
            elements.append(Spacer(1, 6))
            elements.append(Paragraph(f"Notas: {order_data['notes']}", styles["Normal"]))

        elements.append(Spacer(1, 16))

    doc.build(elements)
    out.seek(0)
    return out
