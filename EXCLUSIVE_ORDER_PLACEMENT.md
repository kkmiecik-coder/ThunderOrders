# System Składania Zamówień - Exclusive Pages

## Przegląd

System składania zamówień przez exclusive pages został w pełni zaimplementowany i obsługuje:

✅ **Zalogowanych użytkowników** (admin, mod, client)
✅ **Gości** (bez konta)
✅ **Automatyczne zmniejszanie stanów magazynowych**
✅ **Usuwanie rezerwacji po złożeniu zamówienia**
✅ **Activity logging**
✅ **Modal sukcesu z numerem zamówienia**

---

## Flow Składania Zamówienia

### 1. Dla Zalogowanego Użytkownika

```
1. Użytkownik dodaje produkty do koszyka (rezerwacja)
2. Klikamy "Złóż zamówienie"
3. Modal potwierdzenia:
   - Wyświetla dane użytkownika (imię, email)
   - Pole "Notatka do zamówienia" (opcjonalnie)
   - Przycisk "Potwierdź zamówienie"
4. Po kliknięciu "Potwierdź":
   - Wysyłany jest request POST /exclusive/<token>/place-order
   - System tworzy zamówienie
   - Zmniejsza stany magazynowe
   - Usuwa rezerwacje
   - Loguje activity
5. Modal sukcesu:
   - Numer zamówienia (np. EX/00000001)
   - Kwota zamówienia
   - Przycisk "Przejdź do moich zamówień" → przekierowanie na dashboard
```

---

### 2. Dla Gościa (Bez Konta)

```
1. Gość dodaje produkty do koszyka (rezerwacja)
2. Klikamy "Złóż zamówienie"
3. Modal z formularzem:
   - Imię i nazwisko (required)
   - Email (required)
   - Telefon (required)
   - Pole "Notatka do zamówienia" (opcjonalnie)
   - Przycisk "Potwierdź zamówienie"
4. Po kliknięciu "Potwierdź":
   - Walidacja danych (email, telefon)
   - Wysyłany jest request POST /exclusive/<token>/place-order
   - System tworzy zamówienie jako guest order
   - Zmniejsza stany magazynowe
   - Usuwa rezerwacje
   - Loguje activity
5. Modal sukcesu:
   - Numer zamówienia
   - Kwota zamówienia
   - Komunikat o wysłaniu emaila potwierdzającego
   - Przycisk "OK" → odświeża stronę
```

---

## Backend Implementacja

### Plik: `modules/exclusive/place_order.py`

Główna logika składania zamówienia:

#### Funkcje:

1. **`validate_guest_data(guest_data)`**
   - Waliduje dane gościa (imię, email, telefon)
   - Zwraca `(valid: bool, error: str or None)`

2. **`check_product_availability(reservations, page_id)`**
   - Sprawdza czy produkty są dostępne w magazynie
   - Sprawdza limity sekcji (max_quantity)
   - Zwraca `(available: bool, error: dict or None)`

3. **`place_exclusive_order(page, session_id, guest_data, order_note)`**
   - Główna funkcja składania zamówienia
   - Proces:
     1. Cleanup wygasłych rezerwacji
     2. Pobranie rezerwacji użytkownika
     3. Walidacja danych (jeśli gość)
     4. Sprawdzenie dostępności produktów
     5. Generowanie numeru zamówienia (format: EX/00000001)
     6. Utworzenie zamówienia (Order)
     7. Utworzenie pozycji zamówienia (OrderItem)
     8. Zmniejszenie stanów magazynowych (product.quantity)
     9. Usunięcie rezerwacji
     10. Commit do bazy
     11. Activity log
     12. Email (TODO)

---

### Endpoint: `POST /exclusive/<token>/place-order`

**Plik:** `modules/exclusive/routes.py`

**Request Body:**
```json
{
  "session_id": "uuid-v4",
  "order_note": "Notatka (opcjonalnie)",
  "guest_data": {  // Tylko dla gości
    "name": "Jan Kowalski",
    "email": "jan@example.com",
    "phone": "+48 123 456 789"
  }
}
```

