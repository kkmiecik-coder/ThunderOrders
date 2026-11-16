# Rozdział gratisowych kart — projekt

Data: 2026-11-16 · Właścicielka: Karolina · Status: do akceptacji

## Po co to jest

Klienci zdobywają na stronach ofert gratisowe karty (np. karty członków ATEEZ) — liczba zależy
od kwoty zakupów (1, 2, 6…). Dziś rozdział wygląda tak:

1. Zapisy na produkty na stronie oferty — gratis dopisuje się do zamówienia automatycznie
   (`OfferSetBonus`, pozycja `OrderItem.is_bonus=True`, np. „Karta gratis ATEEZ ×3”).
2. Po zamknięciu zapisów Karolina umawia z klientami godzinę i udostępnia formularz Google
   „na czas” — klient wpisuje tylko imię i nazwisko; kolejność wysłania = kolejność wyboru.
3. Drugi formularz Google (bez pośpiechu): klient układa członków od najbardziej do najmniej
   chcianego.
4. Gdy karty fizycznie dotrą, Karolina liczy ile ma każdego rodzaju i ręcznie, z dwoma
   arkuszami obok siebie, rozdziela karty.

Krok 4 zajmuje dużo czasu, a kroki 2–3 żyją poza systemem i trzeba je ręcznie zestawiać
z zamówieniami. **Cel: wszystko na stronie ThunderOrders, a rozdział robi system — Karolina
tylko przegląda i zatwierdza.**

## Cele

- Klient na jednej stronie: widzi ile kart mu przysługuje, układa ranking, o ustalonej
  godzinie klika „Zgłaszam się” (wyścig o miejsce w kolejce).
- System sam wylicza, ile kart komu się należy — z gratisów w jego zamówieniach.
- Po dotarciu kart Karolina wpisuje ilości każdego rodzaju, klika „Rozdziel”, przegląda
  propozycję, może ręcznie zamienić karty, zatwierdza.
- Przydział trafia do zamówień klientów: klient widzi u siebie, które karty dostał,
  a przy pakowaniu (WMS) widać, które karty włożyć.

## Nie-cele

- Zgarnianie kart na żywo „do koszyka” (rozważone i odrzucone — patrz Podejścia).
- Losowanie (to robi istniejący moduł konkursów).
- Aplikacja mobilna w pierwszej wersji (*decyzja Claude — patrz niżej*).

## Anty-cele (czego nie wolno zepsuć)

- Nie może to dodać Karolinie pracy względem formularzy Google. Założenie akcji ma zająć
  kilka minut.
- Klient z wieloma kartami nie może kończyć z powtórkami, jeśli dało się ich uniknąć.
- Nie ruszamy istniejącego mechanizmu naliczania gratisów przy składaniu zamówienia.

## Zasady rozdziału (ustalone z Karoliną)

1. **Rundami (zasada B).** Runda 1: każdy uczestnik w kolejności wyścigu dostaje 1 kartę.
   Runda 2: po 1 karcie dla tych, którym należy się ≥2 — znów w kolejności wyścigu. I tak dalej.
2. **W swojej kolejce klient dostaje najwyżej postawiony w rankingu rodzaj, którego jeszcze
   nie ma i który jest dostępny.**
3. **Brak powtórek ma pierwszeństwo przed rankingiem i kolejnością.** Jeśli danie komuś
   ulubionego rodzaju spowodowałoby, że ktoś inny (nawet dalej w kolejce) nieuchronnie
   dostanie powtórkę, system daje mu kolejny wybór z rankingu.
   Przykład: zostały 1× San i 1× Yunho. Nr 5 należy się jeszcze 1 karta, w rankingu ma San
   przed Yunho. Nr 9 należy się jeszcze 1 karta i Yunho już ma. Gdyby nr 5 wzięła Sana,
   nr 9 dostałaby drugiego Yunho → więc nr 5 dostaje Yunho, a nr 9 Sana. (Zasada: wybieraj
   tylko taki rodzaj, po którym wciąż istnieje rozdział bez powtórek dla wszystkich.)
