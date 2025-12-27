# Google Analytics 4 (GA4) - Dokumentacja

## 📊 Konfiguracja

### 1. Uzyskaj Measurement ID z Google Analytics

1. Wejdź na: https://analytics.google.com/
2. Zaloguj się swoim kontem Google
3. Utwórz nowe konto Analytics (lub użyj istniejącego)
4. Dodaj nową "właściwość" (property) dla ThunderOrders
5. Wybierz **"Web"** jako platformę
6. Podaj URL: `https://thunderorders.cloud`
7. Skopiuj **Measurement ID** (format: `G-XXXXXXXXXX`)

### 2. Dodaj Measurement ID do pliku `.env`

Otwórz plik `.env` w głównym katalogu projektu i dodaj:

```env
# Google Analytics 4 (GA4)
GA_MEASUREMENT_ID=G-TWOJE-ID-TUTAJ
```

**Przykład:**
```env
GA_MEASUREMENT_ID=G-1234567890
```

### 3. Zrestartuj aplikację Flask

```bash
# Jeśli używasz flask run
flask run

# Jeśli używasz systemd (VPS)
sudo systemctl restart thunderorders
```

### 4. Sprawdź czy działa

1. Otwórz aplikację w przeglądarce
2. Otwórz DevTools (F12) → Console
3. Powinieneś zobaczyć że gtag jest załadowane
4. W Google Analytics → Realtime → Powinieneś zobaczyć aktywnego użytkownika (Ty)

---

## 🎯 Podstawowe trackowanie

### Automatyczne trackowanie (włączone domyślnie)

Google Analytics 4 automatycznie śledzi:

- ✅ **Wyświetlenia stron (pageviews)** - każda zmiana URL
- ✅ **Scrolling** - jak głęboko użytkownicy scrollują strony
- ✅ **Kliknięcia w zewnętrzne linki** (outbound clicks)
- ✅ **Wyszukiwania w witrynie** (jeśli używasz parametru `?q=`)
- ✅ **Pobierania plików** (file downloads)
- ✅ **Odtwarzanie video** (jeśli używasz YouTube iframes)

### Dane demograficzne i zainteresowania

GA4 automatycznie zbiera (jeśli użytkownik wyraził zgodę):
- Wiek i płeć (szacunkowe, na podstawie zachowań)
- Zainteresowania
- Lokalizacja (kraj, miasto)
- Urządzenie (desktop, mobile, tablet)
- Przeglądarka i system operacyjny

---

## 🚀 Custom Event Tracking

ThunderOrders zawiera pomocnicze funkcje do trackowania ważnych akcji użytkowników.

### Dostępne funkcje

#### 1. `trackOrderPlaced()` - Złożenie zamówienia

```javascript
trackOrderPlaced(orderNumber, totalAmount, itemsCount, orderType);
```

**Przykład:**
```javascript
// Po złożeniu zamówienia standardowego
trackOrderPlaced('ST/00000123', 450.00, 3, 'standard');

// Po złożeniu zamówienia exclusive
trackOrderPlaced('EX/00000045', 320.00, 2, 'exclusive');
```

**Parametry:**
- `orderNumber` (string) - Numer zamówienia
- `totalAmount` (number) - Łączna kwota w PLN
- `itemsCount` (number) - Liczba produktów
- `orderType` (string) - `'standard'` lub `'exclusive'`

---

#### 2. `trackUserRegistered()` - Rejestracja użytkownika

```javascript
trackUserRegistered(method);
```

**Przykład:**
```javascript
// Po rejestracji emailem
trackUserRegistered('email');
```

**Parametry:**
- `method` (string) - Metoda rejestracji (domyślnie: `'email'`)

---

#### 3. `trackUserLogin()` - Logowanie użytkownika

```javascript
trackUserLogin(method);
```

**Przykład:**
```javascript
// Po zalogowaniu
trackUserLogin('email');
```

**Parametry:**
- `method` (string) - Metoda logowania (domyślnie: `'email'`)

---

#### 4. `trackAddToCart()` - Dodanie produktu do koszyka

```javascript
trackAddToCart(productName, productSku, price, quantity);
```

**Przykład:**
```javascript
// Po kliknięciu "Dodaj do zamówienia"
trackAddToCart('Pluszak BT21 Cooky', 'BT21-COOKY-001', 45.00, 1);
```

