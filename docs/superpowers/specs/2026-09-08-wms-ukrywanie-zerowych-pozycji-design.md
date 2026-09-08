# Ukrywanie pozycji z ilością 0 w widokach magazynowych

Data: 2026-09-08
Status: zatwierdzony projekt, przed planem wdrożenia

## Problem

Karta zlecenia wysyłki w panelu WMS pokazuje pozycje, których ilość wynosi 0 —
np. „1x Ateez Higher Nasa Selfie - Mingi / 0x Ateez Higher Nasa Selfie - Yunho".
Licznik nad listą podaje „2 produkty", bo liczy wiersze, nie sztuki
(`templates/admin/orders/wms_dashboard.html:337`). Obsługa czyta z tego, że paczka
zawiera więcej rzeczy, niż realnie zawiera.

Zerowe pozycje powstają przy domykaniu strony sprzedaży: produkt, który nie
zmieścił się w komplecie, nie jest kasowany, tylko dostaje `quantity = 0`,
`price = 0`, `total = 0`, `is_set_fulfilled = False`
(`utils/offer_closure.py:190`, `utils/offer_closure.py:237`). Ten sam mechanizm
zeruje gratisy w zamówieniach, którym nic nie weszło w komplet
(`utils/offer_closure.py:470`). To celowe — klient w szczegółach zamówienia widzi,
co zamawiał i co przepadło, a historia zamówienia zostaje kompletna.

Problem jest wyłącznie prezentacyjny: dane są poprawne, widoki magazynowe pokazują
za dużo.

## Zakres

Zerowe pozycje znikają z trzech widoków:

1. **Karta zlecenia w panelu WMS** (`templates/admin/orders/wms_dashboard.html`) —
   obie gałęzie szablonu: paczka zbiorcza (linie ~331–349) i zlecenie zwykłe
   (linie ~369–388).
2. **Lista do kompletacji** (`modules/orders/wms.py`, `_build_session_data`) —
   zerowa pozycja wchodzi dziś do sesji WMS i od razu liczy się jako zebrana
   (`picked_quantity 0 >= quantity 0`), więc pakująca widzi wiersz, którego nie ma
   czego zdjąć z półki.
3. **Widok klienta „moje wysyłki"** (`templates/client/shipping/requests_list.html:58`
   i `:66`).

Poza zakresem — bez zmian:

- szczegóły zamówienia (`templates/admin/orders/detail.html`) — ma osobną sekcję
  „poza setem" i ta informacja ma tam pozostać widoczna,
- domykanie oferty i cała logika alokacji kompletów,
- sumy, ceny, faktury, `items_count` (liczy po sztukach, więc już dziś jest poprawny),
- dane w bazie: żaden wiersz nie jest kasowany ani modyfikowany.

## Rozwiązanie

### Jedna definicja w modelu

W `modules/orders/models.py` (klasa `Order`) powstaje właściwość zwracająca pozycje,
które realnie jadą — analogicznie do istniejącego `ShippingRequest.active_orders`
(`modules/orders/models.py:1695`), który tym samym wzorcem filtruje zamówienia
anulowane i zwroty:

```python
@property
def shippable_items(self):
    """Pozycje, które realnie jadą — bez wyzerowanych przy domykaniu oferty."""
```

Zwraca pozycje z `quantity > 0`, zachowując kolejność z `sorted_items`
(`modules/orders/models.py:602`), żeby układ listy nie zmienił się w zamówieniach
bez zer.

Docstring wyjaśnia, skąd biorą się zera i dlaczego filtrujemy zamiast kasować —
tak jak robi to docstring `active_orders`.

### Kryterium: `quantity > 0`, bez wnikania w powód

Filtrujemy po samej ilości, nie po `is_set_fulfilled is False`. Uzasadnienie: jeśli
sztuk jest zero, nie ma czego zdjąć z półki — niezależnie od tego, skąd to zero się
wzięło. Przy okazji obejmuje to wyzerowane gratisy, które mają dokładnie ten sam
problem, a nie mają `is_set_fulfilled` ustawionego w każdej ścieżce.

### Zamówienie z samymi zerami znika w całości

Jeśli po odfiltrowaniu zamówieniu nie zostaje żadna pozycja, w karcie WMS nie
pokazujemy go wcale — razem z numerem zamówienia. Nic z niego nie jedzie, więc nie
zajmuje miejsca w karcie.

Konsekwencja, którą trzeba obsłużyć: licznik przycisku „Pokaż więcej (N)"
(`wms_dashboard.html`, atrybut `data-hidden-count`) liczy dziś zamówienia przez
`ns.i` oraz `sr.orders|length`. Oba muszą pomijać zamówienia ukryte, inaczej przycisk
obieca więcej pozycji, niż da się rozwinąć.

### Świadomie przyjęte ryzyko

Zamówienie, z którego nic nie weszło w komplet, a które omyłkowo zostało podpięte do
paczki, przestanie być widoczne w karcie WMS. Właścicielka podjęła tę decyzję
świadomie, preferując czystość widoku przy pakowaniu.

## Testy

- pozycja z `quantity = 0` nie trafia do `shippable_items`,
- zamówienie bez zerowych pozycji zwraca dokładnie to samo co dotąd, w tej samej
  kolejności,
- zamówienie z samymi zerami nie pojawia się w karcie WMS (render szablonu),
- licznik produktów w karcie pokazuje liczbę żywych pozycji,
- licznik „Pokaż więcej (N)" zgadza się z liczbą zamówień faktycznie ukrytych,
- `_build_session_data` nie zwraca zerowych pozycji, a postęp kompletacji
  (`picked_percentage`, `is_picked`) zachowuje się jak dotąd.

Testy renderujące szablon wymagają `app.test_request_context()`, nie
`app.app_context()` — globalny context processor czyta `flask.session`.

## Uwaga wykonawcza

W chwili pisania specyfikacji w katalogu roboczym leży niedokończona praca nad
odznakami (`modules/achievements/checkers.py`, `tests/test_odznaki_metryki.py`) na
gałęzi `fix/odznaka-exclusive-veteran`. Wdrożenie tej zmiany zaczyna się dopiero po
tym, jak właścicielka domknie tamto zadanie i da sygnał. Nowa gałąź zakładana od
`main`.
