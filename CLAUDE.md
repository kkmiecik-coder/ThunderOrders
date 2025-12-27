# ThunderOrders - Product Requirements Document (PRD)

**Version:** 1.0
**Date:** 31 października 2025
**Author:** Konrad
**Status:** Draft - Ready for Implementation

---

## ⚠️ WAŻNE UWAGI DLA CLAUDE

### 🤔 KRYTYCZNE: Podejmowanie Decyzji - Zawsze Pytaj Użytkownika

**ZASADA:** Gdy istnieje **więcej niż jedno rozwiązanie** danego problemu, ZAWSZE przedstaw wszystkie opcje użytkownikowi i pozwól mu wybrać.

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

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Tech Stack](#2-tech-stack)
3. [User Roles & Permissions](#3-user-roles--permissions)
4. [Database Schema](#4-database-schema)
5. [Features Breakdown](#5-features-breakdown)
6. [File Structure](#6-file-structure)
7. [UI/UX Guidelines](#7-uiux-guidelines)
8. [MVP Implementation Roadmap](#8-mvp-implementation-roadmap)
9. [API Endpoints](#9-api-endpoints)
10. [Security Considerations](#10-security-considerations)
11. [Configuration Management](#11-configuration-management)

---

## 1. Executive Summary

### 1.1 Project Overview

**ThunderOrders** to dedykowana aplikacja webowa do zarządzania odsprzedażą produktów z Azji (głównie Korea, Chiny) na rynek polski. System umożliwia kompleksową obsługę procesu od zamówienia przez klienta, przez sprowadzenie produktów, aż po wysyłkę do klienta końcowego.

### 1.2 Core Value Proposition

- **Dla administratorów:** Kompleksowe narzędzie do zarządzania zamówieniami, magazynem, klientami i logistyką
- **Dla klientów:** Prosty proces zamawiania produktów z Azji bez konieczności samodzielnego importu
- **Dla moderatorów:** Efektywne narzędzie do obsługi zamówień z kontrolowanymi uprawnieniami

### 1.3 Key Differentiators

- Dedykowane strony zamówień Exclusive (zamknięte linki do konkretnych produktów)
- Zaawansowany moduł WMS do zbierania i pakowania produktów
- System komentarzy do zamówień (komunikacja Admin ↔ Klient)
- Multi-currency support (KRW, USD → PLN) dla łatwego przeliczania kosztów zakupu
- Activity Log dla pełnej transparentności działań w systemie
- Import przelewów bankowych z automatycznym rozpoznawaniem zamówień

---

## 2. Tech Stack

### 2.1 Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.11+ | Backend language |
| **Flask** | 3.0+ | Web framework |
| **Flask-Login** | Latest | User authentication |
| **Flask-WTF** | Latest | Form handling & CSRF protection |
| **Flask-Mail** | Latest | Email notifications |
| **SQLAlchemy** | 2.0+ | ORM for database |
| **Flask-Migrate** | Latest | Database migrations |
| **Werkzeug** | Latest | Password hashing |
| **Pillow** | Latest | Image processing & compression |

### 2.2 Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| **HTMX** | 1.9+ | SPA-like experience without JS framework |
| **Tailwind CSS** | 3.4+ | Utility-first CSS framework |
| **Vanilla JavaScript** | ES6+ | Custom interactions |
| **Jinja2** | 3.1+ | Template engine |

### 2.3 Database

| Technology | Version | Purpose |
|------------|---------|---------|
| **MariaDB** | 10.6+ | Primary database (development + production) |
| **phpMyAdmin** | Latest | Database management UI |

### 2.4 Development Tools

- **VSCode** - IDE
- **Claude Code** - AI-assisted coding
- **Git** - Version control
- **Docker** (opcjonalnie) - Containerization dla lokalnego MariaDB

### 2.5 External APIs (Future)

- **NBP API / ExchangeRate-API** - Kursy walut (KRW, USD → PLN)
- **GUS API** - Pobieranie danych firm (NIP/REGON)
- **InPost API** - Wysyłka paczek (post-MVP)

---

## 3. User Roles & Permissions

### 3.1 Role Hierarchy

```
Admin (Full Access)
  ↓
Mod (Limited Access)
  ↓
Client (Customer Access)
  ↓
Guest (Exclusive Orders Only)
```

### 3.2 Detailed Permissions Matrix

| Feature | Admin | Mod | Client | Guest |
|---------|-------|-----|--------|-------|
| **Authentication** |
| Login/Logout | ✅ | ✅ | ✅ | ❌ |
| Register | ✅ | ✅ | ✅ | ❌ |
| Password Reset | ✅ | ✅ | ✅ | ❌ |
| **Dashboard** |
| View Admin Dashboard | ✅ | ✅ | ❌ | ❌ |
| View Client Dashboard | ✅ | ❌ | ✅ | ❌ |
| **Orders Management** |
| View All Orders | ✅ | ✅ | ❌ | ❌ |
| View Own Orders | ✅ | ❌ | ✅ | ❌ |
| Create Order | ✅ | ✅ | ✅ | ❌ |
| Edit Order | ✅ | ✅ | ❌ | ❌ |
| Delete Order | ✅ | ❌ | ❌ | ❌ |
| Change Order Status | ✅ | ✅ | ❌ | ❌ |
| Add Comments | ✅ | ✅ | ✅ | ❌ |
| View All Order Details | ✅ | ⚠️ (limited) | ⚠️ (own) | ❌ |
| **WMS Module** |
| Access WMS | ✅ | ✅ | ❌ | ❌ |
| Pick Products | ✅ | ✅ | ❌ | ❌ |
| Change Status to Packed | ✅ | ✅ | ❌ | ❌ |
| **Products Management** |
| View Products | ✅ | ✅ | ✅ | ❌ |
| Add Product | ✅ | ⚠️ (limited fields) | ❌ | ❌ |
| Edit Product | ✅ | ⚠️ (limited fields) | ❌ | ❌ |
| Delete Product | ✅ | ❌ | ❌ | ❌ |
| View Purchase Price | ✅ | ❌ | ❌ | ❌ |
| View Supplier Info | ✅ | ❌ | ❌ | ❌ |
| Upload Images | ✅ | ✅ | ❌ | ❌ |
| **Clients Management** |
| View All Clients | ✅ | ✅ | ❌ | ❌ |
| Edit Client Data | ✅ | ❌ | ⚠️ (own) | ❌ |
| Delete Client | ✅ | ❌ | ❌ | ❌ |
| View Order History | ✅ | ✅ | ⚠️ (own) | ❌ |
| **Exclusive Pages** |
| Create Exclusive Page | ✅ | ❌ | ❌ | ❌ |
| Edit Exclusive Page | ✅ | ❌ | ❌ | ❌ |
| Delete Exclusive Page | ✅ | ❌ | ❌ | ❌ |
| View Exclusive Orders | ✅ | ✅ | ⚠️ (own) | ❌ |
| Place Exclusive Order | ✅ | ✅ | ✅ | ✅ |
| **Bank Imports** |
| Import Bank Statements | ✅ | ❌ | ❌ | ❌ |
| Match Payments | ✅ | ❌ | ❌ | ❌ |
| **Warehouse** |
| View Stock Levels | ✅ | ✅ | ❌ | ❌ |
| Create Stock Orders | ✅ | ❌ | ❌ | ❌ |
| Receive Stock | ✅ | ✅ | ❌ | ❌ |
| **Settings** |
| View Settings | ✅ | ⚠️ (limited) | ⚠️ (profile only) | ❌ |
| Edit App Settings | ✅ | ❌ | ❌ | ❌ |
| Manage Categories | ✅ | ❌ | ❌ | ❌ |
| Manage Tags | ✅ | ❌ | ❌ | ❌ |
| Manage Suppliers | ✅ | ❌ | ❌ | ❌ |
| Edit Own Profile | ✅ | ✅ | ✅ | ❌ |
| **Statistics** |
| View Sales Stats | ✅ | ⚠️ (limited) | ❌ | ❌ |
| Export Reports | ✅ | ❌ | ❌ | ❌ |
| **Activity Log** |
| View All Logs | ✅ | ❌ | ❌ | ❌ |
| View Own Logs | ✅ | ✅ | ✅ | ❌ |
| **Refunds** |
| Issue Refund | ✅ | ❌ | ❌ | ❌ |
| Request Refund | ❌ | ❌ | ✅ | ❌ |
| **Email Module** |
| Configure SMTP | ✅ | ❌ | ❌ | ❌ |
| View Email Templates | ✅ | ❌ | ❌ | ❌ |
| Edit Email Templates | ✅ | ❌ | ❌ | ❌ |
| **Global Search** |
| Search Orders/Products/Clients | ✅ | ✅ | ⚠️ (limited) | ❌ |

**Legend:**
- ✅ = Full Access
- ⚠️ = Limited/Partial Access
- ❌ = No Access

### 3.3 Mod Limitations (vs Admin)

**Mod NIE MOŻE:**
- Widzieć cen zakupu produktów (`purchase_price`, `purchase_currency`, `purchase_price_pln`)
- Widzieć informacji o dostawcach
- Widzieć marży na produktach
- Usuwać zamówień, produktów, klientów
- Zarządzać ustawieniami aplikacji
- Tworzyć/edytować stron Exclusive
- Importować przelewów bankowych
- Wydawać zwrotów pieniędzy
- Widzieć Activity Log innych użytkowników
- Zarządzać rolami użytkowników
- Konfigurować SMTP/Email

**Mod MOŻE:**
- Przeglądać wszystkie zamówienia (bez cen zakupu)
- Zmieniać statusy zamówień
- Dodawać komentarze do zamówień
- Korzystać z WMS (zbieranie, pakowanie)
- Dodawać/edytować produkty (bez pól: cena zakupu, dostawca, marża)
- Przesyłać zdjęcia produktów
- Przeglądać klientów i ich historię zamówień
- Widzieć ograniczone statystyki (bez finansowych)

---

## 4. Database Schema

### 4.1 Entity Relationship Diagram (ERD)

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│     users       │         │     orders      │         │  order_items    │
├─────────────────┤         ├─────────────────┤         ├─────────────────┤
│ id (PK)         │────┐    │ id (PK)         │────┐    │ id (PK)         │
│ email           │    │    │ order_number    │    │    │ order_id (FK)   │
│ password_hash   │    │    │ user_id (FK)    │────┘    │ product_id (FK) │
│ first_name      │    │    │ status          │         │ quantity        │
│ last_name       │    │    │ created_at      │         │ price           │
│ role            │    └───→│ updated_at      │         │ total           │
│ is_active       │         │ total_amount    │         └─────────────────┘
│ email_verified  │         │ is_exclusive    │                 │
│ created_at      │         │ exclusive_id(FK)│                 │
│ updated_at      │         │ is_guest_order  │                 │
└─────────────────┘         │ guest_email     │                 │
                            │ guest_name      │                 │
                            └─────────────────┘                 │
                                     │                          │
                                     │                          │
                    ┌────────────────┴────────────┐             │
                    │                             │             │
         ┌──────────▼──────────┐      ┌──────────▼─────────┐   │
         │  order_comments     │      │  order_refunds     │   │
         ├─────────────────────┤      ├────────────────────┤   │
         │ id (PK)             │      │ id (PK)            │   │
         │ order_id (FK)       │      │ order_id (FK)      │   │
         │ user_id (FK)        │      │ amount             │   │
         │ comment             │      │ reason             │   │
         │ created_at          │      │ created_by (FK)    │   │
         └─────────────────────┘      │ status             │   │
                                      │ created_at         │   │
                                      └────────────────────┘   │
                                                               │
┌─────────────────────────────────────────────────────────────┘
│
│         ┌─────────────────┐
└────────→│    products     │
          ├─────────────────┤
          │ id (PK)         │
          │ name            │
          │ sku             │
          │ ean             │
          │ category_id(FK) │
          │ manufacturer    │
          │ series          │
          │ length          │
          │ width           │
          │ height          │
          │ weight          │
          │ sale_price      │
          │ purchase_price  │
          │ purchase_curr   │
          │ purchase_pln    │
          │ margin          │
          │ quantity        │
          │ supplier_id(FK) │
          │ variant_group   │
          │ is_active       │
          │ created_at      │
          │ updated_at      │
          └─────────────────┘
                  │
         ┌────────┴────────┐
         │                 │
┌────────▼───────┐  ┌──────▼────────┐
│ product_images │  │ product_tags  │
├────────────────┤  ├───────────────┤
│ id (PK)        │  │ id (PK)       │
│ product_id(FK) │  │ product_id(FK)│
│ filename       │  │ tag_id (FK)   │
│ path_original  │  └───────────────┘
│ path_compressed│           │
│ is_primary     │           │
│ sort_order     │   ┌───────▼───────┐
│ uploaded_at    │   │     tags      │
└────────────────┘   ├───────────────┤
                     │ id (PK)       │
                     │ name          │
                     │ created_at    │
                     └───────────────┘

┌─────────────────┐         ┌─────────────────────┐
│   categories    │         │  exclusive_pages    │
├─────────────────┤         ├─────────────────────┤
│ id (PK)         │         │ id (PK)             │
│ name            │         │ name                │
│ parent_id (FK)  │─┐       │ token               │
│ slug            │ │       │ description         │
│ sort_order      │ │       │ is_active           │
│ created_at      │ └──────→│ created_by (FK)     │
└─────────────────┘         │ created_at          │
                            │ expires_at          │
┌─────────────────┐         └─────────────────────┘
│    suppliers    │                  │
├─────────────────┤                  │
│ id (PK)         │         ┌────────▼──────────────┐
│ name            │         │ exclusive_products    │
│ contact_email   │         ├───────────────────────┤
│ contact_phone   │         │ id (PK)               │
│ country         │         │ exclusive_id (FK)     │
│ notes           │         │ product_id (FK)       │
│ is_active       │         └───────────────────────┘
│ created_at      │
└─────────────────┘

┌─────────────────┐         ┌─────────────────────┐
│    settings     │         │   activity_log      │
├─────────────────┤         ├─────────────────────┤
│ id (PK)         │         │ id (PK)             │
│ key             │         │ user_id (FK)        │
│ value           │         │ action              │
│ type            │         │ entity_type         │
│ description     │         │ entity_id           │
│ updated_at      │         │ old_value           │
│ updated_by (FK) │         │ new_value           │
└─────────────────┘         │ ip_address          │
                            │ user_agent          │
┌─────────────────┐         │ created_at          │
│  login_attempts │         └─────────────────────┘
├─────────────────┤
│ id (PK)         │         ┌─────────────────────┐
│ email           │         │   order_templates   │
│ ip_address      │         ├─────────────────────┤
│ success         │         │ id (PK)             │
│ attempted_at    │         │ user_id (FK)        │
│ locked_until    │         │ name                │
└─────────────────┘         │ created_at          │
                            └─────────────────────┘
┌─────────────────┐                  │
│ email_templates │         ┌────────▼──────────────┐
├─────────────────┤         │ template_items        │
│ id (PK)         │         ├───────────────────────┤
│ name            │         │ id (PK)               │
│ subject         │         │ template_id (FK)      │
│ body_html       │         │ product_id (FK)       │
│ body_text       │         │ quantity              │
│ type            │         └───────────────────────┘
│ updated_at      │
└─────────────────┘
```

### 4.2 Detailed Table Schemas

#### 4.2.1 users

```sql
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    role ENUM('admin', 'mod', 'client') DEFAULT 'client',
    phone VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    email_verified BOOLEAN DEFAULT FALSE,
    email_verification_token VARCHAR(255),
    password_reset_token VARCHAR(255),
    password_reset_expires DATETIME,
    last_login DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_email (email),
    INDEX idx_role (role),
    INDEX idx_verification_token (email_verification_token),
    INDEX idx_reset_token (password_reset_token)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.2 orders

```sql
CREATE TABLE orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_number VARCHAR(20) UNIQUE NOT NULL, -- Format: ST/00000001 lub EX/00000001
    user_id INT,
    status ENUM(
        'nowe', 
        'oczekujace', 
        'dostarczone_proxy', 
        'w_drodze_polska', 
        'urzad_celny', 
        'dostarczone_gom', 
        'do_pakowania', 
        'spakowane', 
        'wyslane', 
        'dostarczone',
        'anulowane',
        'do_zwrotu',
        'zwrocone'
    ) DEFAULT 'nowe',
    total_amount DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    
    -- Exclusive order fields
    is_exclusive BOOLEAN DEFAULT FALSE,
    exclusive_page_id INT,
    
    -- Guest order fields
    is_guest_order BOOLEAN DEFAULT FALSE,
    guest_email VARCHAR(255),
    guest_name VARCHAR(200),
    guest_phone VARCHAR(20),
    
    -- Shipping request
    shipping_requested BOOLEAN DEFAULT FALSE,
    shipping_requested_at DATETIME,
    
    -- Tracking
    tracking_number VARCHAR(100),
    courier VARCHAR(50),
    
    -- Metadata
    notes TEXT,
    admin_notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (exclusive_page_id) REFERENCES exclusive_pages(id) ON DELETE SET NULL,
    
    INDEX idx_order_number (order_number),
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_is_exclusive (is_exclusive),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.3 order_items

```sql
CREATE TABLE order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    price DECIMAL(10, 2) NOT NULL, -- Cena w momencie zamówienia
    total DECIMAL(10, 2) NOT NULL, -- price * quantity
    
    -- WMS fields
    picked BOOLEAN DEFAULT FALSE,
    picked_at DATETIME,
    picked_by INT,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT,
    FOREIGN KEY (picked_by) REFERENCES users(id) ON DELETE SET NULL,
    
    INDEX idx_order_id (order_id),
    INDEX idx_product_id (product_id),
    INDEX idx_picked (picked)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.4 order_comments

```sql
CREATE TABLE order_comments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    user_id INT,
    comment TEXT NOT NULL,
    is_internal BOOLEAN DEFAULT FALSE, -- Komentarz widoczny tylko dla admin/mod
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    
    INDEX idx_order_id (order_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.5 order_refunds

```sql
CREATE TABLE order_refunds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    reason TEXT NOT NULL,
    status ENUM('pending', 'completed', 'cancelled') DEFAULT 'pending',
    created_by INT NOT NULL,
    completed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
    
    INDEX idx_order_id (order_id),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.6 products

```sql
CREATE TABLE products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    sku VARCHAR(100) UNIQUE,
    ean VARCHAR(13),
    
    -- Taxonomy
    category_id INT,
    manufacturer VARCHAR(100),
    series VARCHAR(100),
    
    -- Physical properties
    length DECIMAL(8, 2), -- cm
    width DECIMAL(8, 2), -- cm
    height DECIMAL(8, 2), -- cm
    weight DECIMAL(8, 2), -- kg
    
    -- Pricing
    sale_price DECIMAL(10, 2) NOT NULL,
    purchase_price DECIMAL(10, 2),
    purchase_currency ENUM('PLN', 'KRW', 'USD') DEFAULT 'PLN',
    purchase_price_pln DECIMAL(10, 2), -- Przeliczona cena
    margin DECIMAL(5, 2), -- Procent marży
    
    -- Stock
    quantity INT DEFAULT 0,
    supplier_id INT,
    
    -- Variants
    variant_group VARCHAR(50), -- Grouping ID dla wariantów (np. ten sam produkt w różnych kolorach)
    
    -- Description
    description TEXT,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL,
    
    INDEX idx_sku (sku),
    INDEX idx_ean (ean),
    INDEX idx_category_id (category_id),
    INDEX idx_variant_group (variant_group),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.7 product_images

```sql
CREATE TABLE product_images (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    filename VARCHAR(255) NOT NULL,
    path_original VARCHAR(500) NOT NULL,
    path_compressed VARCHAR(500) NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    sort_order INT DEFAULT 0,
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    
    INDEX idx_product_id (product_id),
    INDEX idx_is_primary (is_primary)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.8 categories

```sql
CREATE TABLE categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    parent_id INT, -- Self-reference dla hierarchii
    slug VARCHAR(100) UNIQUE NOT NULL,
    sort_order INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE CASCADE,
    
    INDEX idx_parent_id (parent_id),
    INDEX idx_slug (slug)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.9 tags

```sql
CREATE TABLE tags (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.10 product_tags (junction table)

```sql
CREATE TABLE product_tags (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    tag_id INT NOT NULL,
    
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
    
    UNIQUE KEY unique_product_tag (product_id, tag_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.11 suppliers

```sql
CREATE TABLE suppliers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    contact_email VARCHAR(255),
    contact_phone VARCHAR(20),
    country VARCHAR(100),
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.12 exclusive_pages

```sql
CREATE TABLE exclusive_pages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    token VARCHAR(100) UNIQUE NOT NULL, -- Unikalny token w URL
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_by INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME, -- Opcjonalnie - data wygaśnięcia linku
    
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
    
    INDEX idx_token (token),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.13 exclusive_products (junction table)

```sql
CREATE TABLE exclusive_products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    exclusive_page_id INT NOT NULL,
    product_id INT NOT NULL,
    
    FOREIGN KEY (exclusive_page_id) REFERENCES exclusive_pages(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    
    UNIQUE KEY unique_exclusive_product (exclusive_page_id, product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.14 order_templates

```sql
CREATE TABLE order_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(200) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.15 order_template_items (junction table)

```sql
CREATE TABLE order_template_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    template_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT DEFAULT 1,
    
    FOREIGN KEY (template_id) REFERENCES order_templates(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.16 activity_log

```sql
CREATE TABLE activity_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    action VARCHAR(100) NOT NULL, -- 'login', 'order_status_change', 'product_created', etc.
    entity_type VARCHAR(50), -- 'order', 'product', 'user', etc.
    entity_id INT,
    old_value TEXT, -- JSON z poprzednimi wartościami
    new_value TEXT, -- JSON z nowymi wartościami
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    
    INDEX idx_user_id (user_id),
    INDEX idx_action (action),
    INDEX idx_entity (entity_type, entity_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.17 login_attempts

```sql
CREATE TABLE login_attempts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    success BOOLEAN DEFAULT FALSE,
    attempted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    locked_until DATETIME, -- Czas do którego konto jest zablokowane
    
    INDEX idx_email_ip (email, ip_address),
    INDEX idx_attempted_at (attempted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.18 settings

```sql
CREATE TABLE settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    `key` VARCHAR(100) UNIQUE NOT NULL,
    value TEXT,
    type ENUM('string', 'integer', 'boolean', 'json') DEFAULT 'string',
    description VARCHAR(500),
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    updated_by INT,
    
    FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL,
    
    INDEX idx_key (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 4.2.19 email_templates

```sql
CREATE TABLE email_templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    subject VARCHAR(500) NOT NULL,
    body_html TEXT NOT NULL,
    body_text TEXT,
    type ENUM(
        'registration_confirmation',
        'password_reset',
        'order_confirmation',
        'order_status_change',
        'order_comment',
        'refund_notification'
    ) NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_type (type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

## 5. Features Breakdown

### 5.1 Authentication Module

#### 5.1.1 User Registration

**User Story:** _Jako nowy użytkownik, chcę móc zarejestrować się w systemie, aby móc składać zamówienia._

**Acceptance Criteria:**
- Formularz zawiera: Imię, Nazwisko, Email, Hasło, Potwierdzenie hasła
- Walidacja:
  - Email - poprawny format + unikalny w bazie
  - Hasło - min. 8 znaków, zawiera dużą literę, małą literę, cyfrę
  - Hasła muszą się zgadzać
- Po rejestracji:
  - Wysyłany jest email z linkiem aktywacyjnym
  - Konto ma status `email_verified = FALSE`
  - Użytkownik nie może się zalogować dopóki nie potwierdzi emaila
- Link aktywacyjny:
  - Zawiera unikalny token
  - Token wygasa po 24h
  - Po kliknięciu: `email_verified = TRUE`, redirect do strony logowania z komunikatem sukcesu

**Technical Details:**
- Route: `POST /auth/register`
- Template: `templates/auth/register.html`
- Form: WTForms z walidacjami
- Password hashing: Werkzeug `generate_password_hash()`
- Email: Flask-Mail z template `registration_confirmation`
- Toast notification: "Sprawdź swoją skrzynkę email, aby aktywować konto"

---

#### 5.1.2 User Login

**User Story:** _Jako zarejestrowany użytkownik, chcę móc się zalogować, aby uzyskać dostęp do mojego panelu._

**Acceptance Criteria:**
- Formularz: Email + Hasło + "Zapamiętaj mnie" (checkbox)
- Walidacja:
  - Email istnieje w bazie
  - Hasło jest poprawne
  - Konto jest aktywowane (`email_verified = TRUE`)
  - Konto nie jest zablokowane (`is_active = TRUE`)
- Rate limiting:
  - Max 5 nieudanych prób w 15 minut
  - Po 5 próbach: blokada na 15 minut
  - Komunikat: "Zbyt wiele nieudanych prób. Spróbuj ponownie za X minut."
- Po zalogowaniu:
  - Redirect na odpowiedni dashboard (admin → `/admin/dashboard`, client → `/client/dashboard`)
  - Session tworzona przez Flask-Login
  - Activity log: "User logged in"
  - Update `last_login` w tabeli `users`

**Technical Details:**
- Route: `POST /auth/login`
- Template: `templates/auth/login.html`
- Authentication: Flask-Login
- Rate limiting: Tabela `login_attempts` + logic w `auth/routes.py`
- Password verification: Werkzeug `check_password_hash()`

---

#### 5.1.3 Password Reset

**User Story:** _Jako użytkownik, który zapomniał hasła, chcę móc je zresetować poprzez email._

**Acceptance Criteria:**
- **Formularz "Forgot Password":**
  - Pole: Email
  - Po submit: Wysyłany jest email z linkiem resetującym (nawet jeśli email nie istnieje - security by obscurity)
  - Komunikat: "Jeśli podany email istnieje w systemie, otrzymasz link do resetowania hasła"
- **Email resetujący:**
  - Zawiera unikalny token
  - Token wygasa po 1h
  - Link prowadzi do: `/auth/reset-password/<token>`
- **Formularz "Reset Password":**
  - Pole: Nowe hasło, Potwierdzenie hasła
  - Walidacja jak przy rejestracji
  - Po submit: Hasło zmienione, token usunięty, redirect do logowania
  - Activity log: "Password reset"

**Technical Details:**
- Routes:
  - `GET/POST /auth/forgot-password`
  - `GET/POST /auth/reset-password/<token>`
- Templates:
  - `templates/auth/forgot_password.html`
  - `templates/auth/reset_password.html`
- Token generation: `secrets.token_urlsafe(32)`
- Email template: `password_reset`

---

#### 5.1.4 Logout

**User Story:** _Jako zalogowany użytkownik, chcę móc się wylogować._

**Acceptance Criteria:**
- Przycisk "Wyloguj" w navbar/sidebar
- Po kliknięciu: Session kończy się, redirect na `/auth/login`
- Activity log: "User logged out"
- Toast: "Zostałeś wylogowany"

**Technical Details:**
- Route: `GET /auth/logout`
- Flask-Login: `logout_user()`

---

### 5.2 Admin Panel

#### 5.2.1 Admin Dashboard

**User Story:** _Jako administrator, chcę zobaczyć przegląd najważniejszych informacji na dashboardzie._

**Acceptance Criteria:**
- **Widoczne metryki (kafelki):**
  - Liczba zamówień (ogółem)
  - Liczba zamówień dzisiaj
  - Liczba zamówień oczekujących na pakowanie
  - Przychód w tym miesiącu (PLN)
  - Liczba klientów (aktywnych)
  - Liczba produktów (aktywnych)
- **Tabela "Ostatnie zamówienia":**
  - 10 najnowszych zamówień
  - Kolumny: Numer zamówienia, Klient, Status, Data, Kwota
  - Kliknięcie w zamówienie → szczegóły zamówienia
- **Wykres sprzedaży:**
  - Wykres liniowy - sprzedaż w ostatnich 30 dniach (post-MVP)

**Technical Details:**
- Route: `GET /admin/dashboard`
- Template: `templates/admin/dashboard.html`
- Zapytania SQL: Agregacje z tabel `orders`, `users`, `products`
- HTMX: Dashboard nie przeładowuje się po kliknięciu w sidebar

---

#### 5.2.2 Orders List (Admin)

**User Story:** _Jako administrator, chcę widzieć listę wszystkich zamówień z możliwością filtrowania i wyszukiwania._

**Acceptance Criteria:**
- **Tabela zamówień:**
  - Kolumny:
    - Checkbox (do bulk actions)
    - Numer zamówienia (link do szczegółów)
    - Klient (imię + nazwisko / "Gość")
    - Status (badge z kolorem)
    - Typ (Standard / Exclusive)
    - Data utworzenia
    - Kwota
    - Akcje (Edytuj, Usuń - tylko admin)
  - Paginacja (20 na stronę)
  - Sortowanie po: Numer, Data, Status, Kwota
- **Filtry:**
  - Status (dropdown multi-select)
  - Typ (Standard / Exclusive)
  - Zakres dat (od-do)
  - Klient (autosuggest input)
- **Wyszukiwanie:**
  - Pole tekstowe: Szukanie po numerze zamówienia, nazwisku klienta, emailu
- **Bulk actions:**
  - Checkboxy przy zamówieniach
  - Po zaznaczeniu: Floating toolbar na dole ekranu
  - Akcje:
    - Zmień status (dropdown → wybór statusu → potwierdź)
    - Export do CSV
    - WMS Mode (→ `/admin/orders/wms`)
    - Usuń (tylko admin, z potwierdzeniem)

**Technical Details:**
- Route: `GET /admin/orders`
- Template: `templates/admin/orders/list.html`
- HTMX: Filtrowanie/sortowanie wymienia tylko tabelę (nie cały layout)
- JavaScript: `static/js/pages/admin/orders-list.js` (checkboxy, toolbar)

---

#### 5.2.3 Order Detail (Admin)

**User Story:** _Jako administrator, chcę zobaczyć szczegóły zamówienia i móc je edytować._

**Acceptance Criteria:**
- **Sekcja "Informacje o zamówieniu":**
  - Numer zamówienia (duży, na górze)
  - Status (dropdown - możliwość zmiany)
  - Data utworzenia
  - Ostatnia aktualizacja
  - Typ zamówienia (Standard / Exclusive)
  - Suma zamówienia
- **Sekcja "Klient":**
  - Imię i nazwisko (link do profilu klienta)
  - Email, Telefon
  - Jeśli guest order: Oznaczenie "Zamówienie gościa"
- **Sekcja "Produkty":**
  - Tabela:
    - Miniatura zdjęcia
    - Nazwa produktu (link)
    - SKU
    - Ilość
    - Cena jednostkowa
    - Suma (ilość × cena)
    - Status WMS (Zebrane ✓ / Do zebrania)
  - Suma całkowita na dole
- **Sekcja "Tracking":**
  - Numer przesyłki (input)
  - Kurier (dropdown: InPost, DPD, DHL, Inny)
  - Link do śledzenia (generowany automatycznie lub input manual)
- **Sekcja "Timeline / Komentarze":**
  - Historia zdarzeń:
    - 📦 Zamówienie utworzone
    - 💬 Komentarze użytkowników
    - 🔄 Zmiany statusu (z informacją kto zmienił)
    - 💰 Zwroty płatności
  - Formularz dodawania komentarza:
    - Textarea
    - Checkbox "Komentarz wewnętrzny" (widoczny tylko admin/mod)
    - Przycisk "Dodaj komentarz"
- **Sekcja "Zwrot płatności" (tylko admin):**
  - Przycisk "Zwróć płatność"
  - Modal:
    - Kwota (PLN) - domyślnie pełna kwota zamówienia
    - Powód (textarea)
    - Przycisk "Potwierdź zwrot"
  - Po potwierdzeniu:
    - Status zamówienia → "Do zwrotu"
    - Wpis w tabeli `order_refunds`
    - Activity log
    - Email do klienta
    - Timeline event

**Technical Details:**
- Route: `GET/POST /admin/orders/<id>`
- Template: `templates/admin/orders/detail.html`
- HTMX:
  - Zmiana statusu: `hx-post="/admin/orders/<id>/status"`
  - Dodanie komentarza: `hx-post="/admin/orders/<id>/comment"`
  - Zwrot: Modal z `hx-post="/admin/orders/<id>/refund"`
- JavaScript: `static/js/pages/admin/order-detail.js`

---

#### 5.2.4 WMS Mode

**User Story:** _Jako admin/mod, chcę móc zbierać produkty z wielu zamówień jednocześnie w trybie WMS._

**Acceptance Criteria:**
- **Aktywacja WMS:**
  - Na liście zamówień: Zaznacz checkboxy → "WMS Mode" z floating toolbar
  - Przekierowanie na: `/admin/orders/wms?orders=1,2,3`
- **Interfejs WMS:**
  - Lista zamówień na górze (kafelki):
    - Numer zamówienia
    - Status
    - Liczba produktów
    - Progress bar (zebrane / total)
  - Lista produktów do zebrania (zgrupowane):
    - Checkbox (zaznaczenie = zebrane)
    - Miniatura zdjęcia
    - Nazwa produktu
    - SKU / EAN
    - Ilość
    - Z jakiego zamówienia (jeśli produkt w wielu zamówieniach)
    - Lokalizacja w magazynie (opcjonalnie)
  - Po zaznaczeniu checkboxa:
    - `order_items.picked = TRUE`
    - `order_items.picked_at = NOW()`
    - `order_items.picked_by = current_user.id`
    - Progress bar się aktualizuje
- **Zakończenie zbierania:**
  - Gdy wszystkie produkty zebrane → Przycisk "Spakuj zamówienia" (aktywny)
  - Po kliknięciu:
    - Statusy zamówień → "Spakowane"
    - Activity log
    - Toast: "Zamówienia zostały spakowane"
    - Redirect na listę zamówień

**Technical Details:**
- Route: `GET /admin/orders/wms`
- Template: `templates/admin/orders/wms.html`
- JavaScript: `static/js/pages/admin/wms.js` (checkbox logic, progress bars)
- HTMX: Checkbox change → `hx-post="/admin/orders/wms/pick-item"`

---

#### 5.2.5 Clients List (Admin)

**User Story:** _Jako administrator, chcę zobaczyć listę wszystkich klientów z ich historią zamówień._

**Acceptance Criteria:**
- **Tabela klientów:**
  - Kolumny:
    - ID
    - Imię i nazwisko (link do szczegółów)
    - Email
    - Telefon
    - Liczba zamówień
    - Łączna wartość zamówień (PLN)
    - Status (Aktywny / Nieaktywny)
    - Data rejestracji
    - Akcje (Edytuj, Usuń - tylko admin)
  - Paginacja (50 na stronę)
  - Sortowanie po: Nazwa, Email, Liczba zamówień, Wartość zamówień
- **Filtry:**
  - Status (Aktywny / Nieaktywny)
  - Zakres dat rejestracji
- **Wyszukiwanie:**
  - Pole tekstowe: Imię, nazwisko, email

**Technical Details:**
- Route: `GET /admin/clients`
- Template: `templates/admin/clients/list.html`

---

#### 5.2.6 Client Detail (Admin)

**User Story:** _Jako administrator, chcę zobaczyć szczegóły klienta i jego historię zamówień._

**Acceptance Criteria:**
- **Sekcja "Informacje o kliencie":**
  - Imię i nazwisko
  - Email (możliwość edycji)
  - Telefon (możliwość edycji)
  - Data rejestracji
  - Ostatnie logowanie
  - Status (Aktywny/Nieaktywny - toggle)
  - Rola (dropdown - tylko admin może zmieniać)
- **Sekcja "Statystyki":**
  - Liczba zamówień
  - Łączna wartość zamówień
  - Średnia wartość zamówienia
  - Ostatnie zamówienie (data)
- **Sekcja "Historia zamówień":**
  - Tabela jak na `/admin/orders` ale tylko dla tego klienta
  - Możliwość przejścia do szczegółów zamówienia

**Technical Details:**
- Route: `GET/POST /admin/clients/<id>`
- Template: `templates/admin/clients/detail.html`

---

#### 5.2.7 Exclusive Pages Management

**User Story:** _Jako administrator, chcę tworzyć dedykowane strony zamówień (exclusive) dla wybranych produktów._

**Acceptance Criteria:**
- **Lista stron Exclusive:**
  - Tabela:
    - Nazwa strony
    - Token (unikalny identyfikator w URL)
    - Liczba produktów
    - Liczba zamówień
    - Status (Aktywna / Nieaktywna)
    - Data utworzenia
    - Data wygaśnięcia (opcjonalnie)
    - Akcje (Edytuj, Usuń, Kopiuj link)
  - Przycisk "Dodaj nową stronę Exclusive"
- **Formularz tworzenia/edycji:**
  - Nazwa strony (np. "Promocja Pluszaki Wielkanocne")
  - Opis (textarea - wyświetlany na stronie)
  - Wybór produktów:
    - Lista checkbox ze wszystkimi produktami
    - Możliwość filtrowania/wyszukiwania
    - Miniaturka + nazwa + SKU
  - Status (Aktywna/Nieaktywna)
  - Data wygaśnięcia (opcjonalnie - datepicker)
  - Po zapisie:
    - Generowany unikalny token (np. `secrets.token_urlsafe(16)`)
    - Widoczny link: `https://thunderorders.pl/exclusive/<token>`
    - Przycisk "Kopiuj link"
    - Toast: "Strona Exclusive została utworzona. Link skopiowany do schowka."

**Technical Details:**
- Routes:
  - `GET /admin/exclusive` (lista)
  - `GET/POST /admin/exclusive/create` (nowa strona)
  - `GET/POST /admin/exclusive/<id>/edit` (edycja)
  - `DELETE /admin/exclusive/<id>` (usunięcie)
- Templates:
  - `templates/admin/exclusive/list.html`
  - `templates/admin/exclusive/create.html`
  - `templates/admin/exclusive/edit.html`

---

#### 5.2.8 Bank Import

**User Story:** _Jako administrator, chcę importować wyciągi bankowe i automatycznie przypisywać płatności do zamówień._

**Acceptance Criteria:**
- **Formularz importu:**
  - Dropdown: Wybór banku (ING, PayPal, Revolut)
  - File upload (CSV)
  - Przycisk "Importuj"
- **Po upload:**
  - Parsing pliku CSV (różne formaty dla różnych banków)
  - Wyszukiwanie numeru zamówienia w tytule przelewu (regex: `(ST|EX)/\d{8}`)
  - Preview tabeli:
    - Data przelewu
    - Kwota
    - Tytuł przelewu
    - **Rozpoznane zamówienie** (numer + link) LUB "Nie rozpoznano"
    - Status (Dopasowano / Nie dopasowano)
    - Checkbox (czy przypisać?)
- **Potwierdzenie importu:**
  - Przycisk "Potwierdź i zmień statusy"
  - Po kliknięciu:
    - Dla zaznaczonych zamówień:
      - Status → "Oczekujące"
      - Activity log: "Payment received via bank import"
      - Email do klienta (jeśli włączone)
    - Toast: "Zaimportowano X płatności, dopasowano Y zamówień"

**Technical Details:**
- Route: `GET/POST /admin/imports/bank`
- Template: `templates/admin/imports/bank_imports.html`
- Parser: `utils/bank_parser.py` (różne funkcje dla ING/PayPal/Revolut)
- JavaScript: `static/js/pages/admin/bank-import.js`

---

#### 5.2.9 Warehouse - Products List

**User Story:** _Jako administrator, chcę zarządzać produktami w magazynie._

**Acceptance Criteria:**
- **Tabela produktów:**
  - Kolumny:
    - Miniatura zdjęcia
    - Nazwa
    - SKU
    - EAN
    - Kategoria
    - Cena sprzedaży
    - Cena zakupu (tylko admin)
    - Marża % (tylko admin)
    - Stan magazynowy
    - Status (Aktywny/Nieaktywny)
    - Akcje (Edytuj, Usuń)
  - Paginacja (50 na stronę)
  - Sortowanie
- **Filtry:**
  - Kategoria
  - Producent
  - Status
  - Stan magazynowy (>0, =0, <min)
  - Tagi
- **Wyszukiwanie:**
  - Nazwa, SKU, EAN
- **Przycisk "Dodaj produkt"** → `/admin/products/create`

**Technical Details:**
- Route: `GET /admin/products`
- Template: `templates/admin/warehouse/products_list.html`

---

#### 5.2.10 Warehouse - Product Form (Create/Edit)

**User Story:** _Jako administrator, chcę dodać nowy produkt lub edytować istniejący._

**Acceptance Criteria:**
- **Formularz produktu** (accordiony/tabs):
  
  **Tab 1: Podstawowe informacje**
  - Nazwa produktu (required)
  - SKU (auto-generated lub manual)
  - EAN
  - Kategoria (dropdown z hierarchią)
  - Producent (input text)
  - Seria produktowa (input text)
  - Opis (textarea/rich text editor)
  - Status (Aktywny/Nieaktywny)

  **Tab 2: Wymiary i waga**
  - Długość (cm)
  - Szerokość (cm)
  - Wysokość (cm)
  - Waga (kg)

  **Tab 3: Ceny i magazyn**
  - Cena sprzedaży (PLN) (required)
  - Cena zakupu:
    - Input number
    - Dropdown: KRW / USD / PLN
    - **Live preview:** "≈ 450.00 PLN" (przeliczenie na żywo)
    - Przy zapisie: Pobierz kurs z API, zapisz `purchase_price_pln`
  - Marża % (obliczona automatycznie: `(sale_price - purchase_price_pln) / purchase_price_pln * 100`)
  - Stan magazynowy (ilość)
  - Dostawca (dropdown) - **Tylko admin widzi**

  **Tab 4: Media**
  - Upload zdjęć (multi-upload)
  - Preview miniaturek
  - Zaznaczenie głównego zdjęcia
  - Drag & drop do zmiany kolejności
  - Automatyczna kompresja przy upload (max 1600px dłuższy bok, 72 DPI)

  **Tab 5: Warianty**
  - Pole: "Grupa wariantów" (text input)
  - Lista innych produktów z tej samej grupy (jeśli istnieją)

  **Tab 6: Tagi**
  - Multi-select checkbox z tagami
  - Możliwość dodania nowego taga (admin)

- **Walidacja:**
  - Nazwa, cena sprzedaży - required
  - SKU - unikalny
  - EAN - jeśli podany, musi być poprawny (13 cyfr)

- **Uprawnienia:**
  - **Admin:** Widzi wszystkie pola
  - **Mod:** NIE widzi: Cena zakupu, Dostawca, Marża

**Technical Details:**
- Routes:
  - `GET/POST /admin/products/create`
  - `GET/POST /admin/products/<id>/edit`
- Template: `templates/admin/warehouse/product_form.html`
- JavaScript: `static/js/pages/admin/products-form.js`
  - Live currency conversion (fetch exchange rate)
  - Image upload/preview
  - Auto-calculate margin
- Image processing: `utils/image_processor.py` (Pillow)

---

#### 5.2.11 Settings

**User Story:** _Jako administrator, chcę zarządzać ustawieniami aplikacji._

**Acceptance Criteria:**
- **Tabs/Accordiony:**

  **Tab 1: Ogólne**
  - Nazwa firmy
  - Adres
  - NIP
  - REGON
  - Email kontaktowy
  - Telefon kontaktowy

  **Tab 2: Email (SMTP)**
  - SMTP Host
  - SMTP Port
  - SMTP Username
  - SMTP Password (masked input)
  - SMTP Use TLS (checkbox)
  - Email nadawcy (From)
  - Przycisk "Test połączenia" (wysyła testowy email)

  **Tab 3: Kategorie**
  - Hierarchiczna lista kategorii (drzewko)
  - Możliwość dodawania/edytowania/usuwania
  - Drag & drop do zmiany kolejności

  **Tab 4: Tagi**
  - Lista tagów
  - Dodaj nowy tag (input + przycisk)
  - Usuń tag (z potwierdzeniem)

  **Tab 5: Dostawcy**
  - Lista dostawców
  - Formularz: Nazwa, Email, Telefon, Kraj, Notatki
  - Dodaj/Edytuj/Usuń

  **Tab 6: Szablony emaili**
  - Lista szablonów (registration, password_reset, order_confirmation, etc.)
  - Każdy szablon:
    - Temat
    - Treść HTML (rich text editor)
    - Treść plain text
    - Dostępne zmienne (placeholders): `{customer_name}`, `{order_number}`, etc.
    - Preview

- **Zapisanie:**
  - Wszystkie ustawienia zapisywane w tabeli `settings`
  - Activity log: "Settings updated"
  - Toast: "Ustawienia zostały zapisane"

**Technical Details:**
- Route: `GET/POST /admin/settings`
- Template: `templates/admin/settings/general.html` + inne
- JavaScript: `static/js/pages/admin/settings.js`

---

#### 5.2.12 Statistics

**User Story:** _Jako administrator, chcę widzieć statystyki sprzedaży._

**Acceptance Criteria:**
- **Filtry:**
  - Zakres dat (od-do)
  - Typ zamówienia (Standard/Exclusive/Wszystkie)
  - Status zamówienia (multi-select)
- **Metryki:**
  - Liczba zamówień
  - Przychód (suma)
  - Średnia wartość zamówienia
  - Liczba unikalnych klientów
- **Wykresy:**
  - Sprzedaż w czasie (wykres liniowy)
  - Top 10 produktów (wykres słupkowy)
  - Zamówienia wg statusu (wykres kołowy)
- **Export:**
  - Przycisk "Export do CSV"
  - Przycisk "Export do PDF"

**Technical Details:**
- Route: `GET /admin/statistics`
- Template: `templates/admin/statistics.html`
- Charts: Chart.js
- Export: Biblioteka Python (pandas dla CSV, ReportLab dla PDF)

---

#### 5.2.13 Activity Log (Admin)

**User Story:** _Jako administrator, chcę widzieć historię wszystkich akcji w systemie._

**Acceptance Criteria:**
- **Tabela logów:**
  - Kolumny:
    - Data i czas
    - Użytkownik (kto wykonał akcję)
    - Akcja (np. "order_status_change", "product_created")
    - Encja (np. "Order #ST/00000123")
    - Szczegóły (co się zmieniło: "Status: Nowe → Oczekujące")
    - IP Address
  - Paginacja (100 na stronę)
  - Sortowanie po dacie (najnowsze pierwsze)
- **Filtry:**
  - Użytkownik (dropdown)
  - Akcja (multi-select)
  - Typ encji (Order, Product, User, etc.)
  - Zakres dat
- **Wyszukiwanie:**
  - Po ID encji, użytkowniku

**Technical Details:**
- Route: `GET /admin/activity-log`
- Template: `templates/admin/activity_log.html`
- Tylko admin ma dostęp

---

### 5.3 Client Panel

#### 5.3.1 Client Dashboard

**User Story:** _Jako klient, chcę zobaczyć przegląd moich zamówień i aktywności._

**Acceptance Criteria:**
- **Kafelki:**
  - Liczba zamówień (ogółem)
  - Zamówienia w trakcie realizacji
  - Zamówienia dostarczone
  - Ostatnie zamówienie (data)
- **Sekcja "Moje ostatnie zamówienia":**
  - 5 najnowszych zamówień
  - Kolumny: Numer, Status, Data, Kwota
  - Link "Zobacz wszystkie zamówienia"
- **Sekcja "Szybkie akcje":**
  - Przycisk "Nowe zamówienie"
  - Przycisk "Zlecenie wysyłki"

**Technical Details:**
- Route: `GET /client/dashboard`
- Template: `templates/client/dashboard.html`

---

#### 5.3.2 New Order

**User Story:** _Jako klient, chcę złożyć nowe zamówienie._

**Acceptance Criteria:**
- **Strona zamówienia:**
  - Lista produktów (z możliwością wyszukiwania/filtrowania)
  - Każdy produkt:
    - Miniatura
    - Nazwa
    - Cena
    - Przycisk "Dodaj do zamówienia"
  - Koszyk (sidebar/floating):
    - Lista dodanych produktów
    - Możliwość zmiany ilości
    - Usunięcie produktu
    - Suma
  - Formularz:
    - Notatka do zamówienia (textarea, opcjonalnie)
  - Przycisk "Złóż zamówienie"
- **Po złożeniu:**
  - Zamówienie zapisane z statusem "Nowe"
  - Email do klienta (potwierdzenie)
  - Email do admina (nowe zamówienie)
  - Redirect na szczegóły zamówienia
  - Toast: "Zamówienie zostało złożone. Numer: ST/00000123"

**Technical Details:**
- Route: `GET/POST /client/orders/new`
- Template: `templates/client/orders/new.html`
- JavaScript: `static/js/pages/client/new-order.js` (koszyk logic)

---

#### 5.3.3 Order History (Client)

**User Story:** _Jako klient, chcę widzieć historię moich zamówień._

**Acceptance Criteria:**
- **Tabela zamówień:**
  - Kolumny:
    - Numer zamówienia (link do szczegółów)
    - Status (badge)
    - Typ (Standard / Exclusive)
    - Data
    - Kwota
  - Paginacja (20 na stronę)
- **Filtry:**
  - Status
  - Zakres dat
- **Szczegóły zamówienia (widok klienta):**
  - Jak w admin, ale:
    - Brak opcji edycji statusu
    - Brak informacji o cenach zakupu
    - Możliwość dodawania komentarzy
    - Widoczny tracking (jeśli dodany)

**Technical Details:**
- Route: `GET /client/orders`
- Template: `templates/client/orders/list.html`

---

#### 5.3.4 Shipping Request

**User Story:** _Jako klient, chcę zlecić wysyłkę zamówień, które są gotowe do wysłania._

**Acceptance Criteria:**
- **Lista zamówień do wysłania:**
  - Tylko zamówienia w statusach:
    - "Dostarczone do GOM"
    - "Do pakowania"
    - "Spakowane"
  - Tabela:
    - Checkbox
    - Numer zamówienia
    - Status
    - Liczba produktów
    - Waga szacunkowa (suma wag produktów)
  - Zaznaczenie zamówień
  - Przycisk "Zleć wysyłkę"
- **Po kliknięciu:**
  - W zamówieniach: `shipping_requested = TRUE`, `shipping_requested_at = NOW()`
  - Powiadomienie dla admina (email / na dashboardzie)
  - Activity log
  - Toast: "Zlecenie wysyłki zostało wysłane"

**Technical Details:**
- Route: `GET/POST /client/shipping/request`
- Template: `templates/client/shipping/request.html`
- JavaScript: `static/js/pages/client/shipping-request.js`

---

#### 5.3.5 Exclusive Orders (Client)

**User Story:** _Jako klient, chcę widzieć swoje zamówienia złożone przez strony Exclusive._

**Acceptance Criteria:**
- **Lista zamówień Exclusive:**
  - Tylko zamówienia gdzie `is_exclusive = TRUE`
  - Kolumny jak w "Order History"
  - Oznaczenie z jakiej strony Exclusive pochodzi zamówienie

**Technical Details:**
- Route: `GET /client/orders/exclusive`
- Template: `templates/client/exclusive/list.html`

---

#### 5.3.6 Order Templates

**User Story:** _Jako klient, chcę zapisać szablon zamówienia i móc go szybko użyć._

**Acceptance Criteria:**
- **Lista szablonów:**
  - Nazwa szablonu
  - Liczba produktów
  - Data utworzenia
  - Akcje: Użyj, Edytuj, Usuń
- **Tworzenie szablonu:**
  - Podczas składania zamówienia: Checkbox "Zapisz jako szablon"
  - Modal: Nazwa szablonu
  - Po zapisie: Szablon dostępny na liście
- **Użycie szablonu:**
  - Kliknięcie "Użyj" → Produkty z szablonu dodane do koszyka
  - Możliwość modyfikacji przed złożeniem zamówienia

**Technical Details:**
- Routes:
  - `GET /client/orders/templates` (lista)
  - `POST /client/orders/templates/create` (tworzenie)
  - `POST /client/orders/templates/<id>/use` (użycie)
- Template: `templates/client/orders/templates.html`

---

#### 5.3.7 Profile Settings

**User Story:** _Jako klient, chcę zarządzać swoim profilem._

**Acceptance Criteria:**
- **Formularz:**
  - Imię
  - Nazwisko
  - Email (z walidacją unikalności)
  - Telefon
  - Zmiana hasła:
    - Stare hasło
    - Nowe hasło
    - Potwierdzenie nowego hasła
- **Zapisanie:**
  - Walidacja
  - Update w bazie
  - Activity log: "Profile updated"
  - Toast: "Profil został zaktualizowany"

**Technical Details:**
- Route: `GET/POST /client/profile`
- Template: `templates/client/profile.html`

---

### 5.4 Exclusive Order Page (Public)

**User Story:** _Jako osoba z linkiem Exclusive, chcę złożyć zamówienie bez logowania (jako gość) lub po zalogowaniu._

**Acceptance Criteria:**
- **Dostęp:**
  - URL: `/exclusive/<token>`
  - Jeśli token nieprawidłowy lub strona nieaktywna → 404
  - Jeśli wygasła → komunikat "Link wygasł"
- **Strona:**
  - Nagłówek: Nazwa strony Exclusive
  - Opis (jeśli dodany)
  - Lista dostępnych produktów (tylko te przypisane do strony):
    - Miniatura
    - Nazwa
    - Cena
    - Przycisk "Dodaj"
  - Koszyk (jak w New Order)
- **Złożenie zamówienia:**
  - **Jeśli zalogowany:**
    - Przycisk "Złóż zamówienie"
    - Standardowy flow (jak /client/orders/new)
    - `is_exclusive = TRUE`, `exclusive_page_id = <id>`
  - **Jeśli niezalogowany:**
    - Formularz:
      - Imię i nazwisko
      - Email
      - Telefon
      - Checkbox "Chcę założyć konto" (opcjonalnie)
    - Przycisk "Złóż zamówienie jako gość"
    - Po złożeniu:
      - Zamówienie zapisane jako `is_guest_order = TRUE`
      - Dane gościa w polach `guest_*`
      - Email do gościa (potwierdzenie) + instrukcja jak założyć konto
      - Email do admina
      - Strona "Dziękujemy za zamówienie" z numerem zamówienia

**Technical Details:**
- Route: `GET/POST /exclusive/<token>`
- Template: `templates/exclusive/order_page.html`
- JavaScript: `static/js/pages/exclusive-order.js`

---

### 5.5 Email Module

**User Story:** _Jako system, chcę wysyłać emaile przy określonych zdarzeniach._

**Email Templates:**

1. **Registration Confirmation**
   - Trigger: Po rejestracji użytkownika
   - Subject: "Witaj w ThunderOrders! Potwierdź swój email"
   - Content: Link aktywacyjny, instrukcje

2. **Password Reset**
   - Trigger: Po żądaniu resetu hasła
   - Subject: "Reset hasła - ThunderOrders"
   - Content: Link do resetowania, ważny 1h

3. **Order Confirmation (Client)**
   - Trigger: Po złożeniu zamówienia przez klienta
   - Subject: "Potwierdzenie zamówienia {order_number}"
   - Content: Szczegóły zamówienia, produkty, suma

4. **New Order (Admin)**
   - Trigger: Po złożeniu zamówienia
   - Subject: "Nowe zamówienie {order_number}"
   - Content: Klient, produkty, link do zamówienia w panelu admin

5. **Order Status Change**
   - Trigger: Zmiana statusu zamówienia
   - Subject: "Twoje zamówienie {order_number} - {status}"
   - Content: Nowy status, tracking (jeśli dodany), instrukcje

6. **Order Comment**
   - Trigger: Dodanie komentarza do zamówienia
   - Subject: "Nowy komentarz do zamówienia {order_number}"
   - Content: Treść komentarza, link do zamówienia

7. **Refund Notification**
   - Trigger: Wydanie zwrotu
   - Subject: "Zwrot środków - zamówienie {order_number}"
   - Content: Kwota zwrotu, powód, instrukcje

**Technical Details:**
- Moduł: `modules/emails/`
- Konfiguracja SMTP w `settings` (baza danych)
- Templates w `email_templates` (baza danych)
- Wysyłanie: Flask-Mail
- Funkcja pomocnicza: `send_email(to, template_type, context)`

---

### 5.6 Global Search

**User Story:** _Jako użytkownik, chcę szybko wyszukać zamówienie/produkt/klienta z dowolnego miejsca w aplikacji._

**Acceptance Criteria:**
- **Skrót klawiszowy:** `Cmd/Ctrl + K` → Otwiera modal wyszukiwania
- **Modal:**
  - Input z autofocus
  - Wyszukiwanie w czasie rzeczywistym (debounce 300ms)
  - Wyniki pogrupowane:
    - Zamówienia (max 5):
      - Numer zamówienia
      - Klient
      - Status
      - Link: `/admin/orders/<id>` lub `/client/orders/<id>`
    - Produkty (max 5):
      - Miniatura
      - Nazwa
      - SKU
      - Link: `/admin/products/<id>/edit`
    - Klienci (max 5) - tylko admin/mod:
      - Imię i nazwisko
      - Email
      - Link: `/admin/clients/<id>`
  - Nawigacja strzałkami (↑↓)
  - Enter → Przejdź do pierwszego wyniku
  - Esc → Zamknij modal
- **Wyszukiwanie po:**
  - Zamówienia: Numer, nazwisko klienta, email klienta
  - Produkty: Nazwa, SKU, EAN
  - Klienci: Imię, nazwisko, email

**Technical Details:**
- Route: `GET /api/search?q=<query>`
- JavaScript: `static/js/components/global-search.js`
- HTMX: `hx-get="/api/search" hx-trigger="keyup changed delay:300ms"`
- Modal: Część `base.html`

---

### 5.7 Multi-Currency Calculator

**User Story:** _Jako administrator, podczas dodawania/edycji produktu chcę łatwo przeliczyć cenę z KRW/USD na PLN._

**Acceptance Criteria:**
- **W formularzu produktu:**
  - Pole "Cena zakupu" (number input)
  - Dropdown: KRW / USD / PLN
  - **Live preview:** Obok wyświetla się `"≈ 450.00 PLN"`
  - Przy zmianie wartości/waluty → Natychmiast przelicza (bez przeładowania strony)
- **Źródło kursów:**
  - API: NBP (https://api.nbp.pl/) lub ExchangeRate-API (https://www.exchangerate-api.com/)
  - Cache kursu: 24h (zapisany w `settings`)
  - Jeśli API niedostępne → użyj ostatniego zapisanego kursu + warning
- **Przy zapisie produktu:**
  - Zapisz: `purchase_price`, `purchase_currency`, `purchase_price_pln`
  - Oblicz i zapisz `margin`

**Technical Details:**
- JavaScript: `static/js/pages/admin/products-form.js`
- Funkcja: `calculatePLN(amount, currency)`
- API endpoint: `/api/exchange-rate?currency=KRW` (zwraca kurs)
- Backend: `utils/currency.py`

---

## 6. File Structure

```
thunder_orders/
│
├── app.py                          # Główny plik aplikacji z lazy loading blueprintów
├── config.py                       # Konfiguracja aplikacji (Development/Production)
├── .env                            # Wrażliwe dane (nie commitowane do repo)
├── .env.example                    # Przykładowy plik .env do dokumentacji
├── requirements.txt                # Zależności Python
├── README.md                       # Dokumentacja projektu
│
├── database/
│   ├── schema.sql                  # Schemat bazy danych
│   └── migrations/                 # Migracje bazy danych
│       └── 001_initial_schema.sql
│
├── modules/                        # Moduły aplikacji (blueprints)
│   │
│   ├── auth/                       # Moduł autentykacji
│   │   ├── __init__.py
│   │   ├── routes.py              # Endpointy logowania/rejestracji
│   │   ├── models.py              # Model User, Role
│   │   └── forms.py               # Formularze logowania/rejestracji
│   │
│   ├── admin/                      # Panel administratora
│   │   ├── __init__.py
│   │   ├── routes.py              # Routing panelu admin
│   │   ├── dashboard.py           # Dashboard - statystyki
│   │   ├── orders.py              # Zarządzanie zamówieniami
│   │   ├── clients.py             # Zarządzanie klientami
│   │   ├── wms.py                 # Moduł WMS - zbieranie produktów
│   │   ├── exclusive.py           # Zarządzanie stronami exclusive
│   │   ├── imports.py             # Import przelewów bankowych
│   │   ├── warehouse.py           # Zarządzanie magazynem
│   │   ├── settings.py            # Ustawienia aplikacji
│   │   └── statistics.py          # Statystyki sprzedaży
│   │
│   ├── client/                     # Panel klienta
│   │   ├── __init__.py
│   │   ├── routes.py              # Routing panelu klienta
│   │   ├── dashboard.py           # Dashboard klienta
│   │   ├── orders.py              # Historia zamówień
│   │   ├── new_order.py           # Nowe zamówienie
│   │   ├── shipping.py            # Zlecenie wysyłki
│   │   ├── exclusive.py           # Zamówienia exclusive
│   │   └── profile.py             # Ustawienia profilu
│   │
│   ├── products/                   # Moduł produktów
│   │   ├── __init__.py
│   │   ├── routes.py              # CRUD produktów
│   │   ├── models.py              # Model Product, Category, Variant
│   │   ├── forms.py               # Formularze produktów
│   │   └── utils.py               # Pomocnicze funkcje (kompresja zdjęć)
│   │
│   ├── orders/                     # Moduł zamówień
│   │   ├── __init__.py
│   │   ├── routes.py              # CRUD zamówień
│   │   ├── models.py              # Model Order, OrderItem, OrderStatus
│   │   ├── forms.py               # Formularze zamówień
│   │   └── utils.py               # Funkcje pomocnicze (numeracja, statusy)
│   │
│   ├── exclusive/                  # Moduł stron exclusive
│   │   ├── __init__.py
│   │   ├── routes.py              # Generowanie i obsługa exclusive pages
│   │   ├── models.py              # Model ExclusivePage, GuestOrder
│   │   └── forms.py               # Formularz zamówienia (z/bez logowania)
│   │
│   ├── emails/                     # Moduł emaili
│   │   ├── __init__.py
│   │   ├── routes.py              # Endpointy testowania emaili (admin)
│   │   ├── sender.py              # Funkcje wysyłające emaile
│   │   └── templates.py           # Rendering email templates z bazy
│   │
│   └── api/                        # API wewnętrzne
│       ├── __init__.py
│       ├── search.py              # Global search endpoint
│       ├── currency.py            # Exchange rate endpoint
│       └── routes.py              # Inne endpointy API
│
├── templates/                      # Szablony HTML (Jinja2)
│   │
│   ├── base.html                  # Główny szablon bazowy
│   ├── _macros.html               # Makra Jinja2 (komponenty wielokrotnego użytku)
│   │
│   ├── auth/                      # Szablony autentykacji
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── forgot_password.html
│   │   └── reset_password.html
│   │
│   ├── admin/                     # Szablony panelu admin
│   │   ├── base_admin.html       # Bazowy szablon admin (extends base.html)
│   │   ├── dashboard.html
│   │   ├── orders/
│   │   │   ├── list.html         # Lista zamówień
│   │   │   ├── detail.html       # Szczegóły zamówienia
│   │   │   └── wms.html          # Interfejs WMS
│   │   ├── clients/
│   │   │   ├── list.html
│   │   │   └── detail.html
│   │   ├── exclusive/
│   │   │   ├── list.html
│   │   │   ├── create.html
│   │   │   └── edit.html
│   │   ├── warehouse/
│   │   │   ├── products_list.html
│   │   │   ├── product_form.html
│   │   │   └── stock_orders.html
│   │   ├── imports/
│   │   │   └── bank_imports.html
│   │   ├── settings/
│   │   │   ├── general.html
│   │   │   ├── categories.html
│   │   │   ├── tags.html
│   │   │   └── suppliers.html
│   │   ├── statistics.html
│   │   └── activity_log.html
│   │
│   ├── client/                    # Szablony panelu klienta
│   │   ├── base_client.html      # Bazowy szablon klienta (extends base.html)
│   │   ├── dashboard.html
│   │   ├── orders/
│   │   │   ├── new.html
│   │   │   ├── list.html
│   │   │   ├── detail.html
│   │   │   └── templates.html    # Order templates
│   │   ├── shipping/
│   │   │   └── request.html      # Zlecenie wysyłki
│   │   ├── exclusive/
│   │   │   └── list.html
│   │   └── profile.html
│   │
│   ├── exclusive/                 # Szablony stron exclusive (publiczne)
│   │   └── order_page.html       # Formularz zamówienia exclusive
│   │
│   ├── components/                # Komponenty wielokrotnego użytku
│   │   ├── sidebar_admin.html
│   │   ├── sidebar_client.html
│   │   ├── navbar.html
│   │   ├── footer.html
│   │   ├── alerts.html
│   │   ├── toast.html
│   │   └── modals/
│   │       ├── confirm_delete.html
│   │       └── product_preview.html
│   │
│   └── errors/                    # Strony błędów
│       ├── 403.html
│       ├── 404.html
│       └── 500.html
│
├── static/                        # Pliki statyczne
│   │
│   ├── css/
│   │   ├── core/
│   │   │   ├── reset.css
│   │   │   ├── variables.css     # Paleta ThunderOrders
│   │   │   ├── typography.css
│   │   │   └── layout.css
│   │   ├── components/
│   │   │   ├── buttons.css
│   │   │   ├── forms.css
│   │   │   ├── cards.css
│   │   │   ├── tables.css
│   │   │   ├── modals.css
│   │   │   ├── toasts.css
│   │   │   ├── dropdowns.css
│   │   │   ├── badges.css
│   │   │   ├── sidebar.css
│   │   │   ├── navbar.css
│   │   │   └── alerts.css
│   │   ├── pages/
│   │   │   ├── auth/
│   │   │   │   └── login.css
│   │   │   ├── admin/
│   │   │   │   ├── dashboard.css
│   │   │   │   ├── orders-list.css
│   │   │   │   ├── order-detail.css
│   │   │   │   ├── wms.css
│   │   │   │   ├── products.css
│   │   │   │   └── statistics.css
│   │   │   └── client/
│   │   │       ├── dashboard.css
│   │   │       ├── orders.css
│   │   │       └── profile.css
│   │   ├── vendor/
│   │   │   └── tailwind.min.css
│   │   └── main.css              # Import wszystkich core + components
│   │
│   ├── js/
│   │   ├── core/
│   │   │   ├── app.js
│   │   │   ├── htmx-config.js
│   │   │   └── csrf.js
│   │   ├── components/
│   │   │   ├── toast.js          # Globalny toast system
│   │   │   ├── modal.js          # Globalny modal system
│   │   │   ├── dropdown.js
│   │   │   ├── sidebar.js
│   │   │   ├── confirm.js
│   │   │   ├── tabs.js
│   │   │   └── image-preview.js
│   │   ├── utils/
│   │   │   ├── api.js
│   │   │   ├── validators.js
│   │   │   ├── formatters.js
│   │   │   ├── debounce.js
│   │   │   └── storage.js
│   │   ├── pages/
│   │   │   ├── auth/
│   │   │   │   └── register.js
│   │   │   ├── admin/
│   │   │   │   ├── dashboard.js
│   │   │   │   ├── orders-list.js
│   │   │   │   ├── order-detail.js
│   │   │   │   ├── wms.js
│   │   │   │   ├── products-form.js
│   │   │   │   ├── bank-import.js
│   │   │   │   └── exclusive-form.js
│   │   │   └── client/
│   │   │       ├── new-order.js
│   │   │       ├── shipping-request.js
│   │   │       └── profile.js
│   │   ├── vendor/
│   │   │   ├── htmx.min.js
│   │   │   └── chart.min.js
│   │   └── main.js               # Master loader
│   │
│   ├── img/
│   │   ├── logo.svg
│   │   └── placeholders/
│   │
│   └── uploads/
│       ├── products/
│       │   ├── original/
│       │   └── compressed/
│       └── imports/
│
├── utils/                         # Funkcje pomocnicze
│   ├── __init__.py
│   ├── decorators.py             # Dekoratory (role_required, etc.)
│   ├── validators.py             # Walidatory formularzy
│   ├── image_processor.py        # Kompresja i przetwarzanie zdjęć
│   ├── email_sender.py           # Wysyłanie emaili
│   ├── bank_parser.py            # Parsowanie wyciągów bankowych
│   ├── currency.py               # API kursów walut
│   ├── activity_logger.py        # Logging do activity_log
│   └── helpers.py                # Ogólne helpery
│
├── tests/                         # Testy jednostkowe
│   ├── __init__.py
│   ├── test_auth.py
│   ├── test_orders.py
│   └── test_products.py
│
└── logs/
    └── app.log
```

---

## 7. UI/UX Guidelines

### 7.1 Color Palette - ThunderOrders

**Główne kolory marki:**

```css
/* Pomarańczowe (akcenty, CTA) */
--orange-100: #FF6D00;
--orange-200: #FF7900;
--orange-300: #FF8500;
--orange-400: #FF9100;
--orange-500: #FF9E00;

/* Fioletowe (główne, tła) */
--purple-100: #240046;
--purple-200: #3C096C;
--purple-300: #5A189A;
--purple-400: #7B2CBF;
--purple-500: #9D4EDD;

/* Neutralne */
--black: #000000;
--white: #FFFFFF;
--gray-100: #F5F5F5;
--gray-200: #E0E0E0;
--gray-300: #BDBDBD;
--gray-400: #9E9E9E;
--gray-500: #757575;
--gray-600: #616161;
--gray-700: #424242;
--gray-800: #212121;

/* Semantyczne */
--success: #4CAF50;
--warning: #FFC107;
--error: #F44336;
--info: #2196F3;
```

**Użycie:**
- **Sidebar admin:** `background: var(--purple-100)`, text: `var(--white)`
- **Sidebar client:** `background: var(--purple-200)`, text: `var(--white)`
- **Przyciski główne (CTA):** `background: var(--orange-300)`, hover: `var(--orange-400)`
- **Przyciski drugorzędne:** `border: var(--purple-300)`, text: `var(--purple-300)`
- **Badges statusów:**
  - "Nowe": `var(--info)`
  - "Oczekujące": `var(--orange-300)`
  - "W realizacji": `var(--purple-400)`
  - "Wysłane": `var(--purple-500)`
  - "Dostarczone": `var(--success)`
  - "Anulowane": `var(--gray-500)`
  - "Do zwrotu": `var(--warning)`
  - "Zwrócone": `var(--error)`

---

### 7.2 Typography

```css
/* Font Family */
--font-primary: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
--font-mono: 'Fira Code', 'Courier New', monospace;

/* Font Sizes */
--text-xs: 0.75rem;    /* 12px */
--text-sm: 0.875rem;   /* 14px */
--text-base: 1rem;     /* 16px */
--text-lg: 1.125rem;   /* 18px */
--text-xl: 1.25rem;    /* 20px */
--text-2xl: 1.5rem;    /* 24px */
--text-3xl: 1.875rem;  /* 30px */
--text-4xl: 2.25rem;   /* 36px */

/* Font Weights */
--font-normal: 400;
--font-medium: 500;
--font-semibold: 600;
--font-bold: 700;
```

---

### 7.3 Spacing

```css
/* Spacing Scale */
--space-1: 0.25rem;   /* 4px */
--space-2: 0.5rem;    /* 8px */
--space-3: 0.75rem;   /* 12px */
--space-4: 1rem;      /* 16px */
--space-5: 1.25rem;   /* 20px */
--space-6: 1.5rem;    /* 24px */
--space-8: 2rem;      /* 32px */
--space-10: 2.5rem;   /* 40px */
--space-12: 3rem;     /* 48px */
--space-16: 4rem;     /* 64px */
```

---

### 7.4 Components Style Guide

#### Buttons

```css
/* Primary Button */
.btn-primary {
  background: var(--orange-300);
  color: var(--white);
  padding: var(--space-3) var(--space-6);
  border-radius: 6px;
  font-weight: var(--font-semibold);
  transition: all 0.2s;
}
.btn-primary:hover {
  background: var(--orange-400);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(255, 133, 0, 0.3);
}

/* Secondary Button */
.btn-secondary {
  background: transparent;
  color: var(--purple-300);
  border: 2px solid var(--purple-300);
  padding: var(--space-3) var(--space-6);
  border-radius: 6px;
  font-weight: var(--font-semibold);
}
.btn-secondary:hover {
  background: var(--purple-300);
  color: var(--white);
}

/* Danger Button */
.btn-danger {
  background: var(--error);
  color: var(--white);
}
```

#### Cards

```css
.card {
  background: var(--white);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  padding: var(--space-6);
  transition: box-shadow 0.3s;
}
.card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
}
```

#### Badges

```css
.badge {
  display: inline-block;
  padding: var(--space-1) var(--space-3);
  border-radius: 12px;
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
}

.badge-success { background: var(--success); color: white; }
.badge-warning { background: var(--warning); color: var(--gray-800); }
.badge-error { background: var(--error); color: white; }
.badge-info { background: var(--info); color: white; }
```

---

### 7.5 Layout Principles

- **Sidebar:** Fixed, width 240px, nie przeładowuje się (HTMX)
- **Main content:** `margin-left: 240px`, padding: `var(--space-8)`
- **Responsive:** Mobile: Sidebar jako drawer (hamburger menu)
- **Spacing:** Konsekwentne użycie spacing scale
- **Shadows:** Subtelne, tylko dla depth (cards, modals)
- **Borders:** `1px solid var(--gray-200)` dla separacji
- **Radius:** 6-8px dla interaktywnych elementów

---

## 8. MVP Implementation Roadmap

### 🎯 Cel MVP:
**Funkcjonalny system z podstawowymi modułami pozwalającymi na:**
- Rejestrację i logowanie użytkowników
- Zarządzanie produktami (admin)
- Składanie zamówień (client)
- Zmianę statusów zamówień (admin/mod)
- Podstawowy WMS (zbieranie produktów)
- Strony Exclusive z zamówieniami guest

---

### **ETAP 1: Project Setup & Foundation** ⏱️ 1-2 dni

**Cel:** Przygotowanie środowiska, struktury projektu, bazy danych, konfiguracji.

**Tasks:**
1. ✅ Setup repozytorium Git
2. ✅ Stwórz strukturę katalogów (zgodnie z File Structure)
3. ✅ `requirements.txt` - dodaj wszystkie dependencies
4. ✅ `.env.example` - szablon zmiennych środowiskowych
5. ✅ `config.py` - klasy konfiguracyjne (Development/Production)
6. ✅ `app.py` - główny plik aplikacji z Flask app factory
7. ✅ Setup MariaDB lokalnie (XAMPP/Docker)
8. ✅ `database/schema.sql` - Stwórz wszystkie tabele (zgodnie z Database Schema)
9. ✅ Flask-Migrate - Inicjalizacja migracji
10. ✅ Test połączenia z bazą danych

**Deliverable:** Działająca aplikacja Flask z połączeniem do bazy MariaDB

---

### **ETAP 2: Authentication Module** ⏱️ 2-3 dni

**Cel:** Pełna funkcjonalność logowania, rejestracji, resetu hasła, rate limiting.

**Tasks:**
1. ✅ `modules/auth/__init__.py` - Blueprint auth
2. ✅ `modules/auth/models.py` - Model `User`
   - Wszystkie pola z database schema
   - Metody: `set_password()`, `check_password()`, `generate_reset_token()`
3. ✅ `modules/auth/forms.py` - WTForms:
   - LoginForm
   - RegisterForm
   - ForgotPasswordForm
   - ResetPasswordForm
4. ✅ `modules/auth/routes.py` - Endpointy:
   - `/auth/login` (GET, POST)
   - `/auth/register` (GET, POST)
   - `/auth/logout` (GET)
   - `/auth/forgot-password` (GET, POST)
   - `/auth/reset-password/<token>` (GET, POST)
5. ✅ Templates:
   - `templates/auth/login.html`
   - `templates/auth/register.html`
   - `templates/auth/forgot_password.html`
   - `templates/auth/reset_password.html`
6. ✅ Rate Limiting Logic:
   - Model `LoginAttempts`
   - Funkcja `check_login_attempts(email, ip)`
   - Funkcja `record_login_attempt(email, ip, success)`
7. ✅ Flask-Login setup w `app.py`
8. ✅ Test: Rejestracja → Email verification link (mock) → Login → Session

**Deliverable:** Pełna autentykacja z rate limiting

---

### **ETAP 3: Base Templates & UI Components** ⏱️ 2 dni

**Cel:** Stworzenie bazowych szablonów, sidebara, navbara, komponentów globalnych (toast, modal).

**Tasks:**
1. ✅ `templates/base.html` - Główny szablon:
   - HTML structure
   - Import CSS (`main.css`, Tailwind)
   - Import JS (`htmx.min.js`, `main.js`)
   - Toast container
   - Modal container
   - `{% block content %}`
2. ✅ `templates/admin/base_admin.html` - extends `base.html`
   - Include `sidebar_admin.html`
   - Main content wrapper
3. ✅ `templates/client/base_client.html` - extends `base.html`
   - Include `sidebar_client.html`
4. ✅ `templates/components/sidebar_admin.html`
   - Menu links (Dashboard, Zamówienia, Klienci, Magazyn, Ustawienia, Statystyki)
   - Active link highlighting
5. ✅ `templates/components/sidebar_client.html`
   - Menu links (Dashboard, Nowe zamówienie, Historia, Zlecenie wysyłki, Profil)
6. ✅ CSS:
   - `static/css/core/variables.css` - Paleta ThunderOrders
   - `static/css/components/sidebar.css`
   - `static/css/components/toasts.css`
   - `static/css/components/modals.css`
   - `static/css/main.css` - Import wszystkich
7. ✅ JavaScript:
   - `static/js/components/toast.js` - Globalny toast system
   - `static/js/components/modal.js` - Globalny modal system
   - `static/js/core/htmx-config.js` - HTMX event handlers
   - `static/js/main.js` - Import i expose globalnie
8. ✅ HTMX config - Sidebar nie przeładowuje się (target: `#main-content`)

**Deliverable:** Działające szablony bazowe z nawigacją i komponentami globalnymi

---

### **ETAP 4: Admin & Client Dashboard (Empty)** ⏱️ 1 dzień

**Cel:** Podstawowe panele admin/client (pusty dashboard na razie).

**Tasks:**
1. ✅ `modules/admin/__init__.py` - Blueprint admin
2. ✅ `modules/admin/routes.py` - Route: `/admin/dashboard`
   - @login_required
   - @role_required('admin', 'mod')
3. ✅ `templates/admin/dashboard.html` - Pusty dashboard (placeholder)
4. ✅ `modules/client/__init__.py` - Blueprint client
5. ✅ `modules/client/routes.py` - Route: `/client/dashboard`
   - @login_required
6. ✅ `templates/client/dashboard.html` - Pusty dashboard (placeholder)
7. ✅ `utils/decorators.py`:
   - `@role_required('admin', 'mod')`
   - Redirect na 403 jeśli brak uprawnień
8. ✅ Redirect po loginie:
   - Admin/Mod → `/admin/dashboard`
   - Client → `/client/dashboard`

**Deliverable:** Działające panele z nawigacją

---

### **ETAP 5: Products Module (CRUD)** ⏱️ 3-4 dni

**Cel:** Pełne zarządzanie produktami (dodawanie, edytowanie, usuwanie, upload zdjęć).

**Tasks:**
1. ✅ `modules/products/models.py`:
   - Model `Product` (wszystkie pola z schema)
   - Model `Category` (self-reference dla hierarchii)
   - Model `Tag`
   - Model `ProductTag` (junction)
   - Model `ProductImage`
   - Model `Supplier`
2. ✅ `modules/products/forms.py`:
   - ProductForm (wszystkie pola, walidacje)
   - CategoryForm
   - TagForm
   - SupplierForm
3. ✅ `modules/admin/warehouse.py`:
   - Route: `/admin/products` (lista produktów)
   - Route: `/admin/products/create` (dodaj produkt)
   - Route: `/admin/products/<id>/edit` (edytuj)
   - Route: `/admin/products/<id>/delete` (usuń)
4. ✅ Templates:
   - `templates/admin/warehouse/products_list.html` (tabela + filtry)
   - `templates/admin/warehouse/product_form.html` (tabs/accordiony)
5. ✅ `utils/image_processor.py`:
   - Funkcja: `compress_image(file, max_size=1600, dpi=72)`
   - Zapisz oryginał + compressed
6. ✅ JavaScript:
   - `static/js/pages/admin/products-form.js`:
     - Image upload preview
     - Drag & drop sort
     - Multi-currency calculator (live preview)
7. ✅ CSS:
   - `static/css/pages/admin/products.css`
8. ✅ Test: Dodaj produkt → Upload zdjęcia → Zapisz → Edytuj → Usuń

**Deliverable:** Pełny CRUD produktów z upload zdjęć

---

### **ETAP 6: Categories, Tags, Suppliers (Settings)** ⏱️ 1-2 dni

**Cel:** Zarządzanie kategoriami, tagami, dostawcami w ustawieniach.

**Tasks:**
1. ✅ `modules/admin/settings.py`:
   - Route: `/admin/settings`
   - Tab: Categories (CRUD)
   - Tab: Tags (CRUD)
   - Tab: Suppliers (CRUD)
2. ✅ Templates:
   - `templates/admin/settings/categories.html`
   - `templates/admin/settings/tags.html`
   - `templates/admin/settings/suppliers.html`
3. ✅ JavaScript:
   - Drag & drop dla kategorii (zmiana kolejności/hierarchii)

**Deliverable:** Zarządzanie kategoriami/tagami/dostawcami

---

### **ETAP 7: Orders Module - Client (New Order)** ⏱️ 2-3 dni

**Cel:** Klient może składać nowe zamówienia.

**Tasks:**
1. ✅ `modules/orders/models.py`:
   - Model `Order` (wszystkie pola)
   - Model `OrderItem`
2. ✅ `modules/client/new_order.py`:
   - Route: `/client/orders/new` (GET, POST)
   - Logic:
     - Lista produktów (filtry, search)
     - Koszyk (session-based)
     - Submit → Zapisz zamówienie + order_items
     - Generuj `order_number` (format: ST/00000001)
     - Status: "Nowe"
3. ✅ Templates:
   - `templates/client/orders/new.html`
4. ✅ JavaScript:
   - `static/js/pages/client/new-order.js`:
     - Koszyk logic (add, remove, update quantity)
     - Real-time suma
5. ✅ CSS:
   - `static/css/pages/client/orders.css`

**Deliverable:** Klient może składać zamówienia

---

### **ETAP 8: Orders Module - Admin (List, Detail)** ⏱️ 2-3 dni

**Cel:** Admin widzi wszystkie zamówienia, może je edytować, zmieniać statusy.

**Tasks:**
1. ✅ `modules/admin/orders.py`:
   - Route: `/admin/orders` (lista zamówień)
   - Route: `/admin/orders/<id>` (szczegóły zamówienia)
   - Route: `/admin/orders/<id>/status` (POST - zmiana statusu)
2. ✅ Templates:
   - `templates/admin/orders/list.html` (tabela + filtry + bulk actions UI)
   - `templates/admin/orders/detail.html` (wszystkie sekcje)
3. ✅ JavaScript:
   - `static/js/pages/admin/orders-list.js`:
     - Checkboxy
     - Floating toolbar (bulk actions)
   - `static/js/pages/admin/order-detail.js`:
     - Zmiana statusu (dropdown → HTMX POST)
4. ✅ CSS:
   - `static/css/pages/admin/orders-list.css`
   - `static/css/pages/admin/order-detail.css`

**Deliverable:** Admin zarządza zamówieniami

---

### **ETAP 9: Orders Module - Comments & Timeline** ⏱️ 1-2 dni

**Cel:** System komentarzy do zamówień (Admin ↔ Client).

**Tasks:**
1. ✅ `modules/orders/models.py`:
   - Model `OrderComment`
2. ✅ Route: `/admin/orders/<id>/comment` (POST)
3. ✅ Route: `/client/orders/<id>/comment` (POST)
4. ✅ Template:
   - `templates/admin/orders/detail.html` - Sekcja Timeline
   - `templates/client/orders/detail.html` - Sekcja Timeline
5. ✅ JavaScript:
   - HTMX POST komentarza
   - Real-time append do timeline

**Deliverable:** System komentarzy działa

---

### **ETAP 10: WMS Module** ⏱️ 2-3 dni

**Cel:** Admin/Mod może zbierać produkty z wielu zamówień jednocześnie (WMS Mode).

**Tasks:**
1. ✅ `modules/admin/wms.py`:
   - Route: `/admin/orders/wms?orders=1,2,3`
   - Logic:
     - Pobierz zamówienia + order_items
     - Grupuj produkty
     - Checkbox → Update `order_items.picked`
     - Progress bars
     - Przycisk "Spakuj" → Zmień status zamówień na "Spakowane"
2. ✅ Templates:
   - `templates/admin/orders/wms.html`
3. ✅ JavaScript:
   - `static/js/pages/admin/wms.js`:
     - Checkbox logic
     - Progress bars update
     - HTMX POST pick item
4. ✅ CSS:
   - `static/css/pages/admin/wms.css`

**Deliverable:** WMS działa, admin może zbierać produkty

---

### **ETAP 11: Clients Management** ⏱️ 1-2 dni

**Cel:** Admin widzi listę klientów, ich historie zamówień.

**Tasks:**
1. ✅ `modules/admin/clients.py`:
   - Route: `/admin/clients` (lista)
   - Route: `/admin/clients/<id>` (szczegóły + historia zamówień)
2. ✅ Templates:
   - `templates/admin/clients/list.html`
   - `templates/admin/clients/detail.html`
3. ✅ Test: Przejdź do klienta → Zobacz historię zamówień

**Deliverable:** Zarządzanie klientami

---

### **ETAP 12: Exclusive Pages** ⏱️ 3-4 dni

**Cel:** Admin tworzy strony Exclusive, goście/klienci mogą składać zamówienia.

**Tasks:**
1. ✅ `modules/exclusive/models.py`:
   - Model `ExclusivePage`
   - Model `ExclusiveProduct` (junction)
2. ✅ `modules/admin/exclusive.py`:
   - Route: `/admin/exclusive` (lista)
   - Route: `/admin/exclusive/create` (tworzenie)
   - Route: `/admin/exclusive/<id>/edit` (edycja)
   - Logic:
     - Generuj unikalny token
     - Multi-select produktów
3. ✅ `modules/exclusive/routes.py`:
   - Route: `/exclusive/<token>` (publiczny formularz)
   - Logic:
     - Zalogowany → Normalne zamówienie (`is_exclusive = TRUE`)
     - Gość → Guest order (`is_guest_order = TRUE`)
4. ✅ Templates:
   - `templates/admin/exclusive/list.html`
   - `templates/admin/exclusive/create.html`
   - `templates/admin/exclusive/edit.html`
   - `templates/exclusive/order_page.html`
5. ✅ JavaScript:
   - `static/js/pages/exclusive-order.js` (koszyk logic dla gościa)
6. ✅ Test:
   - Stwórz exclusive page → Skopiuj link → Otwórz w incognito → Złóż zamówienie jako gość

**Deliverable:** Strony Exclusive działają, goście mogą składać zamówienia

---

### **ETAP 13: Order History & Shipping Request (Client)** ⏱️ 1-2 dni

**Cel:** Klient widzi historię zamówień, może zlecić wysyłkę.

**Tasks:**
1. ✅ `modules/client/orders.py`:
   - Route: `/client/orders` (historia)
   - Route: `/client/orders/<id>` (szczegóły)
2. ✅ `modules/client/shipping.py`:
   - Route: `/client/shipping/request` (GET, POST)
   - Logic:
     - Pokaż zamówienia w statusach: Dostarczone_GOM, Do_pakowania, Spakowane
     - Checkboxy → Update `shipping_requested = TRUE`
3. ✅ Templates:
   - `templates/client/orders/list.html`
   - `templates/client/orders/detail.html`
   - `templates/client/shipping/request.html`
4. ✅ JavaScript:
   - `static/js/pages/client/shipping-request.js`

**Deliverable:** Klient widzi zamówienia, zleca wysyłkę

---

### **ETAP 14: Email Module (Core)** ⏱️ 2-3 dni

**Cel:** System wysyłania emaili przy kluczowych zdarzeniach.

**Tasks:**
1. ✅ `modules/emails/sender.py`:
   - Funkcja: `send_email(to, template_type, context)`
   - Flask-Mail setup
2. ✅ Model `EmailTemplate` w bazie
3. ✅ Seed tabeli `email_templates` (6 szablonów)
4. ✅ Model `Settings` - SMTP config
5. ✅ `modules/admin/settings.py`:
   - Tab: Email (SMTP config)
   - Tab: Email Templates (edycja szablonów)
6. ✅ Integracja wysyłania emaili:
   - Po rejestracji → `registration_confirmation`
   - Po reset hasła → `password_reset`
   - Po złożeniu zamówienia → `order_confirmation` (client) + `new_order` (admin)
   - Po zmianie statusu → `order_status_change`
   - Po komentarzu → `order_comment`
7. ✅ Test: Skonfiguruj SMTP → Zarejestruj konto → Sprawdź email

**Deliverable:** System emaili działa

---

### **ETAP 15: Activity Log** ⏱️ 2 dni

**Cel:** Logowanie wszystkich ważnych akcji w systemie.

**Tasks:**
1. ✅ `utils/activity_logger.py`:
   - Funkcja: `log_activity(user, action, entity_type, entity_id, old_value, new_value)`
2. ✅ Integracja logowania:
   - Login/Logout
   - Zmiana statusu zamówienia (ze szczegółami: co było → co jest)
   - Dodanie/Edycja/Usunięcie produktu
   - Dodanie/Edycja/Usunięcie klienta
   - Zmiana ustawień
   - Import przelewów
   - Utworzenie exclusive page
   - Zwrot płatności
3. ✅ `modules/admin/routes.py`:
   - Route: `/admin/activity-log`
4. ✅ Template:
   - `templates/admin/activity_log.html` (tabela + filtry)

**Deliverable:** Activity log działa, admin widzi historię akcji

---

### **ETAP 16: Global Search** ⏱️ 1-2 dni

**Cel:** Globalne wyszukiwanie (Cmd/Ctrl + K) po zamówieniach/produktach/klientach.

**Tasks:**
1. ✅ `modules/api/search.py`:
   - Route: `/api/search?q=<query>`
   - Logic:
     - Szukaj w `orders` (numer, klient)
     - Szukaj w `products` (nazwa, SKU, EAN)
     - Szukaj w `users` (imię, nazwisko, email) - tylko admin/mod
     - Return JSON: `{ "orders": [...], "products": [...], "clients": [...] }`
2. ✅ JavaScript:
   - `static/js/components/global-search.js`:
     - Listen: Cmd/Ctrl + K
     - Open modal
     - HTMX: `hx-get="/api/search" hx-trigger="keyup changed delay:300ms"`
     - Render wyniki
     - Nawigacja strzałkami
3. ✅ Template:
   - `templates/components/global-search.html` (modal)
   - Include w `base.html`
4. ✅ CSS:
   - `static/css/components/global-search.css`

**Deliverable:** Global search działa

---

### **ETAP 17: Refunds Module** ⏱️ 1-2 dni

**Cel:** Admin może zwracać płatności klientom.

**Tasks:**
1. ✅ Model `OrderRefund`
2. ✅ Route: `/admin/orders/<id>/refund` (POST)
3. ✅ Logic:
   - Modal z formularzem (kwota, powód)
   - Po submit:
     - Zapisz w `order_refunds`
     - Zmień status zamówienia na "Do zwrotu"
     - Activity log
     - Email do klienta
4. ✅ Template:
   - Modal w `templates/admin/orders/detail.html`
5. ✅ Dodaj statusy zamówień: "Do zwrotu", "Zwrócone"

**Deliverable:** Admin może zwracać płatności

---

### **ETAP 18: Multi-Currency Calculator** ⏱️ 1-2 dni

**Cel:** Live przeliczanie KRW/USD → PLN w formularzu produktu.

**Tasks:**
1. ✅ `utils/currency.py`:
   - Funkcja: `get_exchange_rate(currency)`
   - API: NBP lub ExchangeRate-API
   - Cache w `settings` (24h)
2. ✅ `modules/api/currency.py`:
   - Route: `/api/exchange-rate?currency=KRW`
   - Return JSON: `{ "rate": 0.0032, "cached_at": "2025-10-31T10:00:00" }`
3. ✅ JavaScript:
   - `static/js/pages/admin/products-form.js`:
     - Listen: Change na input/dropdown
     - Fetch: `/api/exchange-rate`
     - Calculate: `amount * rate`
     - Update preview: `"≈ 450.00 PLN"`
4. ✅ Backend:
   - Przy zapisie produktu: Zapisz `purchase_price_pln`

**Deliverable:** Multi-currency działa, live preview

---

### **ETAP 19: Bank Import (Basic)** ⏱️ 2-3 dni

**Cel:** Admin może importować wyciągi bankowe i dopasowywać płatności.

**Tasks:**
1. ✅ `utils/bank_parser.py`:
   - Funkcje:
     - `parse_ing_csv(file)`
     - `parse_paypal_csv(file)`
     - `parse_revolut_csv(file)`
   - Return: Lista transakcji (data, kwota, tytuł)
2. ✅ `modules/admin/imports.py`:
   - Route: `/admin/imports/bank` (GET, POST)
   - Logic:
     - Upload CSV
     - Parse
     - Regex: Znajdź numer zamówienia w tytule `(ST|EX)/\d{8}`
     - Preview tabeli
     - Submit → Zmień status zamówień na "Oczekujące"
3. ✅ Templates:
   - `templates/admin/imports/bank_imports.html`
4. ✅ JavaScript:
   - `static/js/pages/admin/bank-import.js`

**Deliverable:** Import przelewów działa

---

### **ETAP 20: Order Templates (Client)** ⏱️ 1 dzień

**Cel:** Klient może zapisywać szablony zamówień.

**Tasks:**
1. ✅ Models: `OrderTemplate`, `OrderTemplateItem`
2. ✅ Routes:
   - `/client/orders/templates` (lista)
   - `/client/orders/templates/create` (POST)
   - `/client/orders/templates/<id>/use` (POST)
3. ✅ Logic:
   - Podczas składania zamówienia: Checkbox "Zapisz jako szablon"
   - Użycie szablonu: Produkty dodane do koszyka
4. ✅ Template:
   - `templates/client/orders/templates.html`

**Deliverable:** Szablony zamówień działają

---

### **ETAP 21: Admin Dashboard - Real Data** ⏱️ 1 dzień

**Cel:** Wypełnić admin dashboard rzeczywistymi danymi.

**Tasks:**
1. ✅ `modules/admin/dashboard.py`:
   - Agregacje SQL:
     - Liczba zamówień (ogółem, dzisiaj, oczekujących)
     - Przychód w tym miesiącu
     - Liczba klientów
     - Liczba produktów
   - Ostatnie 10 zamówień
2. ✅ Template:
   - `templates/admin/dashboard.html` (kafelki + tabela)

**Deliverable:** Dashboard admin z danymi

---

### **ETAP 22: Client Dashboard - Real Data** ⏱️ 1 dzień

**Cel:** Wypełnić client dashboard rzeczywistymi danymi.

**Tasks:**
1. ✅ `modules/client/dashboard.py`:
   - Liczba zamówień (ogółem, w trakcie, dostarczone)
   - Ostatnie 5 zamówień
2. ✅ Template:
   - `templates/client/dashboard.html`

**Deliverable:** Dashboard client z danymi

---

### **ETAP 23: Statistics Module (Basic)** ⏱️ 2 dni

**Cel:** Podstawowe statystyki sprzedaży dla admina.

**Tasks:**
1. ✅ `modules/admin/statistics.py`:
   - Route: `/admin/statistics`
   - Filtry: Zakres dat, typ zamówienia, status
   - Metryki: Liczba zamówień, przychód, średnia wartość
   - Wykres: Sprzedaż w czasie (Chart.js)
   - Export: CSV (pandas)
2. ✅ Template:
   - `templates/admin/statistics.html`
3. ✅ JavaScript:
   - `static/js/pages/admin/statistics.js` (Chart.js)

**Deliverable:** Statystyki działają

---

### **ETAP 24: Polish & Bug Fixes** ⏱️ 2-3 dni

**Cel:** Dopracowanie UI, fixowanie bugów, optymalizacja.

**Tasks:**
1. ✅ Code review całej aplikacji
2. ✅ UI polish:
   - Spójność kolorów, spacing, typography
   - Responsywność (mobile)
   - Loading states (skeletons)
   - Error states
3. ✅ Performance optimization:
   - Lazy loading images
   - Indexy w bazie danych
   - Query optimization
4. ✅ Security review:
   - CSRF tokens wszędzie
   - SQL injection prevention (SQLAlchemy)
   - XSS prevention (Jinja2 auto-escape)
5. ✅ Testing:
   - Manualne testy wszystkich flow
   - Testy edge cases
6. ✅ Dokumentacja:
   - README.md (setup instructions)
   - .env.example
   - Komentarze w kodzie

**Deliverable:** MVP gotowe do użycia

---

### **ETAP 25: Deployment Preparation** ⏱️ 1 dzień

**Cel:** Przygotowanie aplikacji do wdrożenia na serwer produkcyjny.

**Tasks:**
1. ✅ `config.py` - Production config:
   - `DEBUG = False`
   - `SECRET_KEY` z environment
   - Database URL z environment
2. ✅ `.gitignore` - Exclude:
   - `.env`
   - `*.pyc`
   - `__pycache__/`
   - `logs/`
   - `static/uploads/`
3. ✅ Setup serwera (np. VPS):
   - Install Python, MariaDB, Nginx, Gunicorn
   - Clone repo
   - Setup virtualenv
   - Install dependencies
   - Configure Nginx reverse proxy
4. ✅ Migracja bazy danych na serwer produkcyjny
5. ✅ Test w środowisku produkcyjnym

**Deliverable:** Aplikacja wdrożona na serwerze

---

## 9. API Endpoints

### 9.0 Main Route (Smart Redirect)

| Method | Endpoint | Description | Auth Required | Role |
|--------|----------|-------------|---------------|------|
| GET | `/` | **Main entry point**: If not authenticated → redirect to `/auth/login`; If authenticated → redirect to appropriate dashboard (admin/mod → `/admin/dashboard`, client → `/client/dashboard`) | No | - |

---

### 9.1 Authentication Endpoints

| Method | Endpoint | Description | Auth Required | Role |
|--------|----------|-------------|---------------|------|
| GET | `/auth/login` | Login page (główna strona logowania) | No | - |
| POST | `/auth/login` | Submit login | No | - |
| GET | `/auth/register` | Register page | No | - |
| POST | `/auth/register` | Submit registration | No | - |
| GET | `/auth/logout` | Logout user | Yes | All |
| GET | `/auth/forgot-password` | Forgot password page | No | - |
| POST | `/auth/forgot-password` | Request password reset | No | - |
| GET | `/auth/reset-password/<token>` | Reset password page | No | - |
| POST | `/auth/reset-password/<token>` | Submit new password | No | - |
| GET | `/auth/verify-email/<token>` | Verify email | No | - |

**NOTE:** Główna strona `/` automatycznie przekierowuje na `/auth/login` dla niezalogowanych użytkowników.

---

### 9.2 Admin Endpoints

| Method | Endpoint | Description | Auth Required | Role |
|--------|----------|-------------|---------------|------|
| GET | `/admin/dashboard` | Admin dashboard | Yes | Admin, Mod |
| GET | `/admin/orders` | Orders list | Yes | Admin, Mod |
| GET | `/admin/orders/<id>` | Order detail | Yes | Admin, Mod |
| POST | `/admin/orders/<id>/status` | Change order status | Yes | Admin, Mod |
| POST | `/admin/orders/<id>/comment` | Add comment | Yes | Admin, Mod |
| POST | `/admin/orders/<id>/refund` | Issue refund | Yes | Admin |
| DELETE | `/admin/orders/<id>` | Delete order | Yes | Admin |
| GET | `/admin/orders/wms` | WMS interface | Yes | Admin, Mod |
| POST | `/admin/orders/wms/pick-item` | Mark item as picked | Yes | Admin, Mod |
| POST | `/admin/orders/wms/pack` | Pack orders | Yes | Admin, Mod |
| GET | `/admin/clients` | Clients list | Yes | Admin, Mod |
| GET | `/admin/clients/<id>` | Client detail | Yes | Admin, Mod |
| POST | `/admin/clients/<id>` | Update client | Yes | Admin |
| DELETE | `/admin/clients/<id>` | Delete client | Yes | Admin |
| GET | `/admin/products` | Products list | Yes | Admin, Mod |
| GET | `/admin/products/create` | Create product page | Yes | Admin, Mod |
| POST | `/admin/products/create` | Submit new product | Yes | Admin, Mod |
| GET | `/admin/products/<id>/edit` | Edit product page | Yes | Admin, Mod |
| POST | `/admin/products/<id>/edit` | Update product | Yes | Admin, Mod |
| DELETE | `/admin/products/<id>` | Delete product | Yes | Admin |
| POST | `/admin/products/<id>/images` | Upload images | Yes | Admin, Mod |
| DELETE | `/admin/products/<id>/images/<img_id>` | Delete image | Yes | Admin, Mod |
| GET | `/admin/exclusive` | Exclusive pages list | Yes | Admin |
| GET | `/admin/exclusive/create` | Create exclusive page | Yes | Admin |
| POST | `/admin/exclusive/create` | Submit exclusive page | Yes | Admin |
| GET | `/admin/exclusive/<id>/edit` | Edit exclusive page | Yes | Admin |
| POST | `/admin/exclusive/<id>/edit` | Update exclusive page | Yes | Admin |
| DELETE | `/admin/exclusive/<id>` | Delete exclusive page | Yes | Admin |
| GET | `/admin/imports/bank` | Bank import page | Yes | Admin |
| POST | `/admin/imports/bank` | Process bank import | Yes | Admin |
| GET | `/admin/settings` | Settings page | Yes | Admin |
| POST | `/admin/settings` | Update settings | Yes | Admin |
| GET | `/admin/settings/categories` | Manage categories | Yes | Admin |
| POST | `/admin/settings/categories` | Add/Edit/Delete category | Yes | Admin |
| GET | `/admin/settings/tags` | Manage tags | Yes | Admin |
| POST | `/admin/settings/tags` | Add/Edit/Delete tag | Yes | Admin |
| GET | `/admin/settings/suppliers` | Manage suppliers | Yes | Admin |
| POST | `/admin/settings/suppliers` | Add/Edit/Delete supplier | Yes | Admin |
| GET | `/admin/statistics` | Statistics page | Yes | Admin, Mod |
| GET | `/admin/activity-log` | Activity log | Yes | Admin |

---

### 9.3 Client Endpoints

| Method | Endpoint | Description | Auth Required | Role |
|--------|----------|-------------|---------------|------|
| GET | `/client/dashboard` | Client dashboard | Yes | Client |
| GET | `/client/orders` | Order history | Yes | Client |
| GET | `/client/orders/<id>` | Order detail | Yes | Client |
| POST | `/client/orders/<id>/comment` | Add comment | Yes | Client |
| GET | `/client/orders/new` | New order page | Yes | Client |
| POST | `/client/orders/new` | Submit order | Yes | Client |
| GET | `/client/orders/templates` | Order templates | Yes | Client |
| POST | `/client/orders/templates/create` | Create template | Yes | Client |
| POST | `/client/orders/templates/<id>/use` | Use template | Yes | Client |
| DELETE | `/client/orders/templates/<id>` | Delete template | Yes | Client |
| GET | `/client/shipping/request` | Shipping request page | Yes | Client |
| POST | `/client/shipping/request` | Submit shipping request | Yes | Client |
| GET | `/client/orders/exclusive` | Exclusive orders | Yes | Client |
| GET | `/client/profile` | Profile settings | Yes | Client |
| POST | `/client/profile` | Update profile | Yes | Client |

---

### 9.4 Exclusive (Public) Endpoints

| Method | Endpoint | Description | Auth Required | Role |
|--------|----------|-------------|---------------|------|
| GET | `/exclusive/<token>` | Exclusive order page | No | - |
| POST | `/exclusive/<token>` | Submit exclusive order (guest/logged) | No | - |

---

### 9.5 API Endpoints (Internal)

| Method | Endpoint | Description | Auth Required | Role |
|--------|----------|-------------|---------------|------|
| GET | `/api/search?q=<query>` | Global search | Yes | All |
| GET | `/api/exchange-rate?currency=<curr>` | Get exchange rate | Yes | Admin, Mod |
| POST | `/api/upload-image` | Upload image (generic) | Yes | Admin, Mod |

---

## 10. Security Considerations

### 10.1 Authentication & Authorization

- **Password Hashing:** Werkzeug `generate_password_hash()` with method='pbkdf2:sha256'
- **CSRF Protection:** Flask-WTF automatic CSRF tokens on all forms
- **Rate Limiting:** Max 5 failed login attempts per 15 minutes (IP + email based)
- **Session Security:**
  - `SESSION_COOKIE_HTTPONLY = True`
  - `SESSION_COOKIE_SECURE = True` (production)
  - `SESSION_COOKIE_SAMESITE = 'Lax'`
- **Role-Based Access Control:** `@role_required` decorator na wszystkich endpointach admin/mod

---

### 10.2 Input Validation & Sanitization

- **WTForms Validators:** Email, Length, DataRequired, EqualTo, Regexp
- **SQLAlchemy ORM:** Automatyczna ochrona przed SQL injection
- **Jinja2 Auto-escape:** Automatyczne escapowanie HTML (ochrona przed XSS)
- **File Upload Validation:**
  - Sprawdzanie extension (whitelist: jpg, jpeg, png, gif, webp)
  - Sprawdzanie MIME type
  - Max file size: 10MB
  - Unique filename generation (uuid)

---

### 10.3 Data Protection

- **Sensitive Data:**
  - Passwords: Tylko hash w bazie
  - Email verification tokens: Expired po 24h
  - Password reset tokens: Expired po 1h
  - Exclusive page tokens: Opcjonalnie expired (pole `expires_at`)
- **Environment Variables:** `.env` file z wrażliwymi danymi (nie commitowany)
- **HTTPS:** Required w production (Nginx reverse proxy)

---

### 10.4 Activity Logging

- **Logged Actions:**
  - Login/Logout
  - Order status changes (ze szczegółami: old → new)
  - Product CRUD
  - Client CRUD
  - Settings changes
  - Bank imports
  - Refunds
- **Logged Data:**
  - User ID
  - IP Address
  - User Agent
  - Timestamp
  - Old/New values (JSON)

---

### 10.5 Error Handling

- **Production:**
  - `DEBUG = False`
  - Custom error pages (403, 404, 500)
  - Nie pokazuj stack traces użytkownikom
- **Logging:**
  - Wszystkie błędy logowane do `logs/app.log`
  - Rotation: Daily, max 7 dni
  - Level: WARNING w production, DEBUG w development

---

## 11. Configuration Management

### 11.1 Environment Variables (.env)

```env
# Flask
FLASK_APP=app.py
FLASK_ENV=development  # development / production
SECRET_KEY=your-secret-key-here

# Database
DB_HOST=localhost
DB_PORT=3306
DB_NAME=thunder_orders
DB_USER=root
DB_PASSWORD=your-password

# Email (SMTP) - opcjonalnie w .env, reszta w bazie settings
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-email-password
MAIL_DEFAULT_SENDER=noreply@thunderorders.pl

# Exchange Rate API
EXCHANGE_RATE_API_KEY=your-api-key  # Opcjonalnie
```

---

### 11.2 Database Settings (tabela `settings`)

Przykładowe klucze w tabeli `settings`:

```
key: smtp_host               value: smtp.gmail.com              type: string
key: smtp_port               value: 587                         type: integer
key: smtp_username           value: your-email@gmail.com        type: string
key: smtp_password           value: encrypted-password          type: string
key: smtp_use_tls            value: true                        type: boolean
key: company_name            value: ThunderOrders Sp. z o.o.    type: string
key: company_nip             value: 1234567890                  type: string
key: company_address         value: ul. Przykładowa 123         type: string
key: exchange_rate_krw       value: 0.0032                      type: string
key: exchange_rate_usd       value: 4.10                        type: string
key: exchange_rate_updated   value: 2025-10-31T10:00:00         type: string
```

---

### 11.3 Config Classes (config.py)

```python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600 * 24 * 7  # 7 dni
    
    # Upload
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB
    
    # Pagination
    ITEMS_PER_PAGE = 20

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
```

---

## 12. Appendix

### 12.1 Glossary

- **MVP:** Minimum Viable Product - minimalna wersja produktu z kluczowymi funkcjonalnościami
- **WMS:** Warehouse Management System - system zarządzania magazynem
- **CRUD:** Create, Read, Update, Delete - podstawowe operacje na danych
- **HTMX:** Biblioteka JS umożliwiająca SPA-like experience bez pełnego frameworka
- **ORM:** Object-Relational Mapping - mapowanie obiektów na tabele bazodanowe
- **CSRF:** Cross-Site Request Forgery - atak polegający na wysyłaniu nieautoryzowanych requestów
- **XSS:** Cross-Site Scripting - atak polegający na wstrzykiwaniu złośliwego kodu JS

---

### 12.2 Useful Links

- **Flask Documentation:** https://flask.palletsprojects.com/
- **SQLAlchemy Documentation:** https://docs.sqlalchemy.org/
- **HTMX Documentation:** https://htmx.org/docs/
- **Tailwind CSS:** https://tailwindcss.com/docs
- **Chart.js:** https://www.chartjs.org/docs/
- **Flask-Login:** https://flask-login.readthedocs.io/
- **Flask-WTF:** https://flask-wtf.readthedocs.io/
- **Pillow (Image Processing):** https://pillow.readthedocs.io/

---

### 12.3 Contact & Support

**Project Owner:** Konrad  
**Development Start Date:** 31 października 2025  
**Expected MVP Completion:** ~6-8 tygodni (zależnie od dostępności czasu)

---

**END OF PRD**

---

## Changelog

- **v1.0 (31.10.2025):** Initial PRD creation