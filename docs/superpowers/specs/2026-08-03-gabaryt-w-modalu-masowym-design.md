# Ustalanie gabarytu w modalu masowym „Koszty i gabaryt"

**Data:** 2026-08-03
**ClickUp:** [869eczm7p](https://app.clickup.com/t/869eczm7p) (blokuje [869e674py](https://app.clickup.com/t/869e674py) — eksport InPost)
**Moduł:** WMS dashboard → zakładka „Zlecenia wysyłki"

## Problem

Gabaryt paczki (`ShippingRequest.parcel_size`: mini/A/B/C) da się dziś ustawić wyłącznie pojedynczo —
w modalu edycji zlecenia albo przy pakowaniu w WMS. Przy wycenie kilkunastu zleceń naraz w modalu
„Dodaj koszty" gabarytu nie ma w ogóle, więc admin musi wracać do każdego zlecenia osobno.

Gabarytu nie da się wyliczyć automatycznie: klient wybiera tylko preferencję opakowania
(`client_package_preference`: karton/koperta), a wymiary produktów nie są uzupełniane w kartotece.
Gabaryt ustala admin ręcznie.

Bez kompletu gabarytów nie da się wygenerować pliku do masowego tworzenia listów przewozowych InPost
(kolumna `rozmiar`) — stąd zależność między taskami.

## Zakres

Rozszerzenie istniejącego modala akcji masowej na WMS dashboard. **Backend bez zmian:**

- `PUT /admin/orders/shipping-requests/<id>` przyjmuje już `parcel_size` i `packaging_material_id`
  ([modules/orders/routes.py:3812](../../../modules/orders/routes.py))
- `GET /admin/orders/shipping-requests/<id>` zwraca `packaging_material` (z `size_category`,
  `sale_price`, `size_display`), `client_package_preference`, `client_notes`, `address_type`,
  `pickup_point_id`, `shipping_city` oraz listę zamówień z wartościami
  ([modules/orders/routes.py:3704](../../../modules/orders/routes.py))
- `GET /api/orders/packaging-materials` zwraca aktywne materiały z ceną, gabarytem i wymiarami
  ([modules/orders/wms.py:1500](../../../modules/orders/wms.py))

Poza zakresem: automatyczne wyliczanie gabarytu z wymiarów, zmiany w module materiałów
opakowaniowych, eksport InPost (osobny task).

## Rozwiązanie

### 1. Nazewnictwo

| Element | Było | Będzie |
|---|---|---|
| Przycisk w pasku masowym | „Dodaj koszty" | „Koszty i gabaryt" |
| Tytuł modala | „Dodaj koszty wysyłki" | „Koszty i gabaryt wysyłki" |

`data-action="bulk-cost"` zostaje bez zmian — nazwa akcji jest wewnętrzna.

### 2. Karta zlecenia w modalu

Obecna karta (`.bulk-cost-entry`) to nagłówek z numerem zlecenia, statusem, kwotą łączną i przyciskiem
„Rozłóż równo" plus tabela zamówień. Dochodzą dwa pasy:

```
┌ WYS/000123  [oplacone]  Paczkomat KRA128  Koperta ───────────────┐
│ 3 zamówienia · 847,00 PLN                  [ 24,90 PLN ] [⤢]     │
├──────────────────────────────────────────────────────────────────┤
│ Materiał / cennik  [Koperta A5 (A) — 12,90 zł    ▾]              │
│ Gabaryt *          [A - Mały                     ▾]              │
│ Uwagi klienta: „Proszę ostrożnie, szkło"                          │
├──────────────────────────────────────────────────────────────────┤
│ Zamówienie   Wartość        Koszt wysyłki                        │
│ ZAM/00045    299,00 PLN     [  8,30 ]                            │
└──────────────────────────────────────────────────────────────────┘
```

**Nagłówek — badge'e informacyjne:**

- **Typ dostawy:** przy `address_type === 'pickup_point'` → `{pickup_courier}: {pickup_point_id}`
  (np. „InPost: KRA128"); w przeciwnym razie „Kurier · {shipping_city}". Gdy brak danych — „Kurier".
- **Preferencja klienta:** „Karton" / „Koperta" z `client_package_preference`; badge pominięty gdy pusty.
- **Podtytuł:** „{n} zamówień · {suma wartości} PLN" — liczba i łączna wartość zamówień w zleceniu.

**Pola edycyjne:**

- **Materiał / cennik** — select zasilany z `/api/orders/packaging-materials`, opcje w formacie
  `{type_display} {name} ({size_display}) — {sale_price} zł`, z `data-sale-price` i `data-size-category`.
  Wybór materiału: podstawia cenę sprzedaży do kwoty łącznej zlecenia, rozkłada ją na zamówienia
  (istniejąca `distributeBulkCost`) i ustawia gabaryt z `size_category`. Materiał już przypisany do
  zlecenia jest preselektowany; jeśli został zdezaktywowany — dokładany ręcznie jako opcja, żeby nie
  zgubić przypisania (ten sam mechanizm co w modalu pojedynczego zlecenia).
- **Gabaryt** — select: `-- Wybierz --`, Mini, A - Mały, B - Średni, C - Duży. Widoczny dla każdego
  zlecenia, także kurierskiego. Wartość początkowa z `parcel_size`.
- **Uwagi klienta** — `client_notes`, read-only; wiersz ukryty gdy brak.

Lista materiałów pobierana **raz** przy otwarciu modala i reużywana dla wszystkich kart.

### 3. Walidacja

Gabaryt jest wymagany dla każdego zaznaczonego zlecenia. „Zapisz wszystkie" przy pustym gabarycie:

1. przerywa zapis (żaden `PUT` nie leci),
2. oznacza karty bez gabarytu klasą błędu i podświetla select,
3. przewija do pierwszej takiej karty,
4. pokazuje `window.showToast('Uzupełnij gabaryt: WYS/000123, WYS/000124', 'error')`.

Ten sam rygor obowiązuje w modalu pojedynczego zlecenia (sekcja 4).

### 4. Parytet w modalu pojedynczego zlecenia

Dziś pole gabarytu pokazuje się wyłącznie przy `address_type === 'pickup_point'`
([static/js/pages/admin/shipping-requests.js:620](../../../static/js/pages/admin/shipping-requests.js)),
a przy adresie domowym jest ukrywane i czyszczone. Skoro gabaryt ma być wymagany zawsze:

- pole widoczne niezależnie od typu adresu,
- zapis formularza blokowany, gdy gabaryt pusty — komunikat przez `window.showToast`.

Bez tego ten sam gabaryt byłby wymuszany w jednym modalu i niedostępny w drugim.

### 5. Zapis

Bez zmian w schemacie: `N × PUT /admin/orders/shipping-requests/<id>`, sekwencyjnie, po jednym na
zlecenie. Payload rozszerzony o dwa pola:

```json
{
  "order_costs": [{"order_id": 45, "shipping_cost": 8.30}],
  "parcel_size": "A",
  "packaging_material_id": 7
}
```

Kolejność w backendzie jest bezpieczna: gdy `parcel_size` jest podany jawnie, nie zostaje nadpisany
gabarytem z materiału ([modules/orders/routes.py:3819](../../../modules/orders/routes.py)).

Obsługa wyniku: karty zapisane dostają stan „zapisane", błędne — stan błędu. Zamiast `alert()`
używamy `window.showToast` (`window.Toast` nie istnieje w tym projekcie). Przy komplecie sukcesów
modal zamyka się i strona się przeładowuje — jak dotąd.

**Status zleceń:** bez nowej logiki. Przejście `czeka_na_wycene` → `czeka_na_oplacenie` po wycenie
działa już w tym samym `PUT` ([modules/orders/routes.py:3848](../../../modules/orders/routes.py)),
razem z mailem i pushem do klienta o nowym koszcie wysyłki krajowej.

## Pliki

| Plik | Zmiana |
|---|---|
| [static/js/pages/admin/shipping-requests.js](../../../static/js/pages/admin/shipping-requests.js) | render kart z materiałem/gabarytem/badge'ami, pobranie listy materiałów, auto-podstawianie ceny i gabarytu, walidacja, payload; odsłonięcie i walidacja gabarytu w modalu pojedynczego zlecenia |
| [templates/admin/orders/wms_dashboard.html](../../../templates/admin/orders/wms_dashboard.html) | etykieta przycisku, tytuł modala |
| [static/css/components/modals.css](../../../static/css/components/modals.css) | przeniesione style `.bulk-cost-*` + nowe klasy (badge'e, siatka pól, stan błędu) — light + dark mode |
| [static/css/pages/admin/shipping-requests-list.css](../../../static/css/pages/admin/shipping-requests-list.css) | usunięcie przeniesionych reguł `.bulk-cost-*` (linie ~965–1048 oraz ~1365–1400) |

### CSS — jedno źródło prawdy

Style tego modala są dziś rozproszone: reguły `.bulk-cost-*` siedzą w
`shipping-requests-list.css`, mimo że zasada projektu mówi „style modali w `modals.css`".
Konwencja w `modals.css` dopuszcza klasy specyficzne dla konkretnego modala (`.settings-*`,
`.filters-modal-*`, `.wizard-*`, `.ca-dist-*`), więc:

1. reguły `.bulk-cost-*` przenoszę z `shipping-requests-list.css` do `modals.css` bez zmian wizualnych,
2. markup kart opieram na klasach, które `modals.css` już definiuje — `.form-group`, `.form-label`,
   `.form-control`, `.input-hint` — zamiast dublować własne odpowiedniki,
3. nowe elementy (badge'e typu dostawy i preferencji, siatka pól materiał/gabaryt, stan błędu
   walidacji) dopisuję wyłącznie w `modals.css`.

Wszystko z wariantami `[data-theme="dark"]` w palecie glassmorphism. Na mobile pola materiału
i gabarytu układają się w kolumnę, kontrolki zachowują minimum 44 px wysokości dotykowej.

## Ryzyka

- **Wiele zaznaczonych zleceń = wiele żądań `GET`** przy otwarciu modala (stan obecny, bez zmian).
  Lista materiałów dochodzi jako pojedyncze dodatkowe żądanie.
- **Wymagany gabaryt blokuje szybkie edycje** w modalu pojedynczego zlecenia (np. wklejenie samego
  numeru trackingu wymaga wcześniejszego ustawienia gabarytu) — świadoma decyzja na rzecz kompletu
  danych do eksportu InPost.
- **Zlecenia kurierskie** dostają gabaryt A/B/C, który u części przewoźników nie ma odpowiednika —
  wartość jest wtedy tylko informacyjna.

## Testy

Ręczne, na lokalnym `http://localhost:5001`, zakładka „Zlecenia wysyłki":

1. Zaznaczenie 2+ zleceń → „Koszty i gabaryt" → karty pokazują materiał, gabaryt, badge'e i uwagi klienta.
2. Wybór materiału → cena podstawia się i rozkłada na zamówienia, gabaryt ustawia się z `size_category`.
3. Ręczna zmiana gabarytu po wyborze materiału → zapisuje się wartość ręczna.
4. Zapis z pustym gabarytem w jednym zleceniu → brak zapisu, podświetlenie, toast z numerami.
5. Poprawny zapis → wartości widoczne po przeładowaniu; zlecenie w `czeka_na_wycene` przechodzi do
   `czeka_na_oplacenie`.
6. Zlecenie kurierskie (adres domowy) → gabaryt dostępny i wymagany w obu modalach.
7. Light i dark mode, widok mobilny.
8. Regresja wizualna po przeniesieniu CSS: modal wygląda tak samo jak przed zmianą (nagłówek karty,
   tabela zamówień, stany „zapisane"/„błąd"), a `.bulk-cost-*` nie występuje już w
   `shipping-requests-list.css`.
