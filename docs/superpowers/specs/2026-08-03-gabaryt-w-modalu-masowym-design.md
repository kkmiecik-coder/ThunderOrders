# Scalony modal zlecenia wysyłki (wycena, opakowanie, gabaryt)

**Data:** 2026-08-03
**ClickUp:** [869eczm7p](https://app.clickup.com/t/869eczm7p) (blokuje [869e674py](https://app.clickup.com/t/869e674py) — eksport InPost)
**Moduł:** WMS dashboard → „Zlecenia wysyłki" oraz szczegóły zamówienia

## Problem

**1. Gabarytu nie da się ustawić masowo.** `ShippingRequest.parcel_size` (mini/A/B/C) ustawia się dziś
pojedynczo — w modalu edycji zlecenia albo przy pakowaniu w WMS. Przy wycenie kilkunastu zleceń
naraz trzeba wracać do każdego osobno. Gabarytu nie da się wyliczyć automatycznie: klient wybiera
tylko preferencję opakowania (`client_package_preference`: karton/koperta), a wymiary produktów nie są
uzupełniane w kartotece. Ustala go admin ręcznie. Bez kompletu gabarytów nie powstanie plik do
masowego tworzenia listów przewozowych InPost (kolumna `rozmiar`).

**2. Ten sam modal istnieje w trzech rozjeżdżających się wariantach:**

| Wariant | Gdzie | Czego brakuje |
|---|---|---|
| Partial WMS | [templates/admin/orders/_shipping_request_modal.html](../../../templates/admin/orders/_shipping_request_modal.html) | — (najbogatszy) |
| Kopia inline | [templates/admin/orders/detail.html:3071](../../../templates/admin/orders/detail.html) | materiał, gabaryt, panel „Od klienta", sekcja danych wysyłki |
| Modal masowy | `#bulkCostModal` w [wms_dashboard.html:752](../../../templates/admin/orders/wms_dashboard.html) | wszystko poza kosztami: termin płatności, materiał, gabaryt, adres, dane wysyłki, uwagi klienta |

Wszystkie trzy obsługuje jeden plik JS ([shipping-requests.js](../../../static/js/pages/admin/shipping-requests.js)),
więc kopia w `detail.html` po cichu gubi funkcje, których nie ma w markupie.

**3. Masowa wycena nie ustawia terminu płatności.** Termin (`payment_deadline`) jest wymagany tylko
przez front modala pojedynczego — backend go nie waliduje. Zlecenia wycenione masowo zostają bez
terminu.

## Rozwiązanie

Jeden modal dla wszystkich wejść, obsługujący od 1 do N zleceń, w układzie **lista + szczegóły obok**.

**Backend bez zmian.** `PUT /admin/orders/shipping-requests/<id>` przyjmuje już `order_costs`,
`parcel_size`, `packaging_material_id`, `payment_deadline`, `courier`, `tracking_number`
([routes.py:3780](../../../modules/orders/routes.py)); `GET` zwraca komplet danych łącznie z
materiałem, preferencją i uwagami klienta ([routes.py:3704](../../../modules/orders/routes.py));
`GET /api/orders/packaging-materials` daje listę materiałów z ceną i gabarytem
([wms.py:1500](../../../modules/orders/wms.py)).

Poza zakresem: automatyczne wyliczanie gabarytu z wymiarów, zmiany w module materiałów, eksport InPost.

### Wejścia do modala

| Skąd | Wywołanie | Zawartość |
|---|---|---|
| Karta zlecenia w WMS ([wms_dashboard.html:269](../../../templates/admin/orders/wms_dashboard.html)) | `openShippingRequestsModal([id])` | jedno zlecenie |
| Szczegóły zamówienia ([detail.html:1301](../../../templates/admin/orders/detail.html)) | `openShippingRequestsModal([id])` | jedno zlecenie |
| Akcja masowa „Koszty i gabaryt" | `openShippingRequestsModal(getSelectedRequestIds())` | N zleceń |

`openShippingRequestModal(id)` zostaje jako cienki alias (`openShippingRequestsModal([id])`), żeby nie
przepisywać atrybutów `onclick` w szablonach.

### Układ — desktop

Przy jednym zleceniu lewa lista się nie pojawia: panel szczegółów zajmuje całą szerokość, czyli
zachowuje się jak dzisiejszy modal pojedynczy.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Zlecenia wysyłki · 5                                                   [×] │
├────────────────────────────────────────────────────────────────────────────┤
│ Ustaw we wszystkich:  Termin [2026-08-10] [23:59]   Materiał [—      ▾]    │
│                       Gabaryt [—    ▾]                        [Zastosuj]   │
├──────────────────────┬─────────────────────────────────────────────────────┤
│ ✓ WYS/000123         │  WYS/000123        [czeka na opłacenie]             │
│   Kowalski · KRA128  │                                                     │
│   24,90 PLN · A      │  Wycena                                             │
│ ─────────────────────│  Koszt całkowity [ 24,90 ] PLN        [Rozłóż]      │
│ ! WYS/000124         │  Termin płatności [2026-08-10] [23:59]              │
│   Nowak · Kurier     │                                                     │
│   brak gabarytu      │  Zamówienia (3)                                     │
│ ─────────────────────│  ZAM/00045      299,00 PLN     [  8,30 ]            │
│ ✓ WYS/000125         │  ZAM/00046      548,00 PLN     [ 16,60 ]            │
│   Wiśniewska · WAW350│                                                     │
│   31,00 PLN · B      │  Opakowanie                                         │
│                      │  Materiał [Koperta A5 (A) — 12,90 zł    ▾]          │
│                      │  Gabaryt  [A - Mały                     ▾]          │
│                      │  Od klienta: Koperta · „Ostrożnie, szkło"           │
│                      │                                                     │
│                      │  Adres dostawy                                      │
│                      │  Paczkomat KRA128 · ul. Klonowa 5, 43-300 Kraków    │
│                      │                                                     │
│                      │  Dane wysyłki                                       │
│                      │  Kurier [InPost ▾]   Tracking [________________]    │
├──────────────────────┴─────────────────────────────────────────────────────┤
│ Gotowe 3 z 5                                    [Zamknij] [Zapisz wszystkie]│
└────────────────────────────────────────────────────────────────────────────┘
```

### Układ — mobile (≤ 768 px)

Lista zamienia się w poziomy, przewijalny pasek żetonów nad szczegółami; wybrany żeton jest
podświetlony. Pola układają się w jedną kolumnę, kontrolki mają min. 44 px wysokości.

```
┌──────────────────────────────┐
│ Zlecenia wysyłki · 5     [×] │
├──────────────────────────────┤
│ Ustaw we wszystkich       ▾  │   ← zwinięte, rozwijane tapnięciem
├──────────────────────────────┤
│ [✓ 123] [! 124] [✓ 125] →    │
├──────────────────────────────┤
│ WYS/000124  [czeka na wycenę]│
│ … sekcje jedna pod drugą …   │
├──────────────────────────────┤
│ Gotowe 3 z 5                 │
│ [Zapisz wszystkie]  [Zamknij]│
└──────────────────────────────┘
```

### Lista zleceń — wskaźnik kompletności

To jedyny wyróżniający się element interfejsu; reszta zostaje przy istniejącym języku wizualnym panelu.
Każda pozycja pokazuje: znacznik kompletności, numer zlecenia, nazwisko klienta, skrót adresu
(`InPost: KRA128` albo `Kurier · Warszawa`), kwotę i gabaryt.

Zlecenie jest **gotowe** (`✓`), gdy ma: gabaryt, koszt całkowity > 0 oraz termin płatności — z tym, że
termin nie jest wymagany dla zleceń już opłaconych (status `oplacone`), gdzie stracił sens. Brak
któregokolwiek → `!` i pozycja w kolorze ostrzeżenia. Stopka pokazuje „Gotowe N z M", więc widać
postęp bez wchodzenia w każde zlecenie.

Znacznik przelicza się na bieżąco przy każdej zmianie pola — także po użyciu paska zbiorczego.

### Pasek „Ustaw we wszystkich"

Widoczny tylko przy dwóch lub więcej zleceniach. Trzy pola: termin płatności (data + godzina),
materiał opakowaniowy, gabaryt. Przycisk „Zastosuj" kopiuje **wypełnione** pola do wszystkich zleceń
w modalu; puste pola nie ruszają niczego. Materiał podstawia też cenę sprzedaży (z rozłożeniem na
zamówienia) i gabaryt z `size_category` — tak jak wybór materiału w pojedynczym zleceniu. Po
zastosowaniu: toast „Ustawiono w 5 zleceniach" i przeliczenie znaczników.

Wartości ustawione zbiorczo można nadpisać w każdym zleceniu osobno — pasek to skrót, nie blokada.

### Panel szczegółów

Sekcje w kolejności odpowiadającej pracy admina: najpierw wycena, potem to, co ją uzasadnia.

1. **Wycena** — koszt całkowity + „Rozłóż" (istniejąca logika), termin płatności (data + godzina)
2. **Zamówienia (n)** — tabela: numer, wartość, koszt wysyłki per zamówienie
3. **Opakowanie** — materiał, gabaryt, panel „Od klienta" (preferencja + uwagi, read-only)
4. **Adres dostawy** — podgląd (paczkomat albo adres domowy), bez edycji
5. **Dane wysyłki** — kurier i tracking, **zawsze widoczne**, bez trybu „czytaj/edytuj"

Sekcja „Dane wysyłki" pokazywała się dotąd wyłącznie, gdy zlecenie miało już kuriera albo tracking, i
wymagała kliknięcia ikony ołówka ([shipping-requests.js:589](../../../static/js/pages/admin/shipping-requests.js)).
Znika ten warunek i tryb read/edit — pola są dostępne od razu.

**Anulowanie zlecenia** pozostaje wyłącznie w trybie jednego zlecenia (przycisk w stopce, jak dziś).
Przy wielu zaznaczonych przycisk się nie pojawia — anulowanie masowe ma osobną akcję w pasku.

### Walidacja

Blokują zapis:

- brak gabarytu w którymkolwiek zleceniu,
- brak terminu płatności w zleceniu nieopłaconym,
- termin płatności w przeszłości.

Zachowanie: zapis nie startuje (żaden `PUT` nie leci), pozycje z brakami dostają znacznik `!`,
pierwsza z nich zostaje wybrana w panelu szczegółów, wadliwe pole podświetlone klasą `input-error`,
toast: `Uzupełnij gabaryt i termin płatności: WYS/000123, WYS/000124`.

Wszystkie komunikaty przez `window.showToast` — `alert()` znika z dotykanych ścieżek
(`window.Toast` w tym projekcie nie istnieje).

### Zapis

Stan edycji trzymany w pamięci JS (mapa `id → zmiany`), zapis dopiero po „Zapisz wszystkie":
`N × PUT /admin/orders/shipping-requests/<id>`, sekwencyjnie.

```json
{
  "order_costs": [{"order_id": 45, "shipping_cost": 8.30}],
  "payment_deadline": "2026-08-10T23:59",
  "parcel_size": "A",
  "packaging_material_id": 7,
  "courier": "inpost",
  "tracking_number": "6280123456789012345678"
}
```

`packaging_material_id` trafia do payloadu tylko przy wybranej wartości — backend traktuje obecność
klucza jako „ustaw albo wyczyść", więc pusty select nie może wyzerować istniejącego przypisania
(zachowanie z obecnego kodu). Jawny `parcel_size` ma pierwszeństwo przed gabarytem z materiału
([routes.py:3819](../../../modules/orders/routes.py)) — potwierdzone testem
`test_put_explicit_parcel_size_wins`.

Po zapisie: pozycje udane oznaczone na zielono, nieudane na czerwono. Komplet sukcesów → modal
zamyka się i strona przeładowuje (jak dziś). Częściowy błąd → modal zostaje, toast z liczbą
niezapisanych.

**Status zleceń** bez nowej logiki: przejście `czeka_na_wycene` → `czeka_na_oplacenie` po wycenie
dzieje się w tym samym `PUT` ([routes.py:3848](../../../modules/orders/routes.py)), razem z mailem
i pushem do klienta o koszcie wysyłki krajowej.

## Pliki

| Plik | Zmiana |
|---|---|
| [templates/admin/orders/_shipping_request_modal.html](../../../templates/admin/orders/_shipping_request_modal.html) | przepisany na układ lista + szczegóły; jedyne źródło markupu modala |
| [templates/admin/orders/wms_dashboard.html](../../../templates/admin/orders/wms_dashboard.html) | usunięcie `#bulkCostModal`; etykieta przycisku „Dodaj koszty" → „Koszty i gabaryt" |
| [templates/admin/orders/detail.html](../../../templates/admin/orders/detail.html) | usunięcie kopii modala (linie ~3071–3180), w jej miejsce `{% include %}` partiala |
| `static/js/pages/admin/shipping-request-modal.js` | **nowy plik** — całość modala: `openShippingRequestsModal(ids)`, render listy i szczegółów, stan edycji, pasek zbiorczy, walidacja, zapis, anulowanie |
| [static/js/pages/admin/shipping-requests.js](../../../static/js/pages/admin/shipping-requests.js) | zostaje przy zaznaczaniu kart i akcjach masowych (scal, WMS, usuń); usunięcie kodu modala: `openShippingRequestModal`, `openBulkCostModal`, `submitBulkCosts`, `distributeBulkCost`, `toggleShippingEdit`, `renderOrdersTable`, `renderAddressPreview`, `cancelShippingRequest` |
| [static/css/components/modals.css](../../../static/css/components/modals.css) | style scalonego modala (siatka lista/szczegóły, znaczniki kompletności, pasek zbiorczy, żetony mobilne, stany zapisu) — light + dark |
| [static/css/pages/admin/shipping-requests-list.css](../../../static/css/pages/admin/shipping-requests-list.css) | usunięcie reguł `.bulk-cost-*` (~965–1050, ~1365–1400) oraz reguł wnętrza modala (`.sr-section`, `.sr-box`, `.sr-boxes-row`, `.sr-client-panel`, `.sr-shipping-*`, `.sr-address-preview`, `.sr-orders-table`, `.sr-modal-footer`); klasy kart listy (`.sr-card`, `.sr-checkbox`, `.sr-notes-*`) zostają na miejscu |
| `tests/test_shipping_request_modal_merge.py` | nowe testy renderowania (jeden modal na obu stronach, brak `#bulkCostModal`) |

### CSS — jedno źródło prawdy

Style modala są dziś rozproszone (`.bulk-cost-*` i `.sr-*` w `shipping-requests-list.css`), mimo zasady
projektu „style modali w `modals.css`". Konwencja w `modals.css` dopuszcza klasy specyficzne dla
konkretnego modala (`.settings-*`, `.filters-modal-*`, `.wizard-*`, `.ca-dist-*`), więc:

1. reguły modala przenoszę do `modals.css`,
2. markup opieram na klasach, które `modals.css` już definiuje (`.form-group`, `.form-label`,
   `.form-control`, `.input-hint`), zamiast dublować własne odpowiedniki,
3. nowe elementy (siatka lista/szczegóły, znaczniki kompletności, pasek zbiorczy, żetony mobilne)
   dopisuję wyłącznie w `modals.css`.

Warianty `[data-theme="dark"]` w palecie glassmorphism: tła `rgba(255,255,255,0.05)`, obramowania
`rgba(240,147,251,0.15)`, akcent `#f093fb`. Znacznik gotowości: zielony `#22c55e`, znacznik braku:
bursztynowy `#f59e0b` (odróżnialny od czerwieni błędu zapisu, `#ef4444`).

## Ryzyka

- **Największa zmiana to przepisanie markupu**, z którego korzystają dwie strony. Kopia w `detail.html`
  jest uboższa, więc po scaleniu edycja zlecenia ze szczegółów zamówienia zyskuje pola, których tam
  nie było — to poprawa, ale zmienia wygląd tej strony.
- **Wiele zaznaczonych zleceń = wiele żądań `GET`** przy otwarciu (stan obecny). Lista materiałów
  pobierana raz i reużywana dla wszystkich zleceń.
- **Wymagany termin płatności w trybie masowym** to nowy warunek — zlecenia wyceniane hurtowo nie
  zapiszą się bez niego. Pasek „Ustaw we wszystkich" jest odpowiedzią na ten koszt.
- **Zlecenia kurierskie** dostają gabaryt A/B/C, który u części przewoźników nie ma odpowiednika —
  wartość jest wtedy informacyjna.

## Testy

**Automatyczne** (`python -m pytest`, uruchamiane przez `python -m` — gołe `pytest` pada na `No module named 'app'`):

- `/admin/orders/wms?tab=shipping` renderuje `id="editShippingRequestModal"` i **nie** zawiera
  `id="bulkCostModal"`,
- strona szczegółów zamówienia ze zleceniem renderuje ten sam modal i zawiera `srPackagingMaterial`
  oraz `srParcelSize` (dziś ich tam nie ma),
- przycisk masowy w WMS ma etykietę „Koszty i gabaryt",
- kontrakt `PUT` pozostaje spełniony — istniejące testy w `tests/test_admin_shipping_request_material.py`
  przechodzą bez zmian.

**Ręczne**, na `http://localhost:5001`:

1. Klik w zlecenie w WMS → modal z jedną pozycją, bez lewej listy, komplet sekcji.
2. Klik „Edytuj zlecenie" na szczegółach zamówienia → ten sam modal, z materiałem i gabarytem.
3. Zaznaczenie 3 zleceń → „Koszty i gabaryt" → lista po lewej, szczegóły po prawej, przełączanie.
4. Pasek „Ustaw we wszystkich": termin + materiał + gabaryt → „Zastosuj" → wartości w każdym zleceniu,
   ceny rozłożone na zamówienia, znaczniki przeliczone.
5. Zapis z brakującym gabarytem → brak zapisu, wybór wadliwego zlecenia, toast z numerami.
6. Termin w przeszłości → brak zapisu, komunikat.
7. Poprawny zapis → wartości widoczne po przeładowaniu; zlecenie w `czeka_na_wycene` przechodzi do
   `czeka_na_oplacenie`.
8. Zlecenie kurierskie (adres domowy) → gabaryt i dane wysyłki dostępne.
9. Anulowanie zlecenia dostępne przy jednym zleceniu, nieobecne przy wielu.
10. Light i dark mode, widok mobilny (żetony, jedna kolumna, 44 px).
