# Admin-Grantable Badges — Design Spec

**Date:** 2026-04-26
**Author:** Konrad (z Claude)
**Status:** Approved (ready for implementation plan)

---

## Cel

Rozszerzyć istniejący system osiągnięć (`modules/achievements/`) o możliwość ręcznego przyznawania specjalnych odznak przez admina. Odznaki są dynamicznie tworzone w panelu admina (formularz + upload ikony), przyznawane pojedynczo z poziomu profilu klienta, z natychmiastowym powiadomieniem e-mailem oraz animacją „supernova" w galerii klienta.

## Kontekst

Obecny system seeduje odznaki z listy `ACHIEVEMENTS` w `modules/achievements/seed.py` i odblokowuje je automatycznie przez `trigger_type='event'` (po akcjach jak `order_placed`) lub `trigger_type='cron'` (codzienne sprawdzenia). Brak ścieżki ręcznego nagradzania klientów za rzeczy spoza systemu metryk (Beta Tester, zwycięzca konkursu, wyróżnienie społecznościowe itp.).

## Decyzje projektowe

| Aspekt | Decyzja | Uzasadnienie |
|---|---|---|
| **Tworzenie odznak** | Dynamiczne w panelu admina (formularz + upload) | Pełna elastyczność bez deploy'u |
| **Workflow** | Dwuetapowy: CRUD odznak + przyznawanie z profilu klienta | Jasna separacja, możliwy reuse tej samej odznaki dla wielu osób |
| **Kategoria** | Nowa stała `special` | Wizualne wyodrębnienie + filtr w galerii |
| **Rzadkość** | Nowy poziom `cosmic` (mocniejszy niż `legendary`) | Wizualnie wyróżniony — galaxy/cosmic styl |
| **Widoczność dla klienta** | Per-odznaka — flaga `is_hidden_until_unlocked` | Admin decyduje, czy odznaka jest sekretem czy „celem do osiągnięcia" |
| **Odbieranie** | Możliwe + audit (`granted_by_id`, `granted_at`) | Naprawa pomyłek, kontrola |
| **Powiadomienie klienta** | Animacja w galerii + e-mail | Klient ma pewność, że dostał wyróżnienie |
| **Statystyki** | Ukryte dla `category='special'` | Tajemniczość; zamiast tego etykieta „Wyróżnienie admina" |
| **Bulk grant** | Nie — tylko pojedynczo | Najprostsza implementacja, wystarczy dla MVP |
| **Ikona** | Upload obowiązkowy, auto-resize do 256×256 PNG (Pillow) | Wygoda admina, spójność wizualna |

## Architektura — rozszerzenie istniejących modułów

Nie tworzymy równoległego systemu — rozszerzamy `modules/achievements/`:

1. `Achievement` model — dodajemy `trigger_type='manual'`, wartości `category='special'` i `rarity='cosmic'`, pole `is_hidden_until_unlocked`
2. `UserAchievement` model — dodajemy `granted_by_id` (FK → users)
3. Nowy moduł `modules/admin/achievements.py` — CRUD odznak
4. Rozszerzenie `modules/admin/clients.py` — endpointy grant/revoke
5. Nowe metody serwisu — `AchievementService.grant_manual()`, `AchievementService.revoke_manual()`
6. Nowy szablon e-maila + helper `send_achievement_granted_email`
7. Nowe style CSS — `cosmic` rarity w galerii i spotlight

---

## 1. Schema bazy danych

### Migracja Flask-Migrate

**Tabela `achievement`:**

```sql
ALTER TABLE achievement
  MODIFY category ENUM('orders', 'collection', 'loyalty', 'speed',
                       'exclusive', 'social', 'financial', 'profile',
                       'special') NOT NULL;

ALTER TABLE achievement
  MODIFY rarity ENUM('common', 'rare', 'epic', 'legendary',
                     'cosmic') NOT NULL;

ALTER TABLE achievement
  MODIFY trigger_type ENUM('event', 'cron', 'manual') NOT NULL;

ALTER TABLE achievement
  ADD COLUMN is_hidden_until_unlocked BOOLEAN NOT NULL DEFAULT FALSE;
```

