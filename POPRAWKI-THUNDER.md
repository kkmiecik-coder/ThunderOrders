# POPRAWKI THUNDER - Plan napraw flow Exclusive

**Data:** 2026-02-21
**Status:** W realizacji

---

## Zadania do wykonania

### ZADANIE 1: Email o zmianie statusu zamowienia
**Priorytet:** KRYTYCZNY | **Naklad:** Maly (quick win)
**Status:** [x] ZROBIONE (2026-02-21)

**Problem:** Funkcja `send_order_status_change_email()` i szablon `order_status_change.html` istnieja, ale nigdy nie sa wywolywane. Klient nie wie co sie dzieje z zamowieniem.

**Plan:**
- Dodac wywolanie `send_order_status_change_email()` w `modules/orders/routes.py` w funkcji `admin_update_status()` (~linia 504)
- Dodac wywolanie w `bulk_status_change()` (~linia 1123)
- Pobierac email klienta z `order.customer_email` (obsluguje zalogowanych i gosci)
- Pobierac imie z `order.customer_name`
- Sprawdzic i ewentualnie poprawic szablon `templates/emails/order_status_change.html`

**Pliki do zmiany:**
- `modules/orders/routes.py`
- `templates/emails/order_status_change.html` (weryfikacja)

---

### ZADANIE 2: Usuniecie systemu komentarzy/wiadomosci (admin <-> klient)
**Priorytet:** KRYTYCZNY | **Naklad:** Sredni
**Status:** [x] ZROBIONE (2026-02-21)

**Problem:** System komentarzy nie jest uzywany, brak powiadomien - do usuniecia z UI klienta.

**Plan:**
- Usunac formularz komentarza z `templates/client/orders/detail.html` (sekcja "Wiadomosci/Chat")
- Usunac wyswietlanie komentarzy z widoku klienta
- Usunac/dezaktywowac endpoint `client_add_comment` w `modules/orders/routes.py` (~linia 1636)
- Usunac zakomentowany kod email powiadomien o komentarzach (linie 564-573, 1661-1669)
- Pozostawic system komentarzy po stronie admina (komentarze wewnetrzne `is_internal=True` zostaja)
- Usunac zwiazany JS jesli istnieje

**Pliki do zmiany:**
- `templates/client/orders/detail.html`
- `modules/orders/routes.py`
- `static/js/pages/client/order-detail.js` (jesli zawiera kod komentarzy)
- `static/css/pages/client/order-detail.css` (jesli zawiera style komentarzy)

---

### ZADANIE 3: Email o dodaniu tracking number
**Priorytet:** WAZNY | **Naklad:** Sredni
**Status:** [ ] Do zrobienia

**Problem:** Klient nie wie ze paczka zostala wyslana. Brak emaila przy dodaniu numeru sledzenia.

**Plan:**
- Dodac nowa funkcje `send_tracking_number_email()` w `utils/email_sender.py`
- Stworzyc szablon `templates/emails/tracking_added.html` (z linkiem do sledzenia)
- Znalezc miejsce w kodzie gdzie tracking number jest zapisywany i dodac wywolanie
- Obslugac obu: zalogowanych i gosci (customer_email)
- Szablon powinien zawierac: numer zamowienia, numer tracking, kurier, link sledzenia

**Pliki do zmiany:**
- `utils/email_sender.py`
- `templates/emails/tracking_added.html` (nowy)
- `modules/orders/routes.py` (dodanie wywolania przy zapisie tracking)

---

### ZADANIE 4: Auto-update paid_amount po zatwierdzeniu platnosci
**Priorytet:** WAZNY | **Naklad:** Maly
**Status:** [ ] Do zrobienia

**Problem:** Admin zatwierdza dowod wplaty, ale `paid_amount` na zamowieniu sie nie aktualizuje. Dashboard klienta pokazuje bledna kwote "do zaplaty".

**Plan:**
- W `modules/admin/payment_confirmations.py` w funkcji approve (~linia 112):
  - Po ustawieniu `confirmation.status = 'approved'`
  - Dodac: `order.paid_amount += confirmation.amount`
  - Upewnic sie ze nie przekraczamy `total_amount`
- Sprawdzic czy rejection (cofniecie zatwierdzenia) tez powinno odejmowac kwote

**Pliki do zmiany:**
- `modules/admin/payment_confirmations.py`

---

### ZADANIE 5: Usuniecie dzwoneczka powiadomien
**Priorytet:** WAZNY | **Naklad:** Maly (quick win)
**Status:** [ ] Do zrobienia

**Problem:** Dzwoneczek z hardcoded badge "3" - falzywy, nic nie robi, mylace UX.

