# Rozdział kart z kupionych produktów + zatwierdzenie bez maili — projekt

Data: 2026-11-18 · Gałąź: `feat/kupione-karty` · Bazuje na: rozdział gratisów + pule (2026-11-16, 2026-11-17)

## Po co

Karolina rozdziela nie tylko gratisy, ale też kupione rzeczy, np. losowe trading pc. Chce od klientek
zebrać to samo co przy gratisach: kolejność zgłoszeń, ranking i uwagi. Potem albo rozdziela sama
(z Excela), albo pozwala rozdzielić sklepowi. Często nie chce, żeby klientki dostały/zobaczyły wynik.
Nie zawsze zna ilości kart, ale rodzaje (np. członkowie grupy) zna z góry.

## Cele

1. Akcja ma **rodzaj**: „Gratisy” (jak dziś) albo „Kupione produkty”.
2. Przy „Kupione produkty” karty klientki = suma sztuk kupionych produktów akcji (zwykłe, nie gratisowe
   pozycje zamówień) z wybranych stron ofert, bez zamówień anulowanych/zwróconych. Pule działają jak dziś
   (jeden produkt = jedna pula, wspólny ranking i kolejka).
3. **Excel z odpowiedziami dostępny od publikacji** (nie dopiero po rozdzieleniu) i z nową kolumną
   **Ranking** („1. San, 2. Yunho, …”).
4. **„Zakończ bez rozdziału”** — dla zamkniętej akcji: nowy status „Zakończona (rozdział ręczny)”.
   Nic nie jest liczone ani wysyłane. Da się cofnąć do „Zamknięta”.
5. Przy zatwierdzaniu dwa przyciski: **„Zatwierdź i wyślij maile”** (jak dziś) i **„Zatwierdź bez maili”**.
   Dotyczy obu rodzajów akcji.
6. Po zatwierdzeniu bez maili **klientka nie widzi przydziału nigdzie** (strona akcji, zamówienie, kafelek).
   Admin, szczegóły zamówienia w adminie i pakowanie (WMS) widzą karty jak dziś.

## Poza zakresem

- Mieszanie gratisu i kupionego produktu w jednej akcji (wybrany Sposób 1; można dobudować później).
- Zmiana rodzaju akcji po publikacji (rodzaj zmienia się tylko w szkicu, jak pule).
- Zmiana algorytmu rozdziału.

## Podejścia (wybór Karoliny: 1)

1. **Rodzaj na całej akcji** — wybrane. Proste, mało miejsc na pomyłkę.
2. Rodzaj na każdej puli — elastyczniejsze, ale więcej pracy i ryzyka błędów w liczeniu uprawnień.

## Jak (ustalenia)

- Model `GiftCampaign`: `kind` (`'gratis'` | `'zakup'`, NOT NULL, domyślnie `'gratis'`),
  `results_hidden` (bool, domyślnie False). Nowy status `STATUS_FINISHED_MANUAL = 'zakonczona'`.
  Migracja Alembic; istniejące akcje dostają `kind='gratis'`, `results_hidden=False`.
- `compute_entitlements`: filtr `OrderItem.is_bonus` = `True` dla gratisów, `False` dla zakupu.
- Formularz: przełącznik rodzaju na górze (tylko w szkicu). Dla zakupu lista stron = wszystkie strony
  ofert, lista produktów = produkty kupione (zwykłe pozycje) na stronach ofert, z polem „Szukaj”.
- Zatwierdzenie bez maili: `approve()` + `results_hidden=True`, bez `send_results`. Cofnięcie
  zatwierdzenia czyści `results_hidden`.
- Klient: przy `results_hidden` strona akcji pokazuje „Zgłoszenia zamknięte, dziękujemy” bez kart;
  etykieta kart przy pozycji zamówienia klientki i kafelek nie pokazują przydziału. Osobna właściwość
  dla widoku klientki; admin/WMS zostają przy obecnej (rozszerzonej o pozycje zwykłe dla zakupu).
- Teksty dla klientki przy zakupie: „Twoje karty” zamiast „Gratisowe karty” (strona, kafelek, mail
  z zaproszeniem). Zaproszenie do rankingu przy publikacji wysyłane w obu rodzajach.

## Zostawione budującemu (moje decyzje, do sprawdzenia przez Karolinę)

- „Zakończ bez rozdziału” można cofnąć do „Zamknięta” — tanie, chroni przed misklikiem.
- Excel przed rozdzieleniem: kolumny przydziału puste, reszta (kolejność, ranking, uwagi) wypełniona.
- Nazwa pliku Excel: `karty_…` dla zakupu, `gratisy_…` dla gratisów.

## Bezpieczeństwo

- Lokalnie maile tylko do pułapki SMTP. Przed wdrożeniem kopia bazy produkcyjnej (migracja).
- Push tylko za zgodą Karoliny.
