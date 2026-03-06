# ThunderOrders - Product Requirements Document (PRD)

**Version:** 1.0
**Date:** 31 października 2025
**Author:** Konrad
**Status:** Draft - Ready for Implementation

---

## ⚠️ WAŻNE UWAGI DLA CLAUDE

### 🤔 KRYTYCZNE: Podejmowanie Decyzji - Zawsze Pytaj Użytkownika

**ZASADA:** Gdy istnieje **więcej niż jedno rozwiązanie** danego problemu, ZAWSZE przedstaw wszystkie opcje użytkownikowi i pozwól mu wybrać. Zawsze odpisuje uytkownikowi w języku polskim. Wszystkie informacje

**Dlaczego?**
- Użytkownik (Konrad) zna najlepiej swoje potrzeby i preferencje
- Pozwala uniknąć marnowania czasu na implementację niewłaściwego rozwiązania
- Daje użytkownikowi kontrolę nad kierunkiem rozwoju aplikacji

**Workflow podejmowania decyzji:**
1. **Zidentyfikuj opcje** - gdy widzisz >1 rozwiązanie
2. **Wyjaśnij każdą opcję** - przedstaw:
   - Co obejmuje to rozwiązanie
   - Jakie są zalety i wady
   - Jak wpłynie na kod/UX/wydajność
3. **Zapytaj użytkownika** - "Którą opcję preferujesz?" lub "Jak chcesz to rozwiązać?"
4. **Poczekaj na odpowiedź** - NIE implementuj niczego przed odpowiedzią
5. **Implementuj wybraną opcję**

**Przykład:**
```
User: "po dodaniu metody, strona się przeładowuje i wracam do pierwszej zakładki"

DOBRZE ✅:
"Widzę dwa podejścia:

Opcja 1: Redirect z parametrem ?tab=payment-methods
- Prosta implementacja
- Pełne przeładowanie strony
- Utrata stanu formularzy

Opcja 2: AJAX submission bez przeładowania
- Płynniejsze UX
- Pozostajesz na tej samej zakładce
- Wymaga więcej kodu (JS + backend JSON)

Którą opcję preferujesz?"

ŹLE ❌:
*od razu implementuje AJAX bez pytania*
```

**NIE RÓB:**
- Nie zakładaj co użytkownik chce
- Nie implementuj "domyślnej" opcji bez konsultacji
- Nie mów "zrobię X, chyba że wolisz Y" - to nadal wymuszanie wyboru

**ZAWSZE pytaj i czekaj na odpowiedź gdy jest >1 rozwiązanie.**

---

### 🗄️ KRYTYCZNE: Zmiany w Bazie Danych

**ZASADA:** KAŻDA zmiana w strukturze bazy danych (nowa tabela, nowa kolumna, zmiana typu, indeksy, klucze) MUSI być wykonana przez **plik migracyjny Flask-Migrate**, a NIE bezpośrednio w kodzie modeli.

**Dlaczego?**
- Lokalna baza (XAMPP) i produkcyjna (VPS) muszą być zsynchronizowane
- Bez migracji zmiany nie zostaną zastosowane na serwerze produkcyjnym
- Powoduje to błędy typu "Field 'id' doesn't have a default value"

**Workflow zmian w bazie:**
1. Zmień model w kodzie (np. `models.py`)
2. Wygeneruj migrację: `flask db migrate -m "Opis zmiany"`
3. Sprawdź wygenerowany plik w `migrations/versions/`
4. Zastosuj lokalnie: `flask db upgrade`
5. Commit migrację razem z kodem
6. Na serwerze: `flask db upgrade`

**NIE RÓB:**
- Nie dodawaj kolumn tylko w modelu bez migracji
- Nie zmieniaj struktury bazy ręcznie przez phpMyAdmin/MySQL bez migracji

---

### 🎨 KRYTYCZNE: Style CSS - Light i Dark Mode

