# Pupile: bieg towarzysza i żarty (v3.2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Towarzysz biega na 4 łapach jako zwykły ruch, a dwa „żarty" (kradzież kursora, wychylenie z obrazkiem zarządzanym w adminie) działają za jednym przełącznikiem użytkownika w warsztacie i jednym wyłącznikiem admina.

**Architecture:** Bieg to nowa poza `run` w `PetRig` i rozszerzenie `walkStep` w `pet-companion.js`. Towarzysz wystawia małe API (`window.PetCompanionApi`: `ready`, `rect`, `claim`, `runTo`, `face`), a osobny moduł `pet-jokes.js` (harmonogram + dwa żarty) zajmuje go przez `claim`. Dane: tabela `pet_peek_images`, kolumna `pet_profiles.jokes_enabled`, ustawienie admina `pets_jokes_enabled`; klient dostaje jedną liczbę `state.companion.jokes`.

**Tech Stack:** Flask 3, SQLAlchemy/Flask-Migrate (MariaDB prod, SQLite w testach), Pillow (WebP), Jinja2, vanilla JS w IIFE (styl ES5 jak w `pet-companion.js`), pytest, Playwright (node, z cache npx) do weryfikacji przeglądarkowej.

**Spec:** `docs/superpowers/specs/2026-10-12-pupile-zarty-design.md`

## Global Constraints

- Bieg: `RUN_SPEED = 170` px/s (spacer `WALK_SPEED = 40`), `RUN_CHANCE = 0.2`, `RUN_MIN_DIST = 200` px; chory i krytyczny (`pet.mood`) nie biegają; bieg nie zależy od żadnego wyłącznika.
- Harmonogram żartów: pierwszy najwcześniej 90 s po wejściu, kolejne co 120–300 s; czas „następnego" w `sessionStorage['pets_jokes_next_<uid>']`.
- Kursor: tylko `(hover: hover) and (pointer: fine)`, ostatni `mousemove` ≤ 3 s, najwyżej 2 razy na sesję karty i nie częściej niż co 10 min (`sessionStorage['pets_jokes_cursor_<uid>']`), twardy timer 3 s w `try/finally`, Esc/klawisz/klik/dotyk/blur/`visibilitychange`/`pagehide`/wyłączenie żartów kończą natychmiast.
- Wychylenie: ekspozycja ~6 s (wstrzymana przy fokusie/hoverze), obrazek `<img alt="">` ~72 px, „x" z celem ≥ 44 px i `aria-label="Zamknij obrazek"`, zamknięcie na 7 dni w `localStorage['pets_peek_closed_<id>']` (w `try/catch`), waga wychylenia 0,7, kursora 0,3.
- Upload: PNG/JPG/WebP/GIF, źródło ≤ 2 MB, ≤ 4 000 000 px, zapis WebP z przezroczystością, dłuższy bok ≤ 240 px, limit 30 obrazków, katalog `static/uploads/pet_peeks/`.
- Z-index: warstwa blokująca kursor 1190 (nad sidebarem 1000 i koszykiem 1090–1100, pod nakładkami 1200), narysowany kursor 1191; towarzysz w trybie `walk` ma 890 (pod sidebarem 1000, stąd wychylenie „zza sidebara").
- Żadnego ekranu użytkownika nie wolno uzupełniać o listę rodzajów żartów (element zaskoczenia); opis przełącznika: „Pupil czasem lubi coś wywinąć. Wyłącz, jeśli wolisz spokój."
- CSS: każdy nowy styl ma wariant `[data-theme="dark"]`; cele dotyku ≥ 44 px; brak inline CSS/JS; style modali tylko w `modals.css` (tu modali nie ma).
- Migracja tylko przez plik Flask-Migrate; `CACHE_VERSION` w `static/sw.js` → `thunderorders-v39`; **bez pusha** (push = auto-deploy); repo jest publiczne (żadnych danych infrastruktury).
- Testy: `venv/bin/python -m pytest` (gołe `pytest` nie działa). Pełna suita: `venv/bin/python -m pytest -q --deselect tests/test_mobile_api_auth.py::test_logout_stores_expiry_in_local_time_and_purges_expired` (baza przed zmianami: 2117 passed).
- Commit: styl `feat(pupile): ...` bez polskich znaków w temacie, stopka `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`; `docs/` jest w `.gitignore`, więc pliki dokumentacji dodawaj `git add -f`.
- W testach wszystkie żądania dzielą `g` (fixture `app` trzyma jeden kontekst): po zmianie `Settings` wołaj `PetConfig.load(force=True)`, bo konfiguracja bywa zbuforowana w `g._pet_config`.

## Review Focus

Rzeczy, które spec implikuje, a zwykłe testy ich nie pokrywają; każda ma test w zadaniu-właścicielu:

1. **Kursor zostaje ukryty** po przerwaniu żartu (Esc, klik, blur, ukrycie karty, wyłączenie żartów, zawieszony ruch → twardy timer). Zadanie 8, skrypt `cursor_check.js`.
2. **Zapis ustawień niechcący zeruje żarty:** formularz „Liczby gry" nie może wyzerować wyłącznika admina; stary front bez pola `jokes` nie może włączyć wyłączonych żartów. Zadania 1 i 2 (`test_zapis_liczb_gry_nie_rusza_wylacznika_zartow`, `test_towarzysz_bez_pola_jokes_nie_zmienia_ustawienia`).
3. **Wgrany obrazek:** przezroczystość zachowana, plik uszkodzony / za duży / zły typ / „bomba pikseli" / animowany GIF nie psują panelu ani nie zostawiają plików. Zadanie 3.
4. **Pupil zostaje poza ekranem lub jest „wciągany" w trakcie żartu:** `resize`/`scroll` podczas `claim` nie mogą go teleportować, a przerwanie nie może zostawić `claim`. Zadanie 6 (`api_check.js`).
5. **Żart startuje tam, gdzie nie powinien:** `jokes=false`, `prefers-reduced-motion`, otwarty modal, fokus w polu, pasek zakupowy, tryb `sit`, brak aktywnych lub wszystkie zamknięte obrazki. Zadanie 7 (`peek_check.js`) i test szablonu.

---

## Przygotowanie środowiska weryfikacji przeglądarkowej (przed Zadaniem 1)

Skrypty przeglądarkowe leżą w scratchpadzie sesji (NIE są commitowane); używają Playwrighta z cache npx. Zmienna robocza:

```bash
export JOKES=/private/tmp/claude-501/-Users-konradkmiecik-Documents-GitHub-ThunderOrders/17a3b1ac-474c-4884-92c1-dbc7ff650b20/scratchpad/jokes
```

Stan powłoki nie przechodzi między wywołaniami Bash, więc każde polecenie z `$JOKES` zaczynaj od tego `export` (skrypty node biorą katalog z `lib.js`: `L.DIR`, nie ze zmiennej).

- [ ] **Krok S1: Utwórz katalog i wspólną bibliotekę**

```bash
mkdir -p $JOKES/shots
```

Zapisz `$JOKES/lib.js`:

```js
// Wspólne klocki skryptów przeglądarkowych żartów (Playwright z cache npx).
const { chromium } = require('/Users/konradkmiecik/.npm/_npx/e41f203b7505f1fb/node_modules/playwright');

const PORT = process.env.PORT || '5031';
const BASE = `http://localhost:${PORT}`;

// Deterministyczny Math.random (mulberry32) wstrzykiwany do strony przed jej skryptami.
function mulberry(seed) {
  return `(() => { let a = ${seed | 0}; Math.random = function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; })();`;
}

const results = { pass: 0, fail: 0 };
function check(name, cond, extra) {
  if (cond) { results.pass++; console.log('  ok   ' + name); }
  else { results.fail++; console.log('  FAIL ' + name + (extra !== undefined ? '  -> ' + JSON.stringify(extra) : '')); }
}
function finish(errors) {
  if (errors && errors.length) { results.fail++; console.log('  FAIL błędy strony:', errors.slice(0, 5)); }
  console.log(`\n${results.pass} ok, ${results.fail} fail`);
  process.exit(results.fail ? 1 : 0);
}

// opts: w, h, seed, clock, reducedMotion, touch, mobile, dark, login, path, init, patchState
async function open(opts = {}) {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: opts.w || 1313, height: opts.h || 900 },
    serviceWorkers: 'block',
    reducedMotion: opts.reducedMotion || 'no-preference',
    hasTouch: !!opts.touch, isMobile: !!opts.mobile,
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  if (opts.seed != null) await page.addInitScript(mulberry(opts.seed));
  if (opts.init) await page.addInitScript(opts.init);
  if (opts.patchState) {
    await page.route(/\/client\/pupile\/api\/stan\?lite=1/, async (route) => {
      const resp = await route.fetch();
      const json = await resp.json();
      opts.patchState(json);
      await route.fulfill({ response: resp, json });
    });
  }
  if (opts.clock) await page.clock.install();
  await page.goto(BASE + (opts.login || '/dev-login'));
  await page.goto(BASE + (opts.path || '/client/dashboard'), { waitUntil: 'networkidle' });
  if (opts.dark) await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  return { browser, ctx, page, errors };
}

// Czeka (czas rzeczywisty), aż towarzysz będzie widoczny z rigiem.
async function waitCompanion(page, ms = 10000) {
  await page.waitForFunction(() => { const c = document.getElementById('petCompanion'); return c && !c.hidden && c.querySelector('.pet-rig'); }, null, { timeout: ms });
}

// Zatrzymuje wirtualny zegar; dalej czas płynie tylko przez run()/until().
async function pause(page) {
  const t = await page.evaluate(() => Date.now());
  await page.clock.pauseAt(t + 50);
}
async function run(page, ms, step = 1000) {
  for (let done = 0; done < ms; done += step) {
    await page.clock.runFor(Math.min(step, ms - done));
    await page.waitForTimeout(15);   // czas rzeczywisty: pozwala dokończyć fetch-e
  }
}
async function until(page, fn, maxMs = 15000, step = 500, arg) {
  for (let t = 0; t <= maxMs; t += step) {
    if (await page.evaluate(fn, arg)) return true;
    await page.clock.runFor(step);
    await page.waitForTimeout(15);
  }
  return false;
}

module.exports = { chromium, BASE, DIR: __dirname, open, waitCompanion, pause, run, until, check, finish };
```

- [ ] **Krok S2: Wpis podglądu w `.claude/launch.json` (lokalny plik, nie commitujemy)**

Dopisz do `configurations`:

```json
    {
      "name": "pets-jokes",
      "runtimeExecutable": "venv/bin/python",
      "runtimeArgs": ["docs/dev/dev_pets_preview.py", "--port", "5031", "--scenario", "wszystko", "--no-night"],
      "port": 5031
    }
```

Serwer uruchamiasz `preview_start` (`name: "pets-jokes"`), a po KAŻDEJ zmianie Pythona restartujesz (`preview_stop`, `preview_start`). Skrypt podglądu przy starcie kasuje i odtwarza bazę SQLite ze schematu modeli. Sprawdzenie gotowości: `curl -s -o /dev/null -w '%{http_code}\n' http://localhost:5031/dev-login` → `302`.

---

### Task 1: Dane: model obrazków, kolumna `jokes_enabled`, migracja, wyłącznik admina

