# Admin-Grantable Badges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rozszerzenie systemu osiągnięć o ręczne przyznawanie specjalnych odznak przez admina, z animacją „Supernova v2", mailem i panelem CRUD.

**Architecture:** Rozszerzenie istniejącego `modules/achievements/` o `trigger_type='manual'`, kategorię `special` i rzadkość `cosmic`. Nowy moduł `modules/admin/achievements.py` (CRUD), endpointy grant/revoke w `modules/admin/clients.py`. Audit przez `granted_by_id`. Email + animacja unlock dla każdego przyznania.

**Tech Stack:** Flask, SQLAlchemy, Flask-Migrate (Alembic), Jinja2, vanilla JS, MariaDB, Pillow (PIL), Flask-Login, Flask-WTF.

**Spec:** [`docs/superpowers/specs/2026-04-26-admin-grantable-badges-design.md`](../specs/2026-04-26-admin-grantable-badges-design.md)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `modules/achievements/models.py` | Rozszerzenie ENUMów + nowe pola `is_hidden_until_unlocked`, `granted_by_id` |
| Create | `migrations/versions/xxx_admin_grantable_badges.py` | Migracja DB (auto-generowana, sprawdzić ALTER ENUM) |
| Modify | `modules/achievements/services.py` | `grant_manual`, `revoke_manual`, modyfikacje `get_user_achievements` / `recalculate_stats` / `backfill_all` |
| Modify | `modules/achievements/share.py` | `RARITY_COSMIC`, label `cosmic` w `RARITY_LABELS` |
| Modify | `utils/email_sender.py` | `send_achievement_granted_email` |
| Create | `templates/emails/achievement_granted.html` | Szablon e-maila |
| Create | `modules/admin/achievements.py` | CRUD odznak (list, new, edit, delete, holders, revoke) + Pillow upload |
| Modify | `modules/admin/__init__.py` | Rejestracja nowego modułu |
| Create | `templates/admin/achievements/list.html` | Tabela odznak z akcjami |
| Create | `templates/admin/achievements/form.html` | Formularz tworzenia/edycji |
| Create | `templates/admin/achievements/holders.html` | Lista posiadaczy z opcją „Odbierz" |
| Create | `static/img/icons/achievements.svg` | Ikona w sidebarze |
| Modify | `templates/components/sidebar_admin.html` | Pozycja „Odznaki" w menu admina |
| Modify | `modules/admin/clients.py` | Endpointy `grant_achievement`, `revoke_achievement` na profilu klienta |
| Modify | `templates/admin/clients/detail.html` | Sekcja „Specjalne odznaki" + modal przyznawania |
| Modify | `static/css/pages/client/achievements.css` | Style `cosmic` rarity (light + dark) |
| Modify | `static/css/components/modals.css` | Style modala „Przyznaj odznakę" (light + dark) |
| Create | `static/js/components/cosmic-spotlight.js` | DOM nodes + animacja Supernova v2 dla `data-rarity="cosmic"` |
| Modify | `static/js/components/achievement-spotlight.js` (lub odpowiednik) | Wstrzyknięcie `cosmic-spotlight` przy `data-rarity="cosmic"` |
| Modify | `templates/achievements/gallery.html` | Załączenie nowych JS/CSS |

> Uwaga: dokładny plik JS galerii (`achievement-spotlight.js` lub inna nazwa) zostanie zidentyfikowany w Tasku 11 — `grep` w katalogu `static/js`.

---

## Workflow konwencji

**Każdy task kończy się commitem.** Nazewnictwo commitów: `feat(achievements): <opis>` dla feature, `chore(achievements): <opis>` dla migracji/konfigów, `fix(achievements): <opis>` dla poprawek.

**Po każdej zmianie modeli:** `flask db migrate -m "..."`, ręczny przegląd pliku migracji w `migrations/versions/`, `flask db upgrade`.

**Smoke test po każdym tasku** uruchamiany przez `flask run --port 5001` (XAMPP musi działać).

---

### Task 1: Rozszerzenie ENUMów i dodanie pól w modelach

**Files:**
- Modify: `modules/achievements/models.py`

- [ ] **Step 1: Rozszerz ENUM `category` o `'special'`**

W `modules/achievements/models.py:12-16`, zmień:

```python
    category = db.Column(
        db.Enum('orders', 'collection', 'loyalty', 'speed', 'exclusive',
                'social', 'financial', 'profile', 'special',
                name='achievement_category'),
        nullable=False
    )
```

- [ ] **Step 2: Rozszerz ENUM `rarity` o `'cosmic'`**

W `modules/achievements/models.py:17-20`, zmień:

```python
    rarity = db.Column(
        db.Enum('common', 'rare', 'epic', 'legendary', 'cosmic',
                name='achievement_rarity'),
        nullable=False
    )
```

- [ ] **Step 3: Rozszerz ENUM `trigger_type` o `'manual'`**

W `modules/achievements/models.py:23-26`, zmień:

```python
    trigger_type = db.Column(
        db.Enum('event', 'cron', 'manual', name='achievement_trigger_type'),
        nullable=False
    )
```

- [ ] **Step 4: Dodaj `is_hidden_until_unlocked` do `Achievement`**

Po linii `is_active = db.Column(...)` w klasie `Achievement` dodaj:

```python
    is_hidden_until_unlocked = db.Column(db.Boolean, default=False, nullable=False)
```

- [ ] **Step 5: Dodaj `granted_by_id` do `UserAchievement`**

W klasie `UserAchievement`, po linii `created_at = db.Column(...)`:

```python
    granted_by_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True
    )
    granted_by = db.relationship('User', foreign_keys=[granted_by_id])
```

- [ ] **Step 6: Wygeneruj migrację**

```bash
flask db migrate -m "admin grantable badges: extend enums, add is_hidden_until_unlocked, granted_by_id"
```

- [ ] **Step 7: Przejrzyj plik migracji**

Otwórz najnowszy plik w `migrations/versions/`. Upewnij się, że:
- Są `op.alter_column` dla 3 enumów (`category`, `rarity`, `trigger_type`)
- Jest `op.add_column('achievement', sa.Column('is_hidden_until_unlocked', ...))` z `server_default='0'` lub `existing_nullable=False, nullable=False`
- Jest `op.add_column('user_achievement', sa.Column('granted_by_id', ...))`
- Jest `op.create_foreign_key(...)` z `ondelete='SET NULL'`

Jeśli Alembic nie wykrył ALTER ENUM (MariaDB może wymagać manualnej edycji): edytuj plik i dodaj `op.execute("ALTER TABLE achievement MODIFY category ENUM(...) NOT NULL")` analogicznie dla `rarity` i `trigger_type`.

- [ ] **Step 8: Wykonaj migrację lokalnie**

```bash
flask db upgrade
```

Expected: brak błędów, w phpMyAdmin (`http://localhost/phpmyadmin`) widać:
- `achievement.category` ENUM zawiera `'special'`
- `achievement.rarity` ENUM zawiera `'cosmic'`
- `achievement.trigger_type` ENUM zawiera `'manual'`
- `achievement.is_hidden_until_unlocked` BOOLEAN DEFAULT 0
- `user_achievement.granted_by_id` INT NULL z FK do `users.id`

- [ ] **Step 9: Commit**

```bash
git add modules/achievements/models.py migrations/versions/
git commit -m "feat(achievements): extend schema for admin-grantable badges"
```

---

### Task 2: Service `grant_manual` i `revoke_manual`

**Files:**
- Modify: `modules/achievements/services.py`

- [ ] **Step 1: Dodaj importy na górze pliku (jeśli brakuje)**

W `modules/achievements/services.py` na górze (~linia 5), upewnij się, że są:

```python
from flask import current_app, url_for
```

- [ ] **Step 2: Dodaj metodę `grant_manual` w klasie `AchievementService`**

Wstaw po metodzie `unlock(...)` (~linia 170):

```python
    def grant_manual(self, user, achievement, granted_by, send_animation=True):
        """
        Manual grant by admin. Sets granted_by_id (audit), seen=False (animation),
        sends email notification. Idempotent — returns None if already granted.
        """
        existing = UserAchievement.query.filter_by(
            user_id=user.id, achievement_id=achievement.id
        ).first()
        if existing:
            return None

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
```

- [ ] **Step 3: Dodaj metodę `revoke_manual` po `grant_manual`**

```python
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

- [ ] **Step 4: Smoke test w shell**

```bash
flask shell
```

W shellu:

```python
from modules.achievements.models import Achievement
from modules.achievements.services import AchievementService
from modules.auth.models import User

# Sprawdź, że metody istnieją (bez wywołania)
assert hasattr(AchievementService, 'grant_manual')
assert hasattr(AchievementService, 'revoke_manual')
print('OK')
```

Expected: `OK`. Wyjdź `exit()`.

- [ ] **Step 5: Commit**

```bash
git add modules/achievements/services.py
git commit -m "feat(achievements): add grant_manual and revoke_manual service methods"
```

---

### Task 3: Modyfikacje `get_user_achievements`, `recalculate_stats`, `backfill_all`

**Files:**
- Modify: `modules/achievements/services.py`

- [ ] **Step 1: Filtrowanie ukrytych odznak w `get_user_achievements`**

Znajdź `def get_user_achievements(self, user):` i pętlę `for a in all_achievements:`. Na początku ciała pętli, po `ua = unlocked_map.get(a.id)`, dodaj:

```python
            # Hide flagged achievements that user doesn't have
            if a.is_hidden_until_unlocked and not ua:
                continue
