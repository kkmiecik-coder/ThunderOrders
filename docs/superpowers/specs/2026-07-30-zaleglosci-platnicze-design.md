# Zaległości płatnicze: kafelek na dashboardzie i przypomnienia dla wszystkich etapów — projekt

Data: 2026-07-30
Gałąź: (do ustalenia — osobna od `feat/clo-vat-zerowy-podatek`)

## Problem

Karolina nie ma dziś łatwego sposobu, żeby zobaczyć jednym rzutem oka, kto
zalega z płatnością. Dwie przyczyny:

1. **Brak zbiorczego widoku.** Lista zamówień w panelu admina
   (`orders.admin_list`, `modules/orders/routes.py:89-227`) ma filtry per etap
   (`pay_e1..pay_e4`, `modules/orders/forms.py:101-122`), ale nie ma jednego
   filtra „pokaż wszystko co zalega". Taki filtr (`payment_status=paid|unpaid|partial`)
   istnieje tylko po stronie klienta (`client_list`, `modules/orders/routes.py:1604,1637-1649`),
   nie w panelu admina.
2. **Przypomnienia mailowe nie obejmują wszystkich etapów.** Istniejący cron
   `flask check-payment-reminders` (`app.py:548-810`) i konfiguracja reguł
   (`PaymentReminderConfig`/`PaymentReminderLog`, `modules/offers/reminder_models.py`)
   działają tylko dla etapu 1 (produkt) i etapu 2 (przesyłka z Korei). Etap 3
   (cło/VAT) i etap 4 (przesyłka PL) nie generują żadnych przypomnień, mimo że
   mają swoje terminy w bazie (`Order.get_customs_vat_deadline()`,
   `get_shipping_pl_deadline()`, `modules/orders/models.py:994-1015`).

Istniejąca infrastruktura, na której się opieramy:
- `Order.total_to_pay` / `remaining_to_pay` (`modules/orders/models.py:358-394`) —
  gotowe wyliczenie ile brakuje, sumujące E1–E4 per zamówienie (w Pythonie,
  nie jako zapytanie SQL — nie ma dziś agregatu na poziomie bazy).
- Wzorzec kafelków na dashboardzie (`templates/admin/dashboard.html:16-64`,
  klasa `.pc-dashboard-widget`) — ikona, tekst z licznikiem, link, renderowany
  tylko gdy licznik > 0.
- Reguły przypomnień per etap już istnieją w UI admina
  (`modules/admin/offers.py:1861-1933`).

## Zakres

1. Kafelek „Zaległości płatnicze" na dashboardzie admina.
2. Nowa strona `/admin/payments/overdue` z listą zamówień po terminie.
3. Rozszerzenie przypomnień mailowych/push na etap 3 i 4, z ujednoliceniem
   reguł wszystkich czterech etapów do jednej wspólnej reguły.

**Poza zakresem (świadomie, YAGNI):**
- Cache'owanie/liczenie w tle — liczymy na bieżąco przy każdym wejściu.
  Do rozważenia później, jeśli strona zacznie się wolno ładować przy dużej
  liczbie zamówień.
- Osobne reguły przypomnień per etap — ujednolicamy do jednej reguły.
- Rozbicie licznika na kafelku na etapy — kafelek pokazuje jedną liczbę.

## Kafelek na dashboardzie

W `templates/admin/dashboard.html`, w `.dashboard-alerts-row`, obok kafelków
potwierdzeń i wysyłek, dochodzi kafelek w tym samym stylu
(`.pc-dashboard-widget`):

```html
<div class="pc-dashboard-widget">
    <div class="pc-dashboard-widget-left">
        <div class="pc-dashboard-widget-icon">⏰</div>
        <div class="pc-dashboard-widget-text">
            <h3>{{ overdue_orders_count }} {{ 'zamówienie zalega' if overdue_orders_count == 1 else 'zamówień zalega' }} z płatnością</h3>
            <p>Termin płatności minął, a kwota nie wpłynęła</p>
        </div>
    </div>
    <a href="{{ url_for('admin.overdue_payments_list') }}" class="pc-dashboard-widget-link">Sprawdź →</a>
</div>
```

Widoczny tylko gdy `overdue_orders_count > 0`, tak jak pozostałe kafelki w tym
wierszu. Liczbę wylicza ta sama funkcja co lista poniżej (patrz niżej), żeby
kafelek i strona zawsze pokazywały tę samą wartość.

## Strona `/admin/payments/overdue`

Nowa trasa w `modules/admin/routes.py` (obok `dashboard()`), nowy szablon.

**Kryterium dołączenia zamówienia do listy:** zamówienie ma `remaining_to_pay
> 0` na którymkolwiek etapie ORAZ termin płatności tego etapu już minął.
Zamówienia bez ustalonego terminu na danym etapie (np. cło jeszcze nie
policzone) nie mogą być „po terminie" i nie trafiają na listę z tego powodu —
brak terminu ≠ zaległość. Zamówienia w statusie anulowane/zakończone są
pomijane.

