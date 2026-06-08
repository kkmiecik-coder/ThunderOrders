# Raport zbiorowy ofert (Excel) — projekt

**Data:** 2026-06-08
**Branch:** feature/offers-bulk-edit
**Status:** zatwierdzony do implementacji

## Cel

Akcja masowa „Raport zbiorowy" na liście ofert ma generować jeden plik Excel
podsumowujący wszystkie zaznaczone strony sprzedażowe. Potrzeba pochodzi od
użytkowniczki (Karolina): „zaznaczam 10 stron sprzedażowych, klikam wygeneruj
raport i dostaję ładną podsumkę wszystkich tych stron — każda strona jako osobna
zakładka; chodzi o macierze setów".

Przycisk `data-action="report"` już istnieje w pasku akcji masowych
(`templates/admin/offers/list.html`), a w `offer-list.js` jest dziś tylko
placeholder (toast „funkcja w przygotowaniu"). Tę funkcję trzeba zaimplementować.

## Decyzje (ustalone z użytkownikiem)

- **Format:** jeden plik `.xlsx`, pobierany.
- **Struktura:** arkusz zbiorczy „Podsumowanie" jako pierwsza zakładka, potem
  jedna zakładka per zaznaczona oferta.
- **Zakładka oferty:** nagłówek ze statystykami strony + **obie macierze**
  (ilości sztuk oraz wartości w zł), klient × sekcja/set.
- **Eligibility:** dowolne oferty niezależnie od statusu; oferta bez zamówień =
  pusta zakładka (sam nagłówek). Brak blokad all-or-nothing.
- **Pobieranie:** `fetch POST → blob → download`, spójnie z resztą akcji bulk.
- **„Liczba setów"** w arkuszu zbiorczym = liczba sekcji typu `set` na stronie.
- **Kolejność macierzy** w zakładce oferty: najpierw ilości, potem wartości.

## Architektura / przepływ

```
[Lista ofert] zaznacz N ofert → klik "Raport zbiorowy"
   → JS: fetch POST /admin/offers/bulk/report  { page_ids: [...] }  (+CSRF)
   → przycisk pokazuje spinner "Generuję..."
[Backend] route w modules/admin/offers.py
   → generate_offers_bulk_report(pages)  (utils/excel_export.py)
   → zwraca .xlsx (Response, attachment)  LUB  JSON {error} przy błędzie
[JS] ok → blob → wymuszony download;  błąd → toast
```

Brak zmian w bazie danych — żadnej migracji. Generowanie synchroniczne, jak
istniejące eksporty pojedynczej oferty.

## Backend — generator

Nowa funkcja `generate_offers_bulk_report(pages)` w `utils/excel_export.py`.
Reużywa istniejący `_preorder_collect_data(page)` (to samo źródło danych co
raporty pojedyncze → spójne liczby).

### Arkusz 1 — „Podsumowanie" (zbiorczy)

Tabela, jeden wiersz na ofertę:

| Oferta | Status | Typ | Okres | Liczba zamówień | Przychód (PLN) | Liczba setów |

- Wiersz `SUMA` na dole: suma liczby zamówień i przychodu.
- „Liczba setów" = liczba sekcji typu `set` na stronie.
- „Okres" — format jak `_format_period(starts_at, ends_at)`.
- „Liczba zamówień" — zamówienia oferty bez statusu `anulowane` (zgodnie z logiką
  `_preorder_collect_data`).
- „Przychód (PLN)" — suma wartości pozycji (jak liczone w macierzy wartości:
  `sale_price * quantity`, bez bonusów).

### Arkusze 2..N+1 — jeden per oferta

Zawartość pionowo w jednym arkuszu:

1. Nagłówek: nazwa oferty, status, typ, okres, liczba zamówień, przychód.
2. Pusty wiersz.
3. **Macierz ILOŚCI** (klient × sekcja, sztuki + sumy) — logika obecnego
   `_build_preorder_quantities_sheet`.
4. Pusty wiersz.
5. **Macierz WARTOŚCI** (klient × sekcja, zł + sumy + kurs KRW/PLN) — logika
   obecnego `_build_preorder_summary_sheet`.

Oferta bez zamówień → nagłówek + nagłówki kolumn macierzy bez wierszy klientów.

### Refaktor reużycia

Obecne `_build_preorder_summary_sheet(wb, page, s)` i
`_build_preorder_quantities_sheet(wb, page, s)` tworzą arkusz o stałej nazwie
(`Podsumowanie` / `Ilości`) ze stałym indeksem i piszą od wiersza 1. Aby użyć tej
samej logiki w zbiorczym raporcie (gdzie obie macierze są w jednym arkuszu, jedna
pod drugą), wydzielić rdzeń piszący macierz do podanego arkusza od podanego
wiersza startowego i zwracający numer kolejnego wolnego wiersza:

- `_write_quantities_matrix(ws, page, s, start_row) -> next_row`
- `_write_values_matrix(ws, page, s, start_row) -> next_row`

Istniejące funkcje pojedynczych raportów wywołają ten rdzeń (tworzą arkusz +
`start_row=1`), bez zmiany ich obecnego zachowania ani wyglądu raportów
pojedynczych.

### Nazwy arkuszy

Excel limituje nazwę arkusza do 31 znaków i wymaga unikalności. Nazwę oferty
przyciąć do limitu i zdeduplikować sufiksem: `Nazwa`, `Nazwa (2)`, `Nazwa (3)`.
Helper `_safe_sheet_title(name, used_titles)`.

## Backend — route

`POST /admin/offers/bulk/report` w `modules/admin/offers.py`, dekoratory
`@login_required` + `@admin_required` (jak pozostałe akcje bulk).

- Czyta `page_ids` z JSON; brak/pusta lista → `jsonify({'error': ...}), 400`.
- Pobiera `OfferPage` po id (zachowaj kolejność jak zaznaczone lub po id).
- Woła `generate_offers_bulk_report(pages)`, zwraca `.xlsx` jako `attachment`
  (wzorzec jak `offers_export_excel`).
- Nazwa pliku: `raport_zbiorczy_ofert_YYYYMMDD_HHMM.xlsx`.
- Wyjątek → `traceback.print_exc()` + `jsonify({'error': ...}), 500`.

## Front — `static/js/pages/admin/offer-list.js`

Zamienić `case 'report'` (obecny placeholder toast) na realną logikę:

- Pobierz `ids = getSelectedIds()`; pusty → nic (jak inne akcje).
- Zablokuj przycisk + spinner/etykieta „Generuję...".
- `fetch POST /admin/offers/bulk/report` z `{ page_ids: ids }` + `X-CSRFToken`.
- Jeśli odpowiedź OK i `content-type` to xlsx → `response.blob()` → wymuszony
  download przez tymczasowy `<a download>` + `URL.createObjectURL`.
- Jeśli odpowiedź to JSON (błąd) → `showToast(result.error, 'error')`.
- `finally` → przywróć przycisk do stanu pierwotnego.

## YAGNI — czego nie robimy

- Brak async/kolejki — generowanie synchroniczne.
- Brak migracji bazy — zero zmian w modelach.
- Brak nowego CSS / modala — przycisk i pasek bulk już istnieją.
- Brak blokad eligibility — dowolne oferty dozwolone.

## Pliki do zmiany

- `utils/excel_export.py` — nowy `generate_offers_bulk_report` + refaktor
  rdzeni macierzy + `_safe_sheet_title`.
- `modules/admin/offers.py` — nowy route `POST /offers/bulk/report`.
- `static/js/pages/admin/offer-list.js` — implementacja `case 'report'`.