```

- [ ] **Step 2: Ukryj statystyki dla `category='special'` w `get_user_achievements`**

W tej samej pętli, znajdź gdzie są używane `stat.percentage` i `stat.total_unlocked` w `result.append({...})`. Zamień te dwa pola w dict na:

```python
                'stat_percentage': None if a.category == 'special' else (stat.percentage if stat else 0),
                'stat_total': None if a.category == 'special' else (stat.total_unlocked if stat else 0),
                'is_special': a.category == 'special',
```

- [ ] **Step 3: Pomiń `category='special'` w `recalculate_stats`**

Znajdź `def recalculate_stats(self):`. Zmień zapytanie:

```python
        achievements = Achievement.query.filter_by(is_active=True).all()
```

na:

```python
        achievements = Achievement.query.filter(
            Achievement.is_active == True,  # noqa: E712
            Achievement.category != 'special',
        ).all()
```

- [ ] **Step 4: Wyklucz `manual` z `backfill_all`**

Znajdź `def backfill_all(self):` i linię `all_achievements = Achievement.query.filter_by(is_active=True).all()`. Zamień na:

```python
        all_achievements = Achievement.query.filter(
            Achievement.is_active == True,  # noqa: E712
            Achievement.trigger_type.in_(['event', 'cron']),
        ).all()
```

- [ ] **Step 5: Smoke test w shell**

```bash
flask shell
```

```python
from modules.achievements.services import AchievementService
from modules.auth.models import User

svc = AchievementService()
user = User.query.filter_by(role='client').first()
if user:
    result = svc.get_user_achievements(user)
    print(f'Returned {len(result)} achievements')
    if result:
        print(f'Keys: {list(result[0].keys())}')
        print(f'is_special present: {"is_special" in result[0]}')
```

Expected: lista odznak, `is_special: True` widoczne w kluczach.

- [ ] **Step 6: Commit**

```bash
git add modules/achievements/services.py
git commit -m "feat(achievements): hide flagged achievements + special stats; exclude manual from backfill"
```

---

### Task 4: Email helper i szablon „achievement granted"

**Files:**
- Modify: `utils/email_sender.py`
- Create: `templates/emails/achievement_granted.html`

- [ ] **Step 1: Sprawdź wzorzec helpera**

```bash
grep -A 8 "def send_back_in_stock_email" utils/email_sender.py | head -15
```

Zapamiętaj wzorzec — zwykle wywołuje `send_email(to, subject, template, **kwargs)`.

- [ ] **Step 2: Dodaj helper na końcu `utils/email_sender.py`**

```python
def send_achievement_granted_email(user_email, user_name, achievement_name,
                                   achievement_description, achievement_slug,
                                   gallery_url):
    """
    E-mail wysyłany po ręcznym przyznaniu odznaki przez admina.
    """
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

- [ ] **Step 3: Sprawdź wzorzec istniejącego szablonu e-maila**

```bash
cat templates/emails/back_in_stock.html | head -40
```

Zauważ strukturę: nagłówek z gradientem, treść, CTA, footer.

- [ ] **Step 4: Utwórz `templates/emails/achievement_granted.html`**

Skopiuj strukturę z `templates/emails/back_in_stock.html` i dostosuj. Pełny szablon (samodzielny HTML, bez `extends` — istniejące e-maile w projekcie również są samodzielne):

```html
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <title>Otrzymałeś specjalną odznakę</title>
</head>
<body style="margin:0;padding:0;background:#0f0f23;font-family:Arial,sans-serif;color:#fff;">
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#0f0f23;padding:32px 16px;">
        <tr>
            <td align="center">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width:600px;background:linear-gradient(135deg,#1e1b4b 0%,#0f0f23 100%);border:1px solid rgba(168,85,247,0.4);border-radius:16px;overflow:hidden;">
                    <tr>
                        <td style="padding:48px 40px 24px;text-align:center;background:radial-gradient(ellipse at 50% 0%,rgba(106,13,173,0.4) 0%,transparent 70%);">
                            <h1 style="margin:0;font-size:28px;color:#fff;">🎖️ Wyróżnienie!</h1>
                            <p style="margin:12px 0 0;color:#c084fc;font-size:14px;letter-spacing:2px;text-transform:uppercase;">Specjalna odznaka</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:32px 40px;text-align:center;">
                            <p style="margin:0 0 20px;font-size:16px;color:#fff;">Cześć {{ user_name }}!</p>
                            <p style="margin:0 0 32px;font-size:15px;color:rgba(255,255,255,0.85);line-height:1.6;">
                                Otrzymałeś od nas specjalną odznakę. To wyjątkowe wyróżnienie przyznawane ręcznie przez zespół.
                            </p>
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:0 auto 32px;background:rgba(168,85,247,0.1);border:1px solid rgba(168,85,247,0.4);border-radius:12px;padding:24px;max-width:400px;">
                                <tr>
                                    <td align="center">
                                        <h2 style="margin:0 0 8px;color:#fff;font-size:22px;">{{ achievement_name }}</h2>
                                        <p style="margin:0;color:rgba(255,255,255,0.8);font-size:14px;">{{ achievement_description }}</p>
                                    </td>
                                </tr>
                            </table>
                            <a href="{{ gallery_url }}" style="display:inline-block;padding:14px 32px;background:linear-gradient(135deg,#8b5cf6 0%,#3730a3 100%);color:#fff;text-decoration:none;border-radius:8px;font-weight:700;">Zobacz w galerii odznak</a>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:24px 40px;border-top:1px solid rgba(255,255,255,0.1);text-align:center;color:rgba(255,255,255,0.5);font-size:12px;">
                            ThunderOrders &copy; 2026
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
```

> Jeśli inne szablony e-mail w projekcie używają zmiennej `current_year` z kontekstu, dostosuj odpowiednio (zamiast hardcoded `2026`).

- [ ] **Step 5: Smoke test wysyłki**

```bash
flask shell
```

```python
from utils.email_sender import send_achievement_granted_email
# Lokalny test — sprawdź, czy nie ma błędu importu/render
result = send_achievement_granted_email(
    user_email='test@example.com',
    user_name='Tester',
    achievement_name='Beta Tester',
    achievement_description='Testujesz aplikację z nami',
    achievement_slug='beta-tester',
    gallery_url='http://localhost:5001/achievements'
)
print('Result:', result)
```

Expected: brak wyjątku przy renderowaniu szablonu. Email może faktycznie nie wyjść (bez SMTP), ale wywołanie nie powinno crashować.

- [ ] **Step 6: Commit**

```bash
git add utils/email_sender.py templates/emails/achievement_granted.html
git commit -m "feat(achievements): add achievement_granted email template + helper"
```

---

### Task 5: Utility do uploadu ikony (Pillow)

**Files:**
- Create: `modules/admin/achievements.py` (na razie tylko utility, reszta w Tasku 6)

- [ ] **Step 1: Sprawdź czy Pillow jest w requirements**

```bash
grep -i "pillow\|^Pillow" requirements.txt
```

Expected: linia `Pillow==X.Y.Z`. Jeśli brak, dodaj `Pillow>=10.0.0` i `pip install -r requirements.txt`.

- [ ] **Step 2: Utwórz szkielet `modules/admin/achievements.py`**

```python
"""
Admin CRUD for achievements (manual badges).
"""
import os
import re
from flask import current_app, request, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from PIL import Image

from extensions import db
from modules.admin import admin_bp
from modules.achievements.models import Achievement, UserAchievement
from modules.achievements import services as achievements_services
from modules.auth.models import User
from utils.decorators import admin_required


ALLOWED_IMAGE_MIMES = {'image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif'}
SLUG_RE = re.compile(r'^[a-z0-9-]+$')
MAX_ICON_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MIN_ICON_DIMENSION = 64


def _slugify(name):
    """Bardzo prosta slugifikacja PL → ASCII bez polskich znaków."""
    pl_map = str.maketrans({
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
        'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
        'Ą': 'a', 'Ć': 'c', 'Ę': 'e', 'Ł': 'l', 'Ń': 'n',
        'Ó': 'o', 'Ś': 's', 'Ź': 'z', 'Ż': 'z',
    })
    s = name.translate(pl_map).lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:80] or 'badge'


def _ensure_unique_slug(base_slug, exclude_id=None):
    """Zwraca slug + ewentualny suffix -2, -3, jeśli kolizja."""
    slug = base_slug
    n = 2
    while True:
        q = Achievement.query.filter_by(slug=slug)
        if exclude_id is not None:
            q = q.filter(Achievement.id != exclude_id)
        if not q.first():
            return slug
        slug = f'{base_slug}-{n}'
        n += 1


def _process_icon_upload(file_storage, slug):
    """
    Waliduje i zapisuje ikonę jako <slug>@256.png w static/uploads/achievements/.
    Rzuca ValueError przy błędzie walidacji.
    """
    if not file_storage or not file_storage.filename:
        raise ValueError('Brak pliku ikony')

    if file_storage.mimetype not in ALLOWED_IMAGE_MIMES:
        raise ValueError(f'Nieobsługiwany format: {file_storage.mimetype}')

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > MAX_ICON_SIZE_BYTES:
        raise ValueError(f'Plik za duży ({size} B), max {MAX_ICON_SIZE_BYTES} B')

    try:
        img = Image.open(file_storage.stream)
        img.verify()
    except Exception as e:
        raise ValueError(f'Nieprawidłowy plik obrazu: {e}')

    file_storage.stream.seek(0)
    img = Image.open(file_storage.stream).convert('RGBA')

    if img.width < MIN_ICON_DIMENSION or img.height < MIN_ICON_DIMENSION:
        raise ValueError(f'Obraz za mały ({img.width}×{img.height}), min {MIN_ICON_DIMENSION}×{MIN_ICON_DIMENSION}')

    img.thumbnail((256, 256), Image.LANCZOS)
    canvas = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    x = (256 - img.width) // 2
    y = (256 - img.height) // 2
    canvas.paste(img, (x, y), img)

    if not SLUG_RE.match(slug):
        raise ValueError(f'Nieprawidłowy slug: {slug}')

    upload_dir = os.path.join(current_app.static_folder, 'uploads', 'achievements')
    os.makedirs(upload_dir, exist_ok=True)
    out_path = os.path.join(upload_dir, f'{slug}@256.png')
    canvas.save(out_path, 'PNG', optimize=True)

    # Invalidate icon cache
    from modules.achievements.services import _icon_cache
    _icon_cache.pop(slug, None)
```

