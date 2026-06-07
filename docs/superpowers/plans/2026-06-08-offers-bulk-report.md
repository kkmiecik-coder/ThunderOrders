# Raport zbiorowy ofert (Excel) — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Akcja masowa „Raport zbiorowy" na liście ofert generuje jeden plik `.xlsx`: arkusz zbiorczy + jedna zakładka per zaznaczona oferta (statystyki + macierz ilości + macierz wartości).

**Architecture:** Reużywamy istniejący `_preorder_collect_data(page)` jako źródło danych. Z obecnych funkcji `_build_preorder_*_sheet` wydzielamy rdzenie piszące macierz do dowolnego arkusza od dowolnego wiersza (`_write_quantities_matrix`, `_write_values_matrix`), aby ta sama logika służyła raportom pojedynczym i zbiorczemu. Nowa funkcja `generate_offers_bulk_report(pages)` składa workbook; nowy route `POST /admin/offers/bulk/report` zwraca plik; front pobiera go przez `fetch → blob → download`.

**Tech Stack:** Flask, SQLAlchemy (MariaDB), openpyxl 3.1.2, vanilla JS. Testy: pytest (pure-function, wzorzec jak `tests/test_offers_bulk_eligibility.py`).

---

## Uwagi wstępne dla wykonawcy

