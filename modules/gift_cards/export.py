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


def _cards_text(cards, pools):
    """„San, Yunho ×2” — a przy kilku pulach „50k: San · 100k: Yunho ×2”."""
    def one(group):
        counts = Counter(a.card_type.name for a in group)
        return ', '.join(name if n == 1 else f'{name} ×{n}' for name, n in counts.items())
    if len(pools) <= 1:
        return one(cards)
    parts = []
    for pool in pools:
        group = [a for a in cards if a.pool_id == pool.id]
        if group:
            parts.append(f'{pool.label}: {one(group)}')
    return ' · '.join(parts)


def build_distribution_excel(campaign, rows, usage, status_label) -> BytesIO:
    """rows — wiersze jak na stronie szczegółów; usage — [{'pool', 'items': [{'type', 'assigned', ...}]}]."""
    types = list(campaign.card_types)
    pools = list(campaign.pools)
    several = len(pools) > 1
    columns = [(pool, t) for pool in pools for t in types]
    wb = Workbook()

    # --- Arkusz 1: klientki ---
    ws = wb.active
    ws.title = 'Klientki'
    labels = (['Miejsce', 'Imię i nazwisko', 'Kart', 'Ranking', 'Przydzielone karty']
              + [f'{t.name} — {pool.label}' if several else t.name for pool, t in columns]
              + ['Powtórki', 'Brakuje', 'Uwagi klientki', 'Uwagi'])
    _title(ws, campaign, status_label, len(labels))
    _header(ws, 4, labels)
    wrap_cols = {2, 4, 5, len(labels) - 1, len(labels)}
    dup_col, missing_col = len(labels) - 3, len(labels) - 2
    r = 5
    for row in rows:
        user = row['user']
        cards = row['cards']
        per_cell = Counter((a.pool_id, a.card_type_id) for a in cards)
        duplicates = sum(1 for a in cards if a.is_duplicate)
        # Bez maili — tylko imię i nazwisko (mail pojawi się wyłącznie, gdy konto nie ma imienia).
        values = ([row['place'] or '', user.full_name if user else '',
                   # Ile kart się należy (osoba bez uprawnień — ile ma przydzielonych).
                   row['total'] or len(cards), row.get('ranking_text') or '',
                   _cards_text(cards, pools)]
                  + [per_cell.get((pool.id, t.id)) or None for pool, t in columns]
                  + [duplicates or None, row['missing'] or None, row.get('notes') or '',
                     '' if row['entitled'] else 'bez uprawnień (np. anulowane zamówienie)'])
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=r, column=col, value=value)
            cell.border = _BORDER
            cell.alignment = _WRAP if col in wrap_cols else _CENTER
        if duplicates:
            ws.cell(row=r, column=dup_col).fill = _DUP_FILL
        if row['missing']:
            ws.cell(row=r, column=missing_col).fill = _MISSING_FILL
        r += 1

    widths = ([9, 28, 7, 34, 44]
              + [max(10, min(len(labels[5 + i]) + 2, 24)) for i in range(len(columns))]
              + [10, 10, 36, 30])
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

    # --- Arkusz 2: podsumowanie (osobna tabelka dla każdej puli) ---
    ws2 = wb.create_sheet('Podsumowanie')
    _title(ws2, campaign, status_label, 4)
    r = 4
    for group in usage:
        if several:
            ws2.cell(row=r, column=1, value=group['pool'].label).font = Font(bold=True, size=12, color=_PURPLE)
            r += 1
        _header(ws2, r, ['Rodzaj karty', 'Przydzielono', 'Dostępne (wpisana ilość)', 'Ponad stan'])
        r += 1
        items = group['items']
        for u in items:
            values = [u['type'].name, u['assigned'], u['quantity'], u['over'] or None]
            for col, value in enumerate(values, start=1):
                cell = ws2.cell(row=r, column=col, value=value)
                cell.border = _BORDER
                cell.alignment = _WRAP if col == 1 else _CENTER
            if u['over']:
                ws2.cell(row=r, column=4).fill = _MISSING_FILL
            r += 1
        ws2.cell(row=r, column=1, value='Razem').font = Font(bold=True)
        ws2.cell(row=r, column=2, value=sum(u['assigned'] for u in items)).font = Font(bold=True)
        ws2.cell(row=r, column=3, value=sum(u['quantity'] for u in items)).font = Font(bold=True)
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
        ('Osób z uwagami', sum(1 for row in rows if row.get('notes'))),
    ]
    for label, value in facts:
        ws2.cell(row=r, column=1, value=label).font = Font(bold=True)
        ws2.cell(row=r, column=2, value=value).alignment = _CENTER
        r += 1
    for col, width in enumerate([34, 14, 24, 12], start=1):
        ws2.column_dimensions[get_column_letter(col)].width = width

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