- [ ] **Step 3: Smoke test utility w shell**

```bash
flask shell
```

```python
from modules.admin.achievements import _slugify, _ensure_unique_slug
print(_slugify('Beta Tester'))  # 'beta-tester'
print(_slugify('Złoty Klient!'))  # 'zloty-klient'
print(_ensure_unique_slug('first-order'))  # 'first-order-2' (bo jest taki)
```

Expected: `beta-tester`, `zloty-klient`, `first-order-2`.

- [ ] **Step 4: Commit**

```bash
git add modules/admin/achievements.py
git commit -m "feat(admin/achievements): add icon upload utility (Pillow)"
```

---

### Task 6: Endpointy CRUD odznak

**Files:**
- Modify: `modules/admin/achievements.py`
- Modify: `modules/admin/__init__.py`

- [ ] **Step 1: Sprawdź jak `__init__.py` rejestruje moduły**

```bash
cat modules/admin/__init__.py
```

Zobacz wzorzec importów (np. `from . import offers`).

- [ ] **Step 2: Dodaj import w `modules/admin/__init__.py`**

Po istniejących importach (np. `from . import clients, offers, ...`):

```python
from . import achievements as _achievements_admin  # noqa: F401
```

- [ ] **Step 3: Dodaj endpointy do `modules/admin/achievements.py`**

Na końcu pliku, po utility:

```python
# ========== ENDPOINTY ==========

@admin_bp.route('/achievements')
@login_required
@admin_required
def achievements_list():
    achievements = Achievement.query.order_by(
        Achievement.trigger_type.desc(),  # 'manual' first ('manual' > 'event' > 'cron')
        Achievement.sort_order
    ).all()
    holders_count = {
        ach.id: UserAchievement.query.filter_by(achievement_id=ach.id).count()
        for ach in achievements
    }
    return render_template(
        'admin/achievements/list.html',
        achievements=achievements,
        holders_count=holders_count,
    )


@admin_bp.route('/achievements/new', methods=['GET', 'POST'])
@login_required
@admin_required
def achievements_new():
    if request.method == 'POST':
        return _save_achievement(achievement=None)
    return render_template('admin/achievements/form.html', achievement=None, holders_count=0)


@admin_bp.route('/achievements/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def achievements_edit(id):
    achievement = Achievement.query.get_or_404(id)
    holders_count = UserAchievement.query.filter_by(achievement_id=id).count()
    if request.method == 'POST':
        return _save_achievement(achievement=achievement)
    return render_template(
        'admin/achievements/form.html',
        achievement=achievement,
        holders_count=holders_count,
    )


def _save_achievement(achievement):
    """Wspólna logika save dla new i edit."""
    is_new = achievement is None
    holders_count = 0 if is_new else UserAchievement.query.filter_by(achievement_id=achievement.id).count()

    name = (request.form.get('name') or '').strip()
    description = (request.form.get('description') or '').strip()
    category = request.form.get('category', 'special')
    rarity = request.form.get('rarity', 'cosmic')
    is_hidden = bool(request.form.get('is_hidden_until_unlocked'))
    is_active = bool(request.form.get('is_active'))
    slug_input = (request.form.get('slug') or '').strip().lower()

    # Walidacja
    errors = []
    if not name or len(name) > 120:
        errors.append('Nazwa wymagana, max 120 znaków.')
    if not description or len(description) > 255:
        errors.append('Opis wymagany, max 255 znaków.')
    if category not in ('orders', 'collection', 'loyalty', 'speed', 'exclusive',
                        'social', 'financial', 'profile', 'special'):
        errors.append('Nieprawidłowa kategoria.')
    if rarity not in ('common', 'rare', 'epic', 'legendary', 'cosmic'):
        errors.append('Nieprawidłowa rzadkość.')

    # Slug — auto-gen jeśli puste
    if not slug_input:
        slug_input = _slugify(name)
    if not SLUG_RE.match(slug_input):
        errors.append('Slug może zawierać tylko a-z, 0-9, "-".')

    # Edycja: pola zablokowane gdy są posiadacze
    if not is_new and holders_count > 0:
        if slug_input != achievement.slug:
            errors.append('Nie można zmienić slug — odznaka ma posiadaczy.')
        if category != achievement.category:
            errors.append('Nie można zmienić kategorii — odznaka ma posiadaczy.')

    if errors:
        for err in errors:
            flash(err, 'error')
        return render_template(
            'admin/achievements/form.html',
            achievement=achievement,
            holders_count=holders_count,
        ), 400

    # Slug uniqueness
    final_slug = _ensure_unique_slug(slug_input, exclude_id=None if is_new else achievement.id)

    # Upload ikony
    icon_file = request.files.get('icon')
    if is_new and (not icon_file or not icon_file.filename):
        flash('Ikona jest wymagana przy tworzeniu odznaki.', 'error')
        return render_template('admin/achievements/form.html', achievement=achievement, holders_count=holders_count), 400

    if icon_file and icon_file.filename:
        try:
            _process_icon_upload(icon_file, final_slug)
        except ValueError as e:
            flash(f'Błąd ikony: {e}', 'error')
            return render_template('admin/achievements/form.html', achievement=achievement, holders_count=holders_count), 400

    # Save
    if is_new:
        achievement = Achievement(
            slug=final_slug,
            name=name,
            description=description,
            category=category,
            rarity=rarity,
            trigger_type='manual',
            trigger_config={},
            is_hidden_until_unlocked=is_hidden,
            is_active=is_active,
            sort_order=999,  # manual badges sortuj na końcu domyślnie
        )
        db.session.add(achievement)
    else:
        achievement.name = name
        achievement.description = description
        achievement.rarity = rarity
        achievement.is_hidden_until_unlocked = is_hidden
        achievement.is_active = is_active
        if holders_count == 0:
            achievement.slug = final_slug
            achievement.category = category

    db.session.commit()

    flash(f'Odznaka „{achievement.name}" zapisana.', 'success')
    return redirect(url_for('admin.achievements_list'))


@admin_bp.route('/achievements/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def achievements_delete(id):
    """Soft-delete: is_active=False."""
    achievement = Achievement.query.get_or_404(id)
    achievement.is_active = False
    db.session.commit()
    flash(f'Odznaka „{achievement.name}" dezaktywowana.', 'success')
    return redirect(url_for('admin.achievements_list'))


@admin_bp.route('/achievements/<int:id>/holders')
@login_required
@admin_required
def achievements_holders(id):
    achievement = Achievement.query.get_or_404(id)
    holders = (UserAchievement.query
               .filter_by(achievement_id=id)
               .join(User, UserAchievement.user_id == User.id)
               .order_by(UserAchievement.unlocked_at.desc())
               .all())
    return render_template(
        'admin/achievements/holders.html',
        achievement=achievement,
        holders=holders,
    )


@admin_bp.route('/achievements/<int:id>/holders/<int:user_id>/revoke', methods=['POST'])
@login_required
@admin_required
def achievements_revoke_holder(id, user_id):
    achievement = Achievement.query.get_or_404(id)
    user = User.query.get_or_404(user_id)

    if achievement.trigger_type != 'manual':
        flash('Można odbierać tylko odznaki ręczne.', 'error')
        return redirect(url_for('admin.achievements_holders', id=id))

    service = achievements_services.AchievementService()
    if service.revoke_manual(user, achievement, revoked_by=current_user):
        flash(f'Odebrano „{achievement.name}" od {user.email}.', 'success')
    else:
        flash('Klient nie posiadał tej odznaki.', 'warning')
    return redirect(url_for('admin.achievements_holders', id=id))
```

- [ ] **Step 4: Smoke test rejestracji endpointów**

```bash
flask routes | grep achievement
```

Expected: 6 nowych endpointów: `achievements_list`, `achievements_new`, `achievements_edit`, `achievements_delete`, `achievements_holders`, `achievements_revoke_holder`.

- [ ] **Step 5: Commit**

