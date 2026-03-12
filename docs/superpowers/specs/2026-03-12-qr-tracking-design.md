# QR Code Tracking System — Design Spec

**Date:** 2026-03-12
**Status:** Approved
**Author:** Konrad + Claude

---

## 1. Overview

System śledzenia wizyt z kodów QR umieszczanych na wizytówkach i materiałach marketingowych ThunderOrders. Umożliwia tworzenie wielu kampanii QR, każda z własnym kodem i statystykami. Dane zbierane wewnętrznie — bez zewnętrznych serwisów analitycznych.

### Cel

- Mierzenie skuteczności materiałów marketingowych (wizytówki, ulotki, social media)
- Zbieranie danych o odwiedzających: urządzenia, przeglądarki, lokalizacja, unikalne vs powtarzające się wizyty
- Dashboard w panelu admina z wykresami i eksportem danych

### Mechanizm działania

1. Admin tworzy kampanię QR w panelu (nazwa, slug, docelowy URL)
2. System generuje kod QR z logo ThunderOrders (chmurka) na środku
3. QR prowadzi do `thunderorders.cloud/qr/<slug>`
4. Endpoint rejestruje wizytę (backend-side), ustawia cookie, redirect 302 na docelowy URL
5. Admin przegląda statystyki w panelu "Komunikacja" → "QR Tracking"

---

## 2. Modele bazy danych

### QRCampaign

| Kolumna | Typ | Opis |
|---------|-----|------|
| `id` | Integer, PK, auto-increment | ID kampanii |
| `name` | String(100), NOT NULL | Nazwa kampanii, np. "Wizytówki marzec 2026" |
| `slug` | String(50), UNIQUE, NOT NULL | Identyfikator w URL, np. `wizytowki` → `/qr/wizytowki`. Dozwolone znaki: `[a-z0-9-]`, min 2 znaki, max 50. Auto-generowany z nazwy kampanii (slugify), edytowalny. |
| `is_deleted` | Boolean, default False | Soft-delete — ukrywa kampanię z listy, `/qr/<slug>` zwraca 404 |
| `target_url` | String(500), NOT NULL | Docelowy URL przekierowania, domyślnie `https://thunderorders.cloud` |
| `is_active` | Boolean, default True | Czy kampania jest aktywna (nieaktywna → redirect działa, ale nie liczy wizyt) |
| `created_at` | DateTime, default utcnow | Data utworzenia |
| `updated_at` | DateTime, default utcnow, onupdate utcnow | Data ostatniej modyfikacji |
| `created_by` | Integer, FK → User | Kto stworzył kampanię |

### QRVisit

| Kolumna | Typ | Opis |
|---------|-----|------|
| `id` | Integer, PK, auto-increment | ID wizyty |
| `campaign_id` | Integer, FK → QRCampaign, NOT NULL | Powiązanie z kampanią |
| `visitor_id` | String(64), NOT NULL | Anonimowy identyfikator (cookie hash lub fingerprint) |
| `is_unique` | Boolean, NOT NULL | Czy to pierwsza wizyta tego visitor_id w tej kampanii |
| `ip_address` | String(45) | Adres IP (IPv4/IPv6) |
| `user_agent` | String(500) | Surowy User-Agent string |
| `device_type` | String(20) | `mobile` / `desktop` / `tablet` |
| `browser` | String(50) | Nazwa przeglądarki (Chrome, Safari, Firefox, etc.) |
| `os` | String(50) | System operacyjny (iOS, Android, Windows, macOS, etc.) |
| `country` | String(100) | Kraj (z geolokalizacji IP) |
| `city` | String(100) | Miasto (z geolokalizacji IP) |
| `referer` | String(500) | Referer header (zazwyczaj puste przy skanowaniu QR) |
| `visited_at` | DateTime, default utcnow, index | Timestamp wizyty |

### Indeksy

- `QRVisit.campaign_id` — szybkie filtrowanie po kampanii
- `QRVisit.visited_at` — szybkie zapytania zakresowe (wykresy w czasie)
- `QRVisit.visitor_id` + `QRVisit.campaign_id` — sprawdzanie unikalności

---

## 3. Route'y

### Publiczny endpoint (tracking + redirect)

| Route | Metoda | Opis |
|-------|--------|------|
| `/qr/<slug>` | GET | Rejestruje wizytę, redirect 302 na `campaign.target_url` |