**ZASADA:** KAŻDA zmiana lub dodanie nowych stylów CSS MUSI uwzględniać zarówno **tryb jasny (light mode)** jak i **tryb ciemny (dark mode)**.

**Dlaczego?**
- Aplikacja obsługuje przełączanie między trybami jasnym i ciemnym
- Użytkownicy oczekują spójnego wyglądu w obu trybach
- Brak stylów dark mode powoduje nieczytelne elementy lub brzydki wygląd

**Workflow dodawania stylów:**
1. Dodaj style dla trybu jasnego (domyślne style)
2. Dodaj odpowiednie style dla trybu ciemnego używając selektora `[data-theme="dark"]`
3. Upewnij się, że kolory, tła, obramowania i cienie są czytelne w obu trybach

**Przykład:**
```css
/* Light mode (domyślne) */
.my-component {
    background: #ffffff;
    border: 1px solid #e0e0e0;
    color: #333333;
}

/* Dark mode */
[data-theme="dark"] .my-component {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(240, 147, 251, 0.15);
    color: #ffffff;
}
```

**Paleta Dark Mode (Glassmorphism):**
- Tła: `rgba(255, 255, 255, 0.05)` do `rgba(255, 255, 255, 0.1)`
- Obramowania: `rgba(240, 147, 251, 0.15)` do `rgba(240, 147, 251, 0.3)`
- Akcenty: `#f093fb` (różowy), `#f5576c` (czerwony/różowy)
- Tekst główny: `#ffffff`
- Tekst drugorzędny: `rgba(255, 255, 255, 0.6)` do `rgba(255, 255, 255, 0.8)`
- Backdrop blur: `blur(10px)` do `blur(20px)`

**NIE RÓB:**
- Nie dodawaj stylów tylko dla light mode bez odpowiedników dark mode
- Nie używaj sztywnych kolorów bez wariantów dla dark mode

---

### 📦 KRYTYCZNE: Style Modali - Centralizacja w modals.css

**ZASADA:** WSZYSTKIE style modali MUSZĄ być umieszczone w pliku `static/css/components/modals.css`. NIE dodawaj stylów modali w innych plikach CSS.

**Dlaczego?**
- Jeden plik = jedna prawda dla wyglądu modali
- Łatwiejsze utrzymanie i debugowanie
- Spójny wygląd wszystkich modali w aplikacji
- Unikamy konfliktów CSS między różnymi plikami

**Wzorce modali w aplikacji:**

1. **Modal Overlay (flex centered)** - używany w większości przypadków:
   ```html
   <div id="my-modal" class="modal-overlay">
       <div class="modal-content">
           <div class="modal-header">...</div>
           <div class="modal-body">...</div>
           <div class="modal-footer">...</div>
       </div>
   </div>
   ```
   - Otwieranie: `modal.classList.add('active')`
   - Zamykanie: `modal.classList.remove('active')`

2. **Modal Centered (legacy)** - dla starszych modali:
   ```html
   <div id="my-modal" class="modal-centered">...</div>
   ```
   - Otwieranie: `modal.classList.add('show')`
   - Zamykanie: `modal.classList.remove('show')`

**Workflow dodawania nowego modala:**
1. Użyj wzorca `modal-overlay` + `modal-content`
2. Style dodaj TYLKO do `static/css/components/modals.css`
3. Pamiętaj o stylach dla dark mode w tym samym pliku
4. Użyj istniejących klas (`.modal-header`, `.modal-body`, `.modal-footer`)

**NIE RÓB:**
- Nie dodawaj stylów modali w plikach stron (np. `products-list.css`)
- Nie twórz nowych plików CSS dla modali
- Nie używaj inline styles dla modali

---

### 🚫 KRYTYCZNE: Separacja CSS i JS od HTML

**ZASADA:** Unikamy jak tylko można umieszczania CSS i JavaScript bezpośrednio w plikach HTML. Kod powinien być w dedykowanych plikach `.css` i `.js`.