**Tabela `user_achievement`:**

```sql
ALTER TABLE user_achievement
  ADD COLUMN granted_by_id INT NULL,
  ADD CONSTRAINT fk_user_achievement_granted_by
    FOREIGN KEY (granted_by_id) REFERENCES users(id)
    ON DELETE SET NULL;
```

`granted_at` nie potrzebne jako osobna kolumna — używamy istniejącego `unlocked_at`.

### Model — `modules/achievements/models.py`

```python
class Achievement(db.Model):
    # ... istniejące pola ...
    category = db.Column(
        db.Enum('orders', 'collection', 'loyalty', 'speed', 'exclusive',
                'social', 'financial', 'profile', 'special',
                name='achievement_category'),
        nullable=False
    )
    rarity = db.Column(
        db.Enum('common', 'rare', 'epic', 'legendary', 'cosmic',
                name='achievement_rarity'),
        nullable=False
    )
    trigger_type = db.Column(
        db.Enum('event', 'cron', 'manual', name='achievement_trigger_type'),
        nullable=False
    )
    is_hidden_until_unlocked = db.Column(db.Boolean, default=False, nullable=False)


class UserAchievement(db.Model):
    # ... istniejące pola ...
    granted_by_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True
    )
    granted_by = db.relationship('User', foreign_keys=[granted_by_id])
```

### Decyzje schematu

- `trigger_type='manual'` zamiast bool `is_manual` — istniejący kod już rozgałęzia się przez `trigger_type` w `check_event` i `run_daily_checks`. Kolejna wartość ENUMa pasuje naturalnie i naturalnie wyklucza odznaki manualne z automatycznych przepływów.
- `trigger_config={}` (pusty JSON) dla manualnych — pole jest `NOT NULL`, zapisujemy `{}`.
- `granted_by_id` z `ON DELETE SET NULL` — usunięcie konta admina nie powoduje utraty odznak klientów.

---

## 2. Backend services

### `modules/achievements/services.py` — nowe metody

```python
def grant_manual(self, user, achievement, granted_by, send_animation=True):
    """
    Manual grant by admin. Reuses unlock() but:
    - sets granted_by_id (audit)
    - seen=False -> animation in gallery
    - sends email (always, per design D)

    Returns the new UserAchievement or None if already granted.
    """
    existing = UserAchievement.query.filter_by(
        user_id=user.id, achievement_id=achievement.id
    ).first()
    if existing:
        return None  # idempotent

    try:
        nested = db.session.begin_nested()
        ua = UserAchievement(
            user_id=user.id,
            achievement_id=achievement.id,
            granted_by_id=granted_by.id,
            seen=not send_animation,
        )
        db.session.add(ua)
        nested.commit()
        db.session.commit()
    except Exception:
        db.session.rollback()
        return None

    self.recalculate_stats()

    try:
        from utils.email_sender import send_achievement_granted_email
        from flask import url_for
        if user.email:
            send_achievement_granted_email(
                user_email=user.email,
                user_name=user.first_name or user.email,
                achievement_name=achievement.name,
                achievement_description=achievement.description,
                achievement_slug=achievement.slug,
                gallery_url=url_for('achievements.gallery', _external=True),
            )
    except Exception as e:
        current_app.logger.warning(f'Failed to send achievement email: {e}')

    return ua


def revoke_manual(self, user, achievement, revoked_by):
    """
    Admin revokes a manually-granted achievement.
    Only allowed for trigger_type='manual'.
    """
    if achievement.trigger_type != 'manual':
        raise ValueError('Cannot revoke non-manual achievement')

    ua = UserAchievement.query.filter_by(
        user_id=user.id, achievement_id=achievement.id
    ).first()
    if not ua:
        return False

    current_app.logger.info(
        f'Achievement revoked: user={user.id} achievement={achievement.id} '
        f'by_admin={revoked_by.id} originally_granted_by={ua.granted_by_id}'
    )

    db.session.delete(ua)
    db.session.commit()
    self.recalculate_stats()
    return True
```

### Modyfikacje `get_user_achievements`