**Response (Success):**
```json
{
  "success": true,
  "order_id": 123,
  "order_number": "EX/00000001",
  "total_amount": 450.00,
  "items_count": 3
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "no_reservations",
  "message": "Brak produktów w rezerwacji"
}
```

**Możliwe Błędy:**
- `page_not_found` - Strona nie istnieje
- `page_not_active` - Sprzedaż nie jest aktywna
- `missing_session_id` - Brak session_id
- `no_reservations` - Brak rezerwacji (wygasła)
- `missing_guest_data` - Brak danych gościa
- `missing_field_name` / `missing_field_email` / `missing_field_phone` - Brak wymaganego pola
- `invalid_email` - Nieprawidłowy email
- `invalid_phone` - Nieprawidłowy telefon
- `insufficient_stock` - Brak wystarczającej ilości w magazynie
- `exceeds_section_limit` - Przekroczenie limitu sekcji
- `order_number_failed` - Błąd generowania numeru zamówienia
- `database_error` - Błąd bazy danych

---

## Frontend Implementacja

### Template: `templates/exclusive/order_page.html`

#### Modal Potwierdzenia (Zalogowany)
```html
<div id="orderModal" class="exclusive-modal-overlay">
  <!-- Wyświetla dane użytkownika -->
  <!-- Pole "Notatka do zamówienia" -->
  <!-- Przycisk "Potwierdź zamówienie" onclick="submitOrder()" -->
</div>
```

#### Modal Potwierdzenia (Gość)
```html
<div id="orderModal" class="exclusive-modal-overlay">
  <form id="guestForm">
    <!-- Pola: Imię, Email, Telefon -->
    <!-- Pole "Notatka do zamówienia" -->
    <!-- Przycisk "Potwierdź zamówienie" onclick="submitOrder()" -->
  </form>
</div>
```

#### Modal Sukcesu
```html
<div id="successModal" class="exclusive-modal-overlay">
  <!-- Ikona sukcesu (zielony checkmark z animacją pulse) -->
  <!-- Numer zamówienia -->
  <!-- Kwota -->
  <!-- Komunikat -->
  <!-- Przycisk "Przejdź do moich zamówień" (zalogowany) lub "OK" (gość) -->
</div>
```

---

### JavaScript: `submitOrder()`

**Proces:**

1. **Wyłącz przycisk** i pokaż "Wysyłanie..."
2. **Zbierz dane:**
   - `order_note` (opcjonalnie)
   - Jeśli gość: `guest_data` (name, email, phone)
3. **Walidacja** (jeśli gość):
   - Sprawdź czy wszystkie pola są wypełnione
4. **Wyślij request:**
   ```javascript
   fetch('/exclusive/<token>/place-order', {
     method: 'POST',
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({ session_id, order_note, guest_data })
   })
   ```
5. **Obsługa odpowiedzi:**
   - **Sukces:**
     - Zamknij modal potwierdzenia
     - Wyczyść localStorage (`exclusive_reservation_<token>`)
     - Stop timerów rezerwacji
     - Pokaż modal sukcesu
   - **Błąd:**
     - Wyświetl komunikat błędu (alert)
     - Jeśli `no_reservations` → reload strony po 2s

---

### CSS: `static/css/pages/exclusive/order-page.css`

**Dodane style:**

```css
.exclusive-modal-success { ... }
.exclusive-success-icon { ... }    /* Zielona ikona z animacją pulse */
.exclusive-success-info { ... }    /* Kafelek z danymi zamówienia */
.exclusive-success-row { ... }
.exclusive-success-label { ... }
.exclusive-success-value { ... }
.exclusive-success-message { ... }
.exclusive-success-note { ... }

@keyframes successPulse { ... }    /* Animacja pulsującej ikony */
```

---

## Baza Danych

### Tabela: `orders`