**Dlaczego?**
- Łatwiejsze utrzymanie i debugowanie kodu
- Możliwość cache'owania plików statycznych przez przeglądarkę
- Lepsza organizacja kodu i czytelność
- Unikamy duplikacji kodu

**Struktura plików:**
- **CSS:** `static/css/` (komponenty w `components/`, strony w `pages/`)
- **JavaScript:** `static/js/` (komponenty w `components/`, strony w `pages/`)

**Dozwolone wyjątki:**
- Krótkie inicjalizacje zależne od danych Jinja2 (np. `data-*` attributes)
- Style inline dla dynamicznie generowanych wartości (np. `style="width: {{ progress }}%"`)
- Bardzo małe, jednorazowe skrypty specyficzne dla jednej strony (ale preferuj osobny plik)

**Przykład - ZŁE:**
```html
<style>
.my-component { background: red; }
</style>
<script>
function doSomething() { ... }
</script>
```

**Przykład - DOBRE:**
```html
<!-- W sekcji head -->
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/my-page.css') }}">

<!-- Na końcu body -->
<script src="{{ url_for('static', filename='js/pages/my-page.js') }}"></script>
```

**NIE RÓB:**
- Nie umieszczaj bloków `<style>` w plikach HTML
- Nie umieszczaj dużych bloków `<script>` w plikach HTML
- Nie używaj inline styles (`style="..."`) gdy można użyć klasy CSS

---

### 📊 Google Analytics 4 (GA4) - Tracking

**ZASADA:** Google Analytics 4 jest zintegrowane z aplikacją przez plik `.env`. Measurement ID jest ładowane warunkowo - działa tylko gdy jest ustawione w zmiennej środowiskowej.

**Konfiguracja:**
1. **Measurement ID** jest przechowywane w pliku `.env`:
   ```env
   GA_MEASUREMENT_ID=G-XXXXXXXXXX
   ```
2. **Skrypt GA4** ładuje się automatycznie w `templates/base.html` jeśli `config.GA_MEASUREMENT_ID` jest ustawione
3. **Helper functions** do trackowania custom events są dostępne w `static/js/utils/analytics.js`

**Automatyczne trackowanie (bez dodatkowego kodu):**
- ✅ Wyświetlenia stron (pageviews)
- ✅ Scrolling
- ✅ Kliknięcia w zewnętrzne linki
- ✅ Pobierania plików

**Custom event tracking - dostępne funkcje:**

```javascript
// Złożenie zamówienia
trackOrderPlaced(orderNumber, totalAmount, itemsCount, orderType);

// Rejestracja użytkownika
trackUserRegistered(method);

// Logowanie użytkownika
trackUserLogin(method);

// Dodanie produktu do koszyka
trackAddToCart(productName, productSku, price, quantity);

// Wysłanie formularza
trackFormSubmit(formName);

// Kliknięcie w przycisk
trackButtonClick(buttonName, location);

// Wyświetlenie strony Exclusive
trackExclusivePageView(exclusiveToken, exclusiveName);

// Zamówienie przez gościa
trackGuestOrderPlaced(orderNumber, totalAmount);

// Zlecenie wysyłki
trackShippingRequested(ordersCount);

// Wyszukiwanie
trackSearch(searchTerm);

// Ogólny custom event
trackEvent(eventName, eventParams);
```

**Przykład użycia:**

```javascript
// W pliku: static/js/pages/client/new-order.js

// Po złożeniu zamówienia
fetch('/client/orders/new', { method: 'POST', body: formData })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Track złożenia zamówienia
            if (typeof window.trackOrderPlaced === 'function') {
                window.trackOrderPlaced(
                    data.order_number,  // 'ST/00000123'
                    data.total_amount,  // 450.00
                    data.items_count,   // 3
                    'standard'          // 'standard' lub 'exclusive'
                );
            }
        }
    });
```