```python
def get_user_achievements(self, user):
    all_achievements = Achievement.query.filter_by(is_active=True).order_by(
        Achievement.sort_order
    ).all()

    unlocked_map = {ua.achievement_id: ua for ua in
                    UserAchievement.query.filter_by(user_id=user.id).all()}

    result = []
    for a in all_achievements:
        ua = unlocked_map.get(a.id)
        # NEW: hide if flagged AND user doesn't have it
        if a.is_hidden_until_unlocked and not ua:
            continue

        # ... istniejąca logika obliczania progress ...

        # NEW: hide stats for 'special' category
        if a.category == 'special':
            stat_percentage = None
            stat_total = None
        else:
            stat_percentage = stat.percentage if stat else 0
            stat_total = stat.total_unlocked if stat else 0

        result.append({...})  # plus 'is_special': a.category == 'special'

    return result
```

### Modyfikacje `recalculate_stats`

```python
def recalculate_stats(self):
    achievements = Achievement.query.filter(
        Achievement.is_active == True,
        Achievement.category != 'special',  # NEW
    ).all()
    # ... reszta bez zmian ...
```

### Niezmienne / drobne dostosowania

- `unlock(...)` (ścieżka automatyczna) — bez zmian
- `check_event(...)` / `run_daily_checks(...)` — bez zmian, naturalnie wykluczają `manual` (filtrują po `trigger_type`)
- `backfill_all(...)` — **dodajemy explicit filter** `Achievement.trigger_type.in_(['event', 'cron'])`, żeby nie iterować po manualnych z pustym `trigger_config={}`. Bez tego logika przeszłaby (zwraca `(0, False)` w `get_metric_value`), ale niepotrzebnie obciąża pętlę.
- Cache `_icon_cache` — invalidujemy przy upload/delete: `_icon_cache.pop(slug, None)`

### Nowy email — `utils/email_sender.py`

```python
def send_achievement_granted_email(user_email, user_name, achievement_name,
                                   achievement_description, achievement_slug,
                                   gallery_url):
    return send_email(
        to=user_email,
        subject=f'🎖️ Otrzymałeś specjalną odznakę: {achievement_name}',
        template='achievement_granted',
        user_name=user_name,
        achievement_name=achievement_name,
        achievement_description=achievement_description,
        achievement_slug=achievement_slug,
        gallery_url=gallery_url,
    )
```

Plus szablon `templates/emails/achievement_granted.html` (struktura jak istniejące e-maile — gradient nagłówek + treść + CTA do galerii).

---

## 3. Admin UI

### A) CRUD odznak — `modules/admin/achievements.py`

| Metoda | URL | Akcja |
|---|---|---|
| GET | `/admin/achievements` | Lista wszystkich odznak (manual + auto, z badge informującym o typie) |
| GET | `/admin/achievements/new` | Formularz tworzenia |
| POST | `/admin/achievements/new` | Utworzenie + upload ikony |
| GET | `/admin/achievements/<id>/edit` | Formularz edycji |
| POST | `/admin/achievements/<id>/edit` | Zapis edycji |
| POST | `/admin/achievements/<id>/delete` | Soft-delete (`is_active=False`) |
| GET | `/admin/achievements/<id>/holders` | Lista klientów którzy mają tę odznakę |
| POST | `/admin/achievements/<id>/holders/<user_id>/revoke` | Odbiera od konkretnego klienta |

Wszystkie chronione `@login_required` + `@admin_required`.

### Formularz tworzenia/edycji

| Pole | Typ | Walidacja |
|---|---|---|
| `name` | text | 1-120 znaków, niepuste |
| `slug` | text | regex `^[a-z0-9-]+$`, 1-80, unikalny, auto-generowany z `name` |
| `description` | text | 1-255 znaków |
| `category` | select | enum, domyślnie `special` |
| `rarity` | select | `common`/`rare`/`epic`/`legendary`/`cosmic`, domyślnie `cosmic` |
| `is_hidden_until_unlocked` | checkbox | bool, domyślnie False |
| `icon` | file input | image MIME, max 5MB, min 64×64 |
| `is_active` | checkbox | bool, domyślnie True |

