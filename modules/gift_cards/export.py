"""Plik Excel z rozdziału gratisowych kart: arkusz klientek + podsumowanie rodzajów."""

from collections import Counter
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from utils.timeutil import to_pl, utcnow

_PURPLE = '7B2CBF'
_RED = 'F8D7DA'
_ORANGE = 'FFE5CC'

_thin = Side(style='thin', color='D0D0D0')
_BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
_HEADER_FONT = Font(bold=True, color='FFFFFF', size=10)
_HEADER_FILL = PatternFill(start_color=_PURPLE, end_color=_PURPLE, fill_type='solid')
_HEADER_ALIGN = Alignment(horizontal='center', vertical='center', wrap_text=True)
_TITLE_FONT = Font(bold=True, size=14, color=_PURPLE)
_SUB_FONT = Font(size=10, color='666666')
_WRAP = Alignment(horizontal='left', vertical='center', wrap_text=True)
_CENTER = Alignment(horizontal='center', vertical='center')
_MISSING_FILL = PatternFill(start_color=_RED, end_color=_RED, fill_type='solid')
_DUP_FILL = PatternFill(start_color=_ORANGE, end_color=_ORANGE, fill_type='solid')


def _title(ws, campaign, status_label, columns):
    ws.cell(row=1, column=1, value=f'Rozdział gratisów — {campaign.name}').font = _TITLE_FONT
    ws.cell(row=2, column=1,
            value=f'Status: {status_label} · wygenerowano {to_pl(utcnow()).strftime("%d.%m.%Y %H:%M")}'
            ).font = _SUB_FONT
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(columns, 1))
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(columns, 1))


def _header(ws, row, labels):
    for col, label in enumerate(labels, start=1):
        cell = ws.cell(row=row, column=col, value=label)
        cell.font, cell.fill, cell.alignment, cell.border = _HEADER_FONT, _HEADER_FILL, _HEADER_ALIGN, _BORDER


def _cards_text(cards):
    counts = Counter(a.card_type.name for a in cards)
    return ', '.join(name if n == 1 else f'{name} ×{n}' for name, n in counts.items())


def build_distribution_excel(campaign, rows, usage, status_label) -> BytesIO:
    """rows — wiersze jak na stronie szczegółów; usage — [{'type', 'assigned', 'quantity', 'over'}]."""
    types = list(campaign.card_types)
    wb = Workbook()

    # --- Arkusz 1: klientki ---
    ws = wb.active
    ws.title = 'Klientki'
    labels = (['Miejsce', 'Imię i nazwisko', 'E-mail', 'Kart', 'Przydzielone karty']
              + [t.name for t in types] + ['Powtórki', 'Brakuje', 'Uwagi'])
    _title(ws, campaign, status_label, len(labels))
    _header(ws, 4, labels)
    r = 5
    for row in rows:
        user = row['user']
        cards = row['cards']
        per_type = Counter(a.card_type_id for a in cards)
        duplicates = sum(1 for a in cards if a.is_duplicate)
        values = ([row['place'] or '', user.full_name if user else '', user.email if user else '',
                   len(cards), _cards_text(cards)]
                  + [per_type.get(t.id) or None for t in types]
                  + [duplicates or None, row['missing'] or None,
                     '' if row['entitled'] else 'bez uprawnień (np. anulowane zamówienie)'])
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=r, column=col, value=value)
            cell.border = _BORDER
            cell.alignment = _WRAP if col in (2, 3, 5, len(labels)) else _CENTER
        if duplicates:
            ws.cell(row=r, column=len(labels) - 2).fill = _DUP_FILL
        if row['missing']:
            ws.cell(row=r, column=len(labels) - 1).fill = _MISSING_FILL
        r += 1

    widths = [9, 26, 30, 7, 40] + [max(10, min(len(t.name) + 2, 22)) for t in types] + [10, 10, 30]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = 'C5'
    if rows:
        ws.auto_filter.ref = f'A4:{get_column_letter(len(labels))}{r - 1}'
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = '4:4'

    # --- Arkusz 2: podsumowanie ---
    ws2 = wb.create_sheet('Podsumowanie')
    _title(ws2, campaign, status_label, 4)
    _header(ws2, 4, ['Rodzaj karty', 'Przydzielono', 'Dostępne (wpisana ilość)', 'Ponad stan'])
    r = 5
    for u in usage:
        values = [u['type'].name, u['assigned'], u['type'].quantity, u['over'] or None]
        for col, value in enumerate(values, start=1):
            cell = ws2.cell(row=r, column=col, value=value)
            cell.border = _BORDER
            cell.alignment = _WRAP if col == 1 else _CENTER
        if u['over']:
            ws2.cell(row=r, column=4).fill = _MISSING_FILL
        r += 1
    total_cell = ws2.cell(row=r, column=1, value='Razem')
    total_cell.font = Font(bold=True)
    ws2.cell(row=r, column=2, value=sum(u['assigned'] for u in usage)).font = Font(bold=True)
    quantities = [u['type'].quantity for u in usage]
    if quantities and all(isinstance(q, int) for q in quantities):
        ws2.cell(row=r, column=3, value=sum(quantities)).font = Font(bold=True)
    for col in range(1, 5):
        ws2.cell(row=r, column=col).border = _BORDER
        ws2.cell(row=r, column=col).alignment = _WRAP if col == 1 else _CENTER

    r += 2
    entitled = [row for row in rows if row['entitled']]
    facts = [
        ('Uprawnionych osób', len(entitled)),
        ('Kart należnych łącznie', sum(row['total'] for row in entitled)),
        ('Powtórek', sum(1 for row in rows for a in row['cards'] if a.is_duplicate)),
        ('Osób, którym brakuje kart', sum(1 for row in rows if row['missing'])),
    ]
    for label, value in facts:
        ws2.cell(row=r, column=1, value=label).font = Font(bold=True)
        ws2.cell(row=r, column=2, value=value).alignment = _CENTER
        r += 1
    for col, width in enumerate([32, 14, 24, 12], start=1):
        ws2.column_dimensions[get_column_letter(col)].width = width

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