**Best Practices:**
1. **ZAWSZE** sprawdzaj czy funkcja istnieje przed użyciem (`if (typeof window.trackOrderPlaced === 'function')`)
2. **NIE** trackuj wrażliwych danych (hasła, numery kart, dane osobowe)
3. **Używaj** sensownych nazw eventów (lowercase_with_underscores)
4. **Testuj** lokalnie przed wdrożeniem (GA4 Realtime w Google Analytics)
5. **Skup się** na kluczowych akcjach (zamówienia, rejestracja, dodanie do koszyka)

**Dokumentacja:**
- Pełna dokumentacja: `docs/GOOGLE_ANALYTICS.md`
- Przykłady użycia: `static/js/examples/analytics-usage-examples.js`

**Wyłączenie GA4:**
- W środowisku development: Zostaw `GA_MEASUREMENT_ID` puste w `.env`
- W środowisku production: Ustaw prawdziwe Measurement ID z Google Analytics

**Privacy & RODO:**
- Anonimizacja IP jest włączona (`anonymize_ip: true`)
- Cookies są ustawione jako `SameSite=None;Secure`
- GA4 ładuje się tylko jeśli Measurement ID jest ustawione

---

### 🔄 Workflow Rozwoju Aplikacji

**ZASADA GŁÓWNA:** Pracujemy na kopii lokalnej (Mac + XAMPP), dopiero po wdrożeniu pełnej funkcjonalności robimy push na Git i aktualizujemy serwer produkcyjny.