**Flow `/qr/<slug>`:**

1. Znajdź `QRCampaign` po `slug` → 404 jeśli nie istnieje
2. Jeśli `campaign.is_active == False` → redirect bez rejestracji
3. Sprawdź cookie `thunderorders_qr_visitor`:
   - Istnieje → użyj wartości jako `visitor_id`
   - Brak → wygeneruj hash SHA-256 z `User-Agent + IP + Accept-Language`, ustaw cookie (ważność 1 rok, SameSite=Lax, HttpOnly)
4. Sprawdź czy istnieje `QRVisit` z tym `visitor_id` + `campaign_id` → ustaw `is_unique`
5. Parsuj User-Agent → `device_type`, `browser`, `os`
6. Geolokalizacja IP → `country`, `city` (GeoLite2)
7. Zapisz `QRVisit` do bazy
8. Redirect 302 → `campaign.target_url`

### Endpointy admina

| Route | Metoda | Opis |
|-------|--------|------|
| `/admin/qr-tracking` | GET | Lista kampanii z podsumowaniem |
| `/admin/qr-tracking/new` | GET/POST | Formularz tworzenia nowej kampanii |
| `/admin/qr-tracking/<id>` | GET | Szczegółowe statystyki kampanii |
| `/admin/qr-tracking/<id>/edit` | GET/POST | Edycja kampanii |
| `/admin/qr-tracking/<id>/qr-code` | GET | Podgląd + pobieranie QR kodu |
| `/admin/qr-tracking/<id>/download/<format>` | GET | Pobieranie QR kodu (svg/png) |
| `/admin/qr-tracking/<id>/delete` | POST | Soft-delete kampanii (is_deleted=True, slug pozostaje zarezerwowany) |
| `/admin/qr-tracking/<id>/export` | GET | Export wizyt do XLSX |
| `/admin/qr-tracking/<id>/api/stats` | GET | JSON ze statystykami (AJAX dla wykresów) |

---

## 4. Dashboard admina

### Nawigacja — nowy akordeon "Komunikacja"

Aktualnie Feedback, Popupy i Powiadomienia są flat items w sidebarze. W ramach tego feature'a:
1. Utworzyć nowy akordeon "Komunikacja" (wzorowany na "Zamówienia" / "Magazyn")
2. Przenieść do niego: Feedback, Popupy, Powiadomienia
3. Dodać nowy element: "QR Tracking"
4. Ikona akordeonu: do ustalenia (np. istniejąca ikona megafonu lub nowa)

### Lista kampanii (`/admin/qr-tracking`)

Tabela responsywna z kolumnami:
- Nazwa kampanii
- Slug (z linkiem `/qr/<slug>`)
- Status (aktywna/nieaktywna — toggle)
- Total wizyt
- Unikalnych wizyt
- Ostatnia wizyta
- Akcje (statystyki, edycja, QR kod, usuń)

Przycisk "Nowa kampania" na górze.

### Szczegóły kampanii (`/admin/qr-tracking/<id>`)

**Karty podsumowania (na górze, responsywny grid):**
- Total skanów
- Unikalne wizyty
- Dzisiaj
- Ostatnie 7 dni

**Wykresy (Chart.js v4.4.7 + chartjs-adapter-date-fns):**
- **Liniowy** — wizyty w czasie z przełącznikiem granularności (dziennie/tygodniowo/miesięcznie)
- **Kołowy (doughnut)** — urządzenia (mobile/desktop/tablet)
- **Kołowy (doughnut)** — przeglądarki
- **Słupkowy** — top 10 krajów

**Tabela ostatnich wizyt:**
- Data/godzina, urządzenie, przeglądarka/OS, kraj/miasto, unikalny? (tak/nie)

**Filtrowanie:** zakres dat od-do

**Export:** przycisk "Eksport XLSX" — pobiera wizyty z wybranego zakresu

### Wykresy — implementacja