Auto-slug: `slugify(name)` + ewentualny suffix `-2`, `-3` jeśli kolizja. Admin może nadpisać.

### Upload ikony — Pillow

```python
from PIL import Image
img = Image.open(uploaded_file).convert('RGBA')
img.thumbnail((256, 256), Image.LANCZOS)
canvas = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
x = (256 - img.width) // 2
y = (256 - img.height) // 2
canvas.paste(img, (x, y), img)
canvas.save(f'{upload_dir}/{slug}@256.png', 'PNG', optimize=True)
_icon_cache.pop(slug, None)
```

### Szablony

- `templates/admin/achievements/list.html` — tabela: ikona, nazwa, kategoria, rzadkość, typ (`auto`/`manual`), liczba posiadaczy, akcje
- `templates/admin/achievements/form.html` — formularz tworzenia/edycji
- `templates/admin/achievements/holders.html` — tabela klientów + przycisk „Odbierz"

### B) Przyznawanie z profilu klienta

Modyfikacja `templates/admin/clients/detail.html`:

- Sekcja „Specjalne odznaki" — lista posiadanych przez klienta odznak `manual` z przyciskami „Odbierz"
- Przycisk „Przyznaj specjalną odznakę" → modal z select-em (filtr: odznaki z `trigger_type='manual'` których klient jeszcze nie ma)

Endpointy w `modules/admin/clients.py`:

```python
@admin_bp.route('/clients/<int:id>/grant-achievement', methods=['POST'])
@admin_required
def grant_achievement(id):
    user = User.query.get_or_404(id)
    achievement_id = request.form.get('achievement_id', type=int)
    achievement = Achievement.query.filter_by(
        id=achievement_id, trigger_type='manual', is_active=True
    ).first_or_404()

    service = AchievementService()
    ua = service.grant_manual(user, achievement, granted_by=current_user)
    if ua:
        flash(f'Przyznano odznakę „{achievement.name}" klientowi.', 'success')
    else:
        flash('Klient już posiada tę odznakę.', 'warning')
    return redirect(url_for('admin_bp.client_detail', id=id))


@admin_bp.route('/clients/<int:id>/revoke-achievement/<int:ach_id>', methods=['POST'])
@admin_required
def revoke_achievement(id, ach_id):
    user = User.query.get_or_404(id)
    achievement = Achievement.query.filter_by(
        id=ach_id, trigger_type='manual'
    ).first_or_404()

    service = AchievementService()
    if service.revoke_manual(user, achievement, revoked_by=current_user):
        flash(f'Odebrano odznakę „{achievement.name}".', 'success')
    else:
        flash('Klient nie posiadał tej odznaki.', 'warning')
    return redirect(url_for('admin_bp.client_detail', id=id))
```

### C) Nawigacja — wpis w sidebarze admina

**Plik:** `templates/components/sidebar_admin.html` (już zawiera całą strukturę sidebara, włączane przez `templates/admin/base_admin.html`).

**Pozycja:** nowa pozycja jako osobny `<li class="sidebar-item">` (top-level, nie kategoria) wstawiona po „Statystyki", przed „Moje zadania" — pasuje tematycznie obok statystyk i listy klientów.

**Markup (wzorzec jak istniejące pozycje):**

```html
<li class="sidebar-item">
    <a href="{{ url_for('admin.achievements_list') }}"
       class="sidebar-link {% if request.endpoint and 'achievement' in request.endpoint %}active{% endif %}"
       data-tooltip="Odznaki">
        <img src="{{ url_for('static', filename='img/icons/achievements.svg') }}" alt="Odznaki" class="sidebar-icon">
        <span class="sidebar-text">Odznaki</span>
    </a>
</li>
```

**Widoczność:**
- Pokazujemy **tylko dla `role='admin'`**. W sidebarze opakowujemy w `{% if current_user.role == 'admin' %}…{% endif %}` — `mod` nie zobaczy linku.
- Nawet bez tego linku, endpoint chroniony `@admin_required` na backendzie odrzuca dostęp od mod (404/403).