**Nowe zamówienie:**
```sql
INSERT INTO orders (
  order_number,       -- EX/00000001
  order_type,         -- 'exclusive'
  user_id,            -- NULL jeśli gość
  status,             -- 'nowe'
  is_exclusive,       -- TRUE
  exclusive_page_id,  -- ID strony exclusive
  is_guest_order,     -- TRUE jeśli gość
  guest_name,         -- "Jan Kowalski" (jeśli gość)
  guest_email,        -- "jan@example.com" (jeśli gość)
  guest_phone,        -- "+48 123 456 789" (jeśli gość)
  notes,              -- Notatka klienta
  total_amount,       -- 450.00
  created_at          -- NOW()
)
```

---

### Tabela: `order_items`

**Pozycje zamówienia:**
```sql
INSERT INTO order_items (
  order_id,
  product_id,
  quantity,
  price,     -- Cena w momencie zamówienia
  total,     -- price × quantity
  picked     -- FALSE (do WMS)
)
```

---

### Tabela: `products`

**Zmniejszenie stanu:**
```sql
UPDATE products
SET quantity = quantity - <zamówiona ilość>
WHERE id = <product_id>
```

---

### Tabela: `exclusive_reservations`

**Usunięcie rezerwacji:**
```sql
DELETE FROM exclusive_reservations
WHERE session_id = '<uuid>' AND exclusive_page_id = <page_id>
```

---

### Tabela: `activity_log`

**Log zamówienia:**
```sql
INSERT INTO activity_log (
  user_id,      -- NULL jeśli gość
  action,       -- 'order_created'
  entity_type,  -- 'order'
  entity_id,    -- order.id
  old_value,    -- NULL
  new_value,    -- JSON z danymi zamówienia
  created_at    -- NOW()
)
```

---

## Testowanie

### Test 1: Zalogowany Użytkownik (Client)

1. Zaloguj się jako klient
2. Przejdź na stronę exclusive (np. `/exclusive/<token>`)
3. Dodaj produkty do koszyka (rezerwacja)
4. Kliknij "Złóż zamówienie"
5. **Sprawdź modal:**
   - Czy wyświetla poprawne dane (imię, email)
   - Czy pole "Notatka" jest opcjonalne
6. Dodaj notatkę i kliknij "Potwierdź zamówienie"
7. **Sprawdź modal sukcesu:**
   - Czy wyświetla numer zamówienia (EX/00000001)
   - Czy wyświetla kwotę
   - Czy przycisk "Przejdź do moich zamówień" działa
8. **Sprawdź bazę danych:**
   - `SELECT * FROM orders WHERE order_number LIKE 'EX/%'`
   - Czy `is_exclusive = TRUE`
   - Czy `user_id` jest ustawiony
   - Czy `is_guest_order = FALSE`
9. **Sprawdź order_items:**
   - `SELECT * FROM order_items WHERE order_id = <order_id>`
   - Czy wszystkie produkty są zapisane
10. **Sprawdź stany magazynowe:**
    - `SELECT quantity FROM products WHERE id IN (...)`
    - Czy stany się zmniejszyły
11. **Sprawdź rezerwacje:**
    - `SELECT * FROM exclusive_reservations WHERE session_id = '<uuid>'`
    - Czy rezerwacje zostały usunięte
12. **Sprawdź activity log:**
    - `SELECT * FROM activity_log WHERE entity_type = 'order' AND entity_id = <order_id>`
    - Czy log został utworzony

---

### Test 2: Gość (Bez Konta)

1. Otwórz przeglądarkę incognito
2. Przejdź na stronę exclusive
3. Dodaj produkty do koszyka
4. Kliknij "Złóż zamówienie"
5. **Sprawdź modal:**
   - Czy wyświetla formularz (Imię, Email, Telefon)
   - Czy wszystkie pola są wymagane
6. Wypełnij formularz:
   - Imię: "Jan Kowalski"
   - Email: "test.guest@example.com"
   - Telefon: "+48 123 456 789"
7. Kliknij "Potwierdź zamówienie"
8. **Sprawdź modal sukcesu:**
   - Czy wyświetla numer zamówienia
   - Czy wyświetla komunikat o emailu
   - Czy przycisk "OK" odświeża stronę