**Parametry:**
- `productName` (string) - Nazwa produktu
- `productSku` (string) - SKU produktu
- `price` (number) - Cena jednostkowa w PLN
- `quantity` (number) - Ilość (domyślnie: 1)

---

#### 5. `trackFormSubmit()` - Wysłanie formularza

```javascript
trackFormSubmit(formName);
```

**Przykład:**
```javascript
// Po wysłaniu formularza kontaktowego
trackFormSubmit('contact_form');

// Po wysłaniu zlecenia wysyłki
trackFormSubmit('shipping_request');
```

**Parametry:**
- `formName` (string) - Nazwa formularza

---

#### 6. `trackButtonClick()` - Kliknięcie w ważny przycisk

```javascript
trackButtonClick(buttonName, location);
```

**Przykład:**
```javascript
// Kliknięcie w "Nowe zamówienie" w sidebar
trackButtonClick('new_order', 'sidebar');

// Kliknięcie w "Zapisz szablon"
trackButtonClick('save_template', 'order_form');
```

**Parametry:**
- `buttonName` (string) - Nazwa przycisku
- `location` (string) - Lokalizacja przycisku (domyślnie: `'unknown'`)

---

#### 7. `trackExclusivePageView()` - Wyświetlenie strony Exclusive

```javascript
trackExclusivePageView(exclusiveToken, exclusiveName);
```

**Przykład:**
```javascript
// Po załadowaniu strony exclusive
trackExclusivePageView('abc123xyz', 'Promocja Wielkanocna 2025');
```

**Parametry:**
- `exclusiveToken` (string) - Token strony exclusive
- `exclusiveName` (string) - Nazwa strony exclusive

---

#### 8. `trackGuestOrderPlaced()` - Zamówienie przez gościa

```javascript
trackGuestOrderPlaced(orderNumber, totalAmount);
```

**Przykład:**
```javascript
// Po złożeniu zamówienia przez gościa (bez rejestracji)
trackGuestOrderPlaced('EX/00000046', 280.00);
```

**Parametry:**
- `orderNumber` (string) - Numer zamówienia
- `totalAmount` (number) - Łączna kwota w PLN

---

#### 9. `trackShippingRequested()` - Zlecenie wysyłki

```javascript
trackShippingRequested(ordersCount);
```

**Przykład:**
```javascript
// Po zleceniu wysyłki 3 zamówień
trackShippingRequested(3);
```

**Parametry:**
- `ordersCount` (number) - Liczba zamówień do wysłania

---

#### 10. `trackSearch()` - Wyszukiwanie

```javascript
trackSearch(searchTerm);
```

**Przykład:**
```javascript
// Po wyszukaniu w global search
trackSearch('BT21 Cooky');
```

**Parametry:**
- `searchTerm` (string) - Wyszukiwana fraza

---

#### 11. `trackEvent()` - Ogólne custom event

```javascript
trackEvent(eventName, eventParams);
```

**Przykład:**
```javascript
// Dowolny custom event
trackEvent('custom_action', {
    category: 'engagement',
    label: 'video_play',
    value: 1
});
```

**Parametry:**
- `eventName` (string) - Nazwa eventu
- `eventParams` (object) - Parametry eventu (opcjonalnie)

---

## 📝 Przykłady implementacji

### Przykład 1: Track w formularzu zamówienia (client)

```javascript
// W pliku: static/js/pages/client/new-order.js

// Po kliknięciu "Dodaj produkt"
document.querySelectorAll('.btn-add-product').forEach(btn => {
    btn.addEventListener('click', function() {
        const productName = this.dataset.productName;
        const productSku = this.dataset.productSku;
        const price = parseFloat(this.dataset.price);

        // Track dodania do koszyka
        trackAddToCart(productName, productSku, price, 1);

        // Twój normalny kod dodawania do koszyka...
    });
});

// Po złożeniu zamówienia
document.getElementById('submit-order-btn').addEventListener('click', function() {
    // Po sukcesie złożenia zamówienia (w callback po AJAX)
    // Załóżmy że masz dane z response:
    const orderNumber = response.order_number; // np. 'ST/00000123'
    const totalAmount = response.total_amount; // np. 450.00
    const itemsCount = response.items_count;   // np. 3

    // Track złożenia zamówienia
    trackOrderPlaced(orderNumber, totalAmount, itemsCount, 'standard');
});
```

---

### Przykład 2: Track rejestracji użytkownika

