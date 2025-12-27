# Google Analytics 4 - Checklist Wdrożenia

## 📋 Checklist dla środowiska PRODUCTION (VPS)

### 1. ✅ Uzyskaj Measurement ID z Google Analytics

- [ ] Zaloguj się na https://analytics.google.com/
- [ ] Utwórz nowe konto Analytics (lub użyj istniejącego)
- [ ] Dodaj nową "właściwość" dla ThunderOrders
- [ ] Wybierz "Web" jako platformę
- [ ] Podaj URL: `https://thunderorders.cloud`
- [ ] Skopiuj **Measurement ID** (format: `G-XXXXXXXXXX`)

---

### 2. ✅ Dodaj Measurement ID do pliku `.env` na serwerze VPS

**Na Macu (lokalny terminal):**

```bash
# Połącz się SSH
ssh konrad@191.96.53.209

# Edytuj plik .env
cd /var/www/ThunderOrders
nano .env
```

**Dodaj/edytuj linię:**

```env
# Google Analytics 4 (GA4)
GA_MEASUREMENT_ID=G-TWOJE-PRAWDZIWE-ID
```

**Zapisz:** `Ctrl + X` → `Y` → `Enter`

---

### 3. ✅ Restartuj aplikację na serwerze

```bash
# Restart Gunicorn
sudo systemctl restart thunderorders

# Sprawdź status
sudo systemctl status thunderorders

# Sprawdź logi (czy brak błędów)
sudo journalctl -u thunderorders -n 50 --no-pager
```

---

### 4. ✅ Sprawdź czy GA4 działa

**W przeglądarce:**

1. Otwórz https://thunderorders.cloud
2. Otwórz DevTools (F12) → Console
3. Sprawdź czy `window.gtag` istnieje:
   ```javascript
   console.log(typeof window.gtag); // Powinno być: "function"
   ```
4. Sprawdź czy helper functions są załadowane:
   ```javascript
   console.log(typeof window.trackOrderPlaced); // Powinno być: "function"
   ```

**W Google Analytics:**

1. Wejdź na https://analytics.google.com/
2. Wybierz swoją właściwość (ThunderOrders)
3. Przejdź do: **Reports → Realtime**
4. Powinieneś zobaczyć siebie jako aktywnego użytkownika (w ciągu 30 sekund)
5. Sprawdź czy strona jest trackowana

---

### 5. ✅ Testuj custom events (opcjonalnie)

**Test w konsoli przeglądarki:**

```javascript
// Test trackowania zamówienia (tylko w konsoli, NIE w kodzie!)
if (typeof window.trackOrderPlaced === 'function') {
    window.trackOrderPlaced('TEST/00000001', 100.00, 1, 'standard');
    console.log('✅ Test event sent!');
}
```

**Sprawdź w GA4:**
- Reports → Realtime → Event count by Event name
- Powinieneś zobaczyć event "purchase" za ~10-30 sekund

**WAŻNE:** Usuń testowy event z konsoli po teście!

---

### 6. ✅ Weryfikuj dane przez kilka dni

- [ ] **Day 1:** Sprawdź Realtime - czy są aktywni użytkownicy
- [ ] **Day 2:** Sprawdź Reports → Engagement → Events - czy eventy są zbierane
- [ ] **Day 7:** Sprawdź Reports → Acquisition - skąd przychodzą użytkownicy
- [ ] **Day 30:** Sprawdź Reports → Monetization → Ecommerce purchases - dane o zamówieniach

---

## 🔧 Troubleshooting

### Problem: GA4 nie zbiera danych

**Sprawdź:**

1. Measurement ID w `.env`:
   ```bash
   cat /var/www/ThunderOrders/.env | grep GA_MEASUREMENT_ID
   ```
   Powinno być: `GA_MEASUREMENT_ID=G-XXXXXXXXXX` (bez spacji!)

2. Restart aplikacji:
   ```bash
   sudo systemctl restart thunderorders
   ```

3. Logi błędów:
   ```bash
   sudo journalctl -u thunderorders -n 100 | grep -i "error"
   ```

4. Nginx logi:
   ```bash
   sudo tail -50 /var/log/nginx/error.log
   ```

---

### Problem: Custom eventy nie są widoczne w GA4

**Rozwiązanie:**

1. Poczekaj 24-48h - GA4 potrzebuje czasu na przetworzenie
2. Sprawdź czy funkcje są dostępne (DevTools Console):
   ```javascript
   console.log(typeof window.trackEvent);
   ```
3. Sprawdź Reports → Engagement → Events (nie Realtime)

---

### Problem: Localhost też wysyła dane do GA4

**To normalne!** Jeśli `GA_MEASUREMENT_ID` jest ustawione, GA4 będzie zbierać dane nawet z localhost.

**Rozwiązanie:**

- W pliku `.env` (development/localhost): Zostaw `GA_MEASUREMENT_ID` **puste**
- W pliku `.env` (production/VPS): Ustaw **prawdziwe** Measurement ID

---

## 📊 Co dalej?

### Zaawansowana konfiguracja (opcjonalnie)

1. **Konwersje:**
   - Wejdź: Configure → Events
   - Oznacz event `purchase` jako "Conversion"
   - Będziesz mógł śledzić przychód i ROI

2. **E-commerce Enhanced:**
   - Configure → Data streams → Enhanced measurement
   - Włącz "Ecommerce events"
   - Szczegółowe dane o produktach, koszach, checkout

3. **Custom dimensions:**
   - Configure → Custom definitions
   - Dodaj custom dimensions (np. `user_role`, `order_type`)

4. **Audiences:**
   - Configure → Audiences
   - Stwórz segmenty użytkowników (np. "Klienci VIP", "Częste zamówienia")

5. **Integration z Google Ads:**
   - Admin → Google Ads Links
   - Połącz z kontem Google Ads (jeśli masz)
   - Remarketing, conversion tracking

---

## 🎯 Kluczowe metryki do śledzenia

**Engagement:**
- Active users (dzienny/tygodniowy/miesięczny)
- Sessions per user
- Average engagement time
- Bounce rate

**Acquisition:**
- User acquisition (skąd przychodzą nowi użytkownicy)
- Traffic source/medium (organic, direct, referral, social)
- Landing pages

**Conversions:**
- Purchase event count (liczba zamówień)
- Total revenue (przychód)
- Average order value (AOV)
- Conversion rate (% odwiedzających → zamówienia)

**E-commerce:**
- Top selling products
- Cart abandonment rate (opcjonalnie, wymaga custom tracking)
- Time to purchase

---

## 📚 Przydatne linki

- **GA4 Home:** https://analytics.google.com/
- **GA4 Help Center:** https://support.google.com/analytics/
- **Event Reference:** https://developers.google.com/analytics/devguides/collection/ga4/events
- **gtag.js Reference:** https://developers.google.com/tag-platform/gtagjs/reference

---

**Data ostatniej aktualizacji:** 2025-12-28