**Etapy pracy:**
1. **Rozwój lokalny** (Mac, VSCode, XAMPP MariaDB)
2. **Testowanie lokalne** (http://localhost:5001)
3. **Commit & Push do GitHub** (gdy funkcjonalność działa)
4. **Deploy na VPS** (aktualizacja serwera produkcyjnego)

---

### 📦 Deployment na Serwer VPS (PRODUKCJA)

**KRYTYCZNE:** Podczas pracy nad deploymentem aplikacji na serwer VPS:
- **NIE używaj komend Bash** bezpośrednio w VSCode/Claude Code
- **Wszystkie komendy** muszą być wykonywane przez użytkownika **ręcznie w terminalu SSH na Macu**
- **Podawaj komendy** użytkownikowi do skopiowania i wykonania
- **Czekaj na wyniki** od użytkownika przed kontynuowaniem

**Dane serwera:**
- **Serwer:** VPS Hostinger (Ubuntu 24.04)
- **IP:** 191.96.53.209
- **User:** konrad
- **Domena:** thunderorders.cloud (HTTPS z Let's Encrypt)
- **SSH:** `ssh konrad@191.96.53.209`

---

### ✅ Status Serwera Produkcyjnego (DEPLOYMENT ZAKOŃCZONY)

**Infrastruktura:**
- ✅ Aplikacja w `/var/www/ThunderOrders`
- ✅ Baza danych MariaDB: `thunder_orders`, user: `thunder`
- ✅ Gunicorn na porcie 8000 (4 workers)
- ✅ Systemd service: `thunderorders.service` (auto-start)
- ✅ Nginx reverse proxy (port 80/443 → 8000)
- ✅ SSL/TLS: Let's Encrypt (auto-renewal)
- ✅ phpMyAdmin: https://thunderorders.cloud/admin/db/phpmyadmin (HTTP Basic Auth)
- ✅ DNS rekord A: 191.96.53.209

**Aplikacja działa:**
- 🌐 **Publiczny URL:** https://thunderorders.cloud
- 🔒 **SSL:** Ważny do 2026-03-10 (auto-renewal)
- 🗄️ **phpMyAdmin:** Zabezpieczony HTTP Basic Auth + login MariaDB

---

### 🚀 Jak Aktualizować Aplikację na Serwerze

#### **Scenariusz 1: Zmiany w KODZIE (bez zmian w bazie danych)**

**Na Macu (lokalnie):**
```bash
# 1. Wprowadź zmiany w kodzie
# 2. Commituj i pushuj
git add .
git commit -m "Opis zmian"
git push origin main
```

**Na serwerze (SSH):**
```bash
# 1. Połącz się SSH
ssh konrad@191.96.53.209

# 2. Przejdź do katalogu aplikacji
cd /var/www/ThunderOrders

# 3. Pobierz najnowszy kod
git pull origin main

# 4. Restartuj aplikację
sudo systemctl restart thunderorders

# 5. Sprawdź status
sudo systemctl status thunderorders

# 6. Sprawdź logi (jeśli coś nie działa)
sudo journalctl -u thunderorders -n 50 --no-pager
sudo tail -50 /var/www/ThunderOrders/logs/gunicorn-error.log
```

---

#### **Scenariusz 2: Zmiany w BAZIE DANYCH (tabele/kolumny)**

**KRYTYCZNE: KAŻDA zmiana w bazie danych MUSI być zapisana w migracji Flask-Migrate!**

**Co wymaga migracji:**
- ✅ Dodanie nowej tabeli
- ✅ Dodanie kolumny do istniejącej tabeli
- ✅ Zmiana typu kolumny
- ✅ Usunięcie kolumny/tabeli
- ✅ Dodanie indeksu/klucza obcego
- ✅ Zmiana constraintów

**Workflow:**

**Na Macu (lokalnie):**
```bash
# 1. Wprowadź zmiany w modelach (np. modules/products/models.py)
# 2. Wygeneruj migrację
flask db migrate -m "Added new column: product.barcode"

# 3. Sprawdź wygenerowaną migrację
# Plik: migrations/versions/xxxxx_added_new_column.py

# 4. Wykonaj migrację lokalnie (test)
flask db upgrade

# 5. Sprawdź czy działa lokalnie
# Test w XAMPP phpMyAdmin + aplikacja

# 6. Commituj migrację + zmiany w kodzie
git add migrations/versions/*.py
git add modules/products/models.py
git commit -m "Added product barcode field with migration"
git push origin main
```

**Na serwerze (SSH):**
```bash
# 1. Backup bazy danych (ZAWSZE przed migracją!)
mysqldump -u thunder -p thunder_orders > ~/backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Pobierz kod + migracje
cd /var/www/ThunderOrders
git pull origin main

# 3. Aktywuj venv
source venv/bin/activate

# 4. Wykonaj migrację
flask db upgrade

# 5. Sprawdź tabele w phpMyAdmin
# https://thunderorders.cloud/admin/db/phpmyadmin

# 6. Restartuj aplikację
sudo systemctl restart thunderorders

# 7. Sprawdź logi
sudo journalctl -u thunderorders -n 30
```

**Jeśli coś pójdzie nie tak - rollback:**
```bash
# 1. Przywróć backup bazy
mysql -u thunder -p thunder_orders < ~/backup_YYYYMMDD_HHMMSS.sql

# 2. Cofnij migrację
flask db downgrade

# 3. Restartuj
sudo systemctl restart thunderorders
```

---

#### **Scenariusz 3: Aktualizacja Dependencies (nowe pakiety Python)**

**Na Macu (lokalnie):**
```bash
# 1. Dodaj pakiet
pip install nowy-pakiet

# 2. Zaktualizuj requirements.txt
pip freeze > requirements.txt

# 3. Commituj
git add requirements.txt
git commit -m "Added nowy-pakiet dependency"
git push origin main
```

**Na serwerze (SSH):**
```bash
cd /var/www/ThunderOrders
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart thunderorders
```

---

#### **Scenariusz 4: Zmiany w Nginx/Gunicorn/Systemd**

**Gunicorn config (`gunicorn_config.py`):**
```bash
# Po zmianach
git pull origin main
sudo systemctl restart thunderorders
```

**Nginx config (`/etc/nginx/sites-available/thunderorders`):**
```bash
# Po edycji ręcznej (przez nano)
sudo nginx -t
sudo systemctl restart nginx
```

**Systemd service (`/etc/systemd/system/thunderorders.service`):**
```bash
# Po edycji ręcznej (przez nano)
sudo systemctl daemon-reload
sudo systemctl restart thunderorders
```

---

### 🔧 Zarządzanie Serwerem Produkcyjnym

#### **Podstawowe komendy:**

**Aplikacja (Gunicorn):**
```bash
# Status
sudo systemctl status thunderorders

# Start/Stop/Restart
sudo systemctl start thunderorders
sudo systemctl stop thunderorders
sudo systemctl restart thunderorders

# Logi na żywo
sudo journalctl -u thunderorders -f

# Ostatnie 50 linii logów
sudo journalctl -u thunderorders -n 50 --no-pager

# Logi Gunicorn
sudo tail -50 /var/www/ThunderOrders/logs/gunicorn-error.log
sudo tail -50 /var/www/ThunderOrders/logs/gunicorn-access.log
```

**Nginx:**
```bash
# Status
sudo systemctl status nginx

# Test konfiguracji
sudo nginx -t

# Restart
sudo systemctl restart nginx

# Logi
sudo tail -50 /var/log/nginx/error.log
sudo tail -50 /var/log/nginx/access.log
```

**Baza danych (MariaDB):**
```bash
# Status
sudo systemctl status mariadb

# Połączenie CLI
mysql -u thunder -p thunder_orders

# Backup
mysqldump -u thunder -p thunder_orders > ~/backup.sql

# Restore
mysql -u thunder -p thunder_orders < ~/backup.sql
```

**SSL (Certbot):**
```bash
# Status certyfikatów
sudo certbot certificates

# Odnawianie (auto, ale można manualnie)
sudo certbot renew

# Test auto-renewal
sudo certbot renew --dry-run
```

---

### 🗄️ Dostęp do phpMyAdmin

**URL:** https://thunderorders.cloud/admin/db/phpmyadmin

**Dwuetapowe logowanie:**
1. **HTTP Basic Auth:**
   - User: `admin`
   - Password: (ustalone przy konfiguracji)
2. **MariaDB Login:**
   - User: `thunder`
   - Password: `HN2Nm0LiCdLhGHXx`

**Bezpieczeństwo:**
- Ukryty URL (`/admin/db/phpmyadmin`)
- HTTP Basic Auth (pierwsza warstwa)
- HTTPS (szyfrowanie)
- Dostęp tylko przez HTTPS

---

### 📂 Struktura Katalogów na Serwerze

```
/var/www/ThunderOrders/
├── app.py                    # Główny plik aplikacji
├── config.py                 # Konfiguracja (production)
├── gunicorn_config.py        # Konfiguracja Gunicorn
├── .env                      # Zmienne środowiskowe (PRODUCTION)
├── requirements.txt          # Dependencies Python
├── venv/                     # Virtual environment
├── modules/                  # Moduły aplikacji
├── templates/                # Szablony HTML
├── static/                   # CSS, JS, images
│   └── uploads/              # Uploaded files
├── migrations/               # Flask-Migrate migrations
│   └── versions/             # Pliki migracji
└── logs/                     # Logi aplikacji
    ├── gunicorn-access.log
    └── gunicorn-error.log
```

**Konfiguracje systemowe:**
```
/etc/systemd/system/thunderorders.service    # Systemd service
/etc/nginx/sites-available/thunderorders     # Nginx config
/etc/nginx/sites-enabled/thunderorders       # Symlink
/etc/letsencrypt/live/thunderorders.cloud/   # SSL certificates
```

---

### 🐛 Troubleshooting

**Problem: Aplikacja nie odpowiada**
```bash
# 1. Sprawdź status
sudo systemctl status thunderorders

# 2. Sprawdź logi
sudo journalctl -u thunderorders -n 100

# 3. Sprawdź czy Gunicorn działa lokalnie
curl http://127.0.0.1:8000/

# 4. Restart
sudo systemctl restart thunderorders
```

**Problem: Nginx 502 Bad Gateway**
```bash
# Gunicorn nie działa
sudo systemctl status thunderorders
sudo systemctl start thunderorders
```

**Problem: 500 Internal Server Error**
```bash
# Błąd w aplikacji Flask
sudo tail -100 /var/www/ThunderOrders/logs/gunicorn-error.log
```

**Problem: Baza danych connection error**
```bash
# 1. Sprawdź czy MariaDB działa
sudo systemctl status mariadb

# 2. Sprawdź .env
cat /var/www/ThunderOrders/.env | grep DB_

# 3. Test połączenia
mysql -u thunder -p thunder_orders -e "SELECT 1;"
```

**Problem: SSL certificate expired**
```bash
# Odśwież certyfikat
sudo certbot renew
sudo systemctl restart nginx
```

---

### 📝 Ważne Zasady

1. **ZAWSZE testuj lokalnie** przed push na Git
2. **ZAWSZE rób backup bazy** przed migracją na produkcji
3. **NIGDY nie edytuj kodu bezpośrednio na serwerze** - tylko przez Git
4. **ZAWSZE używaj migracji** do zmian w bazie danych
5. **SPRAWDZAJ logi** po każdej aktualizacji
6. **NIE commituj haseł** do Git (używaj .env, który jest w .gitignore)
7. **Restartuj aplikację** po każdej zmianie kodu

---

---

## Dokumentacja PRD (Product Requirements Document)

Szczegółowa dokumentacja projektu została podzielona na osobne pliki w folderze `docs/`. Czytaj je w razie potrzeby:

| Plik | Zawartość |
|------|-----------|
| [docs/PRD_OVERVIEW.md](docs/PRD_OVERVIEW.md) | Executive Summary, Tech Stack, Core Value Proposition |
| [docs/PRD_PERMISSIONS.md](docs/PRD_PERMISSIONS.md) | Role użytkowników (Admin, Mod, Client, Guest), matryca uprawnień |
| [docs/PRD_DATABASE.md](docs/PRD_DATABASE.md) | Pełny schemat bazy danych, ERD, definicje tabel SQL |
| [docs/PRD_FEATURES.md](docs/PRD_FEATURES.md) | Szczegółowy opis funkcjonalności (User Stories, Acceptance Criteria) |
| [docs/PRD_FILE_STRUCTURE.md](docs/PRD_FILE_STRUCTURE.md) | Struktura katalogów projektu |
| [docs/PRD_UI_UX.md](docs/PRD_UI_UX.md) | Paleta kolorów, typografia, style komponentów |
| [docs/PRD_ROADMAP.md](docs/PRD_ROADMAP.md) | Plan implementacji MVP (25 etapów) |
| [docs/PRD_API.md](docs/PRD_API.md) | Lista wszystkich endpointów API |
| [docs/PRD_SECURITY_CONFIG.md](docs/PRD_SECURITY_CONFIG.md) | Bezpieczeństwo, konfiguracja, glossary |

**Kiedy czytać poszczególne pliki:**
- **PRD_OVERVIEW.md** - gdy potrzebujesz ogólnego kontekstu projektu
- **PRD_PERMISSIONS.md** - gdy implementujesz kontrolę dostępu lub uprawnienia
- **PRD_DATABASE.md** - gdy tworzysz/modyfikujesz modele lub migracje
- **PRD_FEATURES.md** - gdy implementujesz nową funkcjonalność
- **PRD_FILE_STRUCTURE.md** - gdy tworzysz nowe pliki/katalogi
- **PRD_UI_UX.md** - gdy tworzysz style CSS lub komponenty UI
- **PRD_ROADMAP.md** - gdy sprawdzasz status implementacji
- **PRD_API.md** - gdy tworzysz nowe endpointy
- **PRD_SECURITY_CONFIG.md** - gdy konfigurujesz aplikację lub sprawdzasz bezpieczeństwo
