# Plan Implementacji: System Avatarów Użytkowników

## Opis funkcjonalności

System avatarów umożliwia:
1. **Admin zarządza seriami avatarów** - tworzenie serii (kategorii) i upload zdjęć
2. **Netflix-style wybór avatara** - karuzele z avatarami pogrupowanymi po seriach
3. **Obowiązkowy wybór avatara** - każdy użytkownik musi wybrać avatar po pierwszym logowaniu
4. **Wyświetlanie avatara** - w topbar i listach użytkowników

## Struktura plików avatarów

```
static/uploads/avatars/
├── k-pop/
│   ├── k-pop-1.jpg
│   ├── k-pop-2.jpg
│   └── k-pop-3.jpg
├── animals/
│   ├── animals-1.jpg
│   └── animals-2.jpg
└── abstract/
    ├── abstract-1.jpg
    └── abstract-2.jpg
```

---

## Kroki implementacji

### 1. Migracja bazy danych

**Plik:** `database/migrations/008_avatars.sql`

Utworzenie tabel:
- `avatar_series` - serie/kategorie avatarów (id, name, slug, sort_order, created_at)
- `avatars` - poszczególne avatary (id, series_id, filename, sort_order, created_at)
- Dodanie kolumny `avatar_id` do tabeli `users` (INT, nullable, FK do avatars)

### 2. Modele SQLAlchemy

**Plik:** `modules/profile/models.py` (nowy)

Klasy:
- `AvatarSeries` - model serii avatarów
- `Avatar` - model avatara

**Plik:** `modules/auth/models.py`

Modyfikacja:
- Dodanie pola `avatar_id` do modelu `User`
- Dodanie relacji `avatar` do `Avatar`
- Dodanie metody `has_avatar` (property)

### 3. Formularze

**Plik:** `modules/profile/forms.py` (nowy lub rozszerzenie)

Klasy:
- `AvatarSeriesForm` - formularz tworzenia/edycji serii
- `AvatarUploadForm` - formularz uploadu avatarów

### 4. Routes dla admina - zarządzanie avatarami

**Plik:** `modules/profile/routes.py`

Nowe endpointy (tylko admin):
- `GET /profile/avatars` - lista serii z avatarami
- `POST /profile/avatars/series` - tworzenie nowej serii
- `DELETE /profile/avatars/series/<id>` - usunięcie serii
- `POST /profile/avatars/series/<id>/upload` - upload avatarów do serii
- `DELETE /profile/avatars/<id>` - usunięcie avatara

### 5. Routes dla wyboru avatara (wszyscy użytkownicy)

**Plik:** `modules/profile/routes.py`

Nowe endpointy:
- `GET /profile/select-avatar` - strona wyboru avatara (Netflix-style)
- `POST /profile/select-avatar` - zapisanie wybranego avatara

### 6. Middleware - przekierowanie bez avatara

**Plik:** `modules/auth/routes.py` lub `app.py`

Modyfikacja:
- W funkcji logowania: po zalogowaniu sprawdź `current_user.avatar_id`
- Jeśli `None` → redirect do `/profile/select-avatar`
- Dodanie dekoratora `@avatar_required` lub sprawdzanie w `before_request`

### 7. Szablony

**Nowe pliki:**
- `templates/profile/avatars_admin.html` - zarządzanie seriami (admin)
- `templates/profile/select_avatar.html` - Netflix-style wybór avatara

**Modyfikacje:**
- `templates/profile/index.html` - dodanie sekcji "Zarządzanie avatarami" dla admina
- `templates/components/topbar.html` - wyświetlanie avatara użytkownika

### 8. Style CSS

**Nowy plik:** `static/css/pages/avatar-select.css`

Style dla:
- Netflix-style karuzel (scroll horizontal)
- Podświetlenie wybranego avatara
- Responsywność

**Modyfikacja:** `static/css/pages/profile.css`

Style dla sekcji zarządzania avatarami (admin)

### 9. JavaScript

**Nowy plik:** `static/js/pages/avatar-select.js`

Funkcje:
- Obsługa wyboru avatara (kliknięcie)
- Submit formularza
- Animacje karuzeli

**Nowy plik:** `static/js/pages/avatar-admin.js`

Funkcje:
- Upload wielu plików
- Usuwanie avatarów (HTMX)
- Drag & drop sort (opcjonalnie)

### 10. Utils - przetwarzanie obrazów

**Plik:** `utils/image_processor.py`

Nowe funkcje:
- `process_avatar(file, series_slug)` - walidacja rozmiaru, kompresja, zapis
- Walidacja min. rozdzielczości (np. 200x200)
- Kompresja i resize do standardowego rozmiaru (np. 256x256)

---

## Diagram przepływu

```
[Login] → [avatar_id = null?] → YES → [/profile/select-avatar]
                              → NO  → [dashboard]

[Admin: /profile] → [Sekcja: Zarządzanie avatarami] → [Modal: Seria/Upload]

[Topbar] → [Wyświetl avatar użytkownika lub placeholder]
```

---

## Kryteria akceptacji

1. Admin może tworzyć serie avatarów
2. Admin może uploadować zdjęcia do serii (walidacja rozmiaru)
3. Pliki zapisują się jako: `uploads/avatars/{slug}/{slug}-{X}.jpg`
4. Po pierwszym logowaniu użytkownik trafia na stronę wyboru avatara
5. Wybór avatara zapisuje `avatar_id` w tabeli `users`
6. Avatar wyświetla się w topbar
7. Brak domyślnego avatara - każdy musi wybrać