Ponieważ zamówienie może zalegać na więcej niż jednym etapie jednocześnie,
liczy się jako jedna pozycja na liście (nie duplikujemy wierszy), z etapem
najbardziej przeterminowanym jako wskazanym „głównym" powodem.

**Kolumny wiersza:**
- numer zamówienia + link do zamówienia
- klient
- pierwszy produkt z zamówienia (bez wyliczania „i N innych" — reszta widoczna
  po wejściu w zamówienie)
- etap, na którym brakuje wpłaty (E1/E2/E3/E4)
- brakująca kwota
- liczba dni od minięcia terminu

Liczone na bieżąco (bez cache'a) — iteracja po aktywnych zamówieniach z użyciem
istniejących właściwości `total_to_pay`/`remaining_to_pay` i istniejących metod
`get_*_deadline()`. Sortowanie: najdłużej zalegające na górze.

## Rozszerzenie przypomnień na etap 3 i 4

Dziś `PaymentReminderConfig` pozwala skonfigurować regułę osobno dla etapu 1 i
osobno dla etapu 2 (`payment_stage` w modelu, `modules/offers/reminder_models.py`).
Zmiana:

1. **Ujednolicenie do jednej wspólnej reguły** obowiązującej wszystkie 4 etapy
   naraz. To świadoma zmiana dzisiejszego zachowania (nie tylko rozszerzenie) —
   jeśli etap 1 i 2 mają dziś różne ustawienia, przy wdrożeniu zostaną
   skonsolidowane do jednej wartości (zostanie to pokazane i potwierdzone przed
   zapisaniem migracji, nie zniknie po cichu).
2. Cron `flask check-payment-reminders` (`app.py:548-810`) dostaje dwie nowe
   gałęzie sprawdzania: termin cła/VAT (`get_customs_vat_deadline()`) i termin
   przesyłki PL (`get_shipping_pl_deadline()`), analogicznie do istniejącej
   logiki dla etapu 1/2.
3. Treść maila/push — te same szablony co dziś (`EmailManager.build_payment_reminder_message`,
   `PushManager.notify_payment_reminder`), tylko z nazwą właściwego etapu.
4. Log wysyłek (`PaymentReminderLog`) i logika „nie wysyłaj drugi raz tego
   samego przypomnienia" działają bez zmian — już są generyczne względem etapu.
5. UI konfiguracji w `modules/admin/offers.py:1861-1933` upraszcza się do
   jednego zestawu pól reguły zamiast per-etapowych.

## Pliki do zmiany

**Backend**
- `modules/admin/routes.py` — nowa trasa `overdue_payments_list`, funkcja
  licząca listę/licznik zaległości (współdzielona z dashboardem)
- `modules/admin/routes.py:22-47` (`get_shipping_alert_counts`) — wzorzec do
  naśladowania przy pisaniu odpowiednika dla zaległości
- `app.py:548-810` — rozszerzenie `check-payment-reminders` o etap 3 i 4
- `modules/offers/reminder_models.py` — ujednolicenie reguł do jednej (bez
  `payment_stage` jako klucza różnicującego, albo z jedną wartością wspólną)
- `modules/admin/offers.py:1861-1933` — uproszczenie UI konfiguracji reguł
- migracja Alembic konsolidująca istniejące `PaymentReminderConfig` (jeśli
  etap 1 i 2 mają dziś różne wartości)

**Frontend**
- `templates/admin/dashboard.html` — nowy kafelek w `.dashboard-alerts-row`
- nowy szablon `templates/admin/payments/overdue.html`

## Testy

Nowy plik `tests/test_overdue_payments.py`:
- zamówienie z minionym terminem i `remaining_to_pay > 0` trafia na listę
- zamówienie z minionym terminem, ale w pełni opłacone — nie trafia
- zamówienie bez ustalonego terminu na etapie (np. cło nieustalone) — nie
  trafia z tego powodu, nawet jeśli inne pola sugerują brak wpłaty
- zamówienie anulowane/zakończone — pomijane niezależnie od reszty
- zamówienie zalegające na dwóch etapach jednocześnie — jedna pozycja na
  liście, nie dwie
- licznik na kafelku dashboardu zgadza się z liczbą wierszy na stronie listy
- cron wysyła przypomnienie dla etapu 3 i 4 wg tej samej reguły co etap 1/2

Regresja: `tests/test_payment_confirmation_service.py` (istniejące testy
przypomnień, jeśli są).

Uruchamianie: `python -m pytest`.

## Otwarte kwestie

- Konkretna wartość wspólnej reguły przypomnień (np. „X dni przed terminem")
  do potwierdzenia z Karoliną w trakcie wdrożenia, na podstawie tego, jakie
  wartości mają dziś etap 1 i 2 w bazie produkcyjnej.