```bash
git add modules/admin/achievements.py modules/admin/__init__.py
git commit -m "feat(admin/achievements): CRUD endpoints (list, new, edit, delete, holders)"
```

---

### Task 7: Szablon listy odznak `templates/admin/achievements/list.html`

**Files:**
- Create: `templates/admin/achievements/list.html`

- [ ] **Step 1: Sprawdź wzorzec istniejącej listy admin**

```bash
ls templates/admin/clients/
head -30 templates/admin/clients/list.html
```

- [ ] **Step 2: Utwórz `templates/admin/achievements/list.html`**

```html
{% extends 'admin/base_admin.html' %}

{% block title %}Odznaki — Admin{% endblock %}

{% block content %}
<div class="admin-page">
    <div class="admin-page-header">
        <h1>Odznaki</h1>
        <a href="{{ url_for('admin.achievements_new') }}" class="btn btn-primary">+ Nowa odznaka</a>
    </div>

    <table class="admin-table">
        <thead>
            <tr>
                <th>Ikona</th>
                <th>Nazwa</th>
                <th>Slug</th>
                <th>Kategoria</th>
                <th>Rzadkość</th>
                <th>Typ</th>
                <th>Posiadacze</th>
                <th>Aktywna</th>
                <th>Akcje</th>
            </tr>
        </thead>
        <tbody>
            {% for ach in achievements %}
            <tr>
                <td>
                    <img src="{{ url_for('static', filename='uploads/achievements/' + ach.slug + '@256.png') }}"
                         alt="{{ ach.name }}"
                         style="width:40px;height:40px;border-radius:50%;object-fit:cover;"
                         onerror="this.style.display='none'">
                </td>
                <td><strong>{{ ach.name }}</strong><br><small>{{ ach.description }}</small></td>
                <td><code>{{ ach.slug }}</code></td>
                <td><span class="badge badge-category badge-{{ ach.category }}">{{ ach.category }}</span></td>
                <td><span class="badge badge-rarity badge-{{ ach.rarity }}">{{ ach.rarity }}</span></td>
                <td>
                    {% if ach.trigger_type == 'manual' %}
                        <span class="badge badge-manual">manual</span>
                    {% else %}
                        <span class="badge badge-auto">{{ ach.trigger_type }}</span>
                    {% endif %}
                </td>
                <td>
                    <a href="{{ url_for('admin.achievements_holders', id=ach.id) }}">{{ holders_count[ach.id] }}</a>
                </td>
                <td>
                    {% if ach.is_active %}<span class="text-success">Tak</span>{% else %}<span class="text-muted">Nie</span>{% endif %}
                </td>
                <td>
                    <a href="{{ url_for('admin.achievements_edit', id=ach.id) }}" class="btn btn-sm btn-secondary">Edytuj</a>
                    {% if ach.is_active %}
                    <form method="POST" action="{{ url_for('admin.achievements_delete', id=ach.id) }}" style="display:inline" onsubmit="return confirm('Dezaktywować odznakę „{{ ach.name }}"?')">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                        <button type="submit" class="btn btn-sm btn-danger">Dezaktywuj</button>
                    </form>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
```

- [ ] **Step 3: Smoke test w przeglądarce**

```bash
flask run --port 5001
```

Otwórz `http://localhost:5001/admin/achievements`. Expected: tabela z istniejącymi odznakami (na razie wszystkie auto). Brak crashy.

- [ ] **Step 4: Commit**

```bash
git add templates/admin/achievements/list.html
git commit -m "feat(admin/achievements): list view template"
```

---

### Task 8: Szablon formularza `templates/admin/achievements/form.html`

**Files:**
- Create: `templates/admin/achievements/form.html`

- [ ] **Step 1: Utwórz formularz**

```html
{% extends 'admin/base_admin.html' %}

{% block title %}{{ 'Edycja' if achievement else 'Nowa' }} odznaka — Admin{% endblock %}

{% block content %}
<div class="admin-page">
    <div class="admin-page-header">
        <h1>{{ 'Edycja' if achievement else 'Nowa' }} odznaka</h1>
        <a href="{{ url_for('admin.achievements_list') }}" class="btn btn-link">← Powrót</a>
    </div>

    {% if achievement and holders_count > 0 %}
    <div class="alert alert-info">
        Tę odznakę posiada <strong>{{ holders_count }}</strong> klient(ów). Pola <code>slug</code> i <code>kategoria</code> są zablokowane.
    </div>
    {% endif %}

    <form method="POST" enctype="multipart/form-data" class="admin-form">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

        <div class="form-group">
            <label for="name">Nazwa *</label>
            <input type="text" id="name" name="name" required maxlength="120"
                   value="{{ achievement.name if achievement else '' }}">
        </div>

        <div class="form-group">
            <label for="slug">Slug (auto z nazwy jeśli puste)</label>
            <input type="text" id="slug" name="slug" maxlength="80"
                   pattern="[a-z0-9-]+"
                   value="{{ achievement.slug if achievement else '' }}"
                   {% if achievement and holders_count > 0 %}readonly{% endif %}>
            <small>Tylko a-z, 0-9, „-".</small>
        </div>

        <div class="form-group">
            <label for="description">Opis *</label>
            <input type="text" id="description" name="description" required maxlength="255"
                   value="{{ achievement.description if achievement else '' }}">
        </div>

        <div class="form-row">
            <div class="form-group">
                <label for="category">Kategoria *</label>
                <select id="category" name="category" required {% if achievement and holders_count > 0 %}disabled{% endif %}>
                    {% for c in ['special', 'orders', 'collection', 'loyalty', 'speed', 'exclusive', 'social', 'financial', 'profile'] %}
                    <option value="{{ c }}" {% if achievement and achievement.category == c %}selected{% elif not achievement and c == 'special' %}selected{% endif %}>{{ c }}</option>
                    {% endfor %}
                </select>
                {% if achievement and holders_count > 0 %}
                <input type="hidden" name="category" value="{{ achievement.category }}">
                {% endif %}
            </div>

            <div class="form-group">
                <label for="rarity">Rzadkość *</label>
                <select id="rarity" name="rarity" required>
                    {% for r in ['cosmic', 'legendary', 'epic', 'rare', 'common'] %}
                    <option value="{{ r }}" {% if achievement and achievement.rarity == r %}selected{% elif not achievement and r == 'cosmic' %}selected{% endif %}>{{ r }}</option>
                    {% endfor %}
                </select>
            </div>
        </div>

        <div class="form-group">
            <label for="icon">Ikona {% if not achievement %}*{% endif %}</label>
            <input type="file" id="icon" name="icon" accept="image/png,image/jpeg,image/webp,image/gif">
            <small>Min 64×64. Plik zostanie auto-resize'owany do 256×256 PNG. Max 5MB.</small>
            {% if achievement %}
            <div style="margin-top:8px;">
                <img src="{{ url_for('static', filename='uploads/achievements/' + achievement.slug + '@256.png') }}"
                     alt="Aktualna ikona"
                     style="width:64px;height:64px;border-radius:50%;"
                     onerror="this.style.display='none'">
                <small>Aktualna ikona — wgraj nowy plik aby zastąpić.</small>
            </div>
            {% endif %}
        </div>

        <div class="form-group">
            <label class="checkbox-label">
                <input type="checkbox" name="is_hidden_until_unlocked"
                       {% if achievement and achievement.is_hidden_until_unlocked %}checked{% endif %}>
                Ukryta dopóki nie zostanie przyznana (klient jej nie zobaczy)
            </label>
        </div>

        <div class="form-group">
            <label class="checkbox-label">
                <input type="checkbox" name="is_active"
                       {% if not achievement or achievement.is_active %}checked{% endif %}>
                Aktywna
            </label>
        </div>

        <div class="form-actions">
            <button type="submit" class="btn btn-primary">{{ 'Zapisz' if achievement else 'Utwórz' }}</button>
            <a href="{{ url_for('admin.achievements_list') }}" class="btn btn-link">Anuluj</a>
        </div>
    </form>
</div>
{% endblock %}
```

- [ ] **Step 2: Smoke test — utwórz testową odznakę**

W przeglądarce: `/admin/achievements/new`. Wypełnij:
- Nazwa: `Beta Tester`
- Opis: `Pomógł nam testować nową wersję`
- Kategoria: `special`
- Rzadkość: `cosmic`
- Ikona: dowolny PNG/JPG (min 64×64)

Zapisz. Expected: redirect na listę, na liście widać nową pozycję.

```bash
ls -la static/uploads/achievements/beta-tester@256.png
```

Expected: plik 256×256 PNG.

- [ ] **Step 3: Commit**

```bash
git add templates/admin/achievements/form.html
git commit -m "feat(admin/achievements): create/edit form template"
```

---

### Task 9: Szablon listy posiadaczy `templates/admin/achievements/holders.html`

**Files:**
- Create: `templates/admin/achievements/holders.html`

- [ ] **Step 1: Utwórz szablon**

