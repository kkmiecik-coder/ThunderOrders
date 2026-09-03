# Stawki album/incl wpisywane raz na całą paczkę

Data: 2026-09-03
Gałąź: `feat/stawki-na-poziomie-paczki`
Poprzednie projekty: `2026-08-31-wysylka-album-vs-incl-design.md`,
`2026-09-01-przelacznik-cala-paczka-incl-design.md`,
`2026-09-02-okno-partii-wartosc-ostrzezenie-dziennik-design.md`

## Problem

Stawki album/incl wpisuje się dziś osobno przy **każdym produkcie**. W partii
PRX/PL/14 było ich dziewięć — dziewięć razy te same dwie liczby. To nie tylko
mozolne: właśnie przy jednym z tych dziewięciu powtórzeń stawki wylądowały odwrotnie,
co kosztowało godzinę dochodzenia i błędne kwoty u dwóch klientek.

## Ustalenia z właścicielką

- Partia do Polski to zawsze **jedna wysyłka jednego typu rzeczy** — albumy z jednego
  wydania. Koszt wysyłki za sztukę jest w niej *zwykle* wszędzie taki sam —
  **z wyjątkiem setów** (OT8), patrz korekta niżej.
- Groszowe różnice w PRX/PL/14 (Mingi incl 6,52 zamiast 6,51; Wooyoung album 14,56
  zamiast 14,53) były **przypadkowe**, nie celowe.
- Produkty o realnie różnej wadze (lightstick, keyring, pouch) chodzą trybem
  **preorder**, nie exclusive, więc przez to okno nie przechodzą.

Sprawdzone w danych produkcyjnych: **dziesięć ostatnich partii do Polski, wszystkie
zawierają wyłącznie produkty z zamówień exclusive.** Ani jednej mieszanej.

## Rozwiązanie

Dwa pola stawek przenoszą się z każdego produktu do **nagłówka paczki**, w osobny
wiersz pod nim (nagłówek jest już gęsty: tytuł, przełącznik „cała paczka na samo incl",
kwota wysyłki).

```
PACZKA: PRX/12    [✓] cała paczka na samo incl     Wysyłka: [ 0,00 ] PLN
──────────────────────────────────────────────────────────────────────
Stawki paczki:   cały album [ 14,53 ] zł/szt    samo incl [ 6,51 ] zł/szt
──────────────────────────────────────────────────────────────────────
PRODUKT                    CENA/SZT   ILOŚĆ   WARTOŚĆ
```

Przy produktach pola stawek **zostają widoczne i edytowalne** — patrz korekta niżej.
Lista klientów z polami „samo incl" bez zmian.

### Korekta z 2026-09-03: sety psują założenie „jedna stawka na paczkę"

Pierwotnie pola stawek przy produktach miały **zniknąć z widoku**, skoro stawka jest
w paczce wszędzie taka sama. **To założenie jest nieprawdziwe** — wyszło przy pierwszym
użyciu, gdy okazało się, że nie da się wycenić pozycji OT8.

**OT8 to zestaw ośmiu kart**, więc jego „samo incl" kosztuje ośmiokrotność stawki
pojedynczego członka. W PRX/PL/14 widać to wprost: OT8 miał incl **52,08** przy **6,51**
u wszystkich pozostałych — czyli dokładnie 8 × 6,51. Ta liczba była w danych, które
analizowałam dzień wcześniej, i została wtedy błędnie uznana za zgodną z regułą.

Dlatego:

- stawki z nagłówka **wypełniają** wszystkie produkty paczki (wygoda zostaje),
- pole przy produkcie **można nadpisać** — dla setu wpisuje się właściwą wielokrotność,
- **nadpisana linijka nie jest już zamazywana** przy kolejnych zmianach stawki
  w nagłówku i jest wizualnie oznaczona, żeby było widać, która odstaje.

Rozpoznanie nadpisania opiera się na `dataset.manual`, ustawianym wyłącznie w `oninput` —
czyli tylko przy pisaniu przez człowieka. Wypełnianie ze stawek paczki ustawia `.value`
bez zdarzenia, więc samo się nie oznacza.

### Dlaczego pola per produkt zostają w kodzie

Pola stawek przy produktach **nie są usuwane z DOM — są ukrywane**, a wartość z paczki
jest do nich wpisywana. Cała logika pieniężna (`refreshRatesRow`, walidacja przed
wysłaniem, budowanie payloadu, licznik różnicy) czyta dokładnie te pola i **nie wymaga
żadnej zmiany**. Kontrakt wysyłany do serwera zostaje identyczny: stawki lecą przy
każdej pozycji, tylko wypełnione raz zamiast dziewięć razy.

To świadomy wybór: dzień wcześniej przepisanie logiki payloadu wprowadziło błąd, który
podwajał zapisane „samo incl". Tutaj nie ruszamy niczego, co liczy pieniądze.

### Podpowiedź stawki incl — na poziomie paczki

Jak dotąd, tylko dla całej paczki: `(kwota paczki − stawka_album × wszystkie sztuki
album) / wszystkie sztuki incl`. Pojawia się jako podpowiedź w polu incl w nagłówku.

### Ostrzeżenie o odwróconych stawkach

Przenosi się na poziom paczki — jedno zamiast dziewięciu identycznych. Warunki bez
zmian: stawka albumu faktycznie wpisana, są sztuki obu rodzajów, incl wyższe niż album.

### Puste pola stawek = zachowanie jak dotąd

Jeśli pola w nagłówku zostaną puste, okno działa dokładnie jak przed zmianą: wartości
wpisuje się przy produktach, stawki nie lecą do serwera, obowiązuje stara ścieżka
liczenia. To siatka bezpieczeństwa na wypadek partii, która nie pasuje do jednej stawki.

## Czego nie zmieniamy

Modelu danych, algorytmu liczenia, kontraktu payloadu, kodu serwera ani testów. Kwoty
u klientów liczą się identycznie jak dziś.

## Weryfikacja

W przeglądarce, na danych produkcyjnych z lokalnej kopii bazy: wpisanie stawek w
nagłówku wypełnia wszystkie produkty paczki; wartości linijek i licznik różnicy zgadzają
się z ręcznym wyliczeniem; ostrzeżenie pojawia się przy odwróconych stawkach; puste pola
zachowują stare działanie. Testów automatycznych brak — repo nie ma oprzyrządowania do
JavaScriptu, a zmiana nie dotyka kodu serwera.
