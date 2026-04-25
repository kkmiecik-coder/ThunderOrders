# Powiadomienia o zmianie daty zakończenia sprzedaży — design

**Data:** 2026-04-25
**Autor:** Konrad + Claude
**Status:** Zaakceptowany, gotowy do planu implementacji

---

## Cel

Gdy administrator zmieni datę zakończenia sprzedaży na **stronie aktywnej** i kliknie „Zapisz", system pokazuje modal z możliwością wysłania powiadomienia (e-mail i/lub push) do odpowiedniej grupy klientów. Powiadomienia są opcjonalne (admin może odznaczyć checkboxy) i zgodne z RODO.

## Co dostaje admin

- Strona aktywna: u góry edytora pojawia się baner „Strona jest aktywna — automatyczny zapis wyłączony, zmiany zapisuj ręcznie".
- Autozapis działa **tylko** dla stron `draft`, `scheduled`, `paused`. Na stronie `active` jest wyłączony.
- Po zmianie daty zakończenia i kliknięciu „Zapisz" — modal:
  - Stara data → nowa data (sformatowane po polsku).
  - Czerwone ostrzeżenie, jeśli nowa data jest w przeszłości („Ta data spowoduje natychmiastowe zakończenie sprzedaży").
  - Dwa checkboxy domyślnie zaznaczone:
    - „Wyślij e-mail do klientów"
    - „Wyślij powiadomienie push"
  - Przyciski: **Anuluj** (nic się nie zapisuje) / **Zapisz** (zapis + wybrane powiadomienia).
- Po zapisie toast: „Zapisano. Wysłano N maili, M powiadomień push".

## Co dostaje klient

### E-mail (do kogo)

Komunikacja podzielona zgodnie z RODO:
- **Klienci z aktywnym zamówieniem** na tej stronie (zamówienie nieanulowane) → mail **transakcyjny** (art. 6 ust. 1 lit. b — wykonanie umowy). Nie wymaga zgody marketingowej.
- **Klienci z `marketing_consent=True`** (bez zamówień) → mail **informacyjny** w neutralnym tonie.
- Wynikowa lista odbiorców = unia tych dwóch zbiorów (po `User.id`, bez duplikatów).
- Filtr bazowy w obu zbiorach: `User.role='client'` i `User.is_active=True`.

### Push (do kogo)

- Wszyscy aktywni klienci, którzy mają włączoną nową kategorię `sale_date_changes` w preferencjach powiadomień.
- Push respektuje istniejący mechanizm `NotificationPreference` i `PushSubscription`.

### Treść e-maila

- Tytuł: „Zaktualizowano datę zakończenia sprzedaży — [Nazwa strony]"
- Treść (sztywny szablon, neutralny ton, bez CTA marketingowych):
  - Stara data zakończenia (lub „bez limitu czasowego" gdy `null`)
  - Nowa data zakończenia (lub „bez limitu czasowego" gdy `null`)
  - Link do strony sprzedaży
  - Standardowa stopka

### Treść push

- Tytuł: „[Nazwa strony] — zmiana daty zakończenia"
- Body: „Nowa data zakończenia: 08.05.2026, 18:00" (lub „Sprzedaż przedłużona bez limitu czasowego" gdy `null`)
- Klik → otwiera stronę sprzedaży

## Co dochodzi w ustawieniach klienta

- Nowa kategoria w ustawieniach powiadomień: **„Zmiana daty zakończenia sprzedaży"**
- Domyślnie włączona dla nowych użytkowników
- **Migracja dla istniejących użytkowników:**
  - Włączona, jeśli użytkownik miał wszystkie inne kategorie włączone
  - Wyłączona, jeśli wyłączył którąkolwiek (selekcja = nie opt-inujemy)

## Trigger modala — szczegóły

Modal pokazuje się **tylko** gdy spełnione są wszystkie warunki:
1. Strona ma status `active`
2. Wartość `ends_at` różni się od wartości z momentu otwarcia edytora
3. Admin kliknął „Zapisz" (modal nie wyzwala się przez autozapis — autozapis jest wyłączony na stronach aktywnych)

Wszystkie warianty zmiany triggerują modal:
- Data → inna data (przedłużenie/skrócenie)
- `null` → data (ustawienie deadline'u)
- Data → `null` (usunięcie deadline'u)
- Data → data w przeszłości (natychmiastowe zakończenie — pokazuje dodatkowo czerwone ostrzeżenie)

## Architektura zmiany

### Frontend
- Nowy stan w `builderConfig`: `isPageActive`, `originalEndsAt` (renderowane z Jinja2)
- Modyfikacja `static/js/pages/admin/offer-builder.js`:
  - `autoSave()`: jeśli `isPageActive` → return (autosave wyłączony)
  - `savePage()`: hook przed wysłaniem zapisu — jeśli `isPageActive` i zmiana `ends_at` → otwórz modal, czekaj na decyzję, potem dopiero `fetch /save` z dodatkowymi flagami w payloadzie
- Modyfikacja `templates/admin/offers/edit.html`:
  - Banner „Strona aktywna — autosave wyłączony" (warunkowy)
  - HTML modala (zgodnie z konwencją `.modal-overlay` + `.modal-content`)
- Style w `static/css/components/modals.css` (light + dark mode)

### Backend
- `modules/admin/offers.py`:
  - Endpoint `offers_save` rozszerzony o opcjonalne pola payloadu: `notify_email_on_end_date_change`, `notify_push_on_end_date_change`
  - Zapamiętuje `old_ends_at = page.ends_at` przed nadpisaniem
  - Po `db.session.commit()`: jeśli flagi i faktycznie się zmieniła data → wywołuje dispatcher
  - Nowa funkcja `_resolve_end_date_change_recipients(page)` zwraca listę użytkowników (e-mail) i listę ID (push)
  - Nowa funkcja koordynująca `_dispatch_end_date_change_notifications(...)` (wywołuje EmailManager + PushManager z osłoną try/except per kanał, w tle)
- `utils/email_manager.py`: nowa metoda `notify_sale_end_date_changed(page, old_ends_at, new_ends_at, recipients)`
- `utils/push_manager.py`: nowa metoda `notify_sale_end_date_changed(page, new_ends_at, user_ids)`

### Modele i baza
- `modules/notifications/models.py`: nowa kolumna w `NotificationPreference`:
  - `sale_date_changes BOOLEAN NOT NULL DEFAULT TRUE`
  - Aktualizacja `to_dict()` o nowe pole
- Migracja Flask-Migrate:
  - `op.add_column(...)` dla nowej kolumny
  - Backfill dla istniejących wierszy: `TRUE` jeśli wszystkie inne `= TRUE`, inaczej `FALSE`

### Szablony e-mail
- `templates/emails/sale_end_date_changed.html`
- `templates/emails/sale_end_date_changed.txt`

### UI ustawień powiadomień
- Aktualizacja strony ustawień klienta (ścieżka istniejąca w projekcie):
  - Dodanie nowego toggle „Zmiana daty zakończenia sprzedaży"
  - Czytanie i zapis przez istniejący endpoint preferencji

## Przepływ danych (happy path)

1. Admin otwiera `/admin/offers/<id>/edit` → Jinja2 renderuje `isPageActive` i `originalEndsAt` w `builderConfig`.
2. JS przy starcie: gdy `isPageActive` — wyłącza interwał autozapisu, pokazuje banner.
3. Admin zmienia `<input id="endsAt">` i klika „Zapisz".
4. `savePage()`:
   - Jeśli `isPageActive && newEndsAt !== originalEndsAt` → otwiera modal i czeka na decyzję.
   - Inaczej: zwykły zapis bez modala.
5. Modal: stara→nowa data, opcjonalne ostrzeżenie, dwa checkboxy domyślnie zaznaczone.
6. Admin klika „Zapisz" w modalu → JS wysyła `POST /admin/offers/<id>/save` z payloadem zawierającym `notify_email_on_end_date_change` i `notify_push_on_end_date_change`.
7. Backend zapisuje wszystkie zmiany, commituje DB.
8. Po commicie: jeśli flagi włączone i `old_ends_at != new_ends_at` → uruchamia dispatcher w tle.
9. Dispatcher liczy odbiorców osobno dla e-mail (zamówienie ∪ marketing_consent) i push (kategoria `sale_date_changes` włączona), wywołuje wysyłki.
10. Backend zwraca `{success: true, notifications_sent: {email: N, push: M}}` → frontend toast + aktualizacja `originalEndsAt` na `newEndsAt`.

## Sytuacje brzegowe

| Sytuacja | Zachowanie |
|---|---|
| Zapis bez zmiany daty | Zwykły zapis, modal się nie pokazuje |
| Modal → Anuluj | Nic się nie zapisuje, data wraca do pierwotnej |
| Oba checkboxy odznaczone → Zapisz | Data się zapisuje, żadne powiadomienie nie idzie |
| Pusta lista odbiorców e-maila | Mail się nie wysyła, toast pokazuje 0 |
| Pusta lista odbiorców push | Push się nie wysyła, toast pokazuje 0 |
| Data w przeszłości | Modal pokazuje ostrzeżenie, status strony zmienia się na `ended` po zapisie, powiadomienie i tak leci |
| Data → `null` | Modal pokazuje „bez limitu czasowego", powiadomienie informuje o usunięciu deadline'u |
| Wysyłka mail się wyłoży | Push i tak idzie, błąd loguje się w serwerze |
| Wysyłka push się wyłoży | Mail i tak idzie, analogicznie |
| Zapis do bazy się wyłoży | Powiadomienia nie idą (wysyłka odpalana po commicie), admin widzi błąd |
| Strona nieaktywna | Autosave działa, modal nigdy się nie pokazuje |

## Plan testów ręcznych

### Edytor strony
- [ ] Strona `draft` / `scheduled` / `paused` → autozapis działa, banner się nie pokazuje
- [ ] Strona `active` → autozapis nie działa, banner widoczny
- [ ] Zmiana innego pola na stronie aktywnej → modal się nie pokazuje
- [ ] Zmiana daty na aktywnej → modal się pokazuje
- [ ] Modal w trybie jasnym i ciemnym
- [ ] Modal na mobile (mobile touch targets ≥ 44px, ostrzeżenie i checkboxy klikalne)

### Wysyłka — e-mail
- [ ] Klient z zamówieniem na tej stronie, bez zgody marketingowej → mail dochodzi
- [ ] Klient ze zgodą marketingową, bez zamówienia → mail dochodzi
- [ ] Klient bez zamówienia i bez zgody → mail nie dochodzi
- [ ] Klient z zamówieniem **i** zgodą → mail dochodzi raz (bez duplikatów)

### Wysyłka — push
- [ ] Klient z włączoną kategorią `sale_date_changes` → push dochodzi
- [ ] Klient z wyłączoną kategorią → push nie dochodzi
- [ ] Klient bez aktywnej subskrypcji push → pomijany bez błędu

### Migracja
- [ ] Po migracji: użytkownik miał wszystkie kategorie włączone → ma `sale_date_changes = TRUE`
- [ ] Użytkownik wyłączył jedną z istniejących → ma `sale_date_changes = FALSE`
- [ ] Nowi użytkownicy domyślnie mają `TRUE`

### Strona ustawień
- [ ] Nowy przełącznik widoczny w ustawieniach klienta
- [ ] Działa w trybie jasnym i ciemnym
- [ ] Zapis utrwala się w bazie

### Logi
- [ ] Po zapisie z włączonymi powiadomieniami: wpis „Wysłano powiadomienie zmiany daty: page=X, email=N, push=M"
- [ ] Błąd kanału (mail/push) ma osobny wpis z opisem
- [ ] Brak wpisu przy zapisie strony nieaktywnej

## Co NIE wchodzi w zakres

1. Powiadomienia o zmianie daty rozpoczęcia (`starts_at`).
2. Powiadomienia o innych zmianach na stronie aktywnej (cena, limity, sekcje).
3. Tabela historii wysyłek powiadomień (audyt) — tylko logi serwera.
4. Cofnięcie wysyłki / ponowna wysyłka — każda zmiana = nowa wysyłka.
5. Per-kanał wybór klienta (tylko e-mail / tylko push) — jedna kategoria w preferencjach obejmuje oba kanały.
6. Personalizacja treści e-maila per klient (np. „Twoje zamówienie #X") — generyczny szablon.
7. Framework testów automatycznych (`pytest` itp.) — testy ręczne.
8. Lista oczekujących zmian w bannerze — banner statyczny.
