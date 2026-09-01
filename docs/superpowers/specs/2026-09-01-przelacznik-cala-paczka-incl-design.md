# Przełącznik „cała paczka na samo incl"

Data: 2026-09-01
Gałąź: `main` (drobne rozszerzenie okna partii, po wdrożeniu podziału album/incl)
Poprzedni projekt: `2026-08-31-wysylka-album-vs-incl-design.md`

## Problem

Zdarzają się paczki, w których **wszyscy** klienci biorą samo incl. Po wprowadzeniu
podziału album/incl admin musi wtedy kliknąć pole „samo incl" przy każdym kliencie
z osobna — przy partii z kilkunastoma klientami to kilkanaście kliknięć, z których
każde robi dokładnie to samo.

## Ustalenia z właścicielką

- Przełącznik działa na poziomie **całej paczki** (`PACZKA: PRX/x`), nie pojedynczego
  produktu. Paczka może zawierać kilka produktów — przełącznik obejmuje wszystkie.
- **Wyłączenie zeruje wszystkich.** Świadomie odrzucone „przywróć stan sprzed
  włączenia": prostsze i przewidywalne. Cena: ręczne ustawienia sprzed włączenia
  przepadają.
- Gdy w partii nikt nie bierze całego albumu, **linijka stawki albumowej znika**.
- Przełącznik **sam odzwierciedla stan** — zapala się, gdy wszyscy klienci paczki są
  na maksimum, gaśnie, gdy choć jeden nie jest.

## Rozwiązanie

Wyłącznie po stronie przeglądarki, w `static/js/pages/admin/stock-orders.js`.

Żadnej zmiany w bazie, na serwerze ani w kontrakcie payloadu: przełącznik wpisuje
dokładnie te same liczby przy klientach, które admin wpisałby ręcznie. Odrzucony
wariant z flagą „ta paczka jest incl" zapisywaną w bazie — dokładałby drugie źródło
prawdy o tym samym.

### Elementy

- **Znacznik w nagłówku paczki** (`.poland-package-incl-input`), obok pola „Wysyłka",
  z `data-order-index` wiążącym go z paczką.
- **`maksInclKlienta(klient)`** — maksimum to `order_total_quantity` (liczba sztuk
  klienta w **całym zamówieniu**), bo taka jest semantyka `incl_only_quantity`
  w kontrakcie `create_poland_order`.
- **`handlePackageInclToggle(orderIndex)`** — dla każdej pozycji o tym `order_index`
  ustawia wszystkim klientom maksimum (włączenie) albo zero (wyłączenie), przepisuje
  wartości do pól, odświeża wiersze stawek i licznik różnicy.
- **`refreshPackageInclToggle(orderIndex)`** — przelicza stan znacznika; wołane po
  każdej ręcznej zmianie pola „samo incl" oraz raz po wyrenderowaniu okna, żeby paczka
  z zapisanym już maksimum otwierała się zaznaczona.

### Ukrywanie linijki albumowej

W `refreshRatesRow`, gdy `albumQty === 0`, linijka `[data-role="album-line"]` znika,
a jej pole stawki jest **czyszczone**. Bez czyszczenia zostałaby w nim wartość, której
admin już nie widzi, a która poleciałaby w payloadzie — ujemna wywołałaby błąd 400
z serwera o polu niewidocznym na ekranie.

Walidacja przed wysłaniem już wcześniej wymagała stawki albumowej tylko przy
`albumQty > 0`, więc ukrycie pola nie powoduje blokady wysyłki.

## Weryfikacja

Projekt nie ma oprzyrządowania do testów JavaScriptu, a dorabianie go dla jednego
znacznika byłoby nieproporcjonalne. Weryfikacja w przeglądarce, na danych
produkcyjnych z lokalnej bazy (paczka PRX/3, 11 klientów, kwota paczki 220 zł):

| krok | wynik |
|---|---|
| stan początkowy | znacznik zgaszony, album 11 szt, incl 0 szt |
| włączenie | wszystkie pola na `1`, album 0 szt, incl 11 szt, linijka albumowa ukryta |
| stawka incl 20 zł | suma 220,00, różnica 0,00 |
| stawka incl 10 zł | suma 110,00, różnica −110,00 |
| wyłączenie | wszystkie pola na `0`, linijka albumowa z powrotem |
| ręczne ustawienie wszystkich na maksimum | znacznik zapala się sam |
| cofnięcie jednego klienta | znacznik gaśnie, album 1 szt, incl 10 szt |

## Poza zakresem

- Przełącznik na poziomie pojedynczego produktu — do rozważenia, gdyby zdarzały się
  paczki mieszane, w których jeden album idzie w całości na incl, a drugi nie.
- Odtwarzanie stanu sprzed włączenia (świadomie odrzucone, patrz Ustalenia).