**Files:**
- Modify: `modules/pets/models.py` (kolumna w `PetProfile`, nowy model `PetPeekImage`)
- Create: `migrations/versions/c7a4d1e9f2b6_pupile_zarty.py`
- Modify: `modules/pets/config.py` (`PetConfig.jokes_enabled`, `ADMIN_FIELDS`, `SWITCH_KEYS`)
- Modify: `templates/admin/pets/index.html` (checkbox w karcie „Włącznik i rollout")
- Modify: `docs/superpowers/specs/2026-10-12-pupile-zarty-design.md` (§6.6, rozstrzygnięcie formularza)
- Create: `tests/test_pets_zarty_dane.py`
- Modify: `tests/test_pets_migration.py`, `tests/test_pets_admin.py`

**Interfaces:**
- Produces: `PetPeekImage(id, filename, label, is_active, created_at, created_by)`; `PetProfile.jokes_enabled: bool`; `PetConfig.jokes_enabled: bool = True`; klucz `Settings` `pets_jokes_enabled`; `SWITCH_KEYS` zawiera `'pets_jokes_enabled'`; rewizja migracji `c7a4d1e9f2b6` (down: `b5d8e2f4a917`).

**Rozstrzygnięcie (Ruling R1):** spec §6.6 mówił „checkbox poza Włącznikiem". Formularz „Liczby gry" nie zawiera boolean-ów, a `validate_settings` zapisuje `false` dla każdego boolean-a bez pola w formularzu, więc checkbox w „Liczbach gry" kasowałby się przy każdym zapisie liczb. Dlatego checkbox leży w tej samej karcie i formularzu co „Funkcja włączona" (`scope=switch`), a `pets_jokes_enabled` trafia do `SWITCH_KEYS`. To nadal osobny, krótki formularz (3 pola), więc awaryjne wyłączenie nie zależy od 28 liczb. Koszt pomyłki: zero (zmiana miejsca checkboxa).

- [ ] **Step 1: Napisz testy, które muszą na początku paść**

Nowy plik `tests/test_pets_zarty_dane.py`:

```python
"""Żarty towarzysza (spec v3.2 §6.1, 6.2, 6.6): model obrazków, kolumna profilu, wyłącznik admina w PetConfig."""
import pytest
from sqlalchemy.exc import IntegrityError


def test_profil_ma_zarty_domyslnie_wlaczone(db, make_user):
    from modules.pets.models import PetProfile
    user = make_user()
    profil = PetProfile(user_id=user.id)
    db.session.add(profil)
    db.session.commit()
    assert profil.jokes_enabled is True


def test_obrazek_wychylania_domyslnie_aktywny(db):
    from modules.pets.models import PetPeekImage
    obrazek = PetPeekImage(filename='a' * 32 + '.webp', label='Gwiazdka')
    db.session.add(obrazek)
    db.session.commit()
    assert obrazek.is_active is True
    assert obrazek.created_at is not None and obrazek.created_by is None


def test_nazwa_pliku_obrazka_jest_unikalna(db):
    from modules.pets.models import PetPeekImage
    db.session.add(PetPeekImage(filename='dup.webp'))
    db.session.commit()
    db.session.add(PetPeekImage(filename='dup.webp'))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_wylacznik_admina_domyslnie_wlaczony():
    from modules.pets.config import PetConfig
    assert PetConfig().jokes_enabled is True


def test_wylacznik_admina_z_settings(db):
    from modules.auth.models import Settings
    from modules.pets.config import PetConfig
    Settings.set_value('pets_jokes_enabled', 'false', type='boolean')
    db.session.commit()
    assert PetConfig.load(force=True).jokes_enabled is False


def test_wylacznik_jest_w_formularzu_wlacznika():
    from modules.pets.config import SWITCH_KEYS, admin_form_fields
    assert 'pets_jokes_enabled' in SWITCH_KEYS
    assert 'pets_jokes_enabled' in admin_form_fields()
```

W `tests/test_pets_migration.py`:

1. Pod `PLIK_SZPITAL = ...` dodaj:

```python
REWIZJA_ZARTY = 'c7a4d1e9f2b6'
PLIK_ZARTY = pathlib.Path('migrations/versions') / f'{REWIZJA_ZARTY}_pupile_zarty.py'
```

2. W `test_migracja_jest_jedyna_glowa` zastąp asercje:

```python
    assert sd.get_heads() == [REWIZJA_ZARTY]
    assert sd.get_revision(REWIZJA_ZARTY).down_revision == REWIZJA_SZPITAL
    assert sd.get_revision(REWIZJA_SZPITAL).down_revision == REWIZJA
    assert sd.get_revision(REWIZJA).down_revision == 'dde1a45a7d87'
```

3. W `test_upgrade_tworzy_tabele_zgodne_z_modelami`: import zmień na `from modules.pets.models import Pet, PetProfile, PetEvent, PetPeekImage`; po `_zaladuj(PLIK_SZPITAL, 'migracja_szpital').upgrade()` dodaj `_zaladuj(PLIK_ZARTY, 'migracja_zarty').upgrade()`; asercję tabel zmień na `assert {'pets', 'pet_profiles', 'pet_events', 'pet_peek_images'} <= tabele`; pętlę na `for model in (Pet, PetProfile, PetEvent, PetPeekImage):`.

4. Na końcu pliku dodaj:

```python
def test_zarty_upgrade_i_downgrade(silnik):
    with silnik.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            _zaladuj_migracje().upgrade()
            _zaladuj(PLIK_SZPITAL, 'migracja_szpital').upgrade()
            zarty = _zaladuj(PLIK_ZARTY, 'migracja_zarty')
            zarty.upgrade()
            insp = sa.inspect(conn)
            assert 'pet_peek_images' in insp.get_table_names()
            assert 'jokes_enabled' in _kolumny(insp, 'pet_profiles')
            zarty.downgrade()
        insp = sa.inspect(conn)
        assert 'pet_peek_images' not in insp.get_table_names()
        assert 'jokes_enabled' not in _kolumny(insp, 'pet_profiles')
```

W `tests/test_pets_admin.py`: do `PELNY_FORMULARZ` dodaj klucz `'pets_jokes_enabled': 'on',` (po `pets_rollout_pct`), a na końcu pliku:

```python
def test_wylacznik_zartow_zapisuje_sie_z_formularza_wlacznika(client, login, make_user, db):
    from modules.pets.config import PetConfig
    _admin(make_user, login)
    dane = {'scope': 'switch', 'pets_enabled': 'on', 'pets_rollout_pct': '25'}   # bez pets_jokes_enabled = odznaczony
    assert client.post('/admin/pupile/ustawienia', data=dane).status_code == 302
    assert PetConfig.load(force=True).jokes_enabled is False
    dane['pets_jokes_enabled'] = 'on'
    assert client.post('/admin/pupile/ustawienia', data=dane).status_code == 302
    assert PetConfig.load(force=True).jokes_enabled is True


def test_zapis_liczb_gry_nie_rusza_wylacznika_zartow(client, login, make_user, db):
    """Review Focus 2: formularz „Liczby gry” nie zawiera checkboxa żartów — nie może go wyzerować."""
    from modules.auth.models import Settings
    from modules.pets.config import PetConfig
    _admin(make_user, login)
    Settings.set_value('pets_jokes_enabled', 'true', type='boolean')
    db.session.commit()
    liczby = {k: v for k, v in PELNY_FORMULARZ.items()
              if k not in ('pets_enabled', 'pets_rollout_pct', 'pets_jokes_enabled')}
    assert client.post('/admin/pupile/ustawienia', data=liczby).status_code == 302
    assert PetConfig.load(force=True).jokes_enabled is True
```

- [ ] **Step 2: Uruchom testy i potwierdź, że padają**

Run: `venv/bin/python -m pytest tests/test_pets_zarty_dane.py tests/test_pets_migration.py tests/test_pets_admin.py -q`
Expected: FAIL (m.in. `ImportError: cannot import name 'PetPeekImage'`, `FileNotFoundError` dla `c7a4d1e9f2b6_pupile_zarty.py`, `AttributeError ... jokes_enabled`).

- [ ] **Step 3: Implementacja**

`modules/pets/models.py`: w `PetProfile` po `companion_enabled` dodaj:

```python
    # Żarty towarzysza (spec v3.2 §6.2): jeden przełącznik użytkownika w warsztacie
    jokes_enabled = db.Column(db.Boolean, nullable=False, default=True, server_default=db.text('1'))
```

Na końcu pliku dodaj model:

```python
class PetPeekImage(db.Model):
    """Ozdobny obrazek, który towarzysz wychyla zza krawędzi ekranu (spec v3.2 §6.1). Zarządza admin."""
    __tablename__ = 'pet_peek_images'

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(80), nullable=False, unique=True)   # <uuid>.webp w static/uploads/pet_peeks/
    label = db.Column(db.String(60), nullable=True)                     # nazwa dla admina
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.text('1'))
    created_at = db.Column(db.DateTime, nullable=False, default=get_local_now)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    def __repr__(self):
        return f'<PetPeekImage {self.id} {self.filename} active={self.is_active}>'
```

Nowy plik `migrations/versions/c7a4d1e9f2b6_pupile_zarty.py`:

```python
"""Pupile: żarty towarzysza: obrazki wychylania i przełącznik w profilu (spec v3.2 §6)

Revision ID: c7a4d1e9f2b6
Revises: b5d8e2f4a917
"""
from alembic import op
import sqlalchemy as sa

revision = 'c7a4d1e9f2b6'
down_revision = 'b5d8e2f4a917'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pet_peek_images',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=80), nullable=False),
        sa.Column('label', sa.String(length=60), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('filename'),
    )
    with op.batch_alter_table('pet_profiles') as batch:
        batch.add_column(sa.Column('jokes_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')))


def downgrade():
    with op.batch_alter_table('pet_profiles') as batch:
        batch.drop_column('jokes_enabled')
    op.drop_table('pet_peek_images')
```

`modules/pets/config.py`:
- w `PetConfig` po `hospital: dict = _slownik('hospital')` dodaj `jokes_enabled: bool = True`;
- w `ADMIN_FIELDS` po wierszu `pets_rollout_pct` dodaj `('pets_jokes_enabled', 'boolean', None, 'Żarty pupili włączone'),`;
- `SWITCH_KEYS = frozenset({'pets_enabled', 'pets_rollout_pct', 'pets_jokes_enabled'})   # osobny formularz „Włącznik i rollout”`.

`templates/admin/pets/index.html`: pod `{% set enabled_on = ... %}` dodaj `{% set jokes_on = form.get('pets_jokes_enabled') in ('on', 'true', '1') %}`. W `.pa-switch-row`, po `</label>` toggle „Funkcja włączona" a przed `<div class="pa-field ...rollout">`, wstaw:

```jinja
                <label class="pa-toggle">
                    <input type="checkbox" name="pets_jokes_enabled" id="petsJokesEnabled" {% if jokes_on %}checked{% endif %}>
                    <span class="pa-toggle__slider"></span>
                    <span class="pa-toggle__text">Żarty pupili włączone</span>
                </label>
```

W specu (`docs/superpowers/specs/2026-10-12-pupile-zarty-design.md`) §6.6 zdanie „Checkbox w głównym formularzu ustawień (nie w „Włączniku i rollout", bo ten jest awaryjnym wyłączeniem całej funkcji)." zastąp: „Checkbox leży w karcie „Włącznik i rollout" (ten sam krótki formularz `scope=switch`), bo formularz „Liczby gry" nie zawiera boolean-ów, a walidator zapisuje `false` dla każdego boolean-a bez pola."

- [ ] **Step 4: Uruchom testy i potwierdź, że przechodzą**

Run: `venv/bin/python -m pytest tests/test_pets_zarty_dane.py tests/test_pets_migration.py tests/test_pets_admin.py tests/test_pets_config.py -q`
Expected: PASS (wszystkie).

- [ ] **Step 5: Commit**

```bash
git add modules/pets/models.py modules/pets/config.py migrations/versions/c7a4d1e9f2b6_pupile_zarty.py templates/admin/pets/index.html tests/test_pets_zarty_dane.py tests/test_pets_migration.py tests/test_pets_admin.py
git add -f docs/superpowers/specs/2026-10-12-pupile-zarty-design.md
git commit -m "feat(pupile): zarty - model obrazkow, kolumna jokes_enabled, migracja, wylacznik admina

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Stan i API: `companion.jokes`, zapis przełącznika, lista obrazków

**Files:**
- Modify: `modules/pets/state.py` (pole `jokes` w `companion`)
- Modify: `modules/pets/actions.py` (`set_companion(..., jokes=None)`)
- Modify: `modules/pets/routes.py` (`api_companion` + `GET /api/wychylenia`)
- Modify: `tests/test_pets_state.py`, `tests/test_pets_routes.py`
- Create: `tests/test_pets_zarty_api.py`

**Interfaces:**
- Consumes: `PetProfile.jokes_enabled`, `PetConfig.jokes_enabled`, `PetPeekImage` (Zadanie 1).
- Produces: `state['companion'] = {'enabled', 'pet_id', 'auto', 'jokes'}`; `set_companion(user, pet_id=None, enabled=True, jokes=None)` (`None` = bez zmiany); `POST /client/pupile/api/towarzysz` przyjmuje opcjonalne `jokes` (bool); `GET /client/pupile/api/wychylenia` → `{"ok": true, "images": [{"id": int, "url": "/static/uploads/pet_peeks/<f>.webp"}]}`; endpoint Flaska `pets.api_peek_images`.

- [ ] **Step 1: Napisz testy, które muszą na początku paść**

W `tests/test_pets_state.py` do czterech asercji `s['companion'] == {...}` (linie ~23, 47, 83, 96) dopisz klucz `'jokes': True` (np. `{'enabled': True, 'pet_id': None, 'auto': True, 'jokes': True}`). W `tests/test_pets_routes.py` (linia ~208) to samo: `{'enabled': False, 'pet_id': zywy.id, 'auto': False, 'jokes': True}`.

Nowy plik `tests/test_pets_zarty_api.py`:

```python
"""Żarty towarzysza: stan (profil ∧ wyłącznik admina), zapis przełącznika, lista obrazków (spec v3.2 §6.7–6.8)."""
import json

import pytest

from tests.pets_helpers import zaloz_profil, zaloz_pupila


def _wlacz(db):
    from modules.auth.models import Settings
    from modules.pets.config import reset_feature_cache
    Settings.set_value('pets_enabled', 'true', type='boolean')
    Settings.set_value('pets_rollout_pct', 100, type='integer')
    Settings.set_value('pets_night', json.dumps({'start': 0, 'end': 0}), type='json')
    db.session.commit()
    reset_feature_cache()


@pytest.fixture
def gracz(db, make_user, login):
    user = make_user()
    login(user)
    _wlacz(db)
    return user


def _jokes(user):
    from modules.pets.config import PetConfig
    from modules.pets.service import state_for_user
    return state_for_user(user, lite=True, cfg=PetConfig.load(force=True))['companion']['jokes']


def test_stan_bez_profilu_zarty_wlaczone(db, make_user):
    assert _jokes(make_user()) is True


def test_stan_zarty_wylaczone_w_profilu(db, make_user):
    user = make_user()
    zaloz_profil(user).jokes_enabled = False
    db.session.commit()
    assert _jokes(user) is False


def test_stan_zarty_wylaczone_przez_admina(db, make_user):
    from modules.auth.models import Settings
    user = make_user()
    zaloz_profil(user)
    Settings.set_value('pets_jokes_enabled', 'false', type='boolean')
    db.session.commit()
    assert _jokes(user) is False


def test_set_companion_zarty(db, make_user):
    from modules.pets.actions import set_companion
    user = make_user()
    profil = zaloz_profil(user)
    set_companion(user, jokes=False)
    assert profil.jokes_enabled is False and profil.companion_enabled is True
    set_companion(user, enabled=False)          # jokes=None = bez zmiany
    assert profil.jokes_enabled is False and profil.companion_enabled is False
    set_companion(user, jokes=True)
    assert profil.jokes_enabled is True


def test_towarzysz_zapisuje_zarty(client, gracz, db):
    from modules.pets.models import PetProfile
    zaloz_profil(gracz)
    zywy = zaloz_pupila(gracz)
    r = client.post('/client/pupile/api/towarzysz', json={'pet_id': zywy.id, 'enabled': True, 'jokes': False})
    assert r.status_code == 200 and r.get_json()['state']['companion']['jokes'] is False
    assert PetProfile.query.filter_by(user_id=gracz.id).one().jokes_enabled is False
    r = client.post('/client/pupile/api/towarzysz', json={'pet_id': zywy.id, 'enabled': True, 'jokes': True})
    assert r.get_json()['state']['companion']['jokes'] is True


def test_towarzysz_bez_pola_jokes_nie_zmienia_ustawienia(client, gracz, db):
    """Review Focus 2: starszy front (bez `jokes`) nie może po cichu włączyć wyłączonych żartów."""
    from modules.pets.models import PetProfile
    profil = zaloz_profil(gracz)
    profil.jokes_enabled = False
    db.session.commit()
    zywy = zaloz_pupila(gracz)
    r = client.post('/client/pupile/api/towarzysz', json={'pet_id': zywy.id, 'enabled': True})
    assert r.status_code == 200
    assert PetProfile.query.filter_by(user_id=gracz.id).one().jokes_enabled is False


@pytest.mark.parametrize('zle', ['false', 0, 1, 'tak'])
def test_towarzysz_jokes_nie_bool_400(client, gracz, db, zle):
    zaloz_profil(gracz)
    zywy = zaloz_pupila(gracz)
    r = client.post('/client/pupile/api/towarzysz', json={'pet_id': zywy.id, 'enabled': True, 'jokes': zle})
    assert r.status_code == 400 and r.get_json()['error'] == 'bad_request'


def test_wychylenia_tylko_aktywne_posortowane(client, gracz, db):
    from modules.pets.models import PetPeekImage
    db.session.add_all([PetPeekImage(filename='b.webp', is_active=True),
                        PetPeekImage(filename='x.webp', is_active=False),
                        PetPeekImage(filename='a.webp', is_active=True)])
    db.session.commit()
    r = client.get('/client/pupile/api/wychylenia')
    assert r.status_code == 200
    dane = r.get_json()
    assert dane['ok'] is True
    assert [o['url'] for o in dane['images']] == ['/static/uploads/pet_peeks/b.webp', '/static/uploads/pet_peeks/a.webp']
    assert all(isinstance(o['id'], int) for o in dane['images'])
    assert 'private' in r.headers['Cache-Control'] and 'max-age=300' in r.headers['Cache-Control']


def test_wychylenia_pusta_lista(client, gracz, db):
    assert client.get('/client/pupile/api/wychylenia').get_json() == {'ok': True, 'images': []}


def test_wychylenia_bramka_funkcji_404(client, login, make_user):
    login(make_user())
    r = client.get('/client/pupile/api/wychylenia')
    assert r.status_code == 404 and r.get_json()['error'] == 'not_found'


def test_wychylenia_wymagaja_logowania(client, db):
    assert client.get('/client/pupile/api/wychylenia').status_code == 302
```

- [ ] **Step 2: Uruchom testy i potwierdź, że padają**

Run: `venv/bin/python -m pytest tests/test_pets_zarty_api.py tests/test_pets_state.py tests/test_pets_routes.py -q`
Expected: FAIL (`KeyError: 'jokes'`, `TypeError ... unexpected keyword argument 'jokes'`, 404 na `/api/wychylenia`).

- [ ] **Step 3: Implementacja**

`modules/pets/state.py`: słownik `stan['companion']` zastąp:

```python
    stan['companion'] = {
        'enabled': bool(profil.companion_enabled) if profil is not None else True,
        'pet_id': (wybrany or auto or {}).get('id'),
        'auto': wybrany is None,
        # Żarty (spec v3.2 §6.8): przełącznik użytkownika ∧ wyłącznik admina — klient dostaje jedną liczbę
        'jokes': (bool(profil.jokes_enabled) if profil is not None else True) and bool(cfg.jokes_enabled),
    }
```

`modules/pets/actions.py`: `set_companion` zastąp:

```python
def set_companion(user, pet_id=None, enabled=True, jokes=None):
    profil = lock_profile(user)
    if pet_id is not None:
        own_pet(user, pet_id, ('alive',))
    profil.companion_pet_id = pet_id
    profil.companion_enabled = bool(enabled)
    if jokes is not None:           # None = „nie zmieniaj” (spec v3.2 §6.8)
        profil.jokes_enabled = bool(jokes)
    db.session.commit()
    return profil
```

`modules/pets/routes.py`:
- importy: `from flask import abort, jsonify, render_template, request, url_for`; `from modules.pets.models import PetPeekImage`;
- w `api_companion`, po bloku walidacji `enabled`, dodaj i zmień wywołanie:

```python
    jokes = dane.get('jokes')
    if jokes is not None and not isinstance(jokes, bool):
        raise PetError('bad_request', 'Nieprawidłowe pole jokes.', 400)
    service.set_companion(current_user._get_current_object(), pet_id=pet_id, enabled=enabled, jokes=jokes)
```

- przed `@pets_bp.route('/api/<path:_reszta>', ...)` dodaj:

```python
@pets_bp.route('/api/wychylenia')
@feature_required
def api_peek_images():
    """Aktywne obrazki wychylania towarzysza (spec v3.2 §6.7) — ozdobniki wgrane w panelu admina."""
    obrazki = PetPeekImage.query.filter_by(is_active=True).order_by(PetPeekImage.id).all()
    odp = jsonify({'ok': True, 'images': [
        {'id': o.id, 'url': url_for('static', filename=f'uploads/pet_peeks/{o.filename}')} for o in obrazki]})
    odp.headers['Cache-Control'] = 'private, max-age=300'
    return odp
```

- [ ] **Step 4: Uruchom testy i potwierdź, że przechodzą**

Run: `venv/bin/python -m pytest tests -k "pets" -q`
Expected: PASS (wszystkie testy pupili).

- [ ] **Step 5: Commit**

```bash
git add modules/pets/state.py modules/pets/actions.py modules/pets/routes.py tests/test_pets_state.py tests/test_pets_routes.py tests/test_pets_zarty_api.py
git commit -m "feat(pupile): zarty - stan companion.jokes, zapis przelacznika i lista obrazkow w API

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Upload obrazków i karta w adminie

**Files:**
- Create: `modules/pets/peek_images.py`
- Modify: `modules/pets/admin_routes.py` (3 trasy, `_render_index`)
- Modify: `templates/admin/pets/index.html` (karta „Obrazki wychylania")
- Modify: `static/css/pages/admin/pets.css`, `static/js/pages/admin/pets.js`
- Create: `tests/test_pets_zarty_admin.py`

**Interfaces:**
- Consumes: `PetPeekImage` (Zadanie 1).
- Produces: `peek_images.save_upload(storage) -> str` (nazwa `<uuid>.webp`, rzuca `PeekImageError`), `peek_images.remove_file(filename)`, `peek_images.upload_dir()`, `peek_images.MAX_IMAGES = 30`; trasy `pets_admin.peek_upload` (`POST /admin/pupile/obrazki`), `pets_admin.peek_toggle` (`POST /admin/pupile/obrazki/<int:image_id>/przelacz`), `pets_admin.peek_delete` (`POST /admin/pupile/obrazki/<int:image_id>/usun`); klucz konfiguracji testowej `PETS_PEEK_UPLOAD_DIR`.

- [ ] **Step 1: Napisz testy, które muszą na początku paść**

Nowy plik `tests/test_pets_zarty_admin.py`:

```python
"""Obrazki wychylania w panelu /admin/pupile (spec v3.2 §6.4–6.5): upload z przezroczystością, przełącz, usuń."""
import io
import os

import pytest
from PIL import Image


@pytest.fixture(autouse=True)
def _katalog_obrazkow(app, tmp_path):
    app.config['PETS_PEEK_UPLOAD_DIR'] = str(tmp_path)
    yield
    app.config.pop('PETS_PEEK_UPLOAD_DIR', None)


def _admin(make_user, login, role='admin'):
    u = make_user(role=role, profile_completed=True)
    login(u)
    return u


def _png(w=300, h=200, srodek=True):
    """Przezroczyste tło + nieprzezroczysty czerwony kwadrat pośrodku."""
    obraz = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    if srodek:
        obraz.paste((255, 0, 0, 255), (w // 3, h // 3, 2 * w // 3, 2 * h // 3))
    buf = io.BytesIO()
    obraz.save(buf, 'PNG')
    buf.seek(0)
    return buf


def _wgraj(client, plik, nazwa='gwiazdka.png', **form):
    return client.post('/admin/pupile/obrazki', data={'image': (plik, nazwa), **form},
                       content_type='multipart/form-data')


def _flashe(client):
    with client.session_transaction() as sess:
        return [tresc for _kat, tresc in sess.get('_flashes', [])]


def test_upload_zapisuje_webp_z_przezroczystoscia(client, login, make_user, db, tmp_path):
    from modules.admin.models import ActivityLog
    from modules.pets.models import PetPeekImage
    admin = _admin(make_user, login)
    r = _wgraj(client, _png(), label='  Gwiazdka  ')
    assert r.status_code == 302
    obrazek = PetPeekImage.query.one()
    assert obrazek.filename.endswith('.webp') and obrazek.label == 'Gwiazdka'
    assert obrazek.is_active is True and obrazek.created_by == admin.id
    sciezka = tmp_path / obrazek.filename
    assert sciezka.exists()
    wynik = Image.open(sciezka).convert('RGBA')
    assert max(wynik.size) == 240
    assert wynik.getpixel((2, 2))[3] == 0            # tło zostało przezroczyste
    assert wynik.getpixel((wynik.width // 2, wynik.height // 2))[3] == 255
    assert ActivityLog.query.filter_by(action='pet_peek_image_added', entity_id=obrazek.id).count() == 1


def test_upload_malego_obrazka_nie_powieksza(client, login, make_user, db, tmp_path):
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    _wgraj(client, _png(100, 80))
    wynik = Image.open(tmp_path / PetPeekImage.query.one().filename)
    assert wynik.size == (100, 80)


def test_upload_animowanego_gifa_bierze_pierwsza_klatke(client, login, make_user, db, tmp_path):
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    klatki = [Image.new('RGB', (60, 60), kolor) for kolor in ('red', 'blue')]
    buf = io.BytesIO()
    klatki[0].save(buf, 'GIF', save_all=True, append_images=klatki[1:], duration=100, loop=0)
    buf.seek(0)
    assert _wgraj(client, buf, 'ruch.gif').status_code == 302
    wynik = Image.open(tmp_path / PetPeekImage.query.one().filename)
    assert getattr(wynik, 'n_frames', 1) == 1


@pytest.mark.parametrize('plik,nazwa,fragment', [
    (lambda: io.BytesIO(b'to nie jest obrazek'), 'a.png', 'uszkodzony'),
    (lambda: io.BytesIO(b'MZ'), 'wirus.exe', 'Dozwolone formaty'),
    (lambda: io.BytesIO(b'x' * (2 * 1024 * 1024 + 1)), 'duzy.png', 'za duży'),
    (lambda: io.BytesIO(b''), 'pusty.png', 'pusty'),
])
def test_upload_odrzuca_zle_pliki(client, login, make_user, db, tmp_path, plik, nazwa, fragment):
    """Review Focus 3: zły typ / uszkodzony / za duży / pusty — flash, brak rekordu, brak pliku."""
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    r = _wgraj(client, plik(), nazwa)
    assert r.status_code == 302
    assert PetPeekImage.query.count() == 0 and os.listdir(tmp_path) == []
    assert any(fragment in tresc for tresc in _flashe(client))


def test_upload_odrzuca_bombe_pikseli(client, login, make_user, db, tmp_path):
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    buf = io.BytesIO()
    Image.new('RGB', (2001, 2001), 'white').save(buf, 'PNG')   # mały plik, ponad 4 mln pikseli
    buf.seek(0)
    _wgraj(client, buf, 'bomba.png')
    assert PetPeekImage.query.count() == 0 and os.listdir(tmp_path) == []
    assert any('pikseli' in tresc for tresc in _flashe(client))


def test_upload_bez_pliku(client, login, make_user, db):
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    assert client.post('/admin/pupile/obrazki', data={}, content_type='multipart/form-data').status_code == 302
    assert PetPeekImage.query.count() == 0
    assert any('Wybierz plik' in tresc for tresc in _flashe(client))


def test_upload_limit_30(client, login, make_user, db, tmp_path):
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    db.session.add_all([PetPeekImage(filename=f'{i}.webp') for i in range(30)])
    db.session.commit()
    _wgraj(client, _png())
    assert PetPeekImage.query.count() == 30 and os.listdir(tmp_path) == []
    assert any('limit' in tresc for tresc in _flashe(client))


def test_przelacz_i_usun_kasuje_plik(client, login, make_user, db, tmp_path):
    from modules.admin.models import ActivityLog
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    _wgraj(client, _png())
    obrazek = PetPeekImage.query.one()
    assert client.post(f'/admin/pupile/obrazki/{obrazek.id}/przelacz').status_code == 302
    db.session.refresh(obrazek)
    assert obrazek.is_active is False
    assert client.post(f'/admin/pupile/obrazki/{obrazek.id}/przelacz').status_code == 302
    db.session.refresh(obrazek)
    assert obrazek.is_active is True
    plik = tmp_path / obrazek.filename
    assert plik.exists()
    assert client.post(f'/admin/pupile/obrazki/{obrazek.id}/usun').status_code == 302
    assert PetPeekImage.query.count() == 0 and not plik.exists()
    assert ActivityLog.query.filter_by(action='pet_peek_image_deleted').count() == 1


def test_usun_gdy_pliku_juz_nie_ma(client, login, make_user, db, tmp_path):
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    _wgraj(client, _png())
    obrazek = PetPeekImage.query.one()
    os.remove(tmp_path / obrazek.filename)
    assert client.post(f'/admin/pupile/obrazki/{obrazek.id}/usun').status_code == 302
    assert PetPeekImage.query.count() == 0


def test_nieznany_obrazek_404(client, login, make_user, db):
    _admin(make_user, login)
    assert client.post('/admin/pupile/obrazki/999/przelacz').status_code == 404
    assert client.post('/admin/pupile/obrazki/999/usun').status_code == 404


def test_klient_nie_ma_dostepu(client, login, make_user, db):
    login(make_user(role='client', profile_completed=True))
    assert client.post('/admin/pupile/obrazki', data={}).status_code == 403
    assert client.post('/admin/pupile/obrazki/1/przelacz').status_code == 403
    assert client.post('/admin/pupile/obrazki/1/usun').status_code == 403


def test_mod_moze_dodawac(client, login, make_user, db):
    from modules.pets.models import PetPeekImage
    _admin(make_user, login, role='mod')
    _wgraj(client, _png())
    assert PetPeekImage.query.count() == 1


def test_index_pokazuje_karte_i_miniature(client, login, make_user, db):
    _admin(make_user, login)
    _wgraj(client, _png(), label='Gwiazdka')
    html = client.get('/admin/pupile').data.decode()
    assert 'id="paPeekTitle"' in html and 'name="image"' in html and 'data-confirm' in html
    assert '/static/uploads/pet_peeks/' in html and 'Gwiazdka' in html
```

- [ ] **Step 2: Uruchom testy i potwierdź, że padają**

Run: `venv/bin/python -m pytest tests/test_pets_zarty_admin.py -q`
Expected: FAIL (404 na `/admin/pupile/obrazki`, brak modułu `peek_images`).

- [ ] **Step 3: Implementacja**

Nowy plik `modules/pets/peek_images.py`:

```python
"""Obrazki wychylania towarzysza (spec v3.2 §6.4): zapis wgranego pliku jako WebP z przezroczystością.

`utils.image_processor.compress_image` spłaszcza alfę do białego tła — ozdobniki (gwiazdka, serduszko)
jej potrzebują, więc ten moduł robi własny zapis.
"""
import io
import os
import uuid

from flask import current_app
from PIL import Image, ImageOps

ALLOWED_EXT = frozenset({'png', 'jpg', 'jpeg', 'webp', 'gif'})
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_SOURCE_PIXELS = 4_000_000        # ~2000×2000 — chroni przed „bombą” zakodowaną w małym pliku
MAX_IMAGES = 30
BOX = 240                            # dłuższy bok po zapisie
UPLOAD_SUBDIR = ('uploads', 'pet_peeks')


class PeekImageError(ValueError):
    """Komunikat dla admina (po polsku), pokazywany we flashu."""


def upload_dir():
    """Katalog zapisu; testy podmieniają go przez config['PETS_PEEK_UPLOAD_DIR']."""
    return current_app.config.get('PETS_PEEK_UPLOAD_DIR') or os.path.join(current_app.static_folder, *UPLOAD_SUBDIR)


def save_upload(storage):
    """Waliduje i zapisuje wgrany plik; zwraca nazwę pliku (`<uuid>.webp`) albo rzuca PeekImageError."""
    nazwa = storage.filename or ''
    ext = nazwa.rsplit('.', 1)[-1].lower() if '.' in nazwa else ''
    if ext not in ALLOWED_EXT:
        raise PeekImageError('Dozwolone formaty: PNG, JPG, WebP, GIF.')
    dane = storage.read(MAX_SOURCE_BYTES + 1)
    if not dane:
        raise PeekImageError('Plik jest pusty.')
    if len(dane) > MAX_SOURCE_BYTES:
        raise PeekImageError('Plik jest za duży (maks. 2 MB).')
    try:
        obraz = Image.open(io.BytesIO(dane))
        if obraz.width * obraz.height > MAX_SOURCE_PIXELS:
            raise PeekImageError('Obrazek ma za dużo pikseli (maks. 2000×2000).')
        obraz.load()                                    # GIF: pierwsza klatka
        obraz = ImageOps.exif_transpose(obraz).convert('RGBA')
    except PeekImageError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError):
        raise PeekImageError('Nie udało się odczytać obrazka — plik jest uszkodzony.')
    obraz.thumbnail((BOX, BOX), Image.Resampling.LANCZOS)
    katalog = upload_dir()
    os.makedirs(katalog, exist_ok=True)
    filename = f'{uuid.uuid4().hex}.webp'
    obraz.save(os.path.join(katalog, filename), 'WEBP', quality=85)
    return filename


def remove_file(filename):
    """Kasuje plik z dysku; brak pliku lub błąd systemu plików nie blokuje usunięcia rekordu."""
    try:
        os.remove(os.path.join(upload_dir(), filename))
    except OSError:
        current_app.logger.warning('pets: nie udało się usunąć pliku obrazka %s', filename)
```

`modules/pets/admin_routes.py`:
- importy: `from flask import abort, flash, jsonify, redirect, render_template, request, url_for`; `from modules.pets import peek_images, pets_admin_bp, rules, service`; `from modules.pets.models import Pet, PetEvent, PetPeekImage, PetProfile`;
- w `_render_index` dodaj do `render_template`: `peek_items=PetPeekImage.query.order_by(PetPeekImage.id.desc()).all(), peek_limit=peek_images.MAX_IMAGES,`;
- na końcu pliku dodaj:

```python
# ---------------------------------------------------------------------------
# Obrazki wychylania towarzysza (spec v3.2 §6.5)
# ---------------------------------------------------------------------------

def _wroc_do_obrazkow():
    return redirect(url_for('pets_admin.index', _anchor='paPeekTitle'))


def _obrazek_or_404(image_id):
    obrazek = db.session.get(PetPeekImage, image_id)
    if obrazek is None:
        abort(404)
    return obrazek


@pets_admin_bp.route('/obrazki', methods=['POST'])
@role_required('admin', 'mod')
def peek_upload():
    plik = request.files.get('image')
    if plik is None or not plik.filename:
        flash('Wybierz plik obrazka.', 'error')
        return _wroc_do_obrazkow()
    if PetPeekImage.query.count() >= peek_images.MAX_IMAGES:
        flash(f'Osiągnięto limit {peek_images.MAX_IMAGES} obrazków — usuń któryś, żeby dodać nowy.', 'error')
        return _wroc_do_obrazkow()
    try:
        filename = peek_images.save_upload(plik)
    except peek_images.PeekImageError as e:
        flash(str(e), 'error')
        return _wroc_do_obrazkow()
    etykieta = (request.form.get('label') or '').strip()[:60] or None
    obrazek = PetPeekImage(filename=filename, label=etykieta, created_by=current_user.id)
    db.session.add(obrazek)
    db.session.commit()
    log_activity(user=current_user, action='pet_peek_image_added', entity_type='pet_peek_image',
                 entity_id=obrazek.id, new_value=filename)
    flash('Obrazek dodany.', 'success')
    return _wroc_do_obrazkow()


@pets_admin_bp.route('/obrazki/<int:image_id>/przelacz', methods=['POST'])
@role_required('admin', 'mod')
def peek_toggle(image_id):
    obrazek = _obrazek_or_404(image_id)
    obrazek.is_active = not obrazek.is_active
    db.session.commit()
    log_activity(user=current_user, action='pet_peek_image_toggled', entity_type='pet_peek_image',
                 entity_id=obrazek.id, new_value='aktywny' if obrazek.is_active else 'wyłączony')
    flash('Obrazek włączony.' if obrazek.is_active else 'Obrazek wyłączony.', 'success')
    return _wroc_do_obrazkow()


@pets_admin_bp.route('/obrazki/<int:image_id>/usun', methods=['POST'])
@role_required('admin', 'mod')
def peek_delete(image_id):
    obrazek = _obrazek_or_404(image_id)
    filename = obrazek.filename
    db.session.delete(obrazek)
    db.session.commit()
    peek_images.remove_file(filename)
    log_activity(user=current_user, action='pet_peek_image_deleted', entity_type='pet_peek_image',
                 entity_id=image_id, old_value=filename)
    flash('Obrazek usunięty.', 'success')
    return _wroc_do_obrazkow()
```

`templates/admin/pets/index.html`: przed sekcją `{# --- Użytkownik: szukaj i przyznaj jajko --- #}` wstaw:

```jinja
    {# --- Obrazki wychylania (spec v3.2 §6.5) --- #}
    <section class="pa-card" aria-labelledby="paPeekTitle">
        <h2 id="paPeekTitle" class="pa-card__title">Obrazki wychylania</h2>
        <p class="pa-hint">Ozdobne obrazki, które pupil czasem wychyla zza krawędzi ekranu. PNG, JPG, WebP lub GIF do 2 MB; zapisujemy je jako WebP (maks. 240 px, przezroczystość zostaje). Limit {{ peek_limit }} obrazków.</p>
        <form method="post" action="{{ url_for('pets_admin.peek_upload') }}" enctype="multipart/form-data" class="pa-peek-upload">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="pa-field">
                <label for="paPeekFile">plik obrazka</label>
                <input type="file" id="paPeekFile" name="image" accept="image/png,image/jpeg,image/webp,image/gif" required>
            </div>
            <div class="pa-field">
                <label for="paPeekLabel">nazwa (opcjonalnie)</label>
                <input type="text" id="paPeekLabel" name="label" maxlength="60">
            </div>
            <button type="submit" class="pa-btn-primary">Dodaj obrazek</button>
        </form>
        {% if peek_items %}
        <ul class="pa-peek-grid">
            {% for o in peek_items %}
            <li class="pa-peek {% if not o.is_active %}pa-peek--off{% endif %}">
                <div class="pa-peek__thumb"><img src="{{ url_for('static', filename='uploads/pet_peeks/' ~ o.filename) }}" alt="" loading="lazy"></div>
                <div class="pa-peek__label">{{ o.label or 'Bez nazwy' }}</div>
                <div class="pa-peek__state">{{ 'Aktywny' if o.is_active else 'Wyłączony' }}</div>
                <div class="pa-peek__actions">
                    <form method="post" action="{{ url_for('pets_admin.peek_toggle', image_id=o.id) }}">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                        <button type="submit" class="pa-btn-secondary">{{ 'Wyłącz' if o.is_active else 'Włącz' }}</button>
                    </form>
                    <form method="post" action="{{ url_for('pets_admin.peek_delete', image_id=o.id) }}" data-confirm="Usunąć ten obrazek?">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                        <button type="submit" class="pa-btn-danger">Usuń</button>
                    </form>
                </div>
            </li>
            {% endfor %}
        </ul>
        {% else %}
        <p class="pa-results__empty">Brak obrazków — wychylenie się nie zdarzy, dopóki nie dodasz pierwszego.</p>
        {% endif %}
    </section>
```

Na końcu `static/css/pages/admin/pets.css` dopisz:

```css
/* --- Obrazki wychylania (spec v3.2 §6.5) --- */
.pa-peek-upload { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; margin: 12px 0 18px; }
.pa-peek-upload .pa-field { flex: 1 1 220px; }
.pa-peek-upload input[type="file"] { padding: 8px 10px; }
.pa-peek-grid { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 14px; }
.pa-peek { border: 1px solid #ececec; border-radius: 12px; padding: 10px; display: flex; flex-direction: column; gap: 6px; background: #ffffff; }
.pa-peek--off { opacity: 0.6; }
.pa-peek__thumb { height: 110px; border-radius: 8px; display: flex; align-items: center; justify-content: center; background: repeating-conic-gradient(#f1f1f5 0% 25%, #ffffff 0% 50%) 0 0 / 16px 16px; }
.pa-peek__thumb img { max-width: 100%; max-height: 100%; }
.pa-peek__label { font-weight: 700; color: #333333; font-size: 0.9rem; overflow-wrap: anywhere; }
.pa-peek__state { font-size: 0.8rem; color: #666666; }
.pa-peek__actions { display: flex; gap: 8px; flex-wrap: wrap; }
.pa-peek__actions form { margin: 0; }
.pa-btn-secondary, .pa-btn-danger { min-height: 44px; padding: 0 14px; border-radius: 10px; font-weight: 700; font-family: inherit; cursor: pointer; background: #ffffff; }
.pa-btn-secondary { border: 1px solid #f093fb; color: #c2338f; }
.pa-btn-danger { border: 1px solid #f5c2c7; color: #b3261e; }

[data-theme="dark"] .pa-peek { background: rgba(255, 255, 255, 0.05); border-color: rgba(240, 147, 251, 0.2); }
[data-theme="dark"] .pa-peek__thumb { background: repeating-conic-gradient(rgba(255, 255, 255, 0.08) 0% 25%, rgba(255, 255, 255, 0.02) 0% 50%) 0 0 / 16px 16px; }
[data-theme="dark"] .pa-peek__label { color: #ffffff; }
[data-theme="dark"] .pa-peek__state { color: rgba(255, 255, 255, 0.6); }
[data-theme="dark"] .pa-btn-secondary, [data-theme="dark"] .pa-btn-danger { background: rgba(255, 255, 255, 0.05); }
[data-theme="dark"] .pa-btn-secondary { color: #f093fb; }
[data-theme="dark"] .pa-btn-danger { color: #ff8a95; border-color: rgba(245, 87, 108, 0.4); }
[data-theme="dark"] .pa-peek-upload input[type="file"] { color: #ffffff; }
```

Na końcu `static/js/pages/admin/pets.js` dopisz:

```js

// Formularze z data-confirm (usuwanie obrazka wychylania): potwierdzenie bez inline JS
(function () {
    'use strict';
    document.addEventListener('submit', function (e) {
        var form = e.target;
        var msg = form && form.getAttribute && form.getAttribute('data-confirm');
        if (msg && !window.confirm(msg)) e.preventDefault();
    });
})();
```

- [ ] **Step 4: Uruchom testy i potwierdź, że przechodzą**

Run: `venv/bin/python -m pytest tests/test_pets_zarty_admin.py tests/test_pets_admin.py -q && node --check static/js/pages/admin/pets.js`
Expected: PASS i brak wyjścia z `node --check`.

- [ ] **Step 5: Weryfikacja przeglądarkowa karty admina**

Utwórz obrazek testowy i skrypt, zrestartuj serwer podglądu (`preview_stop`/`preview_start` `pets-jokes`):

```bash
venv/bin/python -c "
from PIL import Image, ImageDraw
im = Image.new('RGBA', (200, 200), (0, 0, 0, 0)); ImageDraw.Draw(im).ellipse((20, 20, 180, 180), fill=(255, 200, 60, 255)); im.save('$JOKES/gwiazdka.png')"
```

Zapisz `$JOKES/admin_check.js`:

```js
const L = require('./lib');
(async () => {
  const { browser, page, errors } = await L.open({ login: '/dev-login-admin', path: '/admin/pupile' });
  const dialogs = [];
  page.on('dialog', (d) => { dialogs.push(d.message()); d.dismiss(); });
  L.check('karta Obrazki wychylania', (await page.locator('#paPeekTitle').count()) === 1);
  L.check('checkbox żartów w Włączniku', (await page.locator('input[name="pets_jokes_enabled"]').count()) === 1);
  const n0 = await page.locator('.pa-peek').count();
  await page.setInputFiles('#paPeekFile', L.DIR + '/gwiazdka.png');
  await page.fill('#paPeekLabel', 'Gwiazdka testowa');
  await Promise.all([page.waitForNavigation(), page.click('.pa-peek-upload button[type=submit]')]);
  L.check('po dodaniu +1 miniatura', (await page.locator('.pa-peek').count()) === n0 + 1);
  const src = await page.locator('.pa-peek').first().locator('img').getAttribute('src');
  L.check('miniatura z /static/uploads/pet_peeks/', /\/static\/uploads\/pet_peeks\/.+\.webp/.test(src), src);
  await Promise.all([page.waitForNavigation(), page.locator('.pa-peek').first().locator('.pa-btn-secondary').click()]);
  L.check('po wyłączeniu klasa pa-peek--off', (await page.locator('.pa-peek').first().evaluate((e) => e.classList.contains('pa-peek--off'))) === true);
  await page.locator('.pa-peek').first().locator('.pa-btn-danger').click();
  await page.waitForTimeout(300);
  L.check('confirm pokazany, odmowa zostawia obrazek', dialogs.length === 1 && (await page.locator('.pa-peek').count()) === n0 + 1, dialogs);
  page.removeAllListeners('dialog');
  page.on('dialog', (d) => d.accept());
  await Promise.all([page.waitForNavigation(), page.locator('.pa-peek').first().locator('.pa-btn-danger').click()]);
  L.check('po usunięciu wraca liczba początkowa', (await page.locator('.pa-peek').count()) === n0);
  await page.locator('#paPeekTitle').scrollIntoViewIfNeeded();
  await page.screenshot({ path: L.DIR + '/shots/admin-light.png' });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await page.screenshot({ path: L.DIR + '/shots/admin-dark.png' });
  await browser.close();
  L.finish(errors);
})();
```

Run: `cd $JOKES && node admin_check.js`
Expected: wszystkie `ok`, `0 fail`. Obejrzyj `shots/admin-light.png` i `shots/admin-dark.png` (Read): karta czytelna w obu motywach.

- [ ] **Step 6: Commit**

```bash
git add modules/pets/peek_images.py modules/pets/admin_routes.py templates/admin/pets/index.html static/css/pages/admin/pets.css static/js/pages/admin/pets.js tests/test_pets_zarty_admin.py
git commit -m "feat(pupile): zarty - upload i karta obrazkow wychylania w adminie

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Przełącznik „Żarty pupila" w warsztacie

**Files:**
- Modify: `static/js/pet/world/workshop.js` (ramka „Towarzysz")

**Interfaces:**
- Consumes: `state.companion.jokes`, `POST /towarzysz` z polem `jokes` (Zadanie 2).
- Produces: wiersz `#petsJokesToggle` (`role="switch"`) w ramce „Towarzysz".

- [ ] **Step 1: Napisz skrypt, który ma paść**

Zapisz `$JOKES/workshop_check.js`:

```js
const L = require('./lib');
(async () => {
  const { browser, page, errors } = await L.open({ path: '/client/pupile/warsztat' });
  await page.waitForSelector('#petsCompanionToggle', { timeout: 10000 });
  L.check('przełącznik żartów istnieje', (await page.locator('#petsJokesToggle').count()) === 1);
  if ((await page.locator('#petsJokesToggle').count()) === 0) { await browser.close(); return L.finish(errors); }
  const label = (await page.locator('label[for=petsJokesToggle]').textContent()).trim();
  L.check('etykieta „Żarty pupila"', label === 'Żarty pupila', label);
  const row = page.locator('#petsJokesToggle').locator('xpath=ancestor::div[contains(@class,"pets-setting")][1]');
  const hint = await row.textContent();
  L.check('opis nie wymienia rodzajów żartów', !/kursor|obraz|wychyl|bieg/i.test(hint), hint);
  L.check('domyślnie włączony', await page.locator('#petsJokesToggle').isChecked());

  async function przelacz() {
    const [req] = await Promise.all([
      page.waitForRequest((r) => r.url().includes('/api/towarzysz') && r.method() === 'POST'),
      page.locator('#petsJokesToggle').evaluate((i) => i.click()),
    ]);
    await page.waitForResponse((r) => r.url().includes('/api/towarzysz'));
    return JSON.parse(req.postData());
  }
  const body = await przelacz();
  L.check('POST niesie jokes=false oraz enabled/pet_id', body.jokes === false && typeof body.enabled === 'boolean' && 'pet_id' in body, body);
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('#petsJokesToggle');
  L.check('po odświeżeniu zostaje wyłączony', (await page.locator('#petsJokesToggle').isChecked()) === false);
  const body2 = await przelacz();
  L.check('POST niesie jokes=true', body2.jokes === true, body2);
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('#petsJokesToggle');
  L.check('po odświeżeniu znów włączony', await page.locator('#petsJokesToggle').isChecked());
  await browser.close();
  L.finish(errors);
})();
```

Zrestartuj serwer podglądu (nowy Python z Zadań 1–3) i uruchom:

Run: `cd $JOKES && node workshop_check.js`
Expected: FAIL na „przełącznik żartów istnieje" (brak `#petsJokesToggle`).

- [ ] **Step 2: Implementacja w `static/js/pet/world/workshop.js`**

Edytuj dokładnie te linie (każda występuje raz):

1. Po `var show = switchRow('petsCompanionToggle', 'Pokazuj towarzysza na stronach', null);` dodaj:
```js
        var jokes = switchRow('petsJokesToggle', 'Żarty pupila', 'Pupil czasem lubi coś wywinąć. Wyłącz, jeśli wolisz spokój.');
```
2. Po `frame.appendChild(show.row);` dodaj `frame.appendChild(jokes.row);`.
3. `var companion = state.companion || { enabled: true, pet_id: null, auto: true };` → `var companion = state.companion || { enabled: true, pet_id: null, auto: true, jokes: true };`.
4. Po `show.row.hidden = !has;` dodaj `jokes.row.hidden = !has;`.
5. Po `show.input.checked = !!companion.enabled;` dodaj `jokes.input.checked = companion.jokes !== false;`.
6. Po `show.input.disabled = false;` (jedyne wystąpienie z `false`) dodaj `jokes.input.disabled = false;`.
7. W `saveCompanion` linię z `var body` zastąp:
```js
            var body = { pet_id: value === 'auto' ? null : parseInt(value, 10), enabled: !!show.input.checked, jokes: !!jokes.input.checked };   // boolean, nie string
```
8. Po `show.input.disabled = true;` dodaj `jokes.input.disabled = true;`.
9. Po `show.input.addEventListener('change', saveCompanion);` dodaj `jokes.input.addEventListener('change', saveCompanion);`.

Komentarz nagłówkowy pliku (linie ~4–5, „ramka ze zdjęciem = wybór towarzysza … i włącznik") uzupełnij o „oraz przełącznik żartów (POST /towarzysz, pole jokes)".

- [ ] **Step 3: Uruchom skrypt i potwierdź**

Run: `node --check static/js/pet/world/workshop.js && cd $JOKES && node workshop_check.js`
Expected: `0 fail` (włącznie z zachowaniem po odświeżeniu).

- [ ] **Step 4: Commit**

```bash
git add static/js/pet/world/workshop.js
git commit -m "feat(pupile): zarty - przelacznik w warsztacie

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Bieg na 4 łapach: poza `run` w rigu i ruch podstawowy towarzysza

**Files:**
- Modify: `static/js/components/pet-rig.js` (lista póz, blokada gestów)
- Modify: `static/css/components/pet-rig.css` (`.pose-run`)
- Modify: `static/js/components/pet-companion.js` (stałe, `running`, `runsThisStep`, `startMove`, `endRun`)
- Modify: `static/css/components/pet-companion.css` (`--running`)

**Interfaces:**
- Produces: `PetRig.POSES` zawiera `'run'`; klasa `pet-companion--running` (obok `--walking`) w trakcie biegu; funkcja wewnętrzna `startMove(target, run)` używana też przez `runTo` w Zadaniu 6; zmienne `running`, stałe `RUN_SPEED`, `RUN_CHANCE`, `RUN_MIN_DIST`.

- [ ] **Step 1: Napisz skrypt, który ma paść**

Zapisz `$JOKES/run_gait.js`:

```js
const L = require('./lib');
(async () => {
  const mood = process.argv[2] || '';
  const recorder = () => {
    window.__runs = [];
    document.addEventListener('DOMContentLoaded', () => {
      const el = document.getElementById('petCompanion');
      if (!el) return;
      let on = false;
      new MutationObserver(() => {
        const r = el.classList.contains('pet-companion--running');
        if (r && !on) {
          const rig = el.querySelector('.pet-rig');
          window.__runs.push({ secs: parseFloat(el.style.getPropertyValue('--pet-companion-walk')), rigPose: rig ? rig.className : '' });
        }
        on = r;
      }).observe(el, { attributes: true, attributeFilter: ['class'] });
    });
  };
  const { browser, page, errors } = await L.open({
    clock: true, seed: 7, init: recorder,
    patchState: mood ? (s) => { const id = s.companion && s.companion.pet_id; (s.pets || []).forEach((p) => { if (p.id === id) p.mood = mood; }); } : null,
  });
  await L.waitCompanion(page);
  await L.pause(page);
  await L.run(page, 240000, 2000);   // 4 minuty czasu wirtualnego
  const runs = await page.evaluate(() => window.__runs);
  if (!mood) {
    L.check('co najmniej jeden bieg w 4 minuty (czas wirtualny)', runs.length >= 1, runs.length);
    L.check('każdy bieg ma poza run w rigu', runs.length > 0 && runs.every((r) => /pose-run/.test(r.rigPose)), runs);
    L.check('każdy bieg: dystans >= 200 px (czas × 170)', runs.length > 0 && runs.every((r) => r.secs * 170 >= 199), runs);
  } else {
    L.check(`${mood} nie biega (0 biegów w 4 minuty)`, runs.length === 0, runs.length);
  }
  const fin = await page.evaluate(() => {
    const el = document.getElementById('petCompanion');
    const rig = el.querySelector('.pet-rig');
    return { running: el.classList.contains('pet-companion--running'), pose: /pose-run/.test(rig.className) };
  });
  L.check('poza run tylko w trakcie biegu', fin.running === fin.pose, fin);
  await browser.close();
  L.finish(errors);
})();
```

Zapisz `$JOKES/rig_run_shots.js` (przegląd wizualny wszystkich gatunków):

```js
const L = require('./lib');
(async () => {
  const { browser, page, errors } = await L.open({});
  await L.waitCompanion(page);   // pet-rig.css ładuje się leniwie razem z towarzyszem
  await page.evaluate(() => {
    const host = document.createElement('div');
    host.style.cssText = 'position:fixed;inset:0;z-index:99999;background:#fff;display:grid;grid-template-columns:repeat(8,130px);gap:6px;padding:8px;overflow:auto';
    Object.keys(window.PetSpecies).forEach((sp) => ['maluch', 'dziecko', 'dorosly'].forEach((st) => {
      const c = document.createElement('div');
      c.style.cssText = 'width:130px;height:130px;outline:1px dashed #ccc';
      host.appendChild(c);
      window.PetRig.mount(c, { species: sp, stage: st, size: 'card', pose: 'run', mood: 'szczesliwy', idle: false });
    }));
    document.body.appendChild(host);
  });
  await page.waitForTimeout(600);
  await page.screenshot({ path: L.DIR + '/shots/run-species.png' });
  await browser.close();
  L.finish(errors);
})();
```

Zrestartuj serwer i uruchom: `cd $JOKES && node run_gait.js`
Expected: FAIL „co najmniej jeden bieg…" (brak biegu w kodzie).

- [ ] **Step 2: Rig: poza `run`**

`static/js/components/pet-rig.js`:
- linia komentarza `rig.setPose(pose) — PetRig.POSES: stand | sit | lie | bed (łóżeczko szpitalne z kołderką)` → dopisz ` | run (bieg na 4 łapach: towarzysz w ruchu)`;
- `var POSES = ['stand', 'sit', 'lie', 'bed'];` → `var POSES = ['stand', 'sit', 'lie', 'bed', 'run'];`
- w `rig.gesture`: `if (o.pose === 'lie' || o.pose === 'bed') return false;` → `if (o.pose === 'lie' || o.pose === 'bed' || o.pose === 'run') return false;`

`static/css/components/pet-rig.css`: po bloku `lie` (po regule `.pet-rig.pose-lie.is-sick .rig-fm, .pet-rig.pose-lie.is-critical .rig-fm { animation: none; }`) dodaj:

```css

/* run: bieg na 4 łapach (towarzysz w ruchu, spec v3.2 §3) — korpus pochylony do przodu, głowa wysunięta,
   ramiona jako przednie łapy i stopy pracują naprzemiennie */
.pet-rig.pose-run { --rig-pose-dy: 6px; }
.pet-rig.pose-run:not(.pose-off) .rig-fig { rotate: 26deg; translate: 6px 8px; }
.pet-rig.pose-run:not(.pose-off) .rig-head { rotate: -12deg; translate: 4px 4px; }
.pet-rig.pose-run:not(.pose-off) .rig-tail { rotate: 18deg; translate: -2px -6px; }
.pet-rig.pose-run:not(.pose-off) .rig-arm-l { animation: rig-run-arm-l .3s ease-in-out infinite alternate; }
.pet-rig.pose-run:not(.pose-off) .rig-arm-r { animation: rig-run-arm-r .3s ease-in-out infinite alternate; }
.pet-rig.pose-run:not(.pose-off) .rig-feet { animation: rig-run-feet .3s ease-in-out infinite alternate; }
.pet-rig.pose-run:not(.pose-off) .rig-shadow ellipse { scale: 1.2 1; }

@keyframes rig-run-arm-l { from { rotate: -55deg; } to { rotate: 40deg; } }
@keyframes rig-run-arm-r { from { rotate: 40deg; } to { rotate: -55deg; } }
@keyframes rig-run-feet { from { scale: 1.12 .92; } to { scale: .92 1.08; } }
```

(Animacje wygasza istniejąca reguła `prefers-reduced-motion` / `.pet-rig-rm .pet-rig *`.)

- [ ] **Step 3: Towarzysz: bieg w `walkStep`**

`static/js/components/pet-companion.js`:

1. Po `var WALK_SPEED = 40;               // px/s` dodaj:
```js
    var RUN_SPEED = 170;               // px/s — bieg na 4 łapach (spec v3.2 §3)
    var RUN_CHANCE = 0.2;              // szansa, że dłuższy krok to bieg
    var RUN_MIN_DIST = 200;            // krótsze przejścia zawsze marszem
```
2. Po `var walking = false;` dodaj:
```js
    var running = false;               // walk: bieg na 4 łapach (poza `run` w rigu)
```
3. W `syncPose` po linii `var want = ...;` dodaj `if (want === 'stand' && running) want = 'run';`.
4. W `walkStep` zastąp końcówkę (od `var dx = target.x - pos.x, dy = target.y - pos.y;` do końca funkcji) przez:

```js
        startMove(target, runsThisStep(Math.sqrt(Math.pow(target.x - pos.x, 2) + Math.pow(target.y - pos.y, 2))));
    }

    /** Czy ten krok to bieg: dłuższy dystans, pupil nie jest chory ani krytyczny, los poniżej RUN_CHANCE. */
    function runsThisStep(dist) {
        if (dist < RUN_MIN_DIST || !pet || pet.mood === 'chory' || pet.mood === 'krytyczny') return false;
        return Math.random() < RUN_CHANCE;
    }

    /** Rusza do `target` marszem albo biegiem: zwrot, czas z prędkości, klasy ruchu, cel z przejściem CSS. */
    function startMove(target, run) {
        var dx = target.x - pos.x, dy = target.y - pos.y;
        var secs = Math.sqrt(dx * dx + dy * dy) / (run ? RUN_SPEED : WALK_SPEED);
        // rAF w ukrytej karcie nie rusza — klasa odtworzenia nie może zablokować przejścia marszu
        el.classList.remove('pet-companion--restored');
        if (Math.abs(dx) > 4) el.classList.toggle('pet-companion--flipped', dx < 0);   // patrzy w stronę ruchu
        el.style.setProperty('--pet-companion-walk', secs.toFixed(2) + 's');
        el.classList.add('pet-companion--walking');
        el.classList.toggle('pet-companion--running', run);
        running = run;
        syncPose();
        walking = true;
        setPos(target.x, target.y, true);
        clearTimeout(timers.arrive);
        timers.arrive = setTimeout(arrived, secs * 1000 + 60);
    }

    /** Koniec biegu: zdejmuje klasę i wraca do pozy stojącej. */
    function endRun() {
        if (!running) return;
        running = false;
        el.classList.remove('pet-companion--running');
        syncPose();
    }
```
5. W `arrived()` po `walking = false;` dodaj `endRun();`.
6. W `stopWalk()` po `walking = false;` dodaj `endRun();`.

`static/css/components/pet-companion.css`: po regule `.pet-companion--walking .pet-companion__scene { animation: ...}` i jej `@keyframes` dodaj:

```css

/* Bieg (spec v3.2 §3): szybszy i wyższy rytm kołysania niż w marszu */
.pet-companion--running .pet-companion__scene { animation: pet-companion-bob-run 0.24s ease-in-out infinite alternate; }

@keyframes pet-companion-bob-run {
    from { translate: 0 0; }
    to { translate: 0 -6px; }
}
```

oraz w obu blokach ograniczonego ruchu (`@media (prefers-reduced-motion: reduce)` i `.pet-rig-rm`) dopisz odpowiednio `.pet-companion--running .pet-companion__scene { animation: none; }` / `.pet-rig-rm .pet-companion--running .pet-companion__scene { animation: none; }`.

- [ ] **Step 4: Uruchom skrypty i potwierdź**

Run: `node --check static/js/components/pet-companion.js && node --check static/js/components/pet-rig.js && cd $JOKES && node run_gait.js && node run_gait.js chory && node rig_run_shots.js`
Expected: `0 fail` w obu przebiegach (zwykły: ≥ 1 bieg, `pose-run`, dystans ≥ 200 px; `chory`: 0 biegów). Jeśli przy ziarnie 7 nie ma żadnego biegu, zmień `seed` w skrypcie (to nie jest błąd kodu).
Następnie obejrzyj `$JOKES/shots/run-species.png` (Read): wszystkie 8 gatunków × 3 stadia pochylone do przodu, bez oderwanych części i ucięć. Jeśli któryś wygląda źle, dostrój kąty/przesunięcia w `.pose-run` i powtórz zrzut.

- [ ] **Step 5: Test regresji i commit**

Run: `venv/bin/python -m pytest tests -k "pets or pet_ or dashboard" -q`
Expected: PASS.

```bash
git add static/js/components/pet-rig.js static/css/components/pet-rig.css static/js/components/pet-companion.js static/css/components/pet-companion.css
git commit -m "feat(pupile): bieg towarzysza na 4 lapach (poza run + ruch podstawowy)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: API towarzysza dla żartów (`PetCompanionApi`)

**Files:**
- Modify: `static/js/components/pet-companion.js`
- Modify: `static/css/components/pet-companion.css`

**Interfaces:**
- Consumes: `startMove(target, run)`, `running`, `endRun` (Zadanie 5).
- Produces (`window.PetCompanionApi`, tylko tryb `walk`, rejestrowane w `boot()`):
  - `ready() -> bool`
  - `rect() -> {x, y, w, h}` (px okna)
  - `claim(onBreak?) -> release | null` (`null`, gdy zajęty lub nie `ready`; `release()` oddaje pupila; `onBreak()` wołane, gdy coś przerwie)
  - `runTo(x, y, opts?) -> Promise<boolean>` (`opts.allowOutside`, `opts.face: 'left'|'right'`; wymaga aktywnego `claim`, inaczej `false`)
  - `face('left'|'right')`
- Klasa `pet-companion--claimed` (pupil nieklikalny na czas `claim`).

- [ ] **Step 1: Napisz skrypt, który ma paść**

Zapisz `$JOKES/api_check.js`:

```js
const L = require('./lib');
(async () => {
  const { browser, page, errors } = await L.open({});
  await L.waitCompanion(page);
  const T = (fn, ...a) => page.evaluate(fn, ...a);
  L.check('API istnieje w trybie walk', await T(() => !!window.PetCompanionApi));
  await page.waitForFunction(() => window.PetCompanionApi && window.PetCompanionApi.ready(), null, { timeout: 10000 });

  await T(() => { window.__broke = 0; window.__rel = window.PetCompanionApi.claim(() => { window.__broke++; }); });
  L.check('claim zwraca funkcję release', await T(() => typeof window.__rel === 'function'));
  L.check('drugi claim zwraca null', await T(() => window.PetCompanionApi.claim() === null));
  L.check('ready() jest false w trakcie claim', (await T(() => window.PetCompanionApi.ready())) === false);
  L.check('klasa --claimed (pupil nieklikalny)', await T(() => document.getElementById('petCompanion').classList.contains('pet-companion--claimed')));
  const left0 = await T(() => document.getElementById('petCompanion').style.left);
  await page.waitForTimeout(5000);
  L.check('zajęty pupil stoi (brak spaceru przez 5 s)', (await T(() => document.getElementById('petCompanion').style.left)) === left0);

  const t = await T(async () => {
    const api = window.PetCompanionApi, el = document.getElementById('petCompanion');
    const r = api.rect(), t0 = performance.now();
    const p = api.runTo(r.x + (r.x > 600 ? -300 : 300), r.y);
    await new Promise((res) => setTimeout(res, 150));
    const rig = el.querySelector('.pet-rig');
    const seen = { cls: el.classList.contains('pet-companion--running'), pose: /pose-run/.test(rig.className) };
    const ok = await p;
    return { ok, ms: performance.now() - t0, seen, after: { running: el.classList.contains('pet-companion--running'), walking: el.classList.contains('pet-companion--walking'), pose: rig.className } };
  });
  L.check('runTo(300 px) kończy się true', t.ok === true, t);
  L.check('w trakcie: klasa running i poza run', t.seen.cls && t.seen.pose, t.seen);
  L.check('czas ≈ dystans/170 (300 px ≈ 1,8 s)', t.ms > 1300 && t.ms < 2800, t.ms);
  L.check('po dotarciu: bez running/walking, poza nie run', !t.after.running && !t.after.walking && !/pose-run/.test(t.after.pose), t.after);

  const out = await T(async () => {
    const api = window.PetCompanionApi, el = document.getElementById('petCompanion');
    const ok = await api.runTo(-40, api.rect().y, { allowOutside: true, face: 'right' });
    return { ok, left: el.style.left, flipped: el.classList.contains('pet-companion--flipped') };
  });
  L.check('allowOutside: pozycja poza obszarem (-40 px)', out.ok && out.left === '-40px', out);
  L.check('face po dotarciu: right = nieodwrócony', out.flipped === false, out);
  await T(() => { window.dispatchEvent(new Event('resize')); window.dispatchEvent(new Event('scroll')); });
  await page.waitForTimeout(700);
  L.check('resize/scroll nie wciągają zajętego pupila do obszaru', (await T(() => document.getElementById('petCompanion').style.left)) === '-40px');
  const clamped = await T(async () => ({ ok: await window.PetCompanionApi.runTo(-40, window.PetCompanionApi.rect().y), left: parseFloat(document.getElementById('petCompanion').style.left) }));
  L.check('bez allowOutside cel jest w obszarze (>= 8 px)', clamped.left >= 8, clamped);

  const brk = await T(async () => {
    const api = window.PetCompanionApi, r = api.rect();
    const p = api.runTo(r.x < 600 ? r.x + 500 : r.x - 500, r.y);
    await new Promise((res) => setTimeout(res, 200));
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
    const ok = await p;
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
    return { ok, broke: window.__broke };
  });
  L.check('ukrycie karty przerywa runTo (false) i woła onBreak raz', brk.ok === false && brk.broke === 1, brk);
  L.check('po przerwaniu claim jest zwolniony (--claimed zdjęte)', (await T(() => document.getElementById('petCompanion').classList.contains('pet-companion--claimed'))) === false);

  const rel = await T(() => { window.__broke = 0; const r = window.PetCompanionApi.claim(() => { window.__broke++; }); const was = typeof r; r(); return { was, broke: window.__broke }; });
  L.check('release() nie woła onBreak', rel.was === 'function' && rel.broke === 0, rel);
  const leftA = await T(() => document.getElementById('petCompanion').style.left + '|' + document.getElementById('petCompanion').style.top);
  const moved = await page.waitForFunction((l) => (document.getElementById('petCompanion').style.left + '|' + document.getElementById('petCompanion').style.top) !== l, leftA, { timeout: 16000 }).then(() => true, () => false);
  L.check('po release spacer rusza dalej', moved);
  await browser.close();
  L.finish(errors);
})();
```

Zrestartuj serwer i uruchom: `cd $JOKES && node api_check.js`
Expected: FAIL „API istnieje w trybie walk".

- [ ] **Step 2: Implementacja w `static/js/components/pet-companion.js`**

1. Po `var running = false;` dodaj:
```js
    var claim = null;                  // zajęty przez żart: {onBreak} (spec v3.2 §4)
    var arriveHook = null;             // runTo: wołany po dotarciu (true) albo przerwaniu (false)
```
2. `walkAllowed`: zastąp całość:
```js
    function walkAllowed() {
        return mode === 'walk' && !!pet && !pet.asleep && !reducedMotion() && !el.hidden && !held && !claim &&
            document.visibilityState !== 'hidden';
    }
```
3. `updateWalk`: po `syncPose();` dodaj `if (claim) return;                 // zajęty przez żart — ruchem steruje claim`.
4. `keepInArea`: `if (!isFree() || held || el.hidden || !pos) return;` → `if (!isFree() || held || claim || el.hidden || !pos) return;`.
5. `checkStandingSpot`: `if (mode !== 'walk' || el.hidden || held || walking || !pos || !pet) return;` → `if (mode !== 'walk' || el.hidden || held || claim || walking || !pos || !pet) return;`.
6. `arrived()`: po `savePos();` a przed `if (!walkAllowed()) return;` dodaj:
```js
        var hook = arriveHook;               // runTo: cel żartu osiągnięty — dalszy ciąg w module żartów
        arriveHook = null;
        if (hook) { hook(true); return; }
```
7. `stopWalk()`: na końcu funkcji (po `el.style.removeProperty('--pet-companion-walk');`) dodaj:
```js
        var hook = arriveHook;               // przerwany marsz/bieg: runTo kończy się false
        arriveHook = null;
        if (hook) hook(false);
```
8. `hide()`: pierwszą linią funkcji dodaj `breakClaim();`.
9. `apply()`: między `var samePet = ...;` a `pet = p;` dodaj `if (claim && (!samePet || p.asleep)) breakClaim();   // inny towarzysz albo zasnął — żart się kończy`.
10. `showBubble`: pierwszą linią funkcji dodaj `if (claim) return;                   // żart trwa — dymki czekają`.
11. Handler `visibilitychange`: w gałęzi `hidden`, przed `cancelDrag();`, dodaj `breakClaim();`.
12. Przed sekcją `// --- nie zasłaniaj CTA ---` wstaw nową sekcję:

```js
    // --- API dla żartów (spec v3.2 §4) ----------------------------------------------------------
    // Moduł żartów (pet-jokes.js) „zajmuje” towarzysza: spacer i dymki stoją, ruchem steruje runTo.

    function setClaimed(on) { el.classList.toggle('pet-companion--claimed', on); }

    function apiReady() {
        return mode === 'walk' && !claim && !!pet && !!rig && !pet.asleep && !held && !el.hidden &&
            bubble.hidden && document.visibilityState !== 'hidden' && !reducedMotion();
    }

    function rectNow() {
        var r = el.getBoundingClientRect();
        return { x: r.left, y: r.top, w: r.width, h: r.height };
    }

    function faceDir(dir) { el.classList.toggle('pet-companion--flipped', dir === 'left'); }

    /** Zajmuje pupila (null, gdy zajęty albo nie pora); zwraca release(). onBreak: chwycenie, sen, ukrycie. */
    function claimPet(onBreak) {
        if (!apiReady()) return null;
        var c = { onBreak: onBreak || null };
        claim = c;
        setClaimed(true);
        stopWalk();
        clearTimeout(timers.walk);
        timers.walk = 0;
        sitting = false;
        syncPose();
        return function release() {
            if (claim !== c) return;
            claim = null;
            setClaimed(false);
            stopWalk();
            if (walkAllowed()) scheduleWalk(rand(PAUSE_MIN, PAUSE_MAX));
        };
    }

    /** Przerwanie przez towarzysza (sen, ukrycie, inny pupil, karta w tle): runTo kończy się false, onBreak woła się raz. */
    function breakClaim() {
        if (!claim) return;
        var c = claim;
        claim = null;
        setClaimed(false);
        stopWalk();
        if (c.onBreak) {
            try { c.onBreak(); } catch (e) { /* żart sprząta po sobie sam */ }
        }
        updateWalk();
    }

    /** Biegnie do (x, y) — tylko podczas claim. allowOutside zdejmuje ograniczenie do obszaru spaceru. */
    function runTo(x, y, opts) {
        if (!claim || !pos || el.hidden) return Promise.resolve(false);
        opts = opts || {};
        stopWalk();
        var target = opts.allowOutside ? { x: Math.round(x), y: Math.round(y) } : clampTo(area(), { x: x, y: y });
        var dist = Math.sqrt(Math.pow(target.x - pos.x, 2) + Math.pow(target.y - pos.y, 2));
        if (dist < 2) {
            if (opts.face) faceDir(opts.face);
            return Promise.resolve(true);
        }
        return new Promise(function (resolve) {
            arriveHook = function (ok) {
                if (ok && opts.face) faceDir(opts.face);
                resolve(ok);
            };
            startMove(target, true);
        });
    }
```

13. W `boot()` po wczesnym `return` dla `#petsApp`, a przed `window.PetsState.onChange(`, dodaj:
```js
        if (mode === 'walk') {
            window.PetCompanionApi = { ready: apiReady, rect: rectNow, claim: claimPet, runTo: runTo, face: faceDir };
        }
```

`static/css/components/pet-companion.css`: po regule `.pet-companion > * { pointer-events: auto; }` dodaj:

```css

/* Zajęty przez żart (spec v3.2 §4): pupil nie reaguje na klik/chwyt do końca żartu */
.pet-companion--claimed > .pet-companion__hit { pointer-events: none; }
```

- [ ] **Step 3: Uruchom skrypty i potwierdź**

Run: `node --check static/js/components/pet-companion.js && cd $JOKES && node api_check.js && node run_gait.js`
Expected: `0 fail` w obu (regresja biegu).

- [ ] **Step 4: Commit**

```bash
git add static/js/components/pet-companion.js static/css/components/pet-companion.css
git commit -m "feat(pupile): API towarzysza dla zartow (claim, runTo, rect, face)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Moduł żartów: harmonogram i wychylenie z obrazkiem

**Files:**
- Create: `static/js/components/pet-jokes.js`
- Create: `static/css/components/pet-jokes.css`
- Modify: `templates/components/pet_companion.html` (ładowanie tylko w trybie `walk`)
- Modify: `tests/test_pets_widget_companion.py` (test ładowania)
- Modify (lokalnie, nie commitujemy): `docs/dev/dev_pets_preview.py` (seed 3 obrazków)

**Interfaces:**
- Consumes: `PetCompanionApi` (Zadanie 6), `PetsState.current.companion.jokes`, `PetsState.onChange`, `PetsApi.get('/wychylenia')`.
- Produces: `window.PetJokes = { trigger(name, opts?) -> Promise<boolean>, active() -> 'peek'|'cursor'|null, cancel() }` (`opts.edge: 'left'|'right'|'bottom'` tylko do testów); blok „kradzież kursora" z funkcjami `cursorAvailable()` i `startCursor()` oraz zmienną `mouse` jest w tym zadaniu **zaślepką zwracającą `false`**, którą Zadanie 8 zastępuje.

- [ ] **Step 1: Napisz testy, które muszą na początku paść**

Do `tests/test_pets_widget_companion.py` dopisz (używa istniejących fixtur i helpera `_wlacz`):

```python
def test_towarzysz_laduje_zarty_tylko_w_trybie_walk(client, login, make_user, db, strona_sprzedazy):
    """Spec v3.2 §5: żarty tylko w panelu klienta; strony ofert (tryb sit) ich nie ładują."""
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    panel = client.get('/client/dashboard').data.decode()
    assert 'css/components/pet-jokes.css' in panel and 'js/components/pet-jokes.js' in panel
    assert panel.index('js/components/pet-companion.js') < panel.index('js/components/pet-jokes.js')
    oferta = client.get(f'/offer/{strona_sprzedazy.token}/thank-you').data.decode()
    assert 'js/components/pet-companion.js' in oferta and 'pet-jokes' not in oferta
```

Seed obrazków w podglądzie: w `docs/dev/dev_pets_preview.py`, w `zasiej()`, tuż po linii `print(f'oferta: /offer/{oferta.token}  (thank-you: /offer/{oferta.token}/thank-you)')`, dodaj:

```python
        # Obrazki wychylania (żarty towarzysza, spec v3.2): 3 kolorowe kółka z przezroczystością
        import io
        from PIL import Image, ImageDraw
        from werkzeug.datastructures import FileStorage
        from modules.pets import peek_images
        from modules.pets.models import PetPeekImage
        for nazwa, kolor in (('Gwiazdka', (255, 200, 60, 255)), ('Serduszko', (245, 87, 108, 255)), ('Księżyc', (150, 160, 255, 255))):
            buf = io.BytesIO()
            obraz = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
            ImageDraw.Draw(obraz).ellipse((20, 20, 180, 180), fill=kolor)
            obraz.save(buf, 'PNG')
            buf.seek(0)
            nazwa_pliku = peek_images.save_upload(FileStorage(stream=buf, filename=nazwa + '.png'))
            db.session.add(PetPeekImage(filename=nazwa_pliku, label=nazwa))
        db.session.commit()
```

Zapisz `$JOKES/peek_check.js`:

```js
const L = require('./lib');

async function appeared(page) { return L.until(page, () => !!document.querySelector('.pet-jokes__peek'), 20000, 500); }

(async () => {
  // --- A: wychylenie z prawej krawędzi, zamykanie, Esc, fokus, brak obrazków ----------------
  let ctx = await L.open({ clock: true, seed: 11 });
  let { browser, page, errors } = ctx;
  await L.waitCompanion(page);
  await L.pause(page);
  const T = (fn, ...a) => page.evaluate(fn, ...a);
  L.check('PetJokes istnieje', await T(() => !!window.PetJokes));
  L.check('flaga żartów w stanie = true', await T(() => window.PetsState.current.companion.jokes === true));

  L.check('trigger(peek, right) → true', (await T(() => window.PetJokes.trigger('peek', { edge: 'right' }))) === true);
  L.check('active() = peek', (await T(() => window.PetJokes.active())) === 'peek');
  L.check('obrazek się wychyla', await appeared(page));
  const box = await T(() => {
    const b = document.querySelector('.pet-jokes__peek'); if (!b) return null;
    const x = b.querySelector('.pet-jokes__close').getBoundingClientRect();
    return { src: b.querySelector('img').getAttribute('src'), alt: b.querySelector('img').getAttribute('alt'),
      label: b.querySelector('.pet-jokes__close').getAttribute('aria-label'), w: x.width, h: x.height,
      left: parseFloat(document.getElementById('petCompanion').style.left), vw: document.documentElement.clientWidth };
  });
  L.check('obrazek z /static/uploads/pet_peeks/…webp', box && /^\/static\/uploads\/pet_peeks\/.+\.webp$/.test(box.src), box);
  L.check('alt pusty (dekoracja)', box && box.alt === '');
  L.check('„x": aria-label', box && box.label === 'Zamknij obrazek');
  L.check('„x": cel >= 44 px', box && box.w >= 44 && box.h >= 44, box);
  L.check('pupil stoi częściowo poza prawą krawędzią', box && box.left + 72 > box.vw, box);

  // fokus na „x" wstrzymuje chowanie
  await T(() => document.querySelector('.pet-jokes__close').focus());
  await L.run(page, 8000, 1000);
  L.check('fokus na „x" wstrzymuje chowanie (po 8 s nadal jest)', await T(() => !!document.querySelector('.pet-jokes__peek')));
  await T(() => document.querySelector('.pet-jokes__close').blur());
  await L.run(page, 1500, 500);
  L.check('po utracie fokusu obrazek znika', await T(() => !document.querySelector('.pet-jokes__peek')));
  await L.until(page, () => window.PetJokes.active() === null, 15000, 500);
  L.check('po żarcie active() = null', (await T(() => window.PetJokes.active())) === null);

  // „x" zapisuje zamknięcie i obrazek nie wraca
  const closedIds = [];
  for (const sposob of ['x', 'esc', 'x']) {
    const ok = await T(() => window.PetJokes.trigger('peek', { edge: 'right' }));
    L.check(`trigger(peek) przed zamknięciem (${sposob}) → true`, ok === true);
    await appeared(page);
    if (sposob === 'x') await T(() => document.querySelector('.pet-jokes__close').click());
    else await T(() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    L.check(`po zamknięciu (${sposob}) obrazek znika od razu`, await T(() => !document.querySelector('.pet-jokes__peek')));
    await L.until(page, () => window.PetJokes.active() === null, 15000, 500);
  }
  const zapisane = await T(() => Object.keys(localStorage).filter((k) => k.indexOf('pets_peek_closed_') === 0));
  L.check('3 zamknięte obrazki zapisane w localStorage', zapisane.length === 3, zapisane);
  L.check('wszystkie zamknięte → trigger(peek) = false', (await T(() => window.PetJokes.trigger('peek'))) === false);
  await browser.close();
  L.finish(errors.length ? errors : null);
})().catch((e) => { console.error(e); process.exit(2); });
```

oraz drugi plik `$JOKES/peek_gates.js` (bramki, scheduler, lewa krawędź):

```js
const L = require('./lib');
(async () => {
  // --- jokes=false ---
  {
    const { browser, page, errors } = await L.open({ patchState: (s) => { s.companion.jokes = false; } });
    await L.waitCompanion(page);
    L.check('jokes=false → trigger(peek) = false', (await page.evaluate(() => window.PetJokes.trigger('peek'))) === false);
    L.check('jokes=false → brak obrazka', (await page.locator('.pet-jokes__peek').count()) === 0);
    await browser.close();
    if (errors.length) L.check('brak błędów strony (jokes=false)', false, errors);
  }
  // --- reduced motion ---
  {
    const { browser, page } = await L.open({ reducedMotion: 'reduce' });
    await L.waitCompanion(page);
    L.check('reduced-motion → trigger(peek) = false', (await page.evaluate(() => window.PetJokes.trigger('peek'))) === false);
    await browser.close();
  }
  // --- bramki sytuacyjne: modal, pole tekstowe, pasek zakupowy ---
  {
    const { browser, page } = await L.open({});
    await L.waitCompanion(page);
    await page.waitForFunction(() => window.PetCompanionApi.ready(), null, { timeout: 10000 });
    const T = (fn) => page.evaluate(fn);
    await T(() => { const d = document.createElement('div'); d.id = '__modal'; d.className = 'modal-overlay active'; d.style.cssText = 'position:fixed;inset:0;'; document.body.appendChild(d); });
    L.check('otwarty modal → false', (await T(() => window.PetJokes.trigger('peek'))) === false);
    await T(() => document.getElementById('__modal').remove());
    await T(() => { const i = document.createElement('input'); i.id = '__in'; document.body.appendChild(i); i.focus(); });
    L.check('fokus w polu tekstowym → false', (await T(() => window.PetJokes.trigger('peek'))) === false);
    await T(() => document.getElementById('__in').remove());
    await T(() => { const b = document.createElement('div'); b.id = '__bar'; b.className = 'checkout-bottom-bar'; b.style.cssText = 'position:fixed;bottom:0;left:0;width:100px;height:40px;'; document.body.appendChild(b); });
    L.check('pasek zakupowy → false', (await T(() => window.PetJokes.trigger('peek'))) === false);
    await T(() => document.getElementById('__bar').remove());
    L.check('bez blokad → true', (await T(() => window.PetJokes.trigger('peek'))) === true);
    await T(() => window.PetJokes.cancel());
    L.check('cancel() kończy żart', (await T(() => window.PetJokes.active())) === null);
    await browser.close();
  }
  // --- scheduler: pierwszy żart po >= 90 s czasu wirtualnego ---
  {
    const { browser, page, errors } = await L.open({ clock: true, seed: 5 });
    await L.waitCompanion(page);
    await L.pause(page);
    let first = null;
    for (let t = 0; t < 200 && first === null; t += 5) {
      await L.run(page, 5000, 1000);
      const a = await page.evaluate(() => window.PetJokes.active());
      if (a) first = t + 5;
    }
    L.check('żaden żart przed ~85 s', first === null || first >= 85, first);
    L.check('pierwszy żart ruszył w ciągu 200 s', first !== null, first);
    await browser.close();
    if (errors.length) L.check('brak błędów strony (scheduler)', false, errors);
  }
  // --- lewa krawędź: pupil schowany ZA sidebarem, obrazek widoczny (czas rzeczywisty) ---
  {
    const { browser, page, errors } = await L.open({});
    await L.waitCompanion(page);
    await page.waitForFunction(() => window.PetCompanionApi.ready(), null, { timeout: 10000 });
    L.check('trigger(peek, left) → true', (await page.evaluate(() => window.PetJokes.trigger('peek', { edge: 'left' }))) === true);
    const ok = await page.waitForFunction(() => !!document.querySelector('.pet-jokes__peek'), null, { timeout: 25000 }).then(() => true, () => false);
    L.check('obrazek wychylił się z lewej', ok);
    await page.waitForTimeout(400);
    const geo = await page.evaluate(() => {
      const wl = document.querySelector('.main-wrapper').getBoundingClientRect().left;
      const host = document.getElementById('petCompanion').getBoundingClientRect();
      const probe = document.elementFromPoint(Math.max(1, wl - 8), host.top + host.height / 2);
      const img = document.querySelector('.pet-jokes__peek img').getBoundingClientRect();
      return { wl, hostLeft: host.left, underSidebar: !!(probe && probe.closest('.sidebar')), imgLeft: img.left };
    });
    L.check('lewy brzeg pupila jest pod sidebarem (zasłonięty)', geo.hostLeft < geo.wl && geo.underSidebar, geo);
    L.check('obrazek leży poza sidebarem (widoczny)', geo.imgLeft >= geo.wl - 1, geo);
    await page.screenshot({ path: L.DIR + '/shots/peek-left.png' });
    await browser.close();
    if (errors.length) L.check('brak błędów strony (lewa krawędź)', false, errors);
  }
  L.finish(null);
})().catch((e) => { console.error(e); process.exit(2); });
```

Zrestartuj serwer podglądu (nowy seed) i uruchom:
Run: `venv/bin/python -m pytest tests/test_pets_widget_companion.py -q ; cd $JOKES && node peek_check.js`
Expected: pytest FAIL (brak `pet-jokes` w szablonie), skrypt FAIL (`PetJokes` nie istnieje).

- [ ] **Step 2: Szablon**

`templates/components/pet_companion.html`: po linii `<script src="{{ url_for('static', filename='js/components/pet-companion.js') }}"></script>` dodaj:

```jinja
{% if (companion_mode | default('walk')) == 'walk' %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/components/pet-jokes.css') }}">
<script src="{{ url_for('static', filename='js/components/pet-jokes.js') }}"></script>
{% endif %}
```

- [ ] **Step 3: CSS `static/css/components/pet-jokes.css`**

```css
/* Żarty towarzysza (spec v3.2 §5). Elementy żartów mają stałe kolory z obrysem (czytelne w obu motywach);
   przycisk „x” ma wariant dark. */

/* --- Wychylenie z obrazkiem: obrazek leży przy pyszczku pupila (place: right | left | up) --- */
.pet-jokes__peek {
    position: absolute;
    top: 4px;
    width: 72px;
    height: 72px;
    z-index: 3;
    animation: pet-jokes-pop 0.35s cubic-bezier(0.2, 0.9, 0.3, 1.3) both;
}

.pet-jokes__peek--right { left: 56%; }
.pet-jokes__peek--left { right: 56%; }
.pet-jokes__peek--up { left: 0; top: -58px; }

.pet-jokes__img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: contain;
    filter: drop-shadow(0 3px 6px rgba(0, 0, 0, 0.35));
    transform-origin: 50% 80%;
    animation: pet-jokes-wobble 1.6s ease-in-out 0.4s infinite;
    user-select: none;
    -webkit-user-drag: none;
}

/* „x”: cel dotyku 44 px, widoczne kółko 22 px */
.pet-jokes__close {
    position: absolute;
    top: -16px;
    right: -16px;
    width: 44px;
    height: 44px;
    padding: 0;
    border: 0;
    background: transparent;
    cursor: pointer;
}

.pet-jokes__close::before {
    content: '\00d7';
    position: absolute;
    top: 11px;
    left: 11px;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: #ffffff;
    border: 1px solid #d0d0d8;
    color: #333333;
    font: 700 16px/20px system-ui, sans-serif;
    text-align: center;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.25);
}

.pet-jokes__close:focus-visible::before { outline: 2px solid #7c3aed; outline-offset: 2px; }

[data-theme="dark"] .pet-jokes__close::before {
    background: rgba(30, 27, 60, 0.95);
    border-color: rgba(240, 147, 251, 0.45);
    color: #ffffff;
}

[data-theme="dark"] .pet-jokes__close:focus-visible::before { outline-color: #f093fb; }

@keyframes pet-jokes-pop {
    from { opacity: 0; transform: scale(0.4) rotate(-14deg); }
    to { opacity: 1; transform: scale(1) rotate(0); }
}

@keyframes pet-jokes-wobble {
    0%, 100% { transform: rotate(-4deg); }
    50% { transform: rotate(4deg); }
}
```

- [ ] **Step 4: Moduł `static/js/components/pet-jokes.js`**

```js
/**
 * Żarty towarzysza (spec v3.2 §5) — rzadkie niespodzianki pupila w panelu klienta.
 *
 * Wymaga: window.PetCompanionApi (pet-companion.js, tylko tryb walk), window.PetsState/PetsApi (pets-core.js).
 * Żartów nie wymieniamy w żadnym ekranie użytkownika (element zaskoczenia): jeden przełącznik w warsztacie
 * wyłącza wszystkie (state.companion.jokes); lista żartów żyje tylko tu i w specu.
 *
 * Harmonogram: pierwszy żart najwcześniej 90 s po wejściu, potem co 2–5 min; czas „następnego” w sessionStorage,
 * więc przechodzenie między stronami go nie zeruje. Jeden żart naraz, zawsze na „zajętym” towarzyszu
 * (PetCompanionApi.claim) — chwycenie/sen/ukrycie przerywa żart i sprząta po nim.
 *
 * window.PetJokes: trigger(name, opts) -> Promise<boolean> ('peek' | 'cursor'; opts.edge tylko do testów),
 * active() -> nazwa trwającego żartu albo null, cancel().
 */
(function () {
    'use strict';

    var host = document.getElementById('petCompanion');
    var api = window.PetCompanionApi;
    if (!host || !api || !window.PetsState || !window.PetsApi || window.PetJokes) return;

    var userId = host.getAttribute('data-user-id');
    var html = document.documentElement;

    var FIRST_MS = 90 * 1000;                        // pierwszy żart najwcześniej po 90 s od wejścia
    var GAP_MIN = 120 * 1000, GAP_MAX = 300 * 1000;  // kolejne co 2–5 min
    var RETRY_MS = 30 * 1000;                        // brak warunków / brak żartu do wyboru — próba za 30 s
    var CHECK_MS = 5000;                             // jak często harmonogram sprawdza, czy czas na żart
    var W_PEEK = 0.7;                                // waga wychylenia (kursor dostaje resztę)
    var PEEK_SHOW_MS = 6000;
    var CLOSED_TTL_MS = 7 * 24 * 3600 * 1000;        // „x”: obrazek nie wraca przez 7 dni
    var LIST_TTL_MS = 5 * 60 * 1000;
    var BLOCKERS = '.modal-overlay.active, .modal-centered.show, .pwa-bottom-sheet.open, .cart-sidebar.mobile-open, ' +
        '.cart-mobile-overlay.active, [role="dialog"][aria-modal="true"]';
    var SHOP_BARS = '.checkout-bottom-bar, .product-sticky-bar, .floating-actions, .cart-sidebar .cart-footer';
    var TEXT_FIELDS = 'input, textarea, select, [contenteditable=""], [contenteditable="true"]';
    var NO_CURSOR = 'pet-jokes--no-cursor';

    var nextKey = 'pets_jokes_next_' + userId;
    var lastPeekKey = 'pets_jokes_lastpeek_' + userId;
    var listKey = 'pets_jokes_list_' + userId;
    var closedPrefix = 'pets_peek_closed_';

    var current = null;                              // trwający żart {name, cancel}
    var listPromise = null, listAt = 0;

    // --- pomocnicze -----------------------------------------------------------------------------

    function rand(min, max) { return min + Math.random() * (max - min); }

    function ssGet(key) { try { return sessionStorage.getItem(key); } catch (e) { return null; } }
    function ssSet(key, v) { try { sessionStorage.setItem(key, v); } catch (e) { /* prywatne okno */ } }
    function lsGet(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
    function lsSet(key, v) { try { localStorage.setItem(key, v); } catch (e) { /* prywatne okno */ } }

    function reduced() {
        return !!(window.PetRig && window.PetRig.reducedMotion && window.PetRig.reducedMotion());
    }

    function anyShown(selector) {
        var nodes = document.querySelectorAll(selector);
        for (var i = 0; i < nodes.length; i++) if (nodes[i].getClientRects().length > 0) return true;
        return false;
    }

    function vw() { return document.documentElement.clientWidth || window.innerWidth; }

    function jokesFlag() {
        var s = window.PetsState.current;
        return !!(s && s.companion && s.companion.jokes === true);
    }

    function blocked() {
        if (anyShown(BLOCKERS) || anyShown(SHOP_BARS)) return true;
        if (document.body && document.body.style.overflow === 'hidden') return true;   // scroll-lock = otwarta nakładka
        var a = document.activeElement;
        return !!(a && a !== document.body && a.matches && a.matches(TEXT_FIELDS));
    }

    function canStart() {
        return !current && jokesFlag() && !reduced() && document.visibilityState === 'visible' && api.ready() && !blocked();
    }

    // --- harmonogram ----------------------------------------------------------------------------

    function dueAt() {
        var raw = parseInt(ssGet(nextKey), 10);
        if (!raw) {
            raw = Date.now() + FIRST_MS;
            ssSet(nextKey, String(raw));
        }
        return raw;
    }

    function scheduleNext(ms) {
        ssSet(nextKey, String(Date.now() + (ms != null ? ms : rand(GAP_MIN, GAP_MAX))));
    }

    function tick() {
        setTimeout(tick, CHECK_MS);
        if (Date.now() < dueAt() || !canStart()) return;
        scheduleNext(RETRY_MS);          // chroni przed podwójnym startem na czas decyzji; po żarcie nadpisze odstęp
        decide(null, {});
    }

    /** Wybiera i uruchamia żart. forced = 'peek' | 'cursor' | null. Zwraca Promise<boolean> (czy ruszył). */
    function decide(forced, opts) {
        return loadImages().then(function (list) {
            if (!canStart()) return false;                   // sytuacja zmieniła się w trakcie pobierania listy
            var imgs = candidates(list);
            var peekOk = imgs.length > 0;
            var cursorOk = cursorAvailable();
            var kind = null;
            if (forced === 'peek') kind = peekOk ? 'peek' : null;
            else if (forced === 'cursor') kind = cursorOk ? 'cursor' : null;
            else if (peekOk && cursorOk) kind = Math.random() < W_PEEK ? 'peek' : 'cursor';
            else kind = peekOk ? 'peek' : (cursorOk ? 'cursor' : null);
            if (!kind) return false;
            return kind === 'peek' ? startPeek(imgs, opts || {}) : startCursor();
        });
    }

    // --- lista obrazków -------------------------------------------------------------------------

    function loadImages() {
        if (listPromise && Date.now() - listAt < LIST_TTL_MS) return listPromise;
        var cached = null;
        try { cached = JSON.parse(ssGet(listKey) || 'null'); } catch (e) { cached = null; }
        if (cached && Array.isArray(cached.images) && Date.now() - cached.t < LIST_TTL_MS) {
            listAt = cached.t;
            listPromise = Promise.resolve(cached.images);
            return listPromise;
        }
        listAt = Date.now();
        listPromise = window.PetsApi.get('/wychylenia').then(function (res) {
            var images = (res && Array.isArray(res.images)) ? res.images : [];
            ssSet(listKey, JSON.stringify({ t: Date.now(), images: images }));
            return images;
        }, function () { return []; });
        return listPromise;
    }

    function isClosed(id) {
        var t = parseInt(lsGet(closedPrefix + id), 10);
        return !!t && Date.now() - t < CLOSED_TTL_MS;
    }

    function candidates(list) {
        return list.filter(function (i) {
            return i && i.id != null && typeof i.url === 'string' && i.url.indexOf('/static/') === 0 && !isClosed(i.id);
        });
    }

    function pickImage(list) {
        var last = ssGet(lastPeekKey);
        var rest = list.filter(function (i) { return String(i.id) !== last; });
        var pool = rest.length ? rest : list;
        return pool[Math.floor(Math.random() * pool.length)];
    }

    // --- żart: wychylenie z obrazkiem -----------------------------------------------------------

    /** Cel wychylenia (lewy górny róg pupila): lewa — pod sidebar, prawa/dolna — poza okno. */
    function peekGeometry(forcedEdge) {
        var r = api.rect();
        var w = vw(), h = window.innerHeight;
        var wrap = document.querySelector('.main-wrapper');
        var wl = wrap ? Math.max(0, wrap.getBoundingClientRect().left) : 0;
        var edges = ['right', 'bottom'];
        if (wl >= 40) edges.push('left');                    // sidebar widoczny — wychylenie spod niego
        var edge = edges.indexOf(forcedEdge) >= 0 ? forcedEdge : edges[Math.floor(Math.random() * edges.length)];
        var minY = 96, maxY = Math.max(minY, h - r.h - 96);
        var y = Math.round(rand(minY, maxY));
        if (edge === 'left') {
            return { edge: edge, face: 'right', place: 'right', x: Math.round(wl - r.w * 0.55), y: y, back: { x: wl + 140, y: y } };
        }
        if (edge === 'right') {
            return { edge: edge, face: 'left', place: 'left', x: Math.round(w - r.w * 0.45), y: y, back: { x: w - 220, y: y } };
        }
        var bx = Math.round(rand(wl + 60, Math.max(wl + 61, w - r.w - 60)));
        return { edge: edge, face: Math.random() < 0.5 ? 'left' : 'right', place: 'up', x: bx, y: Math.round(h - r.h * 0.5),
            back: { x: bx, y: h - 240 } };
    }

    function buildPeek(image, place) {
        var box = document.createElement('div');
        box.className = 'pet-jokes__peek pet-jokes__peek--' + place;
        var pic = document.createElement('img');
        pic.className = 'pet-jokes__img';
        pic.alt = '';
        pic.draggable = false;
        pic.src = image.url;
        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'pet-jokes__close';
        close.setAttribute('aria-label', 'Zamknij obrazek');
        box.appendChild(pic);
        box.appendChild(close);
        host.appendChild(box);
        return box;
    }

    function startPeek(imgs, opts) {
        var image = pickImage(imgs);
        var geo = peekGeometry(opts.edge);
        var box = null, ended = false, hideTimer = 0, onKey = null;
        var job = { name: 'peek', cancel: function () { stop(); } };

        function removeBox() {
            if (box && box.parentNode) box.parentNode.removeChild(box);
            box = null;
        }

        function unlistenKey() {
            if (onKey) document.removeEventListener('keydown', onKey, true);
            onKey = null;
        }

        // Idempotentne sprzątanie po żarcie: wołane po spokojnym wyjściu i po każdym przerwaniu
        function stop() {
            if (ended) return;
            ended = true;
            clearTimeout(hideTimer);
            unlistenKey();
            removeBox();
            if (current === job) { current = null; scheduleNext(); }
            if (release) release();
        }

        // Spokojne wyjście: chowa obrazek, wraca w głąb ekranu, dopiero potem oddaje towarzysza
        function leave() {
            if (ended) return;
            clearTimeout(hideTimer);
            unlistenKey();
            removeBox();
            api.runTo(geo.back.x, geo.back.y).then(function () { stop(); });
        }

        function close() {
            lsSet(closedPrefix + image.id, String(Date.now()));
            leave();
        }

        function tryHide() {
            hideTimer = 0;
            if (ended) return;
            if (box && (box.matches(':hover') || box.contains(document.activeElement))) {
                hideTimer = setTimeout(tryHide, 500);        // fokus/kursor nad obrazkiem — nie znikamy spod ręki
                return;
            }
            leave();
        }

        var release = api.claim(function () { stop(); });   // onBreak: chwycenie, sen, ukrycie
        if (!release) return false;
        current = job;
        ssSet(lastPeekKey, String(image.id));

        api.runTo(geo.x, geo.y, { allowOutside: true, face: geo.face }).then(function (ok) {
            if (!ok || ended) return;                        // przerwane — onBreak już posprzątał
            box = buildPeek(image, geo.place);
            box.querySelector('.pet-jokes__close').addEventListener('click', close);
            onKey = function (e) {
                if (e.key === 'Escape') { e.stopPropagation(); close(); }
            };
            document.addEventListener('keydown', onKey, true);
            hideTimer = setTimeout(tryHide, PEEK_SHOW_MS);
        });
        return true;
    }

    // --- kradzież kursora (Zadanie 8 zastępuje ten blok) ----------------------------------------
    var mouse = null;
    function cursorAvailable() { return false; }
    function startCursor() { return false; }
    // --- koniec bloku kursora --------------------------------------------------------------------

    // --- start ----------------------------------------------------------------------------------

    function trigger(name, opts) {
        if (name !== 'peek' && name !== 'cursor') return Promise.resolve(false);
        return decide(name, opts || {});
    }

    function cancel() { if (current) current.cancel(); }

    window.PetJokes = {
        trigger: trigger,
        active: function () { return current ? current.name : null; },
        cancel: cancel
    };

    // Wyłączenie żartów (przełącznik/admin) kończy trwający od razu
    window.PetsState.onChange(function () {
        if (current && !jokesFlag()) current.cancel();
    });
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') cancel();
    });

    setTimeout(tick, CHECK_MS);
})();
```

- [ ] **Step 5: Uruchom testy i potwierdź**

Run: `venv/bin/python -m pytest tests/test_pets_widget_companion.py -q && node --check static/js/components/pet-jokes.js && cd $JOKES && node peek_check.js && node peek_gates.js`
Expected: pytest PASS; oba skrypty `0 fail`. Obejrzyj `$JOKES/shots/peek-left.png` (Read): pupil wychylony spod sidebara z obrazkiem w pyszczku. Jeśli położenie obrazka (`top`, `left: 56%`) wygląda źle, dostrój wartości w `.pet-jokes__peek*` i powtórz zrzut. Zrób też zrzuty w motywie ciemnym (`L.open({dark: true})`) i dla `edge: 'bottom'` oraz na telefonie (`w: 375, h: 812, mobile: true`) i oceń czytelność „x".

- [ ] **Step 6: Commit**

```bash
git add static/js/components/pet-jokes.js static/css/components/pet-jokes.css templates/components/pet_companion.html tests/test_pets_widget_companion.py
git commit -m "feat(pupile): zarty - harmonogram i wychylenie z obrazkiem

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Żart: kradzież kursora

**Files:**
- Modify: `static/js/components/pet-jokes.js` (zastąpienie bloku-zaślepki)
- Modify: `static/css/components/pet-jokes.css`

**Interfaces:**
- Consumes: `PetCompanionApi.claim/runTo/rect` (Zadanie 6), harmonogram i `current`/`scheduleNext`/`decide` (Zadanie 7).
- Produces: działające `cursorAvailable()` i `startCursor()`; klasa `html.pet-jokes--no-cursor`; elementy `.pet-jokes__shield` (z-index 1190) i `.pet-jokes__cursor` (1191).

- [ ] **Step 1: Napisz skrypt, który ma paść**

Zapisz `$JOKES/cursor_check.js`:

```js
const L = require('./lib');

const noCursor = () => document.documentElement.classList.contains('pet-jokes--no-cursor');
const leftovers = () => ({ cls: document.documentElement.classList.contains('pet-jokes--no-cursor'),
  shield: !!document.querySelector('.pet-jokes__shield'), sprite: !!document.querySelector('.pet-jokes__cursor'),
  cursor: getComputedStyle(document.body).cursor, active: window.PetJokes.active() });

async function startujZartu(page, patchRunTo) {
  await L.waitCompanion(page);
  await page.waitForFunction(() => window.PetCompanionApi.ready(), null, { timeout: 10000 });
  await page.mouse.move(700, 500);
  await page.mouse.move(712, 507);
  if (patchRunTo) {
    await page.evaluate(() => { const api = window.PetCompanionApi; let n = 0; api.runTo = function () { n++; return n === 1 ? Promise.resolve(true) : new Promise(() => {}); }; });
  }
  const ok = await page.evaluate(() => window.PetJokes.trigger('cursor'));
  const engaged = await page.waitForFunction(() => document.documentElement.classList.contains('pet-jokes--no-cursor'), null, { timeout: 25000 }).then(() => true, () => false);
  return { ok, engaged };
}

(async () => {
  // --- A: ścieżka szczęśliwa + limit ---
  {
    const { browser, page, errors } = await L.open({});
    const { ok, engaged } = await startujZartu(page, false);
    L.check('trigger(cursor) → true', ok === true);
    L.check('kursor schowany (klasa na <html>)', engaged);
    const st = await page.evaluate(() => ({ shield: !!document.querySelector('.pet-jokes__shield'), sprite: !!document.querySelector('.pet-jokes__cursor'),
      cursor: getComputedStyle(document.querySelector('a, button, body')).cursor, z: getComputedStyle(document.querySelector('.pet-jokes__shield')).zIndex }));
    L.check('warstwa blokująca i narysowany kursor istnieją', st.shield && st.sprite, st);
    L.check('prawdziwy kursor: cursor:none, z-index warstwy 1190', st.cursor === 'none' && st.z === '1190', st);
    await page.screenshot({ path: L.DIR + '/shots/cursor-engaged.png' });
    const ended = await page.waitForFunction(() => !document.documentElement.classList.contains('pet-jokes--no-cursor'), null, { timeout: 6000 }).then(() => true, () => false);
    L.check('żart kończy się sam (max ~3 s od schwytania)', ended);
    const after = await page.evaluate(leftovers);
    L.check('po żarcie: brak klasy, warstwy, narysowanego kursora, żart nieaktywny', !after.cls && !after.shield && !after.sprite && after.active === null && after.cursor !== 'none', after);
    await page.mouse.move(720, 510);
    const rec = await page.evaluate(() => { const k = Object.keys(sessionStorage).find((x) => x.indexOf('pets_jokes_cursor_') === 0); return k ? JSON.parse(sessionStorage.getItem(k)) : null; });
    L.check('licznik kursora w sessionStorage = 1', rec && rec.n === 1, rec);
    L.check('limit: drugi trigger(cursor) od razu = false', (await page.evaluate(() => window.PetJokes.trigger('cursor'))) === false);
    await browser.close();
    if (errors.length) L.check('brak błędów strony (A)', false, errors);
  }
  // --- B: każda ścieżka przerwania zostawia kursor w porządku ---
  const sciezki = {
    escape: async (page) => { await page.keyboard.press('Escape'); },
    klawisz: async (page) => { await page.keyboard.press('a'); },
    klik: async (page) => {
      await page.evaluate(() => { window.__clicks = 0; document.addEventListener('click', () => window.__clicks++); });
      await page.mouse.click(700, 500);
      await page.waitForTimeout(150);
      const n = await page.evaluate(() => window.__clicks);
      L.check('klik w trakcie żartu nie dociera do strony', n === 0, n);
    },
    blur: async (page) => { await page.evaluate(() => window.dispatchEvent(new Event('blur'))); },
    ukrycie: async (page) => { await page.evaluate(() => { Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true }); document.dispatchEvent(new Event('visibilitychange')); }); },
    'wyłączenie żartów': async (page) => { await page.evaluate(() => { const s = window.PetsState.current; window.PetsState.set(Object.assign({}, s, { companion: Object.assign({}, s.companion, { jokes: false }) })); }); },
  };
  for (const [nazwa, akcja] of Object.entries(sciezki)) {
    const { browser, page, errors } = await L.open({});
    const { engaged } = await startujZartu(page, false);
    L.check(`[${nazwa}] kursor schowany przed przerwaniem`, engaged);
    await akcja(page);
    await page.waitForTimeout(200);
    const after = await page.evaluate(leftovers);
    L.check(`[${nazwa}] po przerwaniu: kursor wraca, brak warstw i aktywnego żartu`, !after.cls && !after.shield && !after.sprite && after.active === null && after.cursor !== 'none', after);
    await browser.close();
    if (errors.length) L.check(`brak błędów strony (${nazwa})`, false, errors);
  }
  // --- C: zawieszony ruch → twardy timer 3 s ---
  {
    const { browser, page } = await L.open({});
    const { engaged } = await startujZartu(page, true);   // runTo: 1. wywołanie (dojście) ok, 2. (przenoszenie) wisi
    L.check('[twardy timer] kursor schowany', engaged);
    const t0 = Date.now();
    await page.waitForFunction(() => !document.documentElement.classList.contains('pet-jokes--no-cursor'), null, { timeout: 6000 });
    const dt = Date.now() - t0;
    L.check('[twardy timer] kursor wraca po ~3 s mimo zawieszonego ruchu', dt > 2300 && dt < 3900, dt);
    const after = await page.evaluate(leftovers);
    L.check('[twardy timer] brak pozostałości', !after.shield && !after.sprite && after.active === null, after);
    await browser.close();
  }
  // --- D: warunki ---
  {
    const { browser, page } = await L.open({});
    await L.waitCompanion(page);
    await page.waitForFunction(() => window.PetCompanionApi.ready(), null, { timeout: 10000 });
    L.check('bez ruchu myszy → false', (await page.evaluate(() => window.PetJokes.trigger('cursor'))) === false);
    await page.mouse.move(400, 400);
    await page.waitForTimeout(3300);
    L.check('mysz nieruszana > 3 s → false', (await page.evaluate(() => window.PetJokes.trigger('cursor'))) === false);
    await browser.close();
  }
  {
    const { browser, page } = await L.open({ touch: true, mobile: true, w: 390, h: 800 });
    await L.waitCompanion(page);
    await page.waitForFunction(() => window.PetCompanionApi.ready(), null, { timeout: 10000 });
    L.check('urządzenie dotykowe (bez myszy) → false', (await page.evaluate(() => window.PetJokes.trigger('cursor'))) === false);
    await browser.close();
  }
  L.finish(null);
})().catch((e) => { console.error(e); process.exit(2); });
```

Zrestartuj serwer i uruchom: `cd $JOKES && node cursor_check.js`
Expected: FAIL (zaślepka: `trigger(cursor)` zwraca `false`).

- [ ] **Step 2: CSS (dopisz na końcu `static/css/components/pet-jokes.css`)**

```css

/* --- Kradzież kursora (spec v3.2 §5.2) --- */
html.pet-jokes--no-cursor,
html.pet-jokes--no-cursor * { cursor: none !important; }

/* Przezroczysta warstwa blokuje kliknięcia i hover na czas żartu: nad sidebarem (1000) i koszykiem (1090–1100),
   pod pełnoekranowymi nakładkami (1200) */
.pet-jokes__shield {
    position: fixed;
    inset: 0;
    z-index: 1190;
    background: transparent;
}

.pet-jokes__cursor {
    position: fixed;
    top: 0;
    left: 0;
    z-index: 1191;
    width: 22px;
    height: 28px;
    pointer-events: none;
    will-change: transform;
}

/* Biała strzałka z ciemnym obrysem — czytelna na jasnym i ciemnym tle */
.pet-jokes__cursor svg {
    display: block;
    width: 100%;
    height: 100%;
    overflow: visible;
    filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.45));
}

.pet-jokes__cursor path {
    fill: #ffffff;
    stroke: #1a1a2e;
    stroke-width: 1.4;
    stroke-linejoin: round;
}

[data-theme="dark"] .pet-jokes__cursor svg { filter: drop-shadow(0 1px 3px rgba(0, 0, 0, 0.8)); }

.pet-jokes__cursor.is-dropped svg { animation: pet-jokes-drop 0.3s ease-out both; }

@keyframes pet-jokes-drop {
    from { transform: translateY(-6px) rotate(-10deg); }
    to { transform: translateY(0) rotate(0); }
}
```

- [ ] **Step 3: Implementacja: zastąp blok-zaślepkę w `pet-jokes.js`**

Zastąp dokładnie te linie (od komentarza otwierającego do końcowego):

```js
    // --- kradzież kursora (Zadanie 8 zastępuje ten blok) ----------------------------------------
    var mouse = null;
    function cursorAvailable() { return false; }
    function startCursor() { return false; }
    // --- koniec bloku kursora --------------------------------------------------------------------
```

przez:

```js
    // --- żart: kradzież kursora -----------------------------------------------------------------
    // Pupil dobiega do kursora, prawdziwy kursor znika (cursor:none), pupil ciąga narysowany kursor 2–3 s
    // i oddaje go. Klik w tym czasie nie dociera do strony. KAŻDA ścieżka końca idzie przez end() ->
    // sweepCursor(): kursor wraca zawsze.

    var CURSOR_GAP_MS = 10 * 60 * 1000, CURSOR_MAX = 2;   // najwyżej 2 razy na sesję karty, co 10 min
    var MOUSE_FRESH_MS = 3000;                            // mysz musiała się ruszyć w ciągu 3 s
    var CURSOR_HARD_MS = 3000;                            // twardy limit schowania kursora
    var GRAB_MS = 220, DROP_MS = 350;
    var cursorKey = 'pets_jokes_cursor_' + userId;
    var mouse = null;                                     // {x, y, t}

    function finePointer() {
        return !!(window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches);
    }

    /** Usuwa wszystko, co żart kursora dodał do strony (idempotentne, niezależne od domknięć). */
    function sweepCursor() {
        html.classList.remove(NO_CURSOR);
        var stray = document.querySelectorAll('.pet-jokes__shield, .pet-jokes__cursor');
        for (var i = 0; i < stray.length; i++) {
            if (stray[i].parentNode) stray[i].parentNode.removeChild(stray[i]);
        }
    }

    function onMouseMove(e) {
        mouse = { x: e.clientX, y: e.clientY, t: Date.now() };
        // pas i szelki: klasa została po jakimś błędzie, a żadnego żartu kursora już nie ma
        if (html.classList.contains(NO_CURSOR) && !(current && current.name === 'cursor')) sweepCursor();
    }

    if (finePointer()) {
        window.addEventListener('mousemove', onMouseMove, { passive: true });
        html.addEventListener('mouseleave', function () { mouse = null; });
    }

    function readCursorRec() {
        var rec = null;
        try { rec = JSON.parse(ssGet(cursorKey) || 'null'); } catch (e) { rec = null; }
        return rec && typeof rec === 'object' ? { n: rec.n | 0, last: +rec.last || 0 } : { n: 0, last: 0 };
    }

    function cursorAvailable() {
        if (!finePointer() || !mouse || Date.now() - mouse.t > MOUSE_FRESH_MS) return false;
        var rec = readCursorRec();
        if (rec.n >= CURSOR_MAX) return false;
        return !rec.last || Date.now() - rec.last >= CURSOR_GAP_MS;
    }

    function buildCursorSprite() {
        var wrap = document.createElement('div');
        wrap.className = 'pet-jokes__cursor';
        wrap.setAttribute('aria-hidden', 'true');
        wrap.innerHTML = '<svg viewBox="0 0 22 28" xmlns="http://www.w3.org/2000/svg"><path d="M1 1 L1 22 L6.5 17.2 L10.2 26 L13.4 24.6 L9.8 16 L17 16 Z"/></svg>';
        return wrap;
    }

    function startCursor() {
        var m = mouse;
        if (!m) return false;
        var r0 = api.rect();
        var done = false, engaged = false, raf = 0, hardTimer = 0, dropTimer = 0, shield = null, sprite = null;
        var job = { name: 'cursor', cancel: function () { end(); } };
        var capt = { capture: true, passive: false };

        function swallowNextClick() {
            function eat(e) { e.preventDefault(); e.stopPropagation(); }
            window.addEventListener('click', eat, { capture: true, once: true });
            setTimeout(function () { window.removeEventListener('click', eat, true); }, 400);
        }

        // Przed schwytaniem klik użytkownika działa normalnie (żart tylko się kończy); po schwytaniu jest połykany
        function onPointer(e) {
            if (engaged) {
                e.preventDefault();
                e.stopPropagation();
                swallowNextClick();
            }
            end();
        }
        function onKey() { end(); }                          // klawisza nie połykamy (Tab dalej działa)
        function onHidden() { if (document.visibilityState === 'hidden') end(); }

        function listen() {
            window.addEventListener('keydown', onKey, capt);
            ['pointerdown', 'mousedown', 'touchstart'].forEach(function (t) { window.addEventListener(t, onPointer, capt); });
            window.addEventListener('blur', end);
            window.addEventListener('pagehide', end);
            document.addEventListener('visibilitychange', onHidden);
        }

        function unlisten() {
            window.removeEventListener('keydown', onKey, capt);
            ['pointerdown', 'mousedown', 'touchstart'].forEach(function (t) { window.removeEventListener(t, onPointer, capt); });
            window.removeEventListener('blur', end);
            window.removeEventListener('pagehide', end);
            document.removeEventListener('visibilitychange', onHidden);
        }

        // Idempotentne: WSZYSTKIE ścieżki końca kończą tutaj, a kursor wraca w finally
        function end() {
            if (done) return;
            done = true;
            try {
                cancelAnimationFrame(raf);
                clearTimeout(hardTimer);
                clearTimeout(dropTimer);
                unlisten();
            } finally {
                sweepCursor();
                if (current === job) { current = null; scheduleNext(); }
                if (release) release();
            }
        }

        function engage() {
            engaged = true;
            var from = mouse || { x: r0.x, y: r0.y };
            html.classList.add(NO_CURSOR);
            shield = document.createElement('div');
            shield.className = 'pet-jokes__shield';
            sprite = buildCursorSprite();
            document.body.appendChild(shield);
            document.body.appendChild(sprite);
            hardTimer = setTimeout(end, CURSOR_HARD_MS);
            var t0 = Date.now();
            (function frame() {
                if (done) return;
                var r = api.rect();
                var right = !host.classList.contains('pet-companion--flipped');
                var px = r.x + r.w * (right ? 0.92 : 0.08), py = r.y + r.h * 0.72;
                var k = Math.min(1, (Date.now() - t0) / GRAB_MS);
                sprite.style.transform = 'translate(' + Math.round(from.x + (px - from.x) * k) + 'px,' +
                    Math.round(from.y + (py - from.y) * k) + 'px)';
                raf = requestAnimationFrame(frame);
            })();
            // niesie kursor 150–250 px w stronę najbliższej krawędzi i upuszcza
            var r = api.rect();
            var dir = (r.x + r.w / 2) < vw() / 2 ? -1 : 1;
            if ((dir < 0 && r.x < 200) || (dir > 0 && r.x > vw() - 280)) dir = -dir;
            api.runTo(r.x + dir * rand(150, 250), r.y, { face: dir > 0 ? 'right' : 'left' }).then(function (ok) {
                if (!ok || done) return;
                sprite.classList.add('is-dropped');
                dropTimer = setTimeout(end, DROP_MS);
            });
        }

        var release = api.claim(function () { end(); });
        if (!release) return false;
        current = job;
        var rec = readCursorRec();
        ssSet(cursorKey, JSON.stringify({ n: rec.n + 1, last: Date.now() }));
        try {
            listen();
            // dobiega do punktu obok kursora (nie na sam kursor), potem schwytanie
            var side = m.x + 28 + r0.w < vw() ? 28 : -(28 + r0.w);
            api.runTo(m.x + side, m.y - r0.h / 2).then(function (ok) {
                if (!ok || done) return;
                if (!mouse) { end(); return; }                   // mysz opuściła okno w trakcie dobiegania
                try { engage(); } catch (e) { end(); }
            });
        } catch (e) {
            end();
            return false;
        }
        return true;
    }
    // --- koniec żartu kursora -------------------------------------------------------------------
```

- [ ] **Step 4: Uruchom skrypty i potwierdź**

Run: `node --check static/js/components/pet-jokes.js && cd $JOKES && node cursor_check.js && node peek_check.js && node peek_gates.js`
Expected: `0 fail` we wszystkich trzech. Obejrzyj `$JOKES/shots/cursor-engaged.png` (Read): narysowany kursor w łapkach pupila, widoczny w jasnym i (po ponowieniu z `dark: true`) ciemnym motywie.

- [ ] **Step 5: Commit**

```bash
git add static/js/components/pet-jokes.js static/css/components/pet-jokes.css
git commit -m "feat(pupile): zarty - kradziez kursora

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Integracja, cache, pełna weryfikacja

**Files:**
- Modify: `static/sw.js` (`CACHE_VERSION`)
- Memory: `/Users/konradkmiecik/.claude/projects/-Users-konradkmiecik-Documents-GitHub-ThunderOrders/memory/project_pupile_tamagotchi.md` i `MEMORY.md`

**Interfaces:**
- Consumes: całość.

- [ ] **Step 1: Podbij cache**

`static/sw.js`: `const CACHE_VERSION = 'thunderorders-v38';` → `const CACHE_VERSION = 'thunderorders-v39';`

- [ ] **Step 2: Pełna suita**

Run: `venv/bin/python -m pytest -q --deselect tests/test_mobile_api_auth.py::test_logout_stores_expiry_in_local_time_and_purges_expired > $JOKES/full.txt 2>&1; tail -3 $JOKES/full.txt`
Expected: `passed`, 0 failed (baza 2117 + nowe testy żartów).

- [ ] **Step 3: Komplet skryptów przeglądarkowych na świeżym serwerze**

Zrestartuj `pets-jokes` i uruchom: `cd $JOKES && for s in admin_check workshop_check run_gait api_check peek_check peek_gates cursor_check; do echo "== $s"; node $s.js || echo "!! $s FAIL"; done; node run_gait.js chory`
Expected: żadnego `!! … FAIL`; `0 fail` w każdym.

- [ ] **Step 4: Przegląd wizualny (jasny i ciemny motyw, telefon)**

Zrób zrzuty (Playwright przez `lib.open`): wychylenie w jasnym i ciemnym motywie (`dark: true`), `edge: 'bottom'`, widok telefonu 375×812 (`mobile: true`, tylko prawa i dolna krawędź), kursor w obu motywach. Przejrzyj je (Read). Oceń: obrazek przy pyszczku, „x" widoczny i klikalny, brak ucięć, brak poziomego przewijania strony. Poprawki dostrajające CSS w tym kroku wchodzą do osobnego commita `fix(pupile): zarty - dostrojenie wygladu`.

- [ ] **Step 5: Commit cache**

```bash
git add static/sw.js
git commit -m "chore(pupile): CACHE_VERSION v39 po zartach

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Końcowy przegląd całej gałęzi (świeży recenzent)**

Zgodnie z `superpowers:executing-plans`: `review-package` dla zakresu od `2ce5d97d` (commit specu) do HEAD i recenzja na najzdolniejszym modelu, z Review Focus z tego planu. Poprawki Critical/Important w jednym przebiegu, każda przez test RED→GREEN i zieloną suitę; Minor do ledgera.

- [ ] **Step 7: Pamięć projektu i podgląd dla Konrada**

W `project_pupile_tamagotchi.md` dopisz sekcję v3.2: bieg w `pet-companion.js` (poza `run`), `PetCompanionApi` (`claim`/`runTo`), moduł `pet-jokes` (kursor + wychylenie), `jokes_enabled` + `pets_jokes_enabled`, tabela `pet_peek_images`, migracja `c7a4d1e9f2b6`, CACHE v39, nic niepushowane; zaktualizuj liczbę commitów w jednolinijkowym wpisie w `MEMORY.md`. Zrestartuj podglądy dla Konrada: `pets-preview` (:5001, dzień) i `pets-final-noc` (:5017) przez `preview_stop`/`preview_start`, bo trzymają stary kod i starą bazę. W raporcie końcowym wymień: rulings (R1 i ewentualne), deferred minors, oraz co trzeba zrobić przed produkcją (`flask db upgrade` dla `c7a4d1e9f2b6`, katalog `static/uploads/pet_peeks/` musi być zapisywalny dla procesu aplikacji), bez pusha.