**Ikona:**
- Nowy plik `static/img/icons/achievements.svg` — prosta ikona medalu/gwiazdy w stylu istniejących ikon (one-color, ~24×24, paleta neutralna). Dopasowana do dark mode przez `filter: invert(...)` jeśli inne ikony to robią, lub z założenia mono-kolor.
- Jeśli stylowo łatwiej, można zrobić wariant `achievements-light.svg` / `achievements-dark.svg`.

**Active state:**
- Warunek `'achievement' in request.endpoint` pokrywa wszystkie sub-routes (`achievements_list`, `achievements_new`, `achievements_edit`, `achievements_holders`, `revoke_achievement`, `grant_achievement`).

**Endpoint name w blueprint:**
- W `modules/admin/__init__.py` dodać import nowego modułu: `from . import achievements as _achievements_admin`. Funkcje rejestrujemy na istniejącym `admin_bp` z prefixem `achievements_*` (np. `admin.achievements_list`).

---

## 4. UI klienta — galeria, animacja, styl `cosmic`

### A) Filtrowanie ukrytych odznak

API `/achievements/api/my` używa `service.get_user_achievements(user)`, który po zmianie z sekcji 2 odfiltrowuje `is_hidden_until_unlocked=True` których klient nie ma. Frontend bez zmian.

API `/achievements/api/unseen` zwraca tylko odznaki `seen=False` posiadane przez klienta — nie wymaga zmian.

### B) Style `cosmic` — `static/css/pages/client/achievements.css`

Karta odblokowana (galaxy/nebula/twinkle):

```css
.achievement-card[data-rarity="cosmic"],
.badge-spotlight[data-rarity="cosmic"] {
    --rarity-color: #a855f7;
    --rarity-glow: rgba(168, 85, 247, 0.5);
}

.achievement-card.unlocked[data-rarity="cosmic"] {
    background:
        radial-gradient(ellipse at 20% 30%, #6a0dad 0%, transparent 50%),
        radial-gradient(ellipse at 80% 70%, #1e3a8a 0%, transparent 50%),
        radial-gradient(circle at 50% 50%, #0f0f23 0%, #000000 100%);
    border: 1px solid rgba(168, 85, 247, 0.4);
    box-shadow: 0 0 35px rgba(106, 13, 173, 0.7),
                0 0 60px rgba(30, 58, 138, 0.4);
    position: relative;
    overflow: hidden;
}

.achievement-card.unlocked[data-rarity="cosmic"]::before {
    content: '';
    position: absolute;
    inset: 0;
    background-image:
        radial-gradient(1px 1px at 25% 20%, white, transparent),
        radial-gradient(1px 1px at 60% 35%, white, transparent),
        radial-gradient(1px 1px at 85% 60%, #ffd700, transparent),
        radial-gradient(2px 2px at 40% 75%, white, transparent),
        radial-gradient(1px 1px at 10% 85%, #00d4ff, transparent),
        radial-gradient(1px 1px at 70% 15%, white, transparent),
        radial-gradient(1.5px 1.5px at 30% 50%, #ff80ff, transparent);
    animation: cosmic-twinkle 4s ease-in-out infinite;
    pointer-events: none;
}

@keyframes cosmic-twinkle {
    0%, 100% { opacity: 0.7; }
    50% { opacity: 1; }
}

.badge-rarity.cosmic {
    background: linear-gradient(135deg, #6a0dad, #1e3a8a);
    color: #fff;
    border: 1px solid rgba(168, 85, 247, 0.6);
}

.badge-icon.cosmic {
    background: rgba(168, 85, 247, 0.15);
    border: 2px solid rgba(168, 85, 247, 0.4);
}

[data-theme="dark"] .achievement-card.unlocked[data-rarity="cosmic"] {
    box-shadow: 0 0 45px rgba(106, 13, 173, 0.85),
                0 0 80px rgba(30, 58, 138, 0.55);
}
```

W `static/js/components/achievements-renderer.js` (lub gdziekolwiek jest mapowanie rarity → label PL): dodać `cosmic: 'Kosmiczne'`.

### C) Animacja unlock — Supernova v2

