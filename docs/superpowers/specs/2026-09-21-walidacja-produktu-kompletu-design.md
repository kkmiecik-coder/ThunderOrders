# Walidacja produktu-kompletu w sekcjach setu

**Data:** 2026-09-21
**Status:** zaakceptowana przez Karolinę
**Zadanie ClickUp:** [869f50td6](https://app.clickup.com/t/869f50td6)

## Problem

Strona ofertowa 96 („Ateez GH5 - Whos fans 1.0 (album) cheek heart ver") miała w sekcji setu 742
ustawiony `set_product_id = 576`, czyli OT8 **z innego albumu** („Jump up 1.0 photobook ver").
Produkty składowe pochodziły z poprawnej grupy wariantowej 65, błędny był wyłącznie
produkt-komplet.

Skutki w danych (naprawione 2026-09-21, patrz komentarz w zadaniu ClickUp):

- pozycja zamówienia klientki zapisana pod niewłaściwym produktem,
- lista „Do zamówienia" agreguje po produkcie **ponad stronami**, więc zsumowała 2 szt. jednego
  OT8 i zamówienie u dostawcy PRX/25 poszło na 2 × „Jump up OT8", podczas gdy „Whos fans OT8"
  nie został zamówiony wcale,
- rozbieżność między macierzą setów (1 szt.) a zamówieniem proxy (2 szt.), która ujawniła błąd.

Fizycznie nic nie ucierpiało — u dostawcy zamówiono poprawnie, a klientka dostała właściwe
albumy. Problem dotyczył wyłącznie zapisów.

### Dlaczego to przeszło

`_validate_section_data()` w `modules/admin/offers.py` sprawdza dla produktu-kompletu tylko dwie
rzeczy: czy produkt istnieje i czy jest typu *exclusive*. Nic nie weryfikuje jego związku
z resztą setu.

Strona 96 powstała najprawdopodobniej przez duplikat strony 95 — `offers_duplicate()`
(`modules/admin/offers.py`) kopiuje `set_product_id` 1:1. Podmieniono grupę wariantową,
produkt-komplet został stary i nic nie zaprotestowało.

### Ograniczenie, które kształtuje rozwiązanie

**W danych nie istnieje żadne powiązanie „ten OT8 należy do tego albumu".** Produkty obu albumów
mają identyczne `series_id`, `category_id`, `manufacturer_id` i `product_type_id`. Tabela
`variant_groups` zawiera wyłącznie `id`, `name` i znaczniki czasu — żadnego odniesienia do
produktu-kompletu. Jedyne, co odróżnia albumy, to nazwa produktu (heurystyka tekstowa)
i przypadkowa różnica dostawcy.

Dlatego walidacja „czy OT8 pasuje do setu" jest niewykonalna bez zmiany schematu bazy.
Zamiast tego opieramy się na regule strukturalnej, potwierdzonej przez Karolinę:

> **Ten sam produkt-komplet użyty na dwóch stronach to zawsze błąd.**

Zapytanie po całej bazie produkcyjnej potwierdziło, że jedyny taki przypadek w historii
to omawiany błąd. Reguła jest więc precyzyjna i nie generuje fałszywych alarmów.

## Rozwiązanie

### 1. Unikalność produktu-kompletu, sprawdzana przy zapisie strony

Nowa funkcja walidująca, wołana **raz dla całego zapisu** (a nie per sekcja), ponieważ musi
widzieć wszystkie sekcje naraz. Sprawdza dwa rodzaje kolizji:

- **w obrębie zapisywanej strony** — dwie sekcje-sety wskazujące ten sam produkt-komplet;
  te sekcje mogą jeszcze nie istnieć w bazie, więc porównanie musi objąć przychodzące dane,
- **z innymi stronami** — dowolna `OfferSection` w bazie, która używa tego samego
  `set_product_id`, a **nie należy do sekcji zapisywanych w tym żądaniu**.

Wykluczenie własnych sekcji jest konieczne, żeby ponowny zapis niezmienionej strony nie
blokował się na samym sobie.

Sekcje bez produktu-kompletu (`set_product_id = NULL`) są pomijane — wiele stron może go nie mieć.

### 2. Komunikat wskazujący źródło konfliktu

Komunikat podaje nazwę produktu i nazwę kolidującej strony, żeby wiadomo było, gdzie szukać:

> Produkt-komplet „GH5 - Jump up 1.0 (Album) Photobook ver - OT8" jest już użyty na stronie
> „Ateez GH5 - Jump up 1.0 (album) photobook ver". Każdy komplet może należeć tylko do jednej
> strony.

Dla kolizji w obrębie jednej strony:

> Produkt-komplet „GH5 - Jump up 1.0 (Album) Photobook ver - OT8" jest wybrany w dwóch setach
> na tej stronie. Każdy komplet może należeć tylko do jednego setu.

Błąd wraca tą samą drogą co pozostałe błędy walidacji (`ValueError` → odpowiedź JSON), więc
panel wyświetli go bez zmian po stronie frontendu.

### 3. Duplikowanie strony nie przepisuje produktu-kompletu

`offers_duplicate()` ustawia w kopii `set_product_id = None`. Ponieważ istniejąca walidacja
wymaga produktu-kompletu dla setów z grupami wariantowymi, kopia **nie zapisze się** bez
świadomego wyboru. To usuwa przyczynę błędu u źródła.

Kopiowanie pozostałych pól sekcji (grupy wariantowe, elementy setu, bonusy, zdjęcia) pozostaje
bez zmian.

## Czego rozwiązanie nie obejmuje

- **Zwykłe produkty w sekcjach** (`OfferSection.product_id`, `OfferSetItem.product_id`) — ich
  powtarzanie między stronami jest normalne i nie podlega blokadzie.
- **Migracja ani backfill** — sprawdzenie na produkcji potwierdziło brak innych kolizji.
- **Filtrowanie listy wyboru** w panelu (dziś pokazuje wszystkie produkty) — to osobny wątek,
  powiązany z zadaniem „C" (wyświetlanie nabywców pełnego setu).
- **Powiązanie grupy wariantowej z produktem-kompletem** w schemacie bazy — rozwiązałoby problem
  najpełniej, ale wymaga migracji i zmian w panelu; poza zakresem tej zmiany.

## Testy

Pisane przed implementacją (TDD), w `tests/`:

1. **Kolizja między stronami** — zapis strony B z produktem-kompletem używanym przez stronę A
   kończy się błędem, a komunikat zawiera nazwę strony A.
2. **Kolizja w obrębie jednej strony** — dwie sekcje-sety z tym samym produktem-kompletem
   w jednym zapisie kończą się błędem.
3. **Ponowny zapis własnej strony** — zapis niezmienionej strony przechodzi; sekcja nie blokuje
   się na własnym produkcie-komplecie.
4. **Sekcje bez produktu-kompletu** — zapis wielu setów z `set_product_id = NULL` przechodzi.
5. **Duplikowanie** — kopia strony ma `set_product_id = None`, przy zachowaniu pozostałych pól
   sekcji (grupa wariantowa, elementy setu).

Testy uruchamiane przez `python -m pytest` zgodnie z konwencją projektu.

## Pliki

- `modules/admin/offers.py` — nowa funkcja walidująca, jej wywołanie w zapisie sekcji,
  zmiana w `offers_duplicate()`
- `tests/` — nowy plik testowy dla walidacji produktu-kompletu