```javascript
// W pliku: static/js/pages/auth/register.js

// Po submit formularza rejestracji (i sukcesie)
document.getElementById('register-form').addEventListener('submit', function(e) {
    // Po otrzymaniu sukcesu z serwera (AJAX callback)
    if (response.success) {
        // Track rejestracji
        trackUserRegistered('email');

        // Redirect lub pokaż komunikat...
    }
});
```

---

### Przykład 3: Track w stronie Exclusive (guest order)

```javascript
// W pliku: static/js/pages/exclusive/order-page.js

// Po złożeniu zamówienia przez gościa
document.getElementById('guest-order-form').addEventListener('submit', function(e) {
    // Po sukcesie (AJAX callback)
    if (response.success) {
        const orderNumber = response.order_number;
        const totalAmount = response.total_amount;

        // Track zamówienia gościa
        trackGuestOrderPlaced(orderNumber, totalAmount);
    }
});
```

---

## 📊 Raporty w Google Analytics

### Gdzie znaleźć dane?

1. **Realtime** - Na żywo (ostatnie 30 minut)
   - `Reports → Realtime`
   - Zobacz aktywnych użytkowników, strony, eventy

2. **Events** - Wszystkie eventy
   - `Reports → Engagement → Events`
   - Lista wszystkich custom events (purchase, sign_up, login, itp.)

3. **Conversions** - Konwersje (zamówienia)
   - `Reports → Engagement → Conversions`
   - Oznacz event `purchase` jako konwersję
   - Zobacz przychód, liczba transakcji, średnia wartość zamówienia

4. **E-commerce** - Szczegółowe dane sprzedaży
   - `Reports → Monetization → Ecommerce purchases`
   - Produkty, przychód, AOV (Average Order Value)

5. **User acquisition** - Skąd przychodzą użytkownicy
   - `Reports → Acquisition → User acquisition`
   - Google, bezpośrednio, social media, itp.

---

## 🔒 RODO / Privacy Compliance

Google Analytics 4 w ThunderOrders jest skonfigurowany zgodnie z RODO:

- ✅ **Anonimizacja IP** - `anonymize_ip: true`
- ✅ **Conditional loading** - GA4 ładuje się tylko jeśli ustawiony `GA_MEASUREMENT_ID`
- ✅ **Cookies SameSite=None;Secure** - Bezpieczne cookies

### Cookie consent (opcjonalnie, do przyszłości)

Jeśli chcesz dodać cookie consent banner, możesz użyć:
- **CookieYes** (https://www.cookieyes.com/)
- **Cookiebot** (https://www.cookiebot.com/)
- **Custom solution** (prosty banner z localStorage)

---

## 🐛 Troubleshooting

### GA4 nie zbiera danych

1. **Sprawdź czy Measurement ID jest ustawione:**
   ```bash
   cat .env | grep GA_MEASUREMENT_ID
   ```

2. **Sprawdź w przeglądarce (DevTools → Console):**
   ```javascript
   console.log(window.gtag); // Powinno być: function
   ```

3. **Sprawdź w GA4 Realtime:**
   - Otwórz stronę
   - Wejdź na GA4 → Reports → Realtime
   - Powinieneś zobaczyć siebie w aktywnych użytkownikach

4. **Sprawdź czy skrypt się załadował (DevTools → Network):**
   - Znajdź request do `https://www.googletagmanager.com/gtag/js?id=G-...`
   - Powinien być status 200

### Custom eventy nie są widoczne

- Poczekaj 24-48h - GA4 może potrzebować czasu na przetworzenie
- Sprawdź `Reports → Engagement → Events`
- Sprawdź czy funkcja `trackEvent()` jest dostępna:
  ```javascript
  console.log(typeof window.trackEvent); // Powinno być: "function"
  ```

### Localhost zbiera dane

To normalne - jeśli `GA_MEASUREMENT_ID` jest ustawione, GA4 będzie zbierać dane nawet z localhost.

**Rozwiązanie:**
- W pliku `.env` (development) zostaw `GA_MEASUREMENT_ID` puste
- W pliku `.env` (production VPS) ustaw prawdziwe ID

---

## 📚 Więcej informacji

- **GA4 Documentation:** https://support.google.com/analytics/
- **GA4 Event Reference:** https://developers.google.com/analytics/devguides/collection/ga4/events
- **gtag.js Reference:** https://developers.google.com/tag-platform/gtagjs/reference

---

**Pytania?** Skontaktuj się z administratorem lub sprawdź oficjalną dokumentację Google Analytics 4.