4. **Powtórki tylko gdy nie da się inaczej** (np. ktoś ma 6 kart, a rodzajów są 4). Wtedy
   system minimalizuje łączną liczbę powtórek i daje je w ostatnich rundach, wg rankingu.
5. **Kto przegapił wyścig** — trafia na koniec kolejki, za wszystkimi, którzy kliknęli
   (między sobą wg daty złożenia pierwszego zamówienia). *(decyzja Claude)*
6. **Kto nie ułożył rankingu** — dostaje to, co zostanie po innych (bez powtórek, jeśli się
   da). *(decyzja Claude)*
7. **Karolina ma ostatnie słowo** — przed zatwierdzeniem może ręcznie zamienić dowolną kartę.

## Rodzaje kart — za każdym razem inne

Rodzaje są definiowane w każdej akcji osobno: raz 8 członków ATEEZ, raz 4 karty unitowe
(dwóch członków na karcie, za każdym razem inne pary). Rodzaj = nazwa (wymagana) + zdjęcie
(opcjonalne). Ilości sztuk wpisuje się dopiero po dotarciu kart (przed „Rozdziel”).

## Ranking — jak w formularzu Google

Siatka: wiersze = rodzaje kart, kolumny = miejsca 1…N, jedna odpowiedź w kolumnie i jedna
w wierszu. Bez przeciągania (Karolina nie zawsze ma zdjęcia). Klient musi ułożyć pełny
ranking, żeby go zapisać *(decyzja Claude)*. Ranking można zmieniać do momentu, aż Karolina
zamknie zgłoszenia *(decyzja Claude)*.

```
                 1.   2.   3.   4.   5.   6.   7.   8.
Hongjoong        ○    ○    ●    ○    ○    ○    ○    ○
Seonghwa         ●    ○    ○    ○    ○    ○    ○    ○
Yunho            ○    ○    ○    ○    ○    ●    ○    ○
...
```

## Podejścia (rozważone)

1. **Zgarnianie na żywo z rundami czasowymi** — strona otwiera się o godzinie, przez pierwsze
   X minut każdy bierze 1 kartę, potem limit rośnie. Odrzucone: klienci irytują się czekaniem
   na kolejne rundy, a osoba z wieloma kartami i tak może skończyć z powtórkami (na koniec
   zostaje jeden rodzaj) — przy zgarnianiu na żywo nikt nie widzi całości.
2. **Zgarnianie na żywo bez rund (pomysł Karoliny)** — każdy od razu bierze wszystkie swoje
   karty. Najprostsze, ale osoby z wieloma kartami zabierają najpopularniejsze (zasada A,
   którą Karolina odrzuciła) i ten sam problem z powtórkami.
3. **Wyścig + ranking + automatyczny przydział** ✅ **WYBRANE** — tylko system widzący
   naraz wszystkie ilości, uprawnienia i rankingi może zagwarantować brak powtórek.
   Klient klika raz (wyścig), ranking układa kiedy chce.

## Jak to działa — przebieg

**Karolina (panel admina — osobna zakładka „Rozdział gratisów” w menu, tam całe zarządzanie:
lista akcji, tworzenie/edycja, uczestnicy, rozdział, zatwierdzanie):**
1. Tworzy akcję: nazwa, strona/strony oferty, produkt-gratis (np. „Karta gratis ATEEZ”),
   lista rodzajów kart, data i godzina wyścigu.
2. Widzi listę uprawnionych (wyliczoną automatycznie) z liczbą kart.
3. Publikuje — uprawnieni dostają e-mail „przysługuje Ci X kart, ułóż ranking, wyścig
   o 20:00” *(decyzja Claude; wysyłka przez `send_email_batch`)*.