`.badge-spotlight[data-rarity="cosmic"]` w trybie `.active` dostaje warstwy DOM (wstrzykiwane przez JS renderer):

- **`.cosmic-backdrop`** — animowany gradient tła (drift + hue-shift, 8s, `@keyframes backdrop-drift`)
- **3× `.nebula-cloud`** (klasy `.purple`, `.blue`, `.pink`) — dryfujące mgławice 10-14s
- **`.star-field`** — pole drobnych migoczących gwiazd (radial-gradients), `@keyframes starfield-twinkle` 4s
- **6× `.glow-star`** — duże pulsujące gwiazdy z aureolą, `@keyframes glow-pulse` 3s
- **3× `.shooting-bg`** — spadające gwiazdy w tle, `@keyframes shooting-bg` 4s
- **`.supernova-core`** — biały błysk z box-shadow, `@keyframes supernova-burst` (jednorazowo przy spawn)
- **8× `.ray`** — promienie strzelające z centrum (transform-origin: top center, rotation co 45°), `@keyframes ray-shoot` (jednorazowo)
- **`.demo-card-big::before`** — pulsujące halo wokół karty po pojawieniu

Pełny CSS w sekcji 4 implementacji (z mockupu `cosmic-unlock-animation-v2.html`).

`grant_manual` ustawia `seen=False` → klient po wejściu do galerii dostaje tę samą animację co dla auto-odznak, ale dla `cosmic` z pełnym tłem.

### D) Tooltip „Specjalna odznaka"

W karcie/spotlight'cie — jeśli `category === 'special'`, zamiast statystyk pokazujemy etykietę:

```html
{% if achievement.category == 'special' %}
  <div class="badge-special-tag">Wyróżnienie admina</div>
{% else %}
  <div class="badge-stat">{{ achievement.stat_percentage }}% klientów ma</div>
{% endif %}
```

```css
.badge-special-tag {
    color: rgba(168, 85, 247, 0.9);
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 600;
}
[data-theme="dark"] .badge-special-tag {
    color: #c084fc;
    text-shadow: 0 0 8px rgba(168, 85, 247, 0.4);
}
```

### E) Share image — `modules/achievements/share.py`

Dodajemy wpis w `RARITY_*` dict + label:

```python
RARITY_COSMIC = {
    'card_top_tint': (168, 85, 247),
    'card_top_alpha': 0.18,
    'card_bottom': (10, 5, 30),
    'border_color': (168, 85, 247),
    'border_alpha': 0.45,
    'accent': (180, 100, 255),
    'pill_bg_alpha': 0.20,
    'pill_color': (220, 180, 255),
}

RARITY_LABELS = {
    # ...
    'cosmic': 'Kosmiczne',
}
```

Dispatcher dobiera słownik po `achievement.rarity`. Opcjonalnie w renderze: kilka rozmytych „gwiazd" jako białe punkty z `Image.alpha_composite`, pozycja pseudo-losowa z hash slug → deterministyczne.

---

## 5. Walidacja, bezpieczeństwo, edge cases

### Bezpieczeństwo

- **Autoryzacja** — wszystkie endpointy admin chronione `@login_required` + `@admin_required`. Mod nie może przyznawać/tworzyć.
- **Upload** — whitelist MIME (`image/png`, `image/jpeg`, `image/jpg`, `image/webp`, `image/gif`), walidacja przez `Image.open()`, max 5MB, plik zapisywany **wyłącznie** jako `<slug>@256.png` (gdzie slug spełnia regex `^[a-z0-9-]+$`).
- **CSRF** — standardowa ochrona Flask-WTF.
- **Idempotency** — `grant_manual` sprawdza istnienie + `db.session.begin_nested()` z try/except; bezpieczne dla podwójnego klika i race condition.

### Edge cases