9. **Sprawdź bazę danych:**
   - `SELECT * FROM orders WHERE guest_email = 'test.guest@example.com'`
   - Czy `is_guest_order = TRUE`
   - Czy `user_id = NULL`
   - Czy `guest_name`, `guest_email`, `guest_phone` są zapisane

---

### Test 3: Walidacja i Błędy

#### 3.1 Brak produktów w rezerwacji
- Usuń rezerwacje manualnie z bazy
- Spróbuj złożyć zamówienie
- **Oczekiwany błąd:** "Brak produktów w rezerwacji. Rezerwacja mogła wygasnąć."

#### 3.2 Nieprawidłowy email (gość)
- Wpisz email bez "@"
- Spróbuj złożyć zamówienie
- **Oczekiwany błąd:** "Nieprawidłowe dane użytkownika"

#### 3.3 Nieprawidłowy telefon (gość)
- Wpisz telefon z literami
- Spróbuj złożyć zamówienie
- **Oczekiwany błąd:** "Nieprawidłowe dane użytkownika"

#### 3.4 Brak wystarczającej ilości w magazynie
- Zmniejsz `product.quantity` do 0
- Spróbuj złożyć zamówienie na ten produkt
- **Oczekiwany błąd:** "Produkt '<nazwa>' nie ma wystarczającej ilości w magazynie."

#### 3.5 Strona nieaktywna
- Zmień status strony exclusive na 'paused' lub 'ended'
- Spróbuj złożyć zamówienie
- **Oczekiwany błąd:** "Sprzedaż nie jest już aktywna."

---

## TODO: Email Notifications

**Obecnie email nie są wysyłane (TODO w kodzie).**

### Planowane emaile:

1. **Order Confirmation (dla klienta/gościa)**
   - Template: `order_confirmation`
   - Subject: "Potwierdzenie zamówienia {order_number}"
   - Content:
     - Numer zamówienia
     - Lista produktów
     - Kwota
     - Informacje o statusie
     - Link do śledzenia (jeśli zalogowany)

2. **New Order Notification (dla admina)**
   - Template: `new_order`
   - Subject: "Nowe zamówienie {order_number}"
   - Content:
     - Numer zamówienia
     - Klient (imię + email)
     - Lista produktów
     - Kwota
     - Link do zamówienia w panelu admin

### Implementacja (do wykonania):

```python
# W modules/exclusive/place_order.py (linia ~204):

# 12. Send emails (async)
from utils.email_sender import send_email

# Email do klienta
customer_email = order.guest_email if is_guest else order.user.email
send_email(
    to=customer_email,
    template_type='order_confirmation',
    context={
        'order': order,
        'customer_name': order.customer_name,
        'order_number': order.order_number,
        'total_amount': order.total_amount,
        'items': order.items
    }
)

# Email do admina (jeśli włączone w settings)
from modules.settings.models import Settings
if Settings.get_value('notify_admin_new_order', True):
    admin_email = Settings.get_value('admin_email', 'karolinaburza@gmail.com')
    send_email(
        to=admin_email,
        template_type='new_order',
        context={
            'order': order,
            'customer_name': order.customer_name,
            'order_number': order.order_number,
            'total_amount': order.total_amount,
            'items': order.items
        }
    )
```

---

## Podsumowanie

✅ **Backend:** Pełna logika składania zamówienia
✅ **Frontend:** Modal potwierdzenia + modal sukcesu
✅ **Walidacja:** Dane gościa, dostępność produktów
✅ **Bezpieczeństwo:** Sprawdzanie statusu strony, rate limiting
✅ **UX:** Loading states, error handling, animacje
✅ **Baza danych:** Transakcje, activity logging

⏳ **Do zrobienia:** Email notifications

---

## Kontakt

W razie pytań lub problemów:
- Sprawdź logi: `sudo journalctl -u thunderorders -n 100`
- Sprawdź baza danych: phpMyAdmin lub CLI
- Sprawdź console przeglądarki (F12 → Console)

**Powodzenia! 🚀**