- Chart.js v4.4.7 (zgodne z resztą projektu)
- chartjs-adapter-date-fns v3.0.0 dla osi czasowych
- Dark mode via MutationObserver na `data-theme` (istniejący wzorzec)
- Paleta dark mode: glassmorphism (#f093fb, #4facfe, #ff6b6b)
- Dane ładowane AJAXem z `/admin/qr-tracking/<id>/api/stats`

### Responsywność (mobile)

- Karty podsumowania: 2 kolumny na mobile, 4 na desktop
- Wykresy: pełna szerokość, skalowane `responsive: true, maintainAspectRatio: true`
- Tabela wizyt: horizontal scroll na małych ekranach lub ukryte mniej ważne kolumny
- Formularz kampanii: single-column na mobile
- Przyciski pobierania QR: full-width na mobile

---

## 5. Generator QR kodów

### Parametry generowania

- **Biblioteka:** `qrcode[pil]` v7.4.2 (istniejąca)
- **Error correction:** Level H (30%) — wymagane dla logo na środku
- **Box size:** 10 (SVG), 20 (PNG dla wysokiej rozdzielczości)
- **Border:** 2 moduły
- **Tło:** przezroczyste
- **Kolor modułów:** czarny (#000000)
- **Logo:** `static/img/icons/logo-icon.svg` — chmurka ThunderOrders
- **Rozmiar logo:** ~25% powierzchni kodu QR, wycentrowane

### Format SVG

1. Generuj QR jako SVG via `qrcode.image.svg.SvgPathImage`
2. Ustaw tło na przezroczyste (usuń biały rect)
3. Osadź logo jako `<image>` element na środku SVG
4. Content-type: `image/svg+xml`

### Format PNG

1. Generuj QR jako PIL Image
2. Ustaw tło na przezroczyste (RGBA)
3. Overlay logo (przeskalowane do ~25% QR) na środku via PIL composite
4. Rozdzielczość: 1024x1024px
5. Content-type: `image/png`

### Podgląd w adminie

Strona `/admin/qr-tracking/<id>/qr-code`:
- Renderowany podgląd QR kodu (SVG inline)
- Pełny URL kampanii wyświetlony pod kodem
- Przyciski: "Pobierz SVG", "Pobierz PNG"

---

## 6. Identyfikacja unikalnych odwiedzających

### Strategia: Cookie + Fingerprint fallback

**Priorytet 1 — Cookie `thunderorders_qr_visitor`:**
- Ustawiane przy pierwszej wizycie
- Wartość: UUID v4 (losowy, anonimowy)
- Ważność: 1 rok
- Flagi: `SameSite=Lax`, `HttpOnly`

**Priorytet 2 — Fingerprint (fallback gdy brak cookie):**
- Hash SHA-256 z: `User-Agent + IP + Accept-Language`
- Mniej dokładny (wiele osób może mieć ten sam fingerprint)
- Używany tylko gdy cookie nie istnieje i nie można go ustawić

### Logika `is_unique`

```
is_unique = NOT EXISTS(
    SELECT 1 FROM qr_visit
    WHERE campaign_id = :campaign_id
    AND visitor_id = :visitor_id
)
```

---

## 7. Geolokalizacja IP

### Rozwiązanie: GeoLite2-City (MaxMind)

- Darmowa baza danych `.mmdb` (~70MB)
- Biblioteka Python: `geoip2`
- Odczyt lokalny — brak external API calls
- Zwraca: kraj, miasto, kod kraju

### Setup i konfiguracja

- **Pobranie bazy:** Wymaga darmowego konta MaxMind + license key → download z https://dev.maxmind.com/geoip/geolite2-free-geolocation-data
- **Lokalizacja pliku:** `data/GeoLite2-City.mmdb` (w katalogu projektu)
- **Konfiguracja:** Ścieżka do pliku w `config.py` jako `GEOIP_DB_PATH`, domyślnie `os.path.join(basedir, 'data', 'GeoLite2-City.mmdb')`
- **`.gitignore`:** Dodać `data/*.mmdb` — plik binarny 70MB nie powinien być w repo
- **Fallback:** Jeśli plik `.mmdb` nie istnieje lub IP nie znaleziony → `country=NULL`, `city=NULL`, aplikacja działa normalnie bez geolokalizacji
- **Deployment:** Plik `.mmdb` musi być pobrany osobno na serwerze VPS

### Aktualizacja bazy

- Baza aktualizowana przez MaxMind co 2 tygodnie
- Opcjonalnie: cron job do pobierania nowej wersji (nie krytyczne)

---

## 8. Struktura plików

```
modules/tracking/
├── __init__.py          # Blueprint registration (tracking_bp)
├── models.py            # QRCampaign, QRVisit
├── routes.py            # Endpointy admina (lista, CRUD, statystyki)
├── qr_routes.py         # Publiczny endpoint /qr/<slug>
├── qr_generator.py      # Generowanie QR kodów (SVG/PNG z logo)
├── utils.py             # Parsowanie UA, fingerprint, geolokalizacja IP
└── export.py            # Export do XLSX (openpyxl)

templates/admin/tracking/
├── index.html           # Lista kampanii
├── detail.html          # Statystyki kampanii (wykresy, tabela)
├── form.html            # Formularz nowej/edycji kampanii
└── qr_code.html         # Podgląd + pobieranie QR kodu

static/css/pages/admin/
└── qr-tracking.css      # Style (light + dark mode)

static/js/pages/admin/
└── qr-tracking.js       # Chart.js wykresy, AJAX, filtrowanie

migrations/versions/
└── xxxx_add_qr_tracking.py  # Migracja (QRCampaign + QRVisit)
```

### Nowe zależności Python

| Pakiet | Cel |
|--------|-----|
| `user-agents` | Parsowanie User-Agent → device, browser, OS |
| `geoip2` | Geolokalizacja IP z bazy GeoLite2-City |
| `openpyxl` | Export danych do XLSX |

Wersje zostaną zpinowane w `requirements.txt` po instalacji (`pip freeze`).

Istniejące (bez zmian): `qrcode[pil]` v7.4.2

### Rejestracja blueprintu

Blueprint rejestrowany **bez url_prefix** (tak jak `feedback_bp`, `orders_bp`). Route'y definiowane z pełnymi ścieżkami w dekoratorach:
- `@tracking_bp.route('/qr/<slug>')` — publiczny, BEZ `@login_required`
- `@tracking_bp.route('/admin/qr-tracking/...')` — admin, Z `@login_required` + `@role_required('admin', 'mod')`

W `app.py` dodać:
```python
from modules.tracking import tracking_bp
app.register_blueprint(tracking_bp)
```

**CSRF:** Blueprint NIE jest CSRF-exempt. Publiczny endpoint `/qr/<slug>` to GET-only (nie wymaga CSRF). Formularze admina (POST) chronione standardowo przez Flask-WTF.

---

## 9. Bezpieczeństwo i prywatność

- **Anonimizacja:** `visitor_id` to UUID lub hash — nie przechowujemy danych osobowych
- **IP:** przechowywane do geolokalizacji, ale nie łączone z kontem użytkownika
- **Cookie:** `HttpOnly` — niedostępne z JavaScript
- **RODO:** brak danych osobowych, anonimowe śledzenie wizyt
- **Dostęp do dashboardu:** tylko Admin/Mod (istniejący system uprawnień)
- **CSRF:** formularz tworzenia/edycji kampanii chroniony Flask-WTF CSRF (blueprint NIE jest CSRF-exempt)
- **Usuwanie kampanii:** Soft-delete (`is_deleted=True`) — zachowuje dane wizyt, `/qr/<slug>` zwraca 404 dla usuniętych kampanii
- **Publiczny endpoint:** `/qr/<slug>` jest GET-only, bez `@login_required`, bez CSRF

---

## 10. Decyzje podjęte

| Decyzja | Wybór | Alternatywy rozważane |
|---------|-------|----------------------|
| Mechanizm trackingu | Redirect przez `/qr/<slug>` | UTM parametr, tracking na stronie docelowej |
| Architektura | Osobny moduł `modules/tracking/` | Rozszerzenie API, middleware |
| Identyfikacja unikalnych | Cookie + fingerprint fallback | Tylko cookie, tylko fingerprint |
| Geolokalizacja | GeoLite2 (lokalna baza) | External API, brak geolokalizacji |
| Wykresy | Chart.js v4.4.7 (istniejący w projekcie) | ApexCharts, D3.js |
| Format QR | SVG + PNG z przezroczystym tłem i logo | Tylko PNG, bez logo |
| Export danych | XLSX (openpyxl) | CSV |
| Cookie name | `thunderorders_qr_visitor` | `qr_visitor` |
| Nawigacja admin | Akordeon "Komunikacja" | Osobna sekcja, widget na dashboardzie |