| Scenariusz | Zachowanie |
|---|---|
| Usunięcie konta admina, który przyznał odznakę | `granted_by_id` = NULL (ON DELETE SET NULL); odznaka klienta zostaje |
| Soft-delete odznaki gdy ktoś już ją ma | Ostrzeżenie w UI, `is_active=False`; rekord `UserAchievement` zostaje, klient już jej nie zobaczy |
| Edycja odznaki z posiadaczami | Można: `name`, `description`, `rarity`, `is_hidden_until_unlocked`, `is_active`, ikona. Nie można: `slug`, `category` |
| Brak ikony pliku | Cache `_icon_cache` invalidowany; `has_achievement_icon` → False, fallback emoji |
| Email failure | try/except + log warning; grant się powiedzie |
| Nieaktywny klient | Filter w dropdownie; reaktywacja zachowuje odznakę |

### Migracja produkcyjna

- Brak backfill'u — wszystkie nowe wartości opt-in
- Przed `flask db upgrade` na VPS: `mysqldump` + sprawdzenie `SELECT DISTINCT rarity FROM achievement` w razie orphaned wartości

---

## 6. Smoke checklist (testy ręczne)

1. **Migracja lokalna** — XAMPP, sprawdź ENUM-y w phpMyAdmin
2. **Tworzenie odznaki** — `/admin/achievements/new`, upload 800×600 JPG → zapis jako `<slug>@256.png`
3. **Przyznanie ukrytej** — `is_hidden_until_unlocked=True`, przyznaj klientowi A. B nie widzi w galerii. A widzi + animacja Supernova v2.
4. **Email** — sprawdź skrzynkę / log SMTP
5. **Statystyki ukryte** — A widzi „Wyróżnienie admina" zamiast „X% klientów ma"
6. **Odbieranie** — z profilu A, „Odbierz" → znika z `UserAchievement`, wraca w dropdown
7. **Idempotency** — przyznaj 2× → drugi raz flash „już posiada"
8. **403 dla mod** — z konta `mod` próba wejścia na `/admin/achievements`
9. **Edycja z posiadaczami** — pola `slug` i `category` zablokowane

---

## 7. Out-of-scope (świadomie pominięte)

- **Bulk grant** — pojedynczo wystarczy, można dodać później bez rebuild'u
- **Powód przyznania (reason)** w UI klienta — design B, nie C
- **Versioning odznak** — niepotrzebne w skali aplikacji
- **Tier/tier_group** dla `special` — wszystkie special są niezależne, bez progresji
- **Powiadomienia push/in-app** — tylko email + animacja w galerii
- **Bulk import odznak z CSV** — można dodać później
- **Statystyki w panelu admina** (wykres przyznawanych odznak w czasie) — nice-to-have

---

## 8. Pliki do zmiany / utworzenia

### Nowe pliki

- `migrations/versions/<rev>_admin_grantable_badges.py`
- `modules/admin/achievements.py`
- `templates/admin/achievements/list.html`
- `templates/admin/achievements/form.html`
- `templates/admin/achievements/holders.html`
- `templates/emails/achievement_granted.html`
- `static/img/icons/achievements.svg` — ikona dla pozycji w sidebarze admina

### Modyfikacje

- `modules/achievements/models.py` — pola `is_hidden_until_unlocked`, `granted_by_id`, rozszerzone enumy
- `modules/achievements/services.py` — `grant_manual`, `revoke_manual`, modyfikacje `get_user_achievements`, `recalculate_stats`
- `modules/achievements/share.py` — `RARITY_COSMIC`, label `cosmic`
- `modules/admin/clients.py` — endpointy `grant_achievement`, `revoke_achievement`
- `templates/admin/clients/detail.html` — sekcja „Specjalne odznaki" + modal przyznawania
- `templates/components/sidebar_admin.html` — nowa pozycja „Odznaki" w sidebarze admina (po „Statystyki", przed „Moje zadania")
- `modules/admin/__init__.py` — rejestracja nowego modułu achievements w `admin_bp`
- `static/css/pages/client/achievements.css` — style `cosmic` + Supernova v2 spotlight
- `static/js/components/achievements-renderer.js` (lub odpowiednik) — wstrzyknięcie warstw DOM dla `cosmic`, label PL
- `utils/email_sender.py` — `send_achievement_granted_email`

---

## 9. Następne kroki

Po akceptacji tego speca → invoke skill `superpowers:writing-plans` aby utworzyć szczegółowy plan implementacji z podziałem na taski.