**Plan:**
- Znalezc ikone dzwoneczka w szablonach (prawdopodobnie w topbar/header klienta)
- Usunac caly element HTML dzwoneczka
- Usunac powiazany CSS jesli istnieje
- Usunac powiazany JS jesli istnieje

**Pliki do zmiany:**
- Szablony topbar/header (do zidentyfikowania)
- Powiazany CSS/JS

---

### ZADANIE 6: Email o nowej stronie Exclusive
**Priorytet:** SREDNI | **Naklad:** Sredni-duzy
**Status:** [ ] Do zrobienia

**Problem:** Klienci nie sa informowani o nowych dropach Exclusive.

**Plan:**
- Dodac pole `notify_clients_on_publish` (Boolean, default False) do modelu `ExclusivePage`
- Migracja bazy danych (flask db migrate)
- Dodac toggle w Page Builderze (admin UI) "Wyslij powiadomienie klientom przy publikacji"
- Dodac nowa funkcje `send_new_exclusive_page_email()` w `utils/email_sender.py`
- Stworzyc szablon `templates/emails/new_exclusive_page.html`
- Przy zmianie statusu na 'active' (publish) - jesli toggle wlaczony, wyslac email do wszystkich klientow
- Pobrac liste klientow z rola 'client'

**Pliki do zmiany:**
- `modules/exclusive/models.py` (nowe pole)
- `migrations/versions/` (nowa migracja)
- `modules/admin/exclusive.py` (toggle w UI + logika wysylki)
- `templates/admin/exclusive/` (toggle w formularzu)
- `utils/email_sender.py` (nowa funkcja)
- `templates/emails/new_exclusive_page.html` (nowy szablon)

---

### ZADANIE 7: Usuniecie linku "Nowe zamowienie" z sidebar
**Priorytet:** SREDNI | **Naklad:** Maly (quick win)
**Status:** [ ] Do zrobienia

**Problem:** Link prowadzi do `#`, nie dziala, mylace UX.

**Plan:**
- Znalezc i usunac element "Nowe zamowienie" z `templates/components/sidebar_client.html`

**Pliki do zmiany:**
- `templates/components/sidebar_client.html`

---

### ZADANIE 8: Przeniesienie plikow dowodow platnosci poza static
**Priorytet:** SREDNI | **Naklad:** Sredni-duzy
**Status:** [ ] Do zrobienia

**Problem:** Pliki dowodow platnosci w `static/payment_confirmations/` sa publicznie dostepne.

**Plan:**
- Przeniesc katalog docelowy z `static/payment_confirmations/` na `uploads/payment_confirmations/`
- Zmodyfikowac `save_payment_proof_file()` w `modules/client/payment_confirmations.py` aby zapisywal do nowego katalogu
- Stworzyc nowy endpoint `/payment-proof/<filename>` ktory:
  - Sprawdza autoryzacje (wlasciciel zamowienia LUB admin/mod)
  - Serwuje plik przez `send_from_directory()`
- Zaktualizowac wszystkie odwolania do plikow w szablonach (admin + client)
- Dodac `uploads/` do `.gitignore` jesli nie ma
- Obsluga istniejacych plikow: migracja z `static/` do `uploads/` (skrypt lub reczne)

**Pliki do zmiany:**
- `modules/client/payment_confirmations.py` (sciezka zapisu)
- `modules/orders/routes.py` lub nowy modul (endpoint serwowania)
- `templates/admin/payment_confirmations/list.html` (URL do pliku)
- `templates/client/orders/detail.html` (jesli odwoluje sie do pliku)
- `.gitignore`

---

## Zadania zaparkowane

| # | Pomysl | Powod parkowania |
|---|--------|-----------------|
| 3 (orig) | Email platnosci dla goscia | Do omowienia szczogolow |
| 4 (orig) | Gosc - upload dowodu platnosci | Do omowienia szczogolow |
| 9 (orig) | Przypomnienie o platnosci (CRON) | Wymaga konfiguracji CRON na VPS |

Szczegoly zaparkowanych pomyslow: `POMYSLY-THUNDER.md`

---

## Log realizacji

| Data | Zadanie | Status | Uwagi |
|------|---------|--------|-------|
| 2026-02-21 | Zadanie 1: Email o zmianie statusu | DONE | Dodano wywolanie w admin_update_status() i bulk_status_change(). Szablon OK. |
| 2026-02-21 | Zadanie 2: Usuniecie komentarzy klienta | DONE | Usunieto: chat z detail.html, client_add_comment route, JS/CSS komentarzy, _comment_item.html. |
| 2026-02-21 | Zadanie 2b: Usuniecie komentarzy admina | DONE | Usunieto: sekcja "Wymiana wiadomosci" z admin/orders/detail.html, admin_add_comment route, timeline komentarzy, JS scroll. |