- Branch roboczy: `feature/offers-bulk-report`. NIE commituj na `main` (push do `main` = auto-deploy na produkcję).
- **pytest nie jest zainstalowany.** Przed pierwszym testem: `./venv/bin/pip install pytest`. Testy uruchamiaj interpreterem z venv: `./venv/bin/python -m pytest ...`.
- Testy w tym repo to czyste funkcje bez bazy/Flask (patrz `tests/test_offers_bulk_eligibility.py`). Logikę wymagającą DB (macierze, statystyki, route) weryfikujemy **smoke testem** — uruchomieniem aplikacji lokalnie (XAMPP, http://localhost:5001) i pobraniem pliku, oraz otwarciem pliku przez openpyxl. Nie wymyślamy fixturów DB, bo repo ich nie ma.
- Wszystkie helpery Excela (`_styles`, `_write_cell`, `_write_header_row`, `_set_col_widths`, `_section_column_name`, `_preorder_collect_data`, `_format_period`, `_fmt_price`, `get_column_letter`, stałe `_PURPLE`, `_PURPLE_LIGHT`, `_PREORDER_SUMA_FILL`) już istnieją w `utils/excel_export.py`.

---

## Task 1: Helper `_safe_sheet_title` (nazwy zakładek bezpieczne dla Excela)

Excel limituje nazwę arkusza do 31 znaków, zabrania znaków `[]:*?/\` i wymaga unikalności (case-insensitive). Nazwy ofert mogą być długie i powtarzalne — potrzebny czysty helper.

**Files:**
- Modify: `utils/excel_export.py` (dodaj helper w sekcji „Helpers", obok `_format_period` ~linia 1366)
- Test: `tests/test_offers_bulk_report.py` (create)

- [ ] **Step 1: Napisz failing test**

```python
# tests/test_offers_bulk_report.py
from utils.excel_export import _safe_sheet_title


def test_short_name_unchanged():
    assert _safe_sheet_title('Lato 2026', set()) == 'Lato 2026'


def test_long_name_truncated_to_31():
    name = 'A' * 50
    title = _safe_sheet_title(name, set())
    assert len(title) <= 31
    assert title == 'A' * 31


def test_illegal_chars_replaced():
    title = _safe_sheet_title('Sprzedaż: K-pop / [2026]', set())
    for ch in '[]:*?/\\':
        assert ch not in title


def test_duplicate_gets_suffix():
    used = {'lato 2026'}
    title = _safe_sheet_title('Lato 2026', used)
    assert title != 'Lato 2026'
    assert title.lower() not in used


def test_duplicate_suffix_fits_31_chars():
    used = {('a' * 31).lower()}
    title = _safe_sheet_title('A' * 31, used)
    assert len(title) <= 31
    assert title.lower() not in used


def test_empty_name_gets_fallback():
    assert _safe_sheet_title('', set()) != ''
```

- [ ] **Step 2: Uruchom test — ma FAIL**

Run: `./venv/bin/pip install pytest && ./venv/bin/python -m pytest tests/test_offers_bulk_report.py -v`
Expected: FAIL — `ImportError: cannot import name '_safe_sheet_title'`

- [ ] **Step 3: Zaimplementuj helper**

Dodaj w `utils/excel_export.py` (po `_format_period`):

```python
def _safe_sheet_title(name, used_titles):
    """
    Zwraca nazwę arkusza bezpieczną dla Excela: max 31 znaków, bez znaków
    []:*?/\\, unikalną względem used_titles (porównanie case-insensitive).
    used_titles — kolekcja już użytych tytułów (lowercase). Funkcja NIE mutuje
    used_titles; po użyciu wywołujący powinien dodać zwrócony tytuł (lowercase).
    """
    base = (name or 'Oferta').strip()
    for ch in '[]:*?/\\':
        base = base.replace(ch, ' ')
    base = base.strip() or 'Oferta'
    base = base[:31]

    if base.lower() not in used_titles:
        return base

    n = 2
    while True:
        suffix = f' ({n})'
        trimmed = base[:31 - len(suffix)].rstrip()
        candidate = f'{trimmed}{suffix}'
        if candidate.lower() not in used_titles:
            return candidate
        n += 1
```

- [ ] **Step 4: Uruchom test — ma PASS**

Run: `./venv/bin/python -m pytest tests/test_offers_bulk_report.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add utils/excel_export.py tests/test_offers_bulk_report.py
git commit -m "feat(offers): helper _safe_sheet_title dla nazw zakładek raportu zbiorowego"
```

---

## Task 2: Refaktor — wydziel rdzenie macierzy z funkcji per-arkusz

Cel: ta sama logika macierzy ma działać zarówno w raportach pojedynczych (osobne arkusze), jak i w raporcie zbiorczym (obie macierze w jednym arkuszu, jedna pod drugą). Refaktor jest **behavior-preserving** — raporty pojedyncze muszą wyglądać identycznie.

**Files:**
- Modify: `utils/excel_export.py:1221-1359` (funkcje `_build_preorder_summary_sheet`, `_build_preorder_quantities_sheet`)

- [ ] **Step 1: Dodaj rdzeń `_write_quantities_matrix`**

Wstaw przed `_build_preorder_summary_sheet` (~linia 1221):

```python
def _write_quantities_matrix(ws, page, s, start_row=1):
    """
    Wpisuje macierz ILOŚCI (klient × sekcja, sumy sztuk) do arkusza ws,
    poczynając od wiersza start_row. NIE ustawia szerokości kolumn ani freeze.
    Zwraca krotkę (next_free_row, num_sections).
    """
    data = _preorder_collect_data(page)
    sections = data['sections']
    customers = data['customers']
    matrix = data['matrix']

    headers = ['Klient'] + [_section_column_name(sec) for sec in sections]
    _write_header_row(ws, start_row, headers, s)

    for i, customer in enumerate(customers):
        row = start_row + 1 + i
        _write_cell(ws, row, 1, customer['name'], s, align='left')
        for j, sec in enumerate(sections):
            entries = matrix.get((customer['key'], sec.id), [])
            qty_total = sum(q for _, q in entries) if entries else None
            _write_cell(ws, row, 2 + j, qty_total, s, align='center')

    return start_row + 1 + len(customers), len(sections)
```

- [ ] **Step 2: Przepnij `_build_preorder_quantities_sheet` na rdzeń**

Zastąp całe ciało funkcji `_build_preorder_quantities_sheet` (linie ~1334-1359):

```python
def _build_preorder_quantities_sheet(wb, page, s):
    """Zakładka 'Ilości' — macierz klient × sekcja z łącznymi ilościami sztuk."""
    ws = wb.create_sheet(title='Ilości', index=1)
    ws.sheet_properties.tabColor = _PURPLE_LIGHT

    _, n_sections = _write_quantities_matrix(ws, page, s, start_row=1)

    ws.column_dimensions['A'].width = 24
    for j in range(n_sections):
        ws.column_dimensions[get_column_letter(2 + j)].width = 16

    ws.freeze_panes = 'B2'
```

- [ ] **Step 3: Dodaj rdzeń `_write_values_matrix`**

Wstaw przed `_build_preorder_summary_sheet`. Przenosi logikę z obecnego `_build_preorder_summary_sheet`, ale pisze od `start_row` zamiast od stałych wierszy 1-4, i nie tworzy arkusza/szerokości/freeze:

```python
def _write_values_matrix(ws, page, s, start_row=1):
    """
    Wpisuje macierz WARTOŚCI (klient × sekcja, ceny PLN/KRW, sumy, kurs) do ws
    od wiersza start_row. NIE ustawia szerokości kolumn ani freeze.
    Zwraca krotkę (next_free_row, num_sections).
    """
    data = _preorder_collect_data(page)
    sections = data['sections']
    customers = data['customers']
    matrix = data['matrix']

    price_fill = PatternFill(start_color=_PREORDER_PRICE_FILL, end_color=_PREORDER_PRICE_FILL, fill_type='solid')
    suma_fill = PatternFill(start_color=_PREORDER_SUMA_FILL, end_color=_PREORDER_SUMA_FILL, fill_type='solid')

    header_row = start_row
    headers = ['Klient'] + [_section_column_name(sec) for sec in sections] + ['Suma (PLN)', 'Suma (KRW)']
    _write_header_row(ws, header_row, headers, s)

    section_products = [_section_products(sec) for sec in sections]
    pln_prices = [_price_pln_for_section(prods) for prods in section_products]
    krw_prices = [_price_krw_for_section(prods) for prods in section_products]

    pln_row = header_row + 1
    _write_cell(ws, pln_row, 1, 'pln', s, align='center', bold=True, fill=price_fill)
    for idx, val in enumerate(pln_prices, start=2):
        _write_cell(ws, pln_row, idx, val, s, align='center', fill=price_fill)
    _write_cell(ws, pln_row, len(sections) + 2, None, s, fill=price_fill)
    _write_cell(ws, pln_row, len(sections) + 3, None, s, fill=price_fill)

    krw_row = header_row + 2
    _write_cell(ws, krw_row, 1, 'krw', s, align='center', bold=True, fill=price_fill)
    for idx, val in enumerate(krw_prices, start=2):
        _write_cell(ws, krw_row, idx, val, s, align='center', fill=price_fill)
    _write_cell(ws, krw_row, len(sections) + 2, None, s, fill=price_fill)
    _write_cell(ws, krw_row, len(sections) + 3, None, s, fill=price_fill)

    customer_totals_pln = []
    customer_totals_krw = []
    col_totals_pln = [0.0] * len(sections)
    col_totals_krw = [0.0] * len(sections)

    first_customer_row = header_row + 3
    for i, customer in enumerate(customers):
        row = first_customer_row + i
        _write_cell(ws, row, 1, customer['name'], s, align='left')
        total_pln = 0.0
        total_krw = 0.0

        for j, sec in enumerate(sections):
            col = 2 + j
            entries = matrix.get((customer['key'], sec.id), [])
            if not entries:
                _write_cell(ws, row, col, None, s, align='center')
                continue

            if sec.section_type == 'variant_group':
                cell_value = _format_variant_cell(entries)
            else:
                cell_value = _format_product_cell(entries)

            _write_cell(ws, row, col, cell_value, s, align='center')

            for product, qty in entries:
                if product and product.sale_price is not None:
                    val_pln = float(product.sale_price) * qty
                    total_pln += val_pln
                    col_totals_pln[j] += val_pln
                if product and product.purchase_currency == 'KRW' and product.purchase_price is not None:
                    val_krw = float(product.purchase_price) * qty
                    total_krw += val_krw
                    col_totals_krw[j] += val_krw

        total_pln_val = _fmt_price(total_pln) if total_pln else None
        total_krw_val = _fmt_price(total_krw, decimals=0) if total_krw else None
        _write_cell(ws, row, len(sections) + 2, total_pln_val, s, align='center', bold=True)
        _write_cell(ws, row, len(sections) + 3, total_krw_val, s, align='center', bold=True)

        customer_totals_pln.append(total_pln)
        customer_totals_krw.append(total_krw)

    suma_row = first_customer_row + len(customers)
    _write_cell(ws, suma_row, 1, 'SUMA (PLN)', s, align='left', bold=True, fill=suma_fill)
    for j, total in enumerate(col_totals_pln):
        _write_cell(ws, suma_row, 2 + j, _fmt_price(total) if total else None,
                    s, align='center', bold=True, fill=suma_fill)
    total_all_pln = sum(customer_totals_pln)
    total_all_krw = sum(customer_totals_krw)
    _write_cell(ws, suma_row, len(sections) + 2,
                _fmt_price(total_all_pln) if total_all_pln else None,
                s, align='center', bold=True, fill=suma_fill)
    _write_cell(ws, suma_row, len(sections) + 3,
                _fmt_price(total_all_krw, decimals=0) if total_all_krw else None,
                s, align='center', bold=True, fill=suma_fill)

    rate = _get_krw_pln_rate()
    rate_row = suma_row + 2
    _write_cell(ws, rate_row, 1, 'Kurs KRW/PLN:', s, align='left', bold=True)
    if rate:
        _write_cell(ws, rate_row, 2, round(rate), s, align='center', bold=True)

    return rate_row + 1, len(sections)
```

- [ ] **Step 4: Przepnij `_build_preorder_summary_sheet` na rdzeń**

Zastąp całe ciało `_build_preorder_summary_sheet` (linie ~1221-1331):

```python
def _build_preorder_summary_sheet(wb, page, s):
    """Zakładka 'Podsumowanie' — macierz klient × sekcja z cenami, sumami i kursem."""
    ws = wb.create_sheet(title='Podsumowanie', index=0)
    ws.sheet_properties.tabColor = _PURPLE

    _, n_sections = _write_values_matrix(ws, page, s, start_row=1)

    ws.column_dimensions['A'].width = 24
    for j in range(n_sections):
        ws.column_dimensions[get_column_letter(2 + j)].width = 20
    ws.column_dimensions[get_column_letter(n_sections + 2)].width = 12
    ws.column_dimensions[get_column_letter(n_sections + 3)].width = 14

    ws.freeze_panes = 'B4'
```

- [ ] **Step 5: Smoke test — pojedynczy raport nadal działa**

Wymaga lokalnej bazy (XAMPP) z co najmniej jedną zamkniętą stroną typu preorder. Znajdź id takiej strony i wygeneruj plik bez uruchamiania serwera:

Run:
```bash
./venv/bin/python -c "
from app import create_app
from modules.offers.models import OfferPage
from utils.excel_export import generate_offer_closure_excel
from utils.offer_closure import get_page_summary
app = create_app()
with app.app_context():
    page = OfferPage.query.filter_by(page_type='preorder', is_fully_closed=True).first()
    if not page:
        print('BRAK zamkniętej strony preorder — pomiń, zweryfikuj w Task 7 przez UI'); raise SystemExit
    buf = generate_offer_closure_excel(page, get_page_summary(page.id, include_financials=True))
    open('/tmp/single_report_smoke.xlsx','wb').write(buf.getvalue())
    print('OK zapisano /tmp/single_report_smoke.xlsx')
"
```
Expected: `OK zapisano ...` (lub komunikat o braku danych — wtedy weryfikacja przeniesiona do Task 7). Jeśli `app` nie ma `create_app`, sprawdź `app.py` jak tworzona jest instancja i dostosuj import.

- [ ] **Step 6: Otwórz plik i sprawdź arkusze**

Run:
```bash
./venv/bin/python -c "
import openpyxl
wb = openpyxl.load_workbook('/tmp/single_report_smoke.xlsx')
print('Arkusze:', wb.sheetnames)
ws = wb['Podsumowanie']; print('Podsumowanie A1:', ws['A1'].value)
"
```
Expected: lista arkuszy zawiera `Podsumowanie` i `Ilości`; `A1` = `Klient`.

- [ ] **Step 7: Commit**

```bash
git add utils/excel_export.py
git commit -m "refactor(offers): wydziel rdzenie macierzy ilości/wartości (reuse w raporcie zbiorczym)"
```

---

## Task 3: Helper `_offer_stats` (statystyki jednej oferty)

**Files:**
- Modify: `utils/excel_export.py` (dodaj przed `generate_offers_bulk_report`, patrz Task 4)

- [ ] **Step 1: Zaimplementuj `_offer_stats`**

```python
def _offer_stats(page):
    """
    Zwraca statystyki jednej oferty dla raportu zbiorczego:
        status_label, type_label, period, orders_count, revenue_pln (float), sets_count
    Przychód liczony z tych samych danych co macierz wartości (spójność).
    """
    from modules.orders.models import Order

    status_labels = {
        'draft': 'Szkic', 'scheduled': 'Zaplanowana', 'active': 'Aktywna',
        'paused': 'Wstrzymana', 'ended': 'Zakończona',
    }
    type_labels = {'exclusive': 'Exclusive', 'preorder': 'Pre-order'}

    status_label = status_labels.get(page.status, page.status or '-')
    if page.is_fully_closed:
        status_label += ' (zamknięta)'

    orders_count = Order.query.filter_by(offer_page_id=page.id).filter(
        Order.status != 'anulowane'
    ).count()

    data = _preorder_collect_data(page)
    revenue = 0.0
    for entries in data['matrix'].values():
        for product, qty in entries:
            if product and product.sale_price is not None:
                revenue += float(product.sale_price) * qty

    sets_count = sum(1 for sec in page.sections if sec.section_type == 'set')

    return {
        'status_label': status_label,
        'type_label': type_labels.get(page.page_type, page.page_type or '-'),
        'period': _format_period(page.starts_at, page.ends_at),
        'orders_count': orders_count,
        'revenue_pln': revenue,
        'sets_count': sets_count,
    }
```

- [ ] **Step 2: Commit (razem z Task 4 — helper jest używany przez generator). Przejdź do Task 4.**

Brak osobnego commita; `_offer_stats` zostanie zacommitowany w Task 4 wraz z generatorem, który go używa.

---

## Task 4: Generator `generate_offers_bulk_report` + arkusze zbiorcze

**Files:**
- Modify: `utils/excel_export.py` (dodaj nowe funkcje po `generate_offer_live_excel`, w nowej sekcji)

- [ ] **Step 1: Dodaj arkusz zbiorczy, arkusz oferty i generator**

Wstaw blok (zawiera też `_offer_stats` z Task 3, jeśli jeszcze nie dodany):

```python
# ============================================
# Raport zbiorowy ofert (bulk, multi-offer)
# ============================================

def _build_bulk_overview_sheet(wb, pages, s):
    """Pierwszy arkusz: zestawienie wszystkich zaznaczonych ofert + wiersz SUMA."""
    ws = wb.create_sheet(title='Podsumowanie', index=0)
    ws.sheet_properties.tabColor = _PURPLE

    headers = ['Oferta', 'Status', 'Typ', 'Okres',
               'Liczba zamówień', 'Przychód (PLN)', 'Liczba setów']
    _write_header_row(ws, 1, headers, s)

    suma_fill = PatternFill(start_color=_PREORDER_SUMA_FILL, end_color=_PREORDER_SUMA_FILL, fill_type='solid')

    total_orders = 0
    total_revenue = 0.0
    for i, page in enumerate(pages):
        st = _offer_stats(page)
        row = 2 + i
        _write_cell(ws, row, 1, page.name, s, align='left')
        _write_cell(ws, row, 2, st['status_label'], s, align='center')
        _write_cell(ws, row, 3, st['type_label'], s, align='center')
        _write_cell(ws, row, 4, st['period'], s, align='center')
        _write_cell(ws, row, 5, st['orders_count'], s, align='center')
        _write_cell(ws, row, 6, _fmt_price(st['revenue_pln']) if st['revenue_pln'] else None,
                    s, align='center')
        _write_cell(ws, row, 7, st['sets_count'], s, align='center')
        total_orders += st['orders_count']
        total_revenue += st['revenue_pln']

    suma_row = 2 + len(pages)
    _write_cell(ws, suma_row, 1, 'SUMA', s, align='left', bold=True, fill=suma_fill)
    for col in (2, 3, 4):
        _write_cell(ws, suma_row, col, None, s, fill=suma_fill)
    _write_cell(ws, suma_row, 5, total_orders, s, align='center', bold=True, fill=suma_fill)
    _write_cell(ws, suma_row, 6, _fmt_price(total_revenue) if total_revenue else None,
                s, align='center', bold=True, fill=suma_fill)
    _write_cell(ws, suma_row, 7, None, s, fill=suma_fill)

    _set_col_widths(ws, {1: 32, 2: 18, 3: 12, 4: 22, 5: 16, 6: 16, 7: 14})
    ws.freeze_panes = 'A2'


def _build_bulk_offer_sheet(ws, page, s):
    """Zakładka jednej oferty: nagłówek statystyk + macierz ilości + macierz wartości."""
    ws.sheet_properties.tabColor = _PURPLE_LIGHT
    st = _offer_stats(page)

    _write_cell(ws, 1, 1, page.name, s, align='left', bold=True)
    _write_cell(ws, 2, 1, f"Status: {st['status_label']}", s, align='left')
    _write_cell(ws, 3, 1, f"Typ: {st['type_label']}", s, align='left')
    _write_cell(ws, 4, 1, f"Okres: {st['period']}", s, align='left')
    _write_cell(ws, 5, 1, f"Liczba zamówień: {st['orders_count']}", s, align='left')
    revenue_txt = _fmt_price(st['revenue_pln']) if st['revenue_pln'] else 0
    _write_cell(ws, 6, 1, f"Przychód (PLN): {revenue_txt}", s, align='left')

    title_row = 8
    _write_cell(ws, title_row, 1, 'ILOŚCI (sztuki)', s, align='left', bold=True)
    next_row, n1 = _write_quantities_matrix(ws, page, s, start_row=title_row + 1)

    title2_row = next_row + 1
    _write_cell(ws, title2_row, 1, 'WARTOŚCI (PLN)', s, align='left', bold=True)
    _, n2 = _write_values_matrix(ws, page, s, start_row=title2_row + 1)

    ws.column_dimensions['A'].width = 24
    for j in range(max(n1, n2)):
        ws.column_dimensions[get_column_letter(2 + j)].width = 18


def generate_offers_bulk_report(pages):
    """
    Generuje zbiorczy plik Excel dla wielu ofert.
    Arkusz 1: 'Podsumowanie' (zestawienie wszystkich ofert).
    Kolejne arkusze: jedna zakładka per oferta (statystyki + 2 macierze).

    Args:
        pages: lista obiektów OfferPage (w żądanej kolejności).
    Returns:
        BytesIO z plikiem .xlsx.
    """
    wb = Workbook()
    default_ws = wb.active  # domyślny 'Sheet' — usuniemy na końcu
    s = _styles()

    _build_bulk_overview_sheet(wb, pages, s)

    used_titles = {'podsumowanie'}
    for page in pages:
        title = _safe_sheet_title(page.name, used_titles)
        used_titles.add(title.lower())
        ws = wb.create_sheet(title=title)
        _build_bulk_offer_sheet(ws, page, s)

    wb.remove(default_ws)

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output
```

- [ ] **Step 2: Smoke test generatora na dwóch ofertach**

Run:
```bash
./venv/bin/python -c "
from app import create_app
from modules.offers.models import OfferPage
from utils.excel_export import generate_offers_bulk_report
app = create_app()
with app.app_context():
    pages = OfferPage.query.limit(3).all()
    print('Ofert:', len(pages))
    buf = generate_offers_bulk_report(pages)
    open('/tmp/bulk_report_smoke.xlsx','wb').write(buf.getvalue())
    print('OK zapisano /tmp/bulk_report_smoke.xlsx')
"
```
Expected: `OK zapisano ...` bez wyjątku.

- [ ] **Step 3: Sprawdź strukturę pliku**

Run:
```bash
./venv/bin/python -c "
import openpyxl
wb = openpyxl.load_workbook('/tmp/bulk_report_smoke.xlsx')
print('Arkusze:', wb.sheetnames)
ov = wb['Podsumowanie']
print('Nagłówek zbiorczy:', [ov.cell(1,c).value for c in range(1,8)])
"
```
Expected: pierwszy arkusz to `Podsumowanie`, potem zakładka per oferta; nagłówek = `['Oferta','Status','Typ','Okres','Liczba zamówień','Przychód (PLN)','Liczba setów']`.

- [ ] **Step 4: Commit**

```bash
git add utils/excel_export.py
git commit -m "feat(offers): generator generate_offers_bulk_report (arkusz zbiorczy + zakładki ofert)"
```

---

## Task 5: Route `POST /admin/offers/bulk/report`

**Files:**
- Modify: `modules/admin/offers.py` (dodaj route obok pozostałych akcji bulk, ~po linii 920; wzorzec odpowiedzi pliku jak `offers_export_excel:1845`)

- [ ] **Step 1: Dodaj route**

```python
@admin_bp.route('/offers/bulk/report', methods=['POST'])
@login_required
@admin_required
def offers_bulk_report():
    """Generuje zbiorczy raport Excel dla zaznaczonych ofert."""
    from utils.excel_export import generate_offers_bulk_report

    data = request.get_json(silent=True) or {}
    page_ids = data.get('page_ids') or []
    if not page_ids:
        return jsonify({'error': 'Nie wybrano żadnych stron.'}), 400

    pages = OfferPage.query.filter(OfferPage.id.in_(page_ids)).all()
    if not pages:
        return jsonify({'error': 'Nie znaleziono wybranych stron.'}), 404

    # zachowaj kolejność zaznaczenia z frontu
    order = {pid: i for i, pid in enumerate(page_ids)}
    pages.sort(key=lambda p: order.get(p.id, 0))

    try:
        excel_buffer = generate_offers_bulk_report(pages)
        filename = f'raport_zbiorczy_ofert_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
        return Response(
            excel_buffer.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Błąd generowania raportu: {str(e)}'}), 500
```

- [ ] **Step 2: Sprawdź importy w pliku**

Run: `grep -n "from flask import\|^from datetime\|import datetime" modules/admin/offers.py | head`
Expected: `request`, `jsonify`, `Response` są importowane z flask, oraz `datetime` jest dostępne (używane już w `offers_export_excel`). Jeśli czegoś brakuje — dodaj do istniejącego importu.

- [ ] **Step 3: Smoke test — aplikacja się uruchamia bez błędów importu**

Run: `./venv/bin/python -c "from app import create_app; create_app(); print('app OK')"`
Expected: `app OK` (brak SyntaxError/ImportError).

- [ ] **Step 4: Commit**

```bash
git add modules/admin/offers.py
git commit -m "feat(offers): route POST /offers/bulk/report (pobieranie zbiorczego Excela)"
```

---

## Task 6: Front — implementacja `case 'report'`

**Files:**
- Modify: `static/js/pages/admin/offer-list.js:667-669` (obecny placeholder)

- [ ] **Step 1: Zastąp placeholder realną logiką pobierania**

Zamień blok:

```javascript
                case 'report':
                    showToast('Raport zbiorowy — funkcja w przygotowaniu.', 'info');
                    break;
```

na:

```javascript
                case 'report':
                    bulkReport(ids, this);
                    break;
```

- [ ] **Step 2: Dodaj funkcję `bulkReport`**

Wstaw obok `bulkStatus`/`bulkDelete` (~po linii 741):

```javascript
    function bulkReport(ids, btn) {
        const textEl = btn.querySelector('.btn-bulk-text');
        const originalText = textEl ? textEl.textContent : null;
        btn.classList.add('is-disabled');
        if (textEl) textEl.textContent = 'Generuję...';

        fetch('/admin/offers/bulk/report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ page_ids: ids })
        })
        .then(async (response) => {
            const ct = response.headers.get('content-type') || '';
            if (response.ok && ct.includes('spreadsheetml')) {
                const blob = await response.blob();
                const disposition = response.headers.get('content-disposition') || '';
                const match = disposition.match(/filename="?([^"]+)"?/);
                const filename = match ? match[1] : 'raport_zbiorczy_ofert.xlsx';
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
                showToast('Raport zbiorowy pobrany.', 'success');
            } else {
                const result = await response.json().catch(() => ({}));
                showToast(result.error || 'Błąd generowania raportu.', 'error');
            }
        })
        .catch(err => {
            console.error('bulk report error:', err);
            showToast('Wystąpił błąd.', 'error');
        })
        .finally(() => {
            btn.classList.remove('is-disabled');
            if (textEl && originalText !== null) textEl.textContent = originalText;
        });
    }
