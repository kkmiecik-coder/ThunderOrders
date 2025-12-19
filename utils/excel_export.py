"""
Excel Export Module
===================

Funkcje do generowania plików Excel z danymi zamówień.
"""

from io import BytesIO
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Fill, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter


def generate_exclusive_closure_excel(page_id):
    """
    Generuje plik Excel z zamówieniami dla zamkniętej strony Exclusive.

    Kolumny:
    - Numer zamówienia
    - Imię i nazwisko
    - Email
    - Telefon
    - Data zamówienia
    - [Dla każdego produktu]: Ilość | Status (Zrealizowane/Niezrealizowane)
    - Wartość całkowita

    Args:
        page_id: ID strony Exclusive

    Returns:
        BytesIO: Buffer z plikiem .xlsx
    """
    from modules.exclusive.models import ExclusivePage
    from modules.orders.models import Order, OrderItem

    page = ExclusivePage.query.get(page_id)
    if not page:
        raise ValueError(f"Strona Exclusive o ID {page_id} nie istnieje")

    # Pobierz zamówienia
    orders = Order.query.filter_by(exclusive_page_id=page_id).order_by(Order.created_at.asc()).all()

    # Zbierz unikalne produkty z zamówień
    product_names = []
    product_ids = []
    for order in orders:
        for item in order.items:
            if item.product_id not in product_ids:
                product_ids.append(item.product_id)
                product_names.append(item.product_name)

    # Tworzenie workbooka
    wb = Workbook()
    ws = wb.active
    ws.title = "Zamówienia"

    # Style
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="7B2CBF", end_color="7B2CBF", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    cell_alignment = Alignment(horizontal="left", vertical="center")
    center_alignment = Alignment(horizontal="center", vertical="center")

    thin_border = Border(
        left=Side(style='thin', color='CCCCCC'),
        right=Side(style='thin', color='CCCCCC'),
        top=Side(style='thin', color='CCCCCC'),
        bottom=Side(style='thin', color='CCCCCC')
    )

    fulfilled_fill = PatternFill(start_color="D4EDDA", end_color="D4EDDA", fill_type="solid")
    unfulfilled_fill = PatternFill(start_color="F8D7DA", end_color="F8D7DA", fill_type="solid")

    # Nagłówek - informacje o stronie
    ws.merge_cells('A1:E1')
    ws['A1'] = f"Podsumowanie zamówień: {page.name}"
    ws['A1'].font = Font(bold=True, size=14)
    ws['A1'].alignment = Alignment(horizontal="left")

    ws['A2'] = f"Data zamknięcia: {page.closed_at.strftime('%d.%m.%Y %H:%M') if page.closed_at else '-'}"
    ws['A3'] = f"Liczba zamówień: {len(orders)}"
    ws['A4'] = ""

    # Nagłówki kolumn
    headers = ["Lp.", "Nr zamówienia", "Imię i nazwisko", "Email", "Telefon", "Data zamówienia"]

    # Dodaj kolumny produktów
    for product_name in product_names:
        # Skróć długie nazwy
        short_name = product_name[:30] + "..." if len(product_name) > 30 else product_name
        headers.append(f"{short_name}\n(ilość)")
        headers.append(f"{short_name}\n(status)")

    headers.append("Wartość (PLN)")

    header_row = 5
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border

    # Dane zamówień
    for idx, order in enumerate(orders, 1):
        row = header_row + idx

        # Podstawowe dane
        ws.cell(row=row, column=1, value=idx).alignment = center_alignment
        ws.cell(row=row, column=2, value=order.order_number).alignment = cell_alignment
        ws.cell(row=row, column=3, value=order.customer_name or "-").alignment = cell_alignment
        ws.cell(row=row, column=4, value=order.customer_email or "-").alignment = cell_alignment

        phone = order.guest_phone if order.is_guest_order else (order.user.phone if order.user else None)
        ws.cell(row=row, column=5, value=phone or "-").alignment = cell_alignment

        ws.cell(row=row, column=6, value=order.created_at.strftime('%d.%m.%Y %H:%M')).alignment = center_alignment

        # Kolumny produktów
        col_offset = 7
        for product_idx, product_id in enumerate(product_ids):
            qty_col = col_offset + product_idx * 2
            status_col = qty_col + 1

            # Znajdź order item dla tego produktu
            order_item = next((item for item in order.items if item.product_id == product_id), None)

            if order_item:
                # Ilość
                ws.cell(row=row, column=qty_col, value=order_item.quantity).alignment = center_alignment

                # Status
                if order_item.is_set_fulfilled is None:
                    # Produkt poza setem - zawsze realizowany
                    status_cell = ws.cell(row=row, column=status_col, value="TAK")
                    status_cell.fill = fulfilled_fill
                elif order_item.is_set_fulfilled:
                    status_cell = ws.cell(row=row, column=status_col, value="TAK")
                    status_cell.fill = fulfilled_fill
                else:
                    status_cell = ws.cell(row=row, column=status_col, value="NIE")
                    status_cell.fill = unfulfilled_fill
                status_cell.alignment = center_alignment
            else:
                ws.cell(row=row, column=qty_col, value="-").alignment = center_alignment
                ws.cell(row=row, column=status_col, value="-").alignment = center_alignment

        # Wartość zamówienia
        total_col = col_offset + len(product_ids) * 2
        ws.cell(row=row, column=total_col, value=float(order.total_amount) if order.total_amount else 0).alignment = center_alignment

        # Obramowanie wszystkich komórek w wierszu
        for col in range(1, total_col + 1):
            ws.cell(row=row, column=col).border = thin_border

    # Podsumowanie
    summary_row = header_row + len(orders) + 2
    ws.cell(row=summary_row, column=1, value="PODSUMOWANIE:").font = Font(bold=True)

    total_value = sum(float(o.total_amount or 0) for o in orders)
    ws.cell(row=summary_row + 1, column=1, value=f"Łączna wartość zamówień: {total_value:.2f} PLN")
    ws.cell(row=summary_row + 2, column=1, value=f"Liczba zamówień: {len(orders)}")

    # Dostosuj szerokość kolumn
    ws.column_dimensions['A'].width = 6
    ws.column_dimensions['B'].width = 18
    ws.column_dimensions['C'].width = 25
    ws.column_dimensions['D'].width = 30
    ws.column_dimensions['E'].width = 15
    ws.column_dimensions['F'].width = 18

    # Kolumny produktów
    for i in range(len(product_ids) * 2):
        col_letter = get_column_letter(7 + i)
        ws.column_dimensions[col_letter].width = 12

    # Ostatnia kolumna (wartość)
    last_col_letter = get_column_letter(7 + len(product_ids) * 2)
    ws.column_dimensions[last_col_letter].width = 15

    # Wysokość wiersza nagłówków
    ws.row_dimensions[header_row].height = 45

    # Zapisz do bufora
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output