```html
{% extends 'admin/base_admin.html' %}

{% block title %}Posiadacze odznaki „{{ achievement.name }}" — Admin{% endblock %}

{% block content %}
<div class="admin-page">
    <div class="admin-page-header">
        <h1>Posiadacze: {{ achievement.name }}</h1>
        <a href="{{ url_for('admin.achievements_list') }}" class="btn btn-link">← Powrót do listy</a>
    </div>

    <p>Liczba posiadaczy: <strong>{{ holders|length }}</strong></p>

    {% if holders %}
    <table class="admin-table">
        <thead>
            <tr>
                <th>Klient</th>
                <th>E-mail</th>
                <th>Przyznano</th>
                <th>Przez kogo</th>
                <th>Akcje</th>
            </tr>
        </thead>
        <tbody>
            {% for ua in holders %}
            <tr>
                <td>
                    <a href="{{ url_for('admin.client_detail', id=ua.user.id) }}">
                        {{ ua.user.first_name or ua.user.email }}
                    </a>
                </td>
                <td>{{ ua.user.email }}</td>
                <td>{{ ua.unlocked_at.strftime('%Y-%m-%d %H:%M') }}</td>
                <td>
                    {% if ua.granted_by %}
                        {{ ua.granted_by.email }}
                    {% else %}
                        <small class="text-muted">automat</small>
                    {% endif %}
                </td>
                <td>
                    {% if achievement.trigger_type == 'manual' %}
                    <form method="POST"
                          action="{{ url_for('admin.achievements_revoke_holder', id=achievement.id, user_id=ua.user.id) }}"
                          style="display:inline"
                          onsubmit="return confirm('Odebrać odznakę od {{ ua.user.email }}?')">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                        <button type="submit" class="btn btn-sm btn-danger">Odbierz</button>
                    </form>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <p class="text-muted">Brak posiadaczy.</p>
    {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 2: Smoke test**

W przeglądarce: kliknij liczbę „0" przy odznace „Beta Tester" → wejście na `/admin/achievements/<id>/holders`. Expected: strona pokazuje „Brak posiadaczy".

- [ ] **Step 3: Commit**

```bash
git add templates/admin/achievements/holders.html
git commit -m "feat(admin/achievements): holders list template with revoke action"
```

---

### Task 10: Wpis w sidebarze admina + ikona

**Files:**
- Create: `static/img/icons/achievements.svg`
- Modify: `templates/components/sidebar_admin.html`

- [ ] **Step 1: Utwórz prostą ikonę SVG**

Sprawdź wzorzec istniejących ikon:

```bash
cat static/img/icons/clients.svg | head -10
```

Zwróć uwagę na atrybuty (viewBox, fill). Zapisz `static/img/icons/achievements.svg` (medal/gwiazda):

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="8" r="6"/>
    <path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/>
</svg>
```

> Jeśli istniejące ikony używają `fill="currentColor"` zamiast stroke — dostosuj. Sprawdź.

- [ ] **Step 2: Dodaj wpis w sidebarze**

W `templates/components/sidebar_admin.html`, znajdź pozycję „Statystyki" (~linia 140-147). **Po niej**, przed pozycją „Moje zadania" (~linia 149), wstaw:

```html
            {% if current_user.role == 'admin' %}
            <li class="sidebar-item">
                <a href="{{ url_for('admin.achievements_list') }}"
                   class="sidebar-link {% if request.endpoint and 'achievement' in request.endpoint %}active{% endif %}"
                   data-tooltip="Odznaki">
                    <img src="{{ url_for('static', filename='img/icons/achievements.svg') }}" alt="Odznaki" class="sidebar-icon">
                    <span class="sidebar-text">Odznaki</span>
                </a>
            </li>
            {% endif %}
```

- [ ] **Step 3: Smoke test**

Odśwież `/admin/achievements`. Expected: w sidebarze widać „Odznaki" z ikoną, po Statystykach. Klik prowadzi do listy odznak. Active state podświetla się na stronie odznak.

Zaloguj się jako mod (jeśli istnieje konto): pozycja nie powinna być widoczna.

- [ ] **Step 4: Commit**

```bash
git add static/img/icons/achievements.svg templates/components/sidebar_admin.html
git commit -m "feat(admin): add Odznaki entry to admin sidebar"
```

---

### Task 11: Sekcja „Specjalne odznaki" na profilu klienta

**Files:**
- Modify: `modules/admin/clients.py`
- Modify: `templates/admin/clients/detail.html`
- Modify: `static/css/components/modals.css`

- [ ] **Step 1: Dodaj endpointy grant/revoke w `modules/admin/clients.py`**

Na końcu `modules/admin/clients.py`:

```python
@admin_bp.route('/clients/<int:id>/grant-achievement', methods=['POST'])
@login_required
@admin_required
def grant_achievement(id):
    from modules.achievements.models import Achievement
    from modules.achievements.services import AchievementService

    user = User.query.get_or_404(id)
    achievement_id = request.form.get('achievement_id', type=int)
    if not achievement_id:
        flash('Brak ID odznaki.', 'error')
        return redirect(url_for('admin.client_detail', id=id))

    achievement = Achievement.query.filter_by(
        id=achievement_id, trigger_type='manual', is_active=True
    ).first()
    if not achievement:
        flash('Nie znaleziono aktywnej odznaki.', 'error')
        return redirect(url_for('admin.client_detail', id=id))

    service = AchievementService()
    ua = service.grant_manual(user, achievement, granted_by=current_user)
    if ua:
        flash(f'Przyznano odznakę „{achievement.name}".', 'success')
    else:
        flash('Klient już posiada tę odznakę.', 'warning')
    return redirect(url_for('admin.client_detail', id=id))


@admin_bp.route('/clients/<int:id>/revoke-achievement/<int:ach_id>', methods=['POST'])
@login_required
@admin_required
def revoke_achievement(id, ach_id):
    from modules.achievements.models import Achievement
    from modules.achievements.services import AchievementService

    user = User.query.get_or_404(id)
    achievement = Achievement.query.filter_by(
        id=ach_id, trigger_type='manual'
    ).first_or_404()

    service = AchievementService()
    if service.revoke_manual(user, achievement, revoked_by=current_user):
        flash(f'Odebrano „{achievement.name}".', 'success')
    else:
        flash('Klient nie posiadał tej odznaki.', 'warning')
    return redirect(url_for('admin.client_detail', id=id))
```

- [ ] **Step 2: Sprawdź gdzie w `modules/admin/clients.py` jest renderowany `client_detail` — dodaj kontekst do template**

W funkcji `client_detail(id)` (linia 126), znajdź `return render_template(...)`. Przed return dodaj:

```python
    from modules.achievements.models import Achievement, UserAchievement

    # Specjalne odznaki klienta (manual)
    user_special_badges = (UserAchievement.query
        .filter_by(user_id=user.id)
        .join(Achievement)
        .filter(Achievement.trigger_type == 'manual')
        .order_by(UserAchievement.unlocked_at.desc())
        .all())

    # Lista dostępnych do przyznania (manual + active + nie posiadanych przez klienta)
    owned_ids = [ua.achievement_id for ua in user_special_badges]
    available_special_badges = Achievement.query.filter(
        Achievement.trigger_type == 'manual',
        Achievement.is_active == True,  # noqa: E712
        ~Achievement.id.in_(owned_ids) if owned_ids else True,
    ).order_by(Achievement.name).all()
```

W `render_template(...)` dodaj kwargs:

```python
    return render_template(
        'admin/clients/detail.html',
        # ... istniejące kwargs ...
        user_special_badges=user_special_badges,
        available_special_badges=available_special_badges,
    )
```

- [ ] **Step 3: Dodaj sekcję w `templates/admin/clients/detail.html`**