```

- [ ] **Step 3: Commit**

```bash
git add static/js/pages/admin/offer-list.js
git commit -m "feat(offers): pobieranie zbiorczego raportu z paska akcji masowych"
```

---

## Task 7: Weryfikacja end-to-end w aplikacji

**Files:** brak zmian — weryfikacja ręczna.

- [ ] **Step 1: Uruchom aplikację lokalnie**

Run: `./venv/bin/python app.py` (lub wg `app.py` — sprawdź jak startuje serwer; port 5001). Upewnij się, że XAMPP/MariaDB działa.

- [ ] **Step 2: Przejdź na listę ofert i przetestuj**

W przeglądarce: http://localhost:5001 → panel admina → lista ofert (sales pages). Zaznacz 2-3 oferty (idealnie różne: jedna ze sprzedażą, jedna bez zamówień). Kliknij „Raport zbiorowy".

Oczekiwane:
- Przycisk pokazuje „Generuję..." i jest zablokowany na czas żądania.
- Pobiera się plik `raport_zbiorczy_ofert_YYYYMMDD_HHMM.xlsx`.
- Toast „Raport zbiorowy pobrany.".

- [ ] **Step 3: Otwórz pobrany plik i zweryfikuj zawartość**

Sprawdź w Excelu/LibreOffice:
- Arkusz 1 „Podsumowanie": wiersz na każdą zaznaczoną ofertę + wiersz SUMA.
- Po nim zakładka per oferta: nagłówek statystyk + macierz ILOŚCI + macierz WARTOŚCI (z kursem).
- Oferta bez zamówień: zakładka z nagłówkiem i nagłówkami macierzy, bez wierszy klientów (pusta).
- Oferty o tej samej/długiej nazwie: zakładki mają unikalne, przycięte nazwy.

- [ ] **Step 4: Test przypadku brzegowego — brak zaznaczenia**

Bez zaznaczonych ofert pasek bulk nie jest aktywny (jak inne akcje) — przycisk nie wywołuje żądania. Potwierdź brak błędów w konsoli.

- [ ] **Step 5: Finalny commit (jeśli zaszły poprawki podczas weryfikacji)**

```bash
git add -A
git commit -m "fix(offers): poprawki raportu zbiorowego po weryfikacji e2e"
```

Jeśli nie było poprawek — pomiń.

---

## Self-review (wykonane przez autora planu)

- **Pokrycie specu:** format xlsx (Task 4-6) ✓; arkusz zbiorczy pierwszy (Task 4 `_build_bulk_overview_sheet`) ✓; zakładka per oferta z nagłówkiem + obie macierze (Task 4 `_build_bulk_offer_sheet`) ✓; kolejność ilości→wartości ✓; eligibility dowolne / pusta zakładka (route nie blokuje statusów; pusty matrix → sam nagłówek) ✓; pobieranie fetch→blob→download (Task 6) ✓; liczba setów = sekcje typu set (Task 3 `_offer_stats`) ✓; reużycie `_preorder_collect_data` + refaktor rdzeni (Task 2) ✓; brak migracji/CSS/modala ✓.
- **Placeholdery:** brak — każdy krok z kodem ma pełny kod.
- **Spójność typów/nazw:** `_write_quantities_matrix`/`_write_values_matrix` zwracają `(next_row, n_sections)` i tak są używane w Task 2 i 4; `_offer_stats` zwraca `revenue_pln` jako float, formatowane `_fmt_price` przy zapisie w Task 4; `_safe_sheet_title(name, used_titles)` — sygnatura spójna Task 1↔4; route `/admin/offers/bulk/report` ↔ fetch URL w JS spójne.
- **Ryzyko:** import `create_app` w smoke testach — jeśli `app.py` używa innego wzorca, wykonawca dostosuje (zaznaczone w Task 2 Step 5). To jedyne miejsce wymagające adaptacji do realiów `app.py`.