def generate_orders_excel(orders, filename_prefix="zamowienia"):
    """
    Generuje ogólny plik Excel z listą zamówień.

    Args:
        orders: Lista zamówień (Order objects)
        filename_prefix: Prefix nazwy pliku

    Returns:
        BytesIO: Buffer z plikiem .xlsx
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Zamówienia"

    # Style
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="7B2CBF", end_color="7B2CBF", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")

    # Nagłówki
    headers = [
        "Lp.", "Nr zamówienia", "Klient", "Email", "Telefon",
        "Status", "Typ", "Data", "Wartość (PLN)"
    ]

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment

    # Dane
    for idx, order in enumerate(orders, 1):
        ws.cell(row=idx + 1, column=1, value=idx)
        ws.cell(row=idx + 1, column=2, value=order.order_number)
        ws.cell(row=idx + 1, column=3, value=order.customer_name or "-")
        ws.cell(row=idx + 1, column=4, value=order.customer_email or "-")

        phone = order.guest_phone if order.is_guest_order else (order.user.phone if order.user else None)
        ws.cell(row=idx + 1, column=5, value=phone or "-")

        ws.cell(row=idx + 1, column=6, value=order.status_display)
        ws.cell(row=idx + 1, column=7, value="Exclusive" if order.is_exclusive else "Standard")
        ws.cell(row=idx + 1, column=8, value=order.created_at.strftime('%d.%m.%Y %H:%M'))
        ws.cell(row=idx + 1, column=9, value=float(order.total_amount) if order.total_amount else 0)

    # Dostosuj szerokość kolumn
    column_widths = [6, 18, 25, 30, 15, 20, 12, 18, 15]
    for i, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # Zapisz do bufora
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output