Znajdź odpowiednie miejsce w istniejącym szablonie (np. po sekcji „Statystyki" lub w odpowiedniej zakładce). Wklej:

```html
<div class="card-section">
    <div class="section-header">
        <h3>Specjalne odznaki</h3>
        {% if available_special_badges %}
        <button type="button" class="btn btn-sm btn-primary" onclick="document.getElementById('grant-badge-modal').classList.add('active')">
            + Przyznaj odznakę
        </button>
        {% endif %}
    </div>

    {% if user_special_badges %}
    <ul class="special-badges-list">
        {% for ua in user_special_badges %}
        <li>
            <img src="{{ url_for('static', filename='uploads/achievements/' + ua.achievement.slug + '@256.png') }}"
                 alt="" style="width:48px;height:48px;border-radius:50%;"
                 onerror="this.style.display='none'">
            <div>
                <strong>{{ ua.achievement.name }}</strong>
                <br>
                <small>{{ ua.achievement.description }} · {{ ua.unlocked_at.strftime('%Y-%m-%d') }}</small>
            </div>
            <form method="POST"
                  action="{{ url_for('admin.revoke_achievement', id=user.id, ach_id=ua.achievement_id) }}"
                  style="margin-left:auto"
                  onsubmit="return confirm('Odebrać „{{ ua.achievement.name }}"?')">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <button type="submit" class="btn btn-sm btn-danger">Odbierz</button>
            </form>
        </li>
        {% endfor %}
    </ul>
    {% else %}
    <p class="text-muted">Klient nie posiada żadnych specjalnych odznak.</p>
    {% endif %}
</div>

<!-- Modal: Przyznaj odznakę -->
<div id="grant-badge-modal" class="modal-overlay">
    <div class="modal-content modal-grant-badge">
        <div class="modal-header">
            <h3>Przyznaj specjalną odznakę</h3>
            <button type="button" class="modal-close" onclick="document.getElementById('grant-badge-modal').classList.remove('active')">×</button>
        </div>
        <form method="POST" action="{{ url_for('admin.grant_achievement', id=user.id) }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="modal-body">
                <label for="achievement_id">Wybierz odznakę:</label>
                <select id="achievement_id" name="achievement_id" required>
                    <option value="">— wybierz —</option>
                    {% for a in available_special_badges %}
                    <option value="{{ a.id }}">{{ a.name }} ({{ a.rarity }}) — {{ a.description }}</option>
                    {% endfor %}
                </select>
                <p class="text-muted" style="margin-top:12px;font-size:0.85em;">
                    Klient otrzyma e-mail i animację w galerii odznak.
                </p>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-link" onclick="document.getElementById('grant-badge-modal').classList.remove('active')">Anuluj</button>
                <button type="submit" class="btn btn-primary">Przyznaj</button>
            </div>
        </form>
    </div>
</div>
```

- [ ] **Step 4: Style modala w `static/css/components/modals.css`**

Na końcu pliku dodaj:

```css
/* === Modal: Przyznaj odznakę (admin/clients/detail.html) === */
.modal-grant-badge {
    max-width: 540px;
    width: 92%;
}

.modal-grant-badge .modal-body select {
    width: 100%;
    padding: 10px 12px;
    margin-top: 8px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    background: #fff;
    font-size: 14px;
}

.modal-grant-badge .modal-body label {
    display: block;
    font-weight: 600;
    margin-bottom: 4px;
    color: #1f2937;
}

.special-badges-list {
    list-style: none;
    padding: 0;
    margin: 12px 0 0;
}

.special-badges-list li {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    margin-bottom: 8px;
}

/* Dark mode */
[data-theme="dark"] .modal-grant-badge .modal-body select {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(240, 147, 251, 0.3);
    color: #fff;
}

[data-theme="dark"] .modal-grant-badge .modal-body label {
    color: rgba(255, 255, 255, 0.9);
}

[data-theme="dark"] .special-badges-list li {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(240, 147, 251, 0.15);
    color: #fff;
}

[data-theme="dark"] .special-badges-list li small {
    color: rgba(255, 255, 255, 0.6);
}
```

- [ ] **Step 5: Smoke test**

Wejdź na profil dowolnego klienta `/admin/clients/<id>`. Expected:
- Sekcja „Specjalne odznaki" widoczna
- Komunikat „Klient nie posiada żadnych specjalnych odznak"
- Przycisk „+ Przyznaj odznakę"
- Klik → modal otwiera się
- Wybierz „Beta Tester" z dropdown, „Przyznaj"
- Flash: „Przyznano odznakę „Beta Tester""
- Po reloadzie — odznaka widoczna na liście, przycisk „Odbierz"

```bash
flask shell
```

```python
from modules.achievements.models import UserAchievement
print(UserAchievement.query.filter_by(granted_by_id=1).all())
```

Expected: rekord z `granted_by_id` ustawionym.

- [ ] **Step 6: Commit**

```bash
git add modules/admin/clients.py templates/admin/clients/detail.html static/css/components/modals.css
git commit -m "feat(admin/clients): grant/revoke special achievements from client profile"
```

---

### Task 12: Style `cosmic` rarity w galerii klienta

**Files:**
- Modify: `static/css/pages/client/achievements.css`
- Modify: JS renderer galerii (do zlokalizowania)

- [ ] **Step 1: Znajdź plik JS, który renderuje karty galerii**

```bash
grep -rln "rarity\|achievement-card" static/js/ | head -10
```

Zapisz nazwę głównego pliku (np. `static/js/pages/client/achievements.js` lub `achievements-renderer.js`).

- [ ] **Step 2: Dodaj label PL dla `cosmic` w renderze**

W tym pliku JS znajdź mapowanie `rarity` → label PL (np. `{ common: 'Pospolite', ... }`). Dodaj wpis:

```javascript
const RARITY_LABELS = {
    common: 'Pospolite',
    rare: 'Rzadkie',
    epic: 'Epickie',
    legendary: 'Legendarne',
    cosmic: 'Kosmiczne',  // NEW
};
```

> Jeśli mapowanie nie istnieje w JS (jest po stronie API), pomiń ten krok i upewnij się, że backend zwraca label.

- [ ] **Step 3: Dodaj style `cosmic` w `static/css/pages/client/achievements.css`**

Znajdź sekcję ze stylami `legendary` (~linia 36-37) i po niej dodaj:

```css
/* === COSMIC RARITY (admin-grantable, kategoria 'special') === */
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
    z-index: 1;
}

.achievement-card.unlocked[data-rarity="cosmic"] > * {
    position: relative;
    z-index: 2;
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

/* Special tag — zamiast statystyk dla category='special' */
.badge-special-tag {
    color: rgba(168, 85, 247, 0.9);
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 600;
}

/* Dark mode */
[data-theme="dark"] .achievement-card.unlocked[data-rarity="cosmic"] {
    box-shadow: 0 0 45px rgba(106, 13, 173, 0.85),
                0 0 80px rgba(30, 58, 138, 0.55);
}

[data-theme="dark"] .badge-special-tag {
    color: #c084fc;
    text-shadow: 0 0 8px rgba(168, 85, 247, 0.4);
}
```

- [ ] **Step 4: W rendererze karty — pokaż `badge-special-tag` zamiast statystyk dla `is_special`**

W pliku JS rendującym kartę galerii, znajdź miejsce gdzie wstrzykiwany jest tekst statystyk (np. „X% klientów ma"). Owiń warunkiem:

```javascript
// Pseudokod — dostosuj do faktycznej struktury renderera
const statBlock = ach.is_special
    ? `<div class="badge-special-tag">Wyróżnienie admina</div>`
    : `<div class="badge-stat">${ach.stat_percentage}% klientów ma</div>`;
```

Lub jeśli renderer jest w Jinja (`templates/achievements/gallery.html`):

```html
{% if a.is_special %}
    <div class="badge-special-tag">Wyróżnienie admina</div>
{% else %}
    <div class="badge-stat">{{ a.stat_percentage }}% klientów ma</div>
{% endif %}
```

- [ ] **Step 5: Smoke test w galerii**

Wejdź jako klient z odznaką „Beta Tester" na `/achievements`. Expected:
- Karta odznaki ma kosmiczne tło (galaxy gradient + migoczące gwiazdki)
- Label rzadkości „Kosmiczne"
- Zamiast „X% klientów ma" widać „Wyróżnienie admina"
- Działa w dark mode (przełącz `data-theme`)

- [ ] **Step 6: Commit**

```bash
git add static/css/pages/client/achievements.css static/js/pages/client/ templates/achievements/
git commit -m "feat(achievements): cosmic rarity styling + special-tag in gallery"
```

---

### Task 13: Animacja unlock — Supernova v2 spotlight

**Files:**
- Create: `static/js/components/cosmic-spotlight.js`
- Modify: `static/css/pages/client/achievements.css`
- Modify: główny JS spotlight'u (do zlokalizowania)

- [ ] **Step 1: Znajdź główny JS spotlight'u**

```bash
grep -rln "badge-spotlight\|spotlight" static/js/ | head -10
```

Zapisz nazwę pliku.

- [ ] **Step 2: Utwórz `static/js/components/cosmic-spotlight.js`**

```javascript
/**
 * Cosmic spotlight — wstrzykuje warstwy DOM (mgławice, gwiazdy, promienie supernovej)
 * dla badge-spotlight z data-rarity="cosmic". Wywoływane w momencie aktywacji spotlight'u.
 */
(function() {
    'use strict';

    function buildCosmicLayers() {
        const layers = document.createElement('div');
        layers.className = 'cosmic-layers';
        layers.innerHTML = `
            <div class="cosmic-backdrop"></div>
            <div class="nebula-cloud purple"></div>
            <div class="nebula-cloud blue"></div>
            <div class="nebula-cloud pink"></div>
            <div class="star-field"></div>
            <div class="stars-glow">
                <div class="glow-star" style="left: 12%; top: 18%; animation-delay: 0s;"></div>
                <div class="glow-star" style="left: 28%; top: 60%; animation-delay: 0.5s;"></div>
                <div class="glow-star" style="left: 75%; top: 22%; animation-delay: 1s;"></div>
                <div class="glow-star" style="left: 88%; top: 65%; animation-delay: 1.5s;"></div>
                <div class="glow-star" style="left: 15%; top: 82%; animation-delay: 2s;"></div>
                <div class="glow-star" style="left: 65%; top: 88%; animation-delay: 2.5s;"></div>
            </div>
            <div class="shooting-bg" style="top: 10%; animation-delay: 0s;"></div>
            <div class="shooting-bg" style="top: 55%; animation-delay: 1.3s;"></div>
            <div class="shooting-bg" style="top: 80%; animation-delay: 2.6s;"></div>
            <div class="supernova-core"></div>
            <div class="ray" style="--rot: 0deg; animation-delay: 0.2s;"></div>
            <div class="ray" style="--rot: 45deg; animation-delay: 0.25s;"></div>
            <div class="ray" style="--rot: 90deg; animation-delay: 0.3s;"></div>
            <div class="ray" style="--rot: 135deg; animation-delay: 0.35s;"></div>
            <div class="ray" style="--rot: 180deg; animation-delay: 0.4s;"></div>
            <div class="ray" style="--rot: 225deg; animation-delay: 0.45s;"></div>
            <div class="ray" style="--rot: 270deg; animation-delay: 0.5s;"></div>
            <div class="ray" style="--rot: 315deg; animation-delay: 0.55s;"></div>
        `;
        return layers;
    }

    function injectCosmicLayers(spotlight) {
        if (!spotlight) return;
        if (spotlight.dataset.cosmicInjected === '1') return;
        if (spotlight.dataset.rarity !== 'cosmic') return;

        const layers = buildCosmicLayers();
        spotlight.insertBefore(layers, spotlight.firstChild);
        spotlight.dataset.cosmicInjected = '1';
    }

    // API global do wywołania z kodu spotlight'u
    window.CosmicSpotlight = { inject: injectCosmicLayers };
})();
```

- [ ] **Step 3: Wstrzyknij wywołanie w main JS spotlight'u**

W zlokalizowanym pliku z Step 1, w funkcji aktywującej spotlight (np. tam gdzie jest `spotlight.classList.add('active')`), tuż przed dodaniem `.active`:

```javascript
if (window.CosmicSpotlight && spotlight.dataset.rarity === 'cosmic') {
    window.CosmicSpotlight.inject(spotlight);
}
```

- [ ] **Step 4: Załącz nowy JS w `templates/achievements/gallery.html`**

```html
<script src="{{ url_for('static', filename='js/components/cosmic-spotlight.js') }}"></script>
```

(Przed istniejącym JS galerii, ale po jQuery jeśli go używa.)

- [ ] **Step 5: Dodaj style Supernova v2 w `static/css/pages/client/achievements.css`**

Na końcu pliku, w sekcji stylów spotlight'u, dodaj:

```css
/* === Cosmic spotlight — Supernova v2 === */

.badge-spotlight[data-rarity="cosmic"] {
    background: #000005;
}

.cosmic-layers {
    position: absolute;
    inset: 0;
    overflow: hidden;
    pointer-events: none;
    z-index: 0;
}

.cosmic-backdrop {
    position: absolute;
    inset: 0;
    background:
        radial-gradient(ellipse at 15% 20%, rgba(106, 13, 173, 0.5) 0%, transparent 40%),
        radial-gradient(ellipse at 85% 80%, rgba(30, 58, 138, 0.5) 0%, transparent 40%),
        radial-gradient(ellipse at 50% 50%, rgba(168, 85, 247, 0.2) 0%, transparent 60%),
        radial-gradient(circle at 50% 50%, #0a0518 0%, #000005 100%);
    animation: cosmic-backdrop-drift 8s ease-in-out infinite alternate;
}

@keyframes cosmic-backdrop-drift {
    0% { transform: scale(1) rotate(0deg); filter: hue-rotate(0deg); }
    100% { transform: scale(1.1) rotate(2deg); filter: hue-rotate(20deg); }
}

.nebula-cloud {
    position: absolute;
    border-radius: 50%;
    filter: blur(40px);
}

.nebula-cloud.purple {
    width: 50%; height: 50%; left: 10%; top: 10%;
    background: radial-gradient(circle, rgba(168, 85, 247, 0.4), transparent 60%);
    animation: nebula-cloud-1 12s ease-in-out infinite alternate;
}

.nebula-cloud.blue {
    width: 45%; height: 45%; right: 5%; bottom: 5%;
    background: radial-gradient(circle, rgba(30, 58, 138, 0.5), transparent 60%);
    animation: nebula-cloud-2 14s ease-in-out infinite alternate;
}

.nebula-cloud.pink {
    width: 35%; height: 35%; right: 30%; top: 50%;
    background: radial-gradient(circle, rgba(255, 128, 255, 0.25), transparent 60%);
    animation: nebula-cloud-3 10s ease-in-out infinite alternate;
}

@keyframes nebula-cloud-1 { 0% { transform: translate(0,0) scale(1); } 100% { transform: translate(30px, 20px) scale(1.2); } }
@keyframes nebula-cloud-2 { 0% { transform: translate(0,0) scale(1); } 100% { transform: translate(-40px, -25px) scale(1.15); } }
@keyframes nebula-cloud-3 { 0% { transform: translate(0,0) scale(1); } 100% { transform: translate(20px, -30px) scale(1.3); } }

.star-field {
    position: absolute; inset: 0;
    background-image:
        radial-gradient(1px 1px at 5% 10%, white, transparent),
        radial-gradient(1px 1px at 15% 30%, white, transparent),
        radial-gradient(1px 1px at 25% 65%, #aae, transparent),
        radial-gradient(1px 1px at 35% 15%, white, transparent),
        radial-gradient(1.5px 1.5px at 45% 50%, #ffd, transparent),
        radial-gradient(1px 1px at 55% 85%, white, transparent),
        radial-gradient(1px 1px at 65% 25%, #ffd, transparent),
        radial-gradient(1px 1px at 75% 55%, white, transparent),
        radial-gradient(2px 2px at 85% 35%, white, transparent),
        radial-gradient(1px 1px at 95% 75%, #aae, transparent),
        radial-gradient(1px 1px at 8% 80%, white, transparent),
        radial-gradient(1.5px 1.5px at 38% 92%, #ffd, transparent),
        radial-gradient(1px 1px at 68% 95%, white, transparent),
        radial-gradient(1px 1px at 90% 12%, white, transparent);
    animation: cosmic-starfield-twinkle 4s ease-in-out infinite;
}

@keyframes cosmic-starfield-twinkle { 0%, 100% { opacity: 0.6; } 50% { opacity: 1; } }

.stars-glow { position: absolute; inset: 0; }

.stars-glow .glow-star {
    position: absolute;
    width: 3px; height: 3px;
    background: white;
    border-radius: 50%;
    box-shadow: 0 0 10px white, 0 0 20px rgba(168, 85, 247, 0.6);
    animation: cosmic-glow-pulse 3s ease-in-out infinite;
}

@keyframes cosmic-glow-pulse {
    0%, 100% { opacity: 0.5; transform: scale(1); }
    50% { opacity: 1; transform: scale(1.5); }
}

.shooting-bg {
    position: absolute;
    width: 100px; height: 1px;
    background: linear-gradient(90deg, transparent, white 60%, #c084fc);
    box-shadow: 0 0 8px rgba(255, 255, 255, 0.8);
    transform-origin: left center;
    animation: cosmic-shooting-bg 4s linear infinite;
    opacity: 0;
}

@keyframes cosmic-shooting-bg {
    0% { opacity: 0; transform: translateX(-150px) translateY(0) rotate(20deg); }
    10% { opacity: 1; }
    50% { opacity: 1; }
    100% { opacity: 0; transform: translateX(800px) translateY(280px) rotate(20deg); }
}

.supernova-core {
    position: absolute;
    left: 50%; top: 50%;
    width: 4px; height: 4px;
    border-radius: 50%;
    background: white;
    transform: translate(-50%, -50%);
}

.badge-spotlight.active[data-rarity="cosmic"] .supernova-core {
    animation: cosmic-supernova-burst 1.5s ease-out forwards;
}

@keyframes cosmic-supernova-burst {
    0% {
        box-shadow: 0 0 0 0 rgba(255,255,255,1), 0 0 0 0 rgba(168,85,247,0.9), 0 0 0 0 rgba(30,58,138,0.8);
        opacity: 1;
    }
    20% {
        box-shadow: 0 0 80px 40px rgba(255,255,255,0.7), 0 0 160px 80px rgba(168,85,247,0.5), 0 0 240px 120px rgba(30,58,138,0.4);
    }
    50% {
        box-shadow: 0 0 200px 150px rgba(255,255,255,0), 0 0 350px 250px rgba(168,85,247,0.1), 0 0 500px 350px rgba(30,58,138,0.05);
        opacity: 0.5;
    }
    100% { box-shadow: 0 0 0 0 transparent; opacity: 0; }
}

.ray {
    position: absolute;
    left: 50%; top: 50%;
    width: 2px; height: 0;
    background: linear-gradient(180deg, white, transparent);
    transform-origin: top center;
    transform: translate(-50%, 0) rotate(var(--rot));
    opacity: 0;
}

.badge-spotlight.active[data-rarity="cosmic"] .ray {
    animation: cosmic-ray-shoot 2s ease-out forwards;
}

@keyframes cosmic-ray-shoot {
    0% { height: 0; opacity: 0; }
    20% { height: 0; opacity: 0; }
    35% { height: 50vh; opacity: 1; }
    100% { height: 100vh; opacity: 0; }
}

/* Karta z aureolą */
.badge-spotlight[data-rarity="cosmic"] .badge-spotlight__card {
    background:
        radial-gradient(ellipse at 20% 30%, #6a0dad 0%, transparent 50%),
        radial-gradient(ellipse at 80% 70%, #1e3a8a 0%, transparent 50%),
        radial-gradient(circle at 50% 50%, #0f0f23 0%, #000000 100%);
    border: 2px solid rgba(168, 85, 247, 0.7);
    box-shadow:
        0 0 50px rgba(106, 13, 173, 0.9),
        0 0 100px rgba(30, 58, 138, 0.6),
        inset 0 0 20px rgba(168, 85, 247, 0.2);
    position: relative;
    z-index: 10;
}

.badge-spotlight[data-rarity="cosmic"] .badge-spotlight__card::before {
    content: '';
    position: absolute;
    inset: -8px;
    border-radius: 20px;
    border: 1px solid rgba(168, 85, 247, 0.4);
    box-shadow: 0 0 30px rgba(168, 85, 247, 0.5), inset 0 0 20px rgba(168, 85, 247, 0.1);
    animation: cosmic-card-halo 3s ease-in-out infinite alternate;
    pointer-events: none;
}

@keyframes cosmic-card-halo {
    0% { transform: scale(1); opacity: 0.6; }
    100% { transform: scale(1.04); opacity: 1; }
}

/* Animacja wejścia karty - supernova scale */
.badge-spotlight.active[data-rarity="cosmic"] .badge-spotlight__card {
    animation: cosmic-card-supernova 1.5s cubic-bezier(0.22, 1, 0.36, 1) both 0.4s;
}

@keyframes cosmic-card-supernova {
    0% { transform: scale(0); opacity: 0; }
    50% { transform: scale(1.18); opacity: 1; }
    100% { transform: scale(1); opacity: 1; }
}

/* Dark mode — bez zmian, animacja jest "z natury" ciemna */
```

- [ ] **Step 6: Smoke test animacji unlock**

Jako admin: odbierz odznakę „Beta Tester" od testowego klienta (jeśli ma) i przyznaj ponownie.

Jako klient: zaloguj się, idź na `/achievements`. Expected: spotlight z pełnym kosmicznym tłem, supernova flash, promienie strzelające z centrum, halo wokół karty.

> Jeśli nie ma testowego klienta — w `flask shell` zmień `seen=False` ręcznie:
> ```python
> from modules.achievements.models import UserAchievement
> ua = UserAchievement.query.filter_by(user_id=<id>).order_by(UserAchievement.id.desc()).first()
> ua.seen = False
> from extensions import db; db.session.commit()
> ```

- [ ] **Step 7: Commit**

```bash
git add static/js/components/cosmic-spotlight.js static/css/pages/client/achievements.css templates/achievements/gallery.html
git commit -m "feat(achievements): Supernova v2 unlock animation for cosmic rarity"
```

---

### Task 14: Share image — wsparcie `cosmic`

**Files:**
- Modify: `modules/achievements/share.py`

- [ ] **Step 1: Sprawdź jak są mapowane rarity w `share.py`**

```bash
grep -n "RARITY_\|rarity ==" modules/achievements/share.py | head -20
```

Zlokalizuj `RARITY_LABELS` i pewnie `RARITY_*` dict-y per rzadkość, oraz dispatcher.

- [ ] **Step 2: Dodaj `RARITY_COSMIC` po `RARITY_LEGENDARY`**

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
```

- [ ] **Step 3: Dodaj label w `RARITY_LABELS`**

```python
RARITY_LABELS = {
    'common': 'Pospolite',
    'rare': 'Rzadkie',
    'epic': 'Epickie',
    'legendary': 'Legendarne',
    'cosmic': 'Kosmiczne',  # NEW
}
```

- [ ] **Step 4: Dodaj `cosmic` do dispatcher'a koloru**

Znajdź miejsce gdzie `rarity` jest wybierany (zwykle `if/elif` lub dict lookup). Dodaj:

```python
# Pseudo - dostosuj do istniejącej struktury:
RARITY_PALETTES = {
    'common': RARITY_COMMON,
    'rare': RARITY_RARE,
    'epic': RARITY_EPIC,
    'legendary': RARITY_LEGENDARY,
    'cosmic': RARITY_COSMIC,  # NEW
}
palette = RARITY_PALETTES.get(achievement.rarity, RARITY_COMMON)
```

- [ ] **Step 5: Smoke test generowania obrazu**

Jako klient z odznaką cosmic, w galerii kliknij „Udostępnij" → pobierz PNG. Expected: obraz z fioletowo-granatowym gradientem (paleta cosmic). Sprawdź też różne formaty (1:1, 9:16, 3:4) jeśli są.

- [ ] **Step 6: Commit**

```bash
git add modules/achievements/share.py
git commit -m "feat(achievements): cosmic palette for share image"
```

---

### Task 15: Pełny smoke test E2E (manualny)

**Files:**
- Brak — testy ręczne

- [ ] **Step 1: Reset danych testowych w shell**

```bash
flask shell
```

```python
from modules.achievements.models import Achievement, UserAchievement
from extensions import db

# Usuń testową odznakę jeśli istnieje
Achievement.query.filter_by(slug='beta-tester').delete()
UserAchievement.query.filter(UserAchievement.granted_by_id.isnot(None)).delete()
db.session.commit()
```

- [ ] **Step 2: Test: tworzenie odznaki**

W przeglądarce:
1. `/admin/achievements/new`
2. Nazwa: `Test Cosmic`, opis: `Testowa odznaka cosmic`, kategoria: `special`, rzadkość: `cosmic`, ukryta: NIE
3. Upload PNG/JPG (dowolny, min 64×64)
4. Submit → flash success
5. Plik istnieje: `ls static/uploads/achievements/test-cosmic@256.png`
6. Wymiary: `file static/uploads/achievements/test-cosmic@256.png` → 256×256

- [ ] **Step 3: Test: ukryta odznaka**

1. Utwórz drugą: `Test Hidden`, ukryta: TAK
2. Zaloguj się jako klient X, otwórz `/achievements` → klient X NIE widzi „Test Hidden"

- [ ] **Step 4: Test: przyznanie + animacja + email**

1. Jako admin, profil klienta X (`/admin/clients/<id>`) → „+ Przyznaj odznakę" → wybierz „Test Cosmic"
2. Flash: „Przyznano odznakę „Test Cosmic"
3. Sprawdź log Flask: `tail -50 instance/log/app.log` (lub gdzie loguje) — brak ERROR, jest INFO o granted
4. Zaloguj się jako klient X → `/achievements` → animacja Supernova v2 odpala się, karta cosmic widoczna

- [ ] **Step 5: Test: ukryte statystyki**

1. Klient X w galerii: pod kartą „Test Cosmic" widać „Wyróżnienie admina"
2. Pod kartą zwykłą (np. „Pierwsze kroki") widać „X% klientów ma"

- [ ] **Step 6: Test: odbieranie**

1. Jako admin, profil klienta X → „Odbierz" przy „Test Cosmic" → confirm → flash success
2. W bazie: `flask shell` → `UserAchievement.query.filter_by(user_id=X_ID, achievement_id=Y_ID).first()` → None

- [ ] **Step 7: Test: idempotency**

1. Przyznaj „Test Cosmic" klientowi X
2. Spróbuj jeszcze raz → flash „Klient już posiada tę odznakę"

- [ ] **Step 8: Test: 403 dla mod**

1. Zaloguj się jako mod
2. Próba `/admin/achievements` → 403 lub 404 (zależnie od decoratora)

- [ ] **Step 9: Test: edycja odznaki z posiadaczami**

1. Jako admin, edytuj „Test Cosmic" (ma posiadacza X)
2. Pola `slug` i `kategoria` powinny być `readonly`/`disabled`
3. Zmień nazwę na „Test Cosmic v2" + zapisz → success
4. Klient X w galerii widzi nową nazwę

- [ ] **Step 10: Test: dezaktywacja**

1. W liście odznak admin „Dezaktywuj" → confirm → flash success, kolumna „Aktywna: Nie"
2. Klient X w galerii już nie widzi „Test Cosmic v2"
3. Reaktywacja w `flask shell`:
```python
from modules.achievements.models import Achievement
from extensions import db
ach = Achievement.query.filter_by(slug='test-cosmic').first()
ach.is_active = True
db.session.commit()
```
4. Klient X znów widzi w galerii

- [ ] **Step 11: Test: dark mode**

W panelu klienta przełącz `data-theme="dark"`. Wszystkie nowe elementy:
- Modal „Przyznaj" (admin) — sprawdź dark mode w modals.css
- Karta cosmic w galerii — gradienty, tekst czytelny
- Spotlight Supernova v2 — animacja działa identycznie

- [ ] **Step 12: Cleanup commit (jeśli były poprawki)**

```bash
# Jeśli w trakcie testów coś poprawiałeś:
git add -A
git commit -m "fix(achievements): post-smoke-test polish"
```

---

## Done Definition

Implementacja jest kompletna gdy:

1. ✅ Migracja DB zaaplikowana lokalnie, ENUMy rozszerzone
2. ✅ Admin może utworzyć odznakę z uploadem ikony
3. ✅ Admin może przyznać/odebrać odznakę z profilu klienta
4. ✅ Klient widzi animację Supernova v2 i otrzymuje email
5. ✅ Statystyki ukryte dla `category='special'` (etykieta „Wyróżnienie admina")
6. ✅ Flaga `is_hidden_until_unlocked` działa poprawnie
7. ✅ Style działają w light + dark mode
8. ✅ Mod nie ma dostępu do `/admin/achievements`
9. ✅ Audit: `granted_by_id` zapisuje się przy przyznaniu, `ON DELETE SET NULL` przy usunięciu admina
10. ✅ Smoke checklist (Task 15) przeszedł bez błędów

## Deployment

Po wszystkich commitach na `main`:

```bash
git push origin main
```

Webhook deployu (zob. memory `reference_deploy_webhook`) automatycznie:
1. `git pull` na serwerze
2. `flask db upgrade`
3. Restart `thunderorders.service`

Sprawdź na produkcji: `https://thunderorders.cloud/admin/achievements` (jako admin).