4. Po wyścigu widzi kolejkę i kto ułożył ranking. Zamyka zgłoszenia.
5. Gdy karty dotrą: wpisuje ilości sztuk każdego rodzaju → „Rozdziel” → tabela propozycji
   (osoba, miejsce w kolejce, przydzielone karty, które miejsce w rankingu dostała, ostrzeżenie
   przy powtórkach) → ewentualne ręczne zamiany → „Zatwierdź”.
6. Po zatwierdzeniu: przydział zapisuje się przy pozycjach-gratisach w zamówieniach; klienci
   dostają e-mail „Twoje gratisowe karty: San, Yunho, Mingi” *(decyzja Claude)*.

**Klient (strona akcji, wymaga logowania):**
- Widzi „Przysługują Ci 3 karty”, siatkę rankingu, odliczanie do wyścigu.
- O godzinie wyścigu pojawia się przycisk „Zgłaszam się” — klik zapisuje znacznik czasu
  serwera (z dokładnością do ms) i pokazuje „Jesteś nr 14 w kolejce”.
- Po zatwierdzeniu przydziału widzi swoje karty na stronie akcji i w szczegółach zamówienia.

## Skąd wiadomo, komu ile się należy

Suma `quantity` pozycji `OrderItem` z `is_bonus=True` i `product_id` = produkt-gratis akcji,
w zamówieniach ze wskazanych stron ofert, pogrupowana po kliencie (klient może mieć kilka
zamówień). Zamówienia anulowane się nie liczą. Lista jest liczona na bieżąco, a zamrażana
w momencie „Rozdziel”.

## Gdzie ląduje przydział

Przy pozycji-gratisie w zamówieniu (np. „Karta gratis ATEEZ ×3 → San, Yunho, Mingi”), bez
tworzenia osobnych produktów dla każdego rodzaju — rodzaje są jednorazowe, zakładanie
produktów dodałoby Karolinie pracy *(decyzja Claude)*. Widoczne w: szczegółach zamówienia
(admin i klient), liście kompletowania WMS, liście zamówień admina. Jeśli klient ma gratisy
w kilku zamówieniach, karty przypisuje się do konkretnych pozycji.

## Co zostaje budującemu

- Algorytm: rundy wg kolejki + sprawdzanie przed każdym przydziałem, czy po nim wciąż
  istnieje rozdział bez powtórek (np. przepływ w sieci osoby × rodzaje, pojemność 1);
  gdy bez powtórek się nie da — minimalizacja powtórek. Musi być deterministyczny
  i pokryty testami (przykład San/Yunho jako test).
- Model danych (propozycja): akcja, rodzaje kart (nazwa, zdjęcie, ilość), uczestnik
  (klient, znacznik wyścigu, ranking), przydział (pozycja zamówienia, rodzaj). Migracje
  przez Flask-Migrate.
- Odporność wyścigu na szczyt ruchu (wiele kliknięć w tej samej sekundzie; jeden zapis na
  klienta, unikalność).
- Ekrany w jasnym i ciemnym motywie, przyciski 44px, CSRF — wg konwencji projektu.
- Aplikacja mobilna: później, osobne zadanie.
- Stronę akcji widzą tylko zalogowani klienci, którym należy się ≥1 karta; inni dostają
  „Ta akcja Cię nie dotyczy” *(decyzja Claude)*.
- Dopóki przydział nie jest zatwierdzony, pozycja-gratis w WMS ma dopisek „przydział
  w toku”, żeby nie spakować jej przez pomyłkę *(decyzja Claude)*.
- Cofnięcie zatwierdzenia: możliwe, dopóki żadne z zamówień z akcji nie zostało
  spakowane *(decyzja Claude)*.

## Otwarte — do decyzji Karoliny

- **Za mało kart:** co, jeśli dotrze mniej kart niż łącznie się należy (np. należy się 50,
  dotarło 45)? Propozycja: ostatnie osoby w kolejce dostają mniej, system to wyraźnie
  oznacza, a Karolina decyduje (np. dosyła później).
