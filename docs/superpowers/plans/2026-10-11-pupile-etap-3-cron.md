# Pupile — Etap 3 (cron i powiadomienia) — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Godzinny cron `flask pets tick`, który dla każdego użytkownika liczy stan pupili, zapisuje
odejścia, wysyła **jeden zbiorczy push** i (gdy trzeba) **jeden zbiorczy mail**, raz na epizod,
z poszanowaniem preferencji „Pupile" (widocznej także bez pusha) i kill-switcha maila w adminie;
plus przypomnienie o nieodebranym jajku ratunkowym i porządki `pet_events`.

**Architecture:** Logika w `modules/pets/notifications.py` jako czyste-ish funkcje przyjmujące
`now`/`cfg` (testowalne bez CLI): `users_to_check` → per użytkownik `collect_for_user` pod
blokadą profilu (zapis poziomów/odejść/flag jajek w jednej transakcji) → po commicie wysyłka:
push **synchronicznie** (`PushManager.send_to_user`; `_fire_and_forget` to wątek daemon, który
ginie z procesem CLI), maile zebrane ze wszystkich użytkowników w **jeden** `send_email_batch_sync`
na końcu przebiegu (limit SMTP Hostingera per IP). Komenda CLI jest cienkim wrapperem w grupie
`flask pets`. Odczyt stanu nadal przez `rules.simulate()`; cron nie zapisuje stanu pupili (tylko
odejścia i flagi powiadomień) — zgodnie z §3.1 specu.

**Tech Stack:** Flask 3 CLI (click), SQLAlchemy 2.0, Flask-Mail (`prepare_email` +
`send_email_batch_sync`), `PushManager`, Jinja2 (szablony maili), pytest na SQLite.

**Spec:** `docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md` (§2.9, §3.2, §3.6, §8, §9 etap 3).

## Global Constraints

- Gałąź `feat/pupile` (etap 1 + 2 scalone, HEAD `4e9c6b47`). Testy **zawsze** przez
  `venv/bin/python -m pytest …`; wynik pytesta sprawdzaj z pliku/`$?`, nie przez `| tail`
  (maskuje kod wyjścia). Znana porażka spoza gałęzi: `test_mobile_api_auth.py::test_logout_stores_expiry_in_local_time_and_purges_expired`.
- Czas naiwny polski; każda funkcja przyjmuje `now=None` (→ `get_local_now()`), `cfg=None`
  (→ `PetConfig.load()`). Testy wstrzykują, nie monkeypatchują czasu.
- **Każdy odczyt po blokadzie profilu blokujący** (`*_lock_query` z `common.py`, lekcja recenzji
  etapu 2). Kolejność blokad profil → pupil.
- Push z CLI **synchronicznie** przez `PushManager.send_to_user(user_id, title, body, url, tag,
  notification_type)`; `send_to_user` zapisuje wpis w dzwonku PRZED sprawdzeniem preferencji, więc
  cron sprawdza `pet_updates` **sam, zanim** cokolwiek zawoła. Brak wiersza `NotificationPreference`
  = włączone.
- Maile tylko dla: krytyczny, odejście, ratunkowe nieodebrane ≥ 7 dni; przez
  `prepare_email('pets_alert', …)` + **jeden** `send_email_batch_sync` na przebieg; globalny
  kill-switch `EmailManager.is_email_enabled('notify_pet_alert')`; importy `send_email_batch_sync`
  **wewnątrz funkcji** (`from utils.email_sender import send_email_batch_sync`), żeby testy mogły
  monkeypatchować `utils.email_sender.send_email_batch_sync` jak w `test_dostawa_cron.py`.
- Język: „odszedł do gwiazd" — zawsze w zdaniu z podmiotem **„pupil {imię}"** („Pupil Wiewiórka
  odszedł do gwiazd"), żeby rodzaj gramatyczny się zgadzał niezależnie od imienia (odroczony
  Minor z recenzji rozwiązany sformułowaniem).
- Komunikaty po polsku; tematy commitów ASCII `feat(pupile): …`; na końcu
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. **Nie pushować.** Żadnego inline JS
  w szablonach (nowy plik w `static/js/pages/profile/`).
- Odbiorcy: tylko `User.is_active == True` i `role == 'client'` (anonimizowane konta mają
  `is_active=False`). Adres pupili w pushu: `/client/pupile`; w mailu absolutny:
  `current_app.config.get('BASE_URL', 'https://thunderorders.cloud') + '/client/pupile'`
  (trasa powstaje w etapie 4 — link celowo literalny).

## Review Focus

1. **Użytkownik z włączonym `pet_updates`, ale bez subskrypcji push** → wpis w dzwonku (`Notification`)
   powstaje, przebieg nie rzuca wyjątku, `send_to_user` zwraca False i to nie jest błąd (Task 5).
2. **Pupil krytyczny w poprzednim przebiegu, nakarmiony między przebiegami** → `notify_level`
   wraca do 0 i NIE idzie spóźniony push „krytyczny" (Task 4).
3. **Nieudana wysyłka maila** → przypomnienie o ratunkowym NIE jest oznaczone (powtórka za godzinę),
   ale odejście JEST oznaczone (`death_notified_at`), bo push/dzwonek wyszły (Task 5).
4. **Dwa przebiegi w tej samej godzinie** (ręczny + cron) → zero podwójnych pushy/maili/wpisów (Task 5).
5. **Użytkownik bez wiersza `NotificationPreference`** → traktowany jako włączony, dostaje push (Task 5).

---

### Task 1: Preferencja „Pupile" — API i karta w profilu

**Files:**
- Modify: `modules/notifications/routes.py:107-144` (`get_preferences` domyślne, `allowed_fields`)
- Modify: `modules/profile/routes.py:17-27` (`index` — flaga `pets_available`)
- Modify: `templates/profile/index.html` (karta „Pupile" przed kartą Push; skrypt w `extra_js`)
- Create: `static/js/pages/profile/pet-updates-toggle.js`
- Test: `tests/test_pets_notifications_prefs.py`

**Interfaces:**
- Consumes: `NotificationPreference.pet_updates` (etap 1), `modules.pets.config.pets_feature_for(user)`.
- Produces: `GET /notifications/preferences` zawiera `pet_updates`; `POST /notifications/preferences
  {"pet_updates": bool}` zapisuje; profil renderuje `#petUpdatesToggle` tylko gdy
  `pets_feature_for(current_user)`.

- [ ] **Step 1: Failujące testy**

```python
# tests/test_pets_notifications_prefs.py
"""Preferencja „Pupile" (pet_updates): API preferencji + karta w profilu widoczna bez pusha."""
from flask import url_for


def _wlacz_funkcje(db):
    from modules.auth.models import Settings
    from modules.pets.config import reset_feature_cache
    Settings.set_value('pets_enabled', 'true', type='boolean')
    Settings.set_value('pets_rollout_pct', 100, type='integer')
    db.session.commit()
    reset_feature_cache()


def test_get_preferences_domyslnie_ma_pet_updates(client, login, make_user):
    user = make_user()
    login(user)
    r = client.get('/notifications/preferences')
    assert r.status_code == 200
    dane = r.get_json()
    assert dane['pet_updates'] is True
    assert dane['sale_date_changes'] is True and dane['order_supplier_ordered'] is True


def test_post_preferences_zapisuje_pet_updates(client, login, make_user, db):
    from modules.notifications.models import NotificationPreference
    user = make_user()
    login(user)
    r = client.post('/notifications/preferences', json={'pet_updates': False})
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert NotificationPreference.query.filter_by(user_id=user.id).one().pet_updates is False
    assert client.get('/notifications/preferences').get_json()['pet_updates'] is False


def test_karta_pupili_w_profilu_tylko_gdy_funkcja_dostepna(app, client, login, make_user, db):
    user = make_user(profile_completed=True)
    login(user)
    with app.test_request_context():
        url = url_for('profile.index')
    r = client.get(url)
    assert r.status_code == 200 and b'petUpdatesToggle' not in r.data
    _wlacz_funkcje(db)
    r = client.get(url)
    assert r.status_code == 200 and b'petUpdatesToggle' in r.data
    assert b'pet-updates-toggle.js' in r.data
```

- [ ] **Step 2: Uruchom — mają paść**

Run: `venv/bin/python -m pytest tests/test_pets_notifications_prefs.py -q`
Expected: 3 FAIL (`KeyError: 'pet_updates'` w GET; POST nie zapisuje; brak `petUpdatesToggle`).

- [ ] **Step 3: API preferencji**

W `modules/notifications/routes.py` w `get_preferences` zastąp blok domyślnych:

```python
    if not pref:
        # Domyślne (wszystko włączone) — ta sama lista co NotificationPreference.to_dict()
        return jsonify({
            'order_status_changes': True,
            'payment_updates': True,
            'shipping_updates': True,
            'new_exclusive_pages': True,
            'cost_added': True,
            'admin_alerts': True,
            'sale_date_changes': True,
            'order_supplier_ordered': True,
            'pet_updates': True,
        })
```

a w `update_preferences` listę `allowed_fields`:

```python
    allowed_fields = [
        'order_status_changes', 'payment_updates', 'shipping_updates',
        'new_exclusive_pages', 'cost_added', 'sale_date_changes', 'admin_alerts',
        'order_supplier_ordered', 'pet_updates',
    ]
```

- [ ] **Step 4: Trasa profilu i karta**

`modules/profile/routes.py` — `index()`:

```python
@profile_bp.route('/')
@login_required
def index():
    """
    Strona profilu użytkownika
    GET /profile
    """
    from modules.pets.config import pets_feature_for
    return render_template(
        'profile/index.html',
        title='Mój Profil',
        pets_available=pets_feature_for(current_user),
    )
```

(`current_user` jest już importowany w tym pliku — sprawdź nagłówek; jeśli nie, dopisz
`from flask_login import current_user`.)

`templates/profile/index.html` — bezpośrednio PRZED linią `<!-- Powiadomienia Push -->` wstaw:

```jinja
                <!-- Pupile — przełącznik poza kartą Push, bo steruje też mailami -->
                {% if pets_available %}
                <div class="profile-card" id="petUpdatesCard">
                    <div class="profile-card-header">
                        <h2>Pupile</h2>
                    </div>
                    <div class="privacy-item">
                        <div class="privacy-info">
                            <h3>Powiadomienia o pupilach</h3>
                            <p class="privacy-description">
                                Push i e-mail, gdy pupil jest smutny, chory albo w stanie krytycznym,
                                gdy odejdzie do gwiazd i gdy jajko jest gotowe. Działa także bez
                                powiadomień push (wtedy tylko e-mail w sytuacjach krytycznych).
                            </p>
                        </div>
                        <label class="toggle-switch">
                            <input type="checkbox" id="petUpdatesToggle" checked>
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                </div>
                {% endif %}

```

W bloku `extra_js` po `push-settings.js` dodaj:

```jinja
<script src="{{ url_for('static', filename='js/pages/profile/pet-updates-toggle.js') }}"></script>
```

- [ ] **Step 5: JS przełącznika**

```javascript
// static/js/pages/profile/pet-updates-toggle.js
/**
 * Przełącznik „Powiadomienia o pupilach" (push + e-mail) na stronie profilu.
 * Niezależny od push-settings.js — tamten kończy działanie, gdy przeglądarka nie
 * obsługuje pusha, a ten przełącznik steruje też mailami.
 */
(function () {
    'use strict';

    var toggle = document.getElementById('petUpdatesToggle');
    if (!toggle) return;

    var csrfMeta = document.querySelector('meta[name="csrf-token"]');
    var URL = '/notifications/preferences';

    fetch(URL)
        .then(function (r) { return r.json(); })
        .then(function (prefs) {
            if (prefs && 'pet_updates' in prefs) toggle.checked = !!prefs.pet_updates;
        })
        .catch(function () {});

    toggle.addEventListener('change', function () {
        var wlaczone = toggle.checked;
        fetch(URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfMeta ? csrfMeta.getAttribute('content') : ''
            },
            body: JSON.stringify({ pet_updates: wlaczone })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data && data.success && window.showToast) {
                    window.showToast(wlaczone ? 'Powiadomienia o pupilach włączone' : 'Powiadomienia o pupilach wyłączone', 'success');
                }
            })
            .catch(function () {
                toggle.checked = !wlaczone;
                if (window.showToast) window.showToast('Błąd zapisu preferencji', 'error');
            });
    });
})();
```

- [ ] **Step 6: Uruchom — mają przejść**

Run: `venv/bin/python -m pytest tests/test_pets_notifications_prefs.py -q`
Expected: `3 passed`.

- [ ] **Step 7: Commit**

```bash
git add modules/notifications/routes.py modules/profile/routes.py templates/profile/index.html static/js/pages/profile/pet-updates-toggle.js tests/test_pets_notifications_prefs.py
git commit -m "$(cat <<'EOF'
feat(pupile): preferencja pet_updates w API i karta Pupile w profilu

GET/POST /notifications/preferences obsluguja pet_updates (domyslne
uzupelnione o sale_date_changes i order_supplier_ordered); karta Pupile
w profilu poza karta Push, widoczna tylko gdy funkcja dostepna dla usera.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Kill-switch maila `notify_pet_alert` w adminie

**Files:**
- Modify: `modules/orders/routes.py:2163-2175` (`ALLOWED_KEYS`)
- Modify: `templates/admin/orders/settings.html:725-734` (nowy `email-notif-item` po „Przypomnienie o odbiorze")
- Test: `tests/test_pets_email_switch.py`

**Interfaces:**
- Produces: klucz `notify_pet_alert` w `email_notifications_config`; `EmailManager.is_email_enabled('notify_pet_alert')`
  honoruje przełącznik (JS `orders-settings.js` zbiera `.email-notif-toggle` generycznie — bez zmian).

- [ ] **Step 1: Failujące testy**

```python
# tests/test_pets_email_switch.py
"""Globalny wyłącznik maila o pupilach w ustawieniach maili admina."""


def test_notify_pet_alert_zapisuje_sie_i_wylacza(client, login, make_user):
    from utils.email_manager import EmailManager
    admin = make_user(role='admin')
    login(admin)
    r = client.post('/admin/orders/settings/email-notifications', json={'toggles': {'notify_pet_alert': False}})
    assert r.status_code == 200, r.data
    EmailManager.clear_email_config_cache()
    assert EmailManager.is_email_enabled('notify_pet_alert') is False
    assert EmailManager.is_email_enabled('notify_pickup_reminder') is True   # reszta domyślnie True


def test_strona_ustawien_ma_przelacznik_pupili(client, login, make_user):
    admin = make_user(role='admin')
    login(admin)
    r = client.get('/admin/orders/settings')
    assert r.status_code == 200 and b'notify_pet_alert' in r.data
```

- [ ] **Step 2: Uruchom — mają paść**

Run: `venv/bin/python -m pytest tests/test_pets_email_switch.py -q`
Expected: 2 FAIL (`is_email_enabled` zwraca True — klucz spoza whitelisty; brak w HTML).

- [ ] **Step 3: Whitelist i toggle**

W `ALLOWED_KEYS` (`modules/orders/routes.py`) dopisz na końcu zbioru:

```python
        'notify_pickup_reminder',
        'notify_pet_alert',
```

W `templates/admin/orders/settings.html` po bloku „Przypomnienie o odbiorze" (`</div>` zamykające
`email-notif-item` z `notify_pickup_reminder`) dodaj:

```jinja
                            <div class="email-notif-item">
                                <div class="email-notif-info">
                                    <div class="email-notif-name">Pupile — stan krytyczny i odejście</div>
                                    <div class="email-notif-desc">Mail, gdy pupil jest w stanie krytycznym, odszedł do gwiazd lub jajko ratunkowe czeka od tygodnia</div>
                                </div>
                                <label class="email-toggle-switch">
                                    <input type="checkbox" class="email-notif-toggle" data-key="notify_pet_alert" {{ 'checked' if email_notif_config.get('notify_pet_alert', true) != false }}>
                                    <span class="email-toggle-slider"></span>
                                </label>
                            </div>
```

- [ ] **Step 4: Uruchom — mają przejść**

Run: `venv/bin/python -m pytest tests/test_pets_email_switch.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add modules/orders/routes.py templates/admin/orders/settings.html tests/test_pets_email_switch.py
git commit -m "$(cat <<'EOF'
feat(pupile): kill-switch maila notify_pet_alert w ustawieniach admina

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Treść powiadomień — push i szablony maila `pets_alert`

**Files:**
- Create: `modules/pets/notifications.py` (część 1: stałe, `level_of`, `pet_updates_enabled`,
  `build_push_text`, `needs_email`, `build_email_message`, `pets_url`)
- Create: `templates/emails/pets_alert.html`, `templates/emails/pets_alert.txt`
- Test: `tests/test_pets_cron.py` (część 1)

**Interfaces:**
- Produces: `LEVEL_SAD=1, LEVEL_SICK=2, LEVEL_CRITICAL=3, LEVEL_DEAD=4`, `PETS_URL_PATH='/client/pupile'`,
  `PUSH_TAG='pets'`, `PREF_FIELD='pet_updates'`, `EMAIL_SWITCH='notify_pet_alert'`,
  `PRUNE_DAYS=90`, `PUSH_BODY_MAX=200`;
  `level_of(state) -> int`; `pet_updates_enabled(user_id) -> bool`;
  **koszyk** = `dict(user=User, alerts=[(Pet, int)], deaths=[Pet], eggs_ready=[Pet], monthly=bool,
  rescue_reminders=[Pet])`; `basket_is_empty(basket) -> bool`;
  `build_push_text(basket) -> (title: str, body: str)`; `needs_email(basket) -> bool`;
  `pets_url() -> str` (absolutny); `build_email_message(user, basket) -> Message | None`.

- [ ] **Step 1: Failujące testy**

```python
# tests/test_pets_cron.py
"""Cron pupili: treść powiadomień, koszyk per użytkownik, przebieg tick (spec §2.9, §3.6)."""
from datetime import timedelta

import pytest

from tests.pets_helpers import T0, zaloz_profil, zaloz_pupila, zaloz_zmarlego, zaloz_jajko


def _cfg(**over):
    from modules.pets.config import PetConfig
    return PetConfig(**over)


def _koszyk(user, **pola):
    koszyk = dict(user=user, alerts=[], deaths=[], eggs_ready=[], monthly=False, rescue_reminders=[])
    koszyk.update(pola)
    return koszyk


# --- treść ---

def test_level_of_z_nastroju():
    from modules.pets import rules
    from modules.pets.notifications import level_of, LEVEL_SAD, LEVEL_SICK, LEVEL_CRITICAL
    assert level_of(rules.PetState()) == 0
    assert level_of(rules.PetState(hunger=40)) == 0            # głodny, ale bez zera i zdrowy
    assert level_of(rules.PetState(fun=0)) == LEVEL_SAD
    assert level_of(rules.PetState(fun=0, health=60)) == LEVEL_SICK
    assert level_of(rules.PetState(health=10)) == LEVEL_CRITICAL


def test_push_zbiorczy_tekst(db, make_user):
    from modules.pets.notifications import build_push_text, LEVEL_SICK, LEVEL_SAD
    user = make_user()
    zaloz_profil(user)
    a = zaloz_pupila(user, species='kotek', name='Mruczek')
    b = zaloz_pupila(user, species='mis', name='Wiewiórka')
    zmarly = zaloz_zmarlego(user, species='piesek', name='Puszek')
    jajko = zaloz_jajko(user)
    tytul, tresc = build_push_text(_koszyk(user, alerts=[(a, LEVEL_SICK), (b, LEVEL_SAD)], deaths=[zmarly],
                                           eggs_ready=[jajko], monthly=True))
    assert tytul == 'Twoje pupile'
    assert 'Pupil Mruczek jest chory.' in tresc
    assert 'Pupil Wiewiórka jest smutny.' in tresc       # podmiot „pupil" — rodzaj zawsze się zgadza
    assert 'Pupil Puszek odszedł do gwiazd.' in tresc
    assert 'Jajko gotowe do wyklucia!' in tresc and 'Czeka na Ciebie nowe jajko!' in tresc
    assert len(tresc) <= 200


def test_push_pusty_koszyk_i_dwa_jajka(db, make_user):
    from modules.pets.notifications import build_push_text, basket_is_empty
    user = make_user()
    zaloz_profil(user)
    assert basket_is_empty(_koszyk(user)) is True
    assert build_push_text(_koszyk(user)) == ('Twoje pupile', '')
    j1, j2 = zaloz_jajko(user), zaloz_jajko(user)
    _, tresc = build_push_text(_koszyk(user, eggs_ready=[j1, j2]))
    assert '2 jajka gotowe do wyklucia!' in tresc


def test_needs_email_tylko_krytyczny_odejscie_ratunkowe(db, make_user):
    from modules.pets.notifications import needs_email, LEVEL_SICK, LEVEL_CRITICAL
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user)
    assert needs_email(_koszyk(user, alerts=[(pet, LEVEL_SICK)], eggs_ready=[pet], monthly=True)) is False
    assert needs_email(_koszyk(user, alerts=[(pet, LEVEL_CRITICAL)])) is True
    assert needs_email(_koszyk(user, deaths=[pet])) is True
    assert needs_email(_koszyk(user, rescue_reminders=[pet])) is True


def test_build_email_message_renderuje_szablony(app, db, make_user):
    from modules.pets.notifications import build_email_message, LEVEL_CRITICAL
    from modules.admin.models import EmailLog
    user = make_user(first_name='Ania')
    zaloz_profil(user)
    krytyczny = zaloz_pupila(user, species='kotek', name='Mruczek', health=10.0)
    zmarly = zaloz_zmarlego(user, species='mis', name='Puszek', hatched_at=T0 - timedelta(days=40),
                            care_days=33, stars=2)
    ratunkowy = zaloz_zmarlego(user, species='piesek', name='Reksio', died_at=T0 - timedelta(days=8))
    with app.test_request_context():
        msg = build_email_message(user, _koszyk(user, alerts=[(krytyczny, LEVEL_CRITICAL)], deaths=[zmarly],
                                                rescue_reminders=[ratunkowy]))
    assert msg is not None and msg.recipients == [user.email]
    assert msg.subject == 'Pupil Puszek odszedł do gwiazd'
    for fragment in ('Ania', 'Mruczek', 'Stan krytyczny', 'Puszek', '40 dni', '33', 'Reksio', '/client/pupile'):
        assert fragment in msg.html, fragment
        assert fragment in msg.body, fragment
    assert 'zmarł' not in msg.html.lower() and 'umarł' not in msg.html.lower()
    assert EmailLog.query.filter_by(template='pets_alert').count() == 1


def test_temat_maila_wedlug_wagi(app, db, make_user):
    from modules.pets.notifications import build_email_message, LEVEL_CRITICAL
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, name='Mruczek', health=10.0)
    ratunkowy = zaloz_zmarlego(user, name='Reksio', died_at=T0 - timedelta(days=8))
    with app.test_request_context():
        assert build_email_message(user, _koszyk(user, alerts=[(pet, LEVEL_CRITICAL)])).subject == \
            'Pupil Mruczek potrzebuje pomocy — stan krytyczny'
        assert build_email_message(user, _koszyk(user, rescue_reminders=[ratunkowy])).subject == \
            'Jajko ratunkowe czeka na odebranie'
        assert build_email_message(user, _koszyk(user)) is None
```

- [ ] **Step 2: Uruchom — mają paść**

Run: `venv/bin/python -m pytest tests/test_pets_cron.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.pets.notifications'`.

- [ ] **Step 3: `notifications.py` część 1**

```python
# modules/pets/notifications.py
"""Powiadomienia o pupilach (spec §2.9, §3.6): koszyk per użytkownik, zbiorczy push, zbiorczy mail,
przebieg crona `flask pets tick`.

Dlaczego tak:
- `_fire_and_forget` PushManagera to wątek daemon — proces CLI kończy się wcześniej i push ginie,
  więc tu wołamy `send_to_user` synchronicznie;
- `send_to_user` zapisuje wpis w dzwonku PRZED sprawdzeniem preferencji, więc `pet_updates`
  sprawdzamy sami, zanim cokolwiek zawołamy;
- maile ze wszystkich użytkowników idą jednym `send_email_batch_sync` (limit SMTP per IP).
"""
from datetime import timedelta

from flask import current_app

from extensions import db
from modules.pets import rules
from modules.pets.common import (
    cfg_or, egg_progress, lock_profile, next_monthly_at, now_or, persist_death, simulate_pet,
)
from modules.pets.models import PRUNABLE_EVENT_TYPES, Pet, PetEvent, PetProfile
from modules.pets.species import SPECIES_BY_SLUG

LEVEL_SAD, LEVEL_SICK, LEVEL_CRITICAL, LEVEL_DEAD = 1, 2, 3, 4
_LEVEL_BY_MOOD = {'smutny': LEVEL_SAD, 'chory': LEVEL_SICK, 'krytyczny': LEVEL_CRITICAL}
_OPIS_POZIOMU = {
    LEVEL_SAD: 'jest smutny',
    LEVEL_SICK: 'jest chory',
    LEVEL_CRITICAL: 'potrzebuje pomocy — stan krytyczny',
}
PETS_URL_PATH = '/client/pupile'
PUSH_TAG = 'pets'
PUSH_TITLE = 'Twoje pupile'
PREF_FIELD = 'pet_updates'
EMAIL_SWITCH = 'notify_pet_alert'
PRUNE_DAYS = 90
PUSH_BODY_MAX = 200


def level_of(state):
    """Poziom ostrzeżenia z nastroju (spec §2.9): 0 brak, 1 smutny, 2 chory, 3 krytyczny."""
    return _LEVEL_BY_MOOD.get(rules.mood(state), 0)


def pet_updates_enabled(user_id):
    """Brak wiersza preferencji = włączone (jak w PushManager.send_to_user)."""
    from modules.notifications.models import NotificationPreference
    pref = NotificationPreference.query.filter_by(user_id=user_id).first()
    return True if pref is None else bool(getattr(pref, PREF_FIELD, True))


def empty_basket(user):
    return dict(user=user, alerts=[], deaths=[], eggs_ready=[], monthly=False, rescue_reminders=[])


def basket_is_empty(basket):
    return not (basket['alerts'] or basket['deaths'] or basket['eggs_ready'] or basket['monthly']
                or basket['rescue_reminders'])


def _imie(pet):
    if pet.name:
        return pet.name
    gatunek = SPECIES_BY_SLUG.get(pet.species)
    return gatunek.name if gatunek else 'pupil'


def build_push_text(basket):
    """Jeden zbiorczy push: zdania z podmiotem „Pupil {imię}" (rodzaj gramatyczny zawsze zgodny)."""
    zdania = []
    for pet in basket['deaths']:
        zdania.append(f'Pupil {_imie(pet)} odszedł do gwiazd.')
    for pet, poziom in sorted(basket['alerts'], key=lambda para: -para[1]):
        zdania.append(f'Pupil {_imie(pet)} {_OPIS_POZIOMU[poziom]}.')
    gotowe = len(basket['eggs_ready'])
    if gotowe == 1:
        zdania.append('Jajko gotowe do wyklucia!')
    elif gotowe > 1:
        zdania.append(f'{gotowe} jajka gotowe do wyklucia!' if gotowe < 5 else f'{gotowe} jajek gotowych do wyklucia!')
    if basket['monthly']:
        zdania.append('Czeka na Ciebie nowe jajko!')
    tresc = ' '.join(zdania)
    if len(tresc) > PUSH_BODY_MAX:
        tresc = tresc[:PUSH_BODY_MAX - 1].rstrip() + '…'
    return PUSH_TITLE, tresc


def needs_email(basket):
    """Mail tylko przy krytycznym, odejściu i przypomnieniu o ratunkowym (spec §2.9)."""
    return bool(basket['deaths'] or basket['rescue_reminders']
                or any(poziom == LEVEL_CRITICAL for _, poziom in basket['alerts']))


def pets_url():
    base = (current_app.config.get('BASE_URL') or 'https://thunderorders.cloud').rstrip('/')
    return base + PETS_URL_PATH


def _memorial(pet):
    wiek = rules.age_days(pet.hatched_at, pet.died_at) if pet.hatched_at and pet.died_at else 0
    return {'name': _imie(pet), 'age_days': wiek, 'care_days': int(pet.care_days), 'stars': int(pet.stars),
            'species_name': SPECIES_BY_SLUG[pet.species].name if pet.species in SPECIES_BY_SLUG else ''}


def build_email_message(user, basket):
    """Message (bez wysyłki) albo None, gdy koszyk nie wymaga maila. Wymaga kontekstu żądania
    (prepare_email renderuje szablony; CLI owija komendę _with_request_context)."""
    if not needs_email(basket):
        return None
    from utils.email_sender import prepare_email
    krytyczne = [_imie(pet) for pet, poziom in basket['alerts'] if poziom == LEVEL_CRITICAL]
    odeszly = [_memorial(pet) for pet in basket['deaths']]
    ratunkowe = [_imie(pet) for pet in basket['rescue_reminders']]
    if odeszly:
        temat = f"Pupil {odeszly[0]['name']} odszedł do gwiazd"
    elif krytyczne:
        temat = f'Pupil {krytyczne[0]} potrzebuje pomocy — stan krytyczny'
    else:
        temat = 'Jajko ratunkowe czeka na odebranie'
    return prepare_email(
        to=user.email,
        subject=temat,
        template='pets_alert',
        log_context={'entity_type': 'pet_user', 'entity_id': user.id},
        user_name=user.first_name or None,
        critical=krytyczne,
        dead=odeszly,
        rescue=ratunkowe,
        url=pets_url(),
    )
```

- [ ] **Step 4: Szablony maila**

`templates/emails/pets_alert.html` (układ 1:1 jak `contest_win.html` — logo `cid:logo@thunderorders`,
stopka):

```jinja
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Twoje pupile - ThunderOrders</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; background-color: #F5F5F5; line-height: 1.6;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #F5F5F5; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; width: 100%; background-color: #FFFFFF; border-radius: 8px; overflow: hidden;">

                    <tr>
                        <td align="center" style="padding: 40px 40px 20px 40px;">
                            <img src="cid:logo@thunderorders" alt="ThunderOrders" style="height: 40px; width: auto; display: block;" />
                        </td>
                    </tr>

                    <tr>
                        <td style="padding: 20px 40px;">
                            <div style="text-align: center; font-size: 48px; margin: 20px 0;">
                                {% if dead %}✨{% elif critical %}🩺{% else %}🥚{% endif %}
                            </div>

                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #212121;">
                                {% if user_name %}Cześć <strong>{{ user_name }}</strong>!{% else %}Cześć!{% endif %}
                            </p>

                            {% for p in dead %}
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 16px 0;">
                                <tr>
                                    <td style="background-color: #F5F5F5; padding: 24px; border-radius: 8px;">
                                        <p style="margin: 0 0 8px 0; font-size: 20px; font-weight: 700; color: #240046;">
                                            Pupil {{ p.name }} odszedł do gwiazd
                                        </p>
                                        <p style="margin: 0; font-size: 15px; color: #212121;">
                                            {{ p.species_name }} {{ p.name }} był z Tobą <strong>{{ p.age_days }} dni</strong>,
                                            z czego <strong>{{ p.care_days }}</strong> to dni Twojej opieki{% if p.stars %},
                                            i zdobył {{ p.stars }} {% if p.stars == 1 %}gwiazdkę{% elif p.stars < 5 %}gwiazdki{% else %}gwiazdek{% endif %}{% endif %}.
                                            Dziękujemy, że się nim opiekowałeś.
                                        </p>
                                        <p style="margin: 12px 0 0 0; font-size: 14px; color: #616161;">
                                            W domku czeka już jajko ratunkowe — kiedy będziesz gotowy.
                                        </p>
                                    </td>
                                </tr>
                            </table>
                            {% endfor %}

                            {% if critical %}
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 16px 0;">
                                <tr>
                                    <td style="background-color: #FFF4F4; padding: 24px; border-radius: 8px; border: 1px solid #F5576C;">
                                        <p style="margin: 0 0 8px 0; font-size: 18px; font-weight: 700; color: #B3261E;">
                                            Stan krytyczny: {{ critical | join(', ') }}
                                        </p>
                                        <p style="margin: 0; font-size: 15px; color: #212121;">
                                            {% if critical | length == 1 %}Pupil {{ critical[0] }} potrzebuje pomocy{% else %}Twoje pupile potrzebują pomocy{% endif %} —
                                            bez karmienia i leczenia odejdzie do gwiazd w ciągu kilkunastu godzin.
                                        </p>
                                    </td>
                                </tr>
                            </table>
                            {% endif %}

                            {% if rescue %}
                            <p style="margin: 16px 0; font-size: 15px; color: #212121;">
                                Od tygodnia czeka na Ciebie jajko ratunkowe
                                ({% for n in rescue %}za pupila {{ n }}{% if not loop.last %}, {% endif %}{% endfor %}).
                                Odbierz je, kiedy będziesz gotowy — nic nie przepada.
                            </p>
                            {% endif %}

                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 30px 0;">
                                <tr>
                                    <td align="center">
                                        <a href="{{ url }}" style="display: inline-block; background: linear-gradient(135deg, #7B2CBF 0%, #240046 100%); color: #FFFFFF; text-decoration: none; padding: 16px 40px; border-radius: 8px; font-weight: 700; font-size: 18px; text-align: center;">
                                            Przejdź do pupili
                                        </a>
                                    </td>
                                </tr>
                            </table>

                            <p style="margin: 10px 0 20px 0; font-size: 14px; color: #616161; text-align: center;">
                                Lub przejdź bezpośrednio pod adres:<br>
                                <a href="{{ url }}" style="color: #7B2CBF; text-decoration: underline; font-size: 14px; word-break: break-all;">{{ url }}</a>
                            </p>

                            <p style="margin: 20px 0 0 0; font-size: 13px; color: #9E9E9E;">
                                Powiadomienia o pupilach możesz wyłączyć w profilu (Pupile → Powiadomienia o pupilach).
                            </p>

                            <p style="margin: 20px 0 0 0; font-size: 16px; color: #212121;">
                                Pozdrawiamy,<br>
                                ThunderOrders
                            </p>
                        </td>
                    </tr>

                    <tr>
                        <td style="padding: 30px 40px; background-color: #F5F5F5; border-top: 1px solid #E0E0E0; text-align: center;">
                            <img src="cid:logo@thunderorders" alt="ThunderOrders" style="height: 32px; width: auto; display: block; margin: 0 auto 12px auto;" />
                            <p style="margin: 0; font-size: 12px; color: #9E9E9E;">
                                <a href="https://thunderorders.cloud" style="color: #7B2CBF; text-decoration: none;">thunderorders.cloud</a> |
                                <a href="mailto:noreply@thunderorders.cloud" style="color: #7B2CBF; text-decoration: none;">noreply@thunderorders.cloud</a>
                            </p>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>
```

`templates/emails/pets_alert.txt`:

```jinja
Cześć {{ user_name or '' }}!
{% for p in dead %}
Pupil {{ p.name }} odszedł do gwiazd. {{ p.species_name }} {{ p.name }} był z Tobą {{ p.age_days }} dni, z czego {{ p.care_days }} to dni Twojej opieki{% if p.stars %}, i zdobył {{ p.stars }} gwiazdek{% endif %}. Dziękujemy, że się nim opiekowałeś. W domku czeka już jajko ratunkowe.
{% endfor %}{% if critical %}
Stan krytyczny: {{ critical | join(', ') }} — bez karmienia i leczenia pupil odejdzie do gwiazd w ciągu kilkunastu godzin.
{% endif %}{% if rescue %}
Od tygodnia czeka na Ciebie jajko ratunkowe ({% for n in rescue %}za pupila {{ n }}{% if not loop.last %}, {% endif %}{% endfor %}). Odbierz je, kiedy będziesz gotowy.
{% endif %}
Przejdź do pupili: {{ url }}

Powiadomienia o pupilach możesz wyłączyć w profilu.

Pozdrawiamy,
ThunderOrders
```

- [ ] **Step 5: Uruchom — mają przejść**

Run: `venv/bin/python -m pytest tests/test_pets_cron.py -q`
Expected: `6 passed`. Jeśli `'40 dni'` nie pasuje — sprawdź `age_days(hatched_at, died_at)`
dla `hatched_at = T0 − 40 d`, `died_at = T0` (= 40).

- [ ] **Step 6: Commit**

```bash
git add modules/pets/notifications.py templates/emails/pets_alert.html templates/emails/pets_alert.txt tests/test_pets_cron.py
git commit -m "$(cat <<'EOF'
feat(pupile): tresc powiadomien - zbiorczy push i szablony maila pets_alert

Poziomy z nastroju, zdania z podmiotem "Pupil {imie}" (rodzaj zawsze
zgodny), mail tylko przy krytycznym/odejsciu/ratunkowym, temat wg wagi.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Koszyk per użytkownik — `collect_for_user`

**Files:**
- Modify: `modules/pets/notifications.py` (dopisz `collect_for_user`)
- Test: `tests/test_pets_cron.py` (dopisz)

**Interfaces:**
- Consumes: `common.lock_profile`, `simulate_pet`, `persist_death`, `egg_progress`, `next_monthly_at`;
  `rules.egg_is_ready`; `Pet.query.populate_existing().with_for_update()`.
- Produces: `collect_for_user(user, now, cfg) -> basket` — **pod blokadą profilu, bez commitu**
  (woła przebieg); mutuje `notify_level`, `egg_ready_notified_at`, `monthly_notified_at`, zapisuje
  odejścia; NIE ustawia `death_notified_at` ani `rescue_reminder_sent_at` (to po wysyłce).

- [ ] **Step 1: Failujące testy**

Dopisz do `tests/test_pets_cron.py`:

```python
# --- koszyk ---

def test_poziom_raz_na_epizod_i_reset(db, make_user):
    """Review Focus 2: nakarmiony między przebiegami nie dostaje spóźnionego alertu."""
    from modules.pets.notifications import collect_for_user, LEVEL_SAD, LEVEL_SICK
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, fun=0.0)                        # od T0 zdrowie spada
    k1 = collect_for_user(user, T0 + timedelta(hours=1), _cfg())
    db.session.commit()
    assert k1['alerts'] == [(pet, LEVEL_SAD)] and pet.notify_level == LEVEL_SAD
    k2 = collect_for_user(user, T0 + timedelta(hours=2), _cfg())    # nadal smutny — bez powtórki
    db.session.commit()
    assert k2['alerts'] == []
    k3 = collect_for_user(user, T0 + timedelta(hours=30), _cfg())   # zdrowie ~58 → chory
    db.session.commit()
    assert k3['alerts'] == [(pet, LEVEL_SICK)] and pet.notify_level == LEVEL_SICK
    # użytkownik zadbał: paski pełne, zdrowie wraca; epizod się kończy
    pet.fun = pet.hunger = pet.clean = 100.0
    pet.health = 80.0
    pet.state_at = T0 + timedelta(hours=31)
    db.session.commit()
    k4 = collect_for_user(user, T0 + timedelta(hours=32), _cfg())
    db.session.commit()
    assert k4['alerts'] == [] and pet.notify_level == 0
    # nowy epizod po resecie znów alarmuje od „smutny"
    pet.fun = 0.0
    pet.state_at = T0 + timedelta(hours=33)
    db.session.commit()
    assert collect_for_user(user, T0 + timedelta(hours=34), _cfg())['alerts'] == [(pet, LEVEL_SAD)]


def test_poziom_nie_spada_w_dol_bez_wyzdrowienia(db, make_user):
    from modules.pets.notifications import collect_for_user, LEVEL_CRITICAL
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=0.0, health=20.0)       # krytyczny
    collect_for_user(user, T0 + timedelta(minutes=5), _cfg())
    db.session.commit()
    assert pet.notify_level == LEVEL_CRITICAL
    pet.hunger = 60.0                                         # nakarmiony raz, zdrowie wciąż 20
    pet.state_at = T0 + timedelta(hours=1)
    db.session.commit()
    k = collect_for_user(user, T0 + timedelta(hours=2), _cfg())
    assert k['alerts'] == [] and pet.notify_level == LEVEL_CRITICAL


def test_odejscie_w_cronie_i_odejscie_z_odczytu(db, make_user):
    from modules.pets.notifications import collect_for_user
    from modules.pets.models import PetEvent
    user = make_user()
    zaloz_profil(user)
    w_cronie = zaloz_pupila(user, species='kotek', hunger=0.0)
    z_odczytu = zaloz_zmarlego(user, species='mis', died_at=T0 - timedelta(hours=1))   # death_notified_at None
    k = collect_for_user(user, T0 + timedelta(hours=80), _cfg())
    db.session.commit()
    assert {p.id for p in k['deaths']} == {w_cronie.id, z_odczytu.id}
    assert w_cronie.status == 'dead' and w_cronie.died_at == T0 + timedelta(hours=72)
    assert PetEvent.query.filter_by(pet_id=w_cronie.id, type='die').count() == 1
    assert w_cronie.death_notified_at is None     # oznacza dopiero przebieg po wysyłce


def test_jajko_gotowe_i_miesieczne_raz(db, make_user):
    from modules.pets.notifications import collect_for_user
    user = make_user()
    profil = zaloz_profil(user, now=T0 - timedelta(days=31))
    jajko = zaloz_jajko(user, now=T0 - timedelta(hours=200))
    k1 = collect_for_user(user, T0, _cfg())
    db.session.commit()
    assert k1['eggs_ready'] == [jajko] and k1['monthly'] is True
    assert jajko.egg_ready_notified_at == T0 and profil.monthly_notified_at == T0
    k2 = collect_for_user(user, T0 + timedelta(hours=1), _cfg())
    assert k2['eggs_ready'] == [] and k2['monthly'] is False


def test_miesieczne_po_odbiorze_znow_powiadamia_po_30_dniach(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.notifications import collect_for_user
    user = make_user()
    profil = zaloz_profil(user, now=T0 - timedelta(days=31))
    collect_for_user(user, T0, _cfg())
    db.session.commit()
    claim_egg(user, 'monthly', now=T0, cfg=_cfg())            # czyści monthly_notified_at
    assert profil.monthly_notified_at is None
    assert collect_for_user(user, T0 + timedelta(days=29), _cfg())['monthly'] is False
    assert collect_for_user(user, T0 + timedelta(days=30), _cfg())['monthly'] is True


def test_przypomnienie_o_ratunkowym_po_7_dniach(db, make_user):
    from modules.pets.notifications import collect_for_user
    user = make_user()
    zaloz_profil(user)
    swiezy = zaloz_zmarlego(user, species='kotek', died_at=T0 - timedelta(days=6), death_notified_at=T0 - timedelta(days=6))
    stary = zaloz_zmarlego(user, species='mis', died_at=T0 - timedelta(days=8), death_notified_at=T0 - timedelta(days=8))
    odebrany = zaloz_zmarlego(user, species='piesek', died_at=T0 - timedelta(days=9), death_notified_at=T0 - timedelta(days=9),
                              rescue_egg_claimed_at=T0 - timedelta(days=8))
    k = collect_for_user(user, T0, _cfg())
    assert k['rescue_reminders'] == [stary] and k['deaths'] == []


def test_bez_profilu_koszyk_pusty(db, make_user):
    from modules.pets.notifications import collect_for_user, basket_is_empty
    user = make_user()
    assert basket_is_empty(collect_for_user(user, T0, _cfg()))
```

- [ ] **Step 2: Uruchom — mają paść**

Run: `venv/bin/python -m pytest tests/test_pets_cron.py -q`
Expected: 7 nowych FAIL (`ImportError: cannot import name 'collect_for_user'`).

- [ ] **Step 3: Dopisz `collect_for_user`**

```python
# ---------------------------------------------------------------------------
# Koszyk per użytkownik (spec §3.6 krok 2) — pod blokadą profilu, bez commitu
# ---------------------------------------------------------------------------

def collect_for_user(user, now, cfg):
    """Liczy stan wszystkich pupili użytkownika i zbiera, o czym powiadomić.

    Zapisuje: odejścia (persist_death), podniesione `notify_level`, reset epizodu,
    `egg_ready_notified_at`, `monthly_notified_at`. NIE zapisuje `death_notified_at` ani
    `rescue_reminder_sent_at` — to robi przebieg po wysyłce. Wołający commituje.
    """
    basket = empty_basket(user)
    profil = lock_profile(user, required=False)
    pety = (Pet.query.filter(Pet.user_id == user.id, Pet.status.in_(('egg', 'alive', 'dead')))
            .populate_existing().with_for_update().order_by(Pet.id).all())
    prog_ratunkowe = now - timedelta(days=int(cfg.rescue_reminder_days))

    for pet in pety:
        if pet.status == 'alive':
            sim = simulate_pet(pet, now, cfg)
            if sim.died_at is not None:
                persist_death(pet, sim, now)
                basket['deaths'].append(pet)
                continue
            poziom = level_of(sim.state)
            if poziom > int(pet.notify_level or 0):
                pet.notify_level = poziom
                basket['alerts'].append((pet, poziom))
            elif poziom == 0 and pet.notify_level:
                pet.notify_level = 0          # koniec epizodu: żaden pasek na zerze, zdrowie ≥ 75
        elif pet.status == 'dead':
            if pet.death_notified_at is None:
                basket['deaths'].append(pet)
            if (pet.rescue_egg_claimed_at is None and pet.rescue_reminder_sent_at is None
                    and pet.died_at is not None and pet.died_at <= prog_ratunkowe):
                basket['rescue_reminders'].append(pet)
        else:  # egg
            if pet.egg_ready_notified_at is None and rules.egg_is_ready(egg_progress(pet, now, cfg), pet.egg_hours):
                pet.egg_ready_notified_at = now
                basket['eggs_ready'].append(pet)

    if profil is not None and profil.monthly_notified_at is None and now >= next_monthly_at(profil, cfg):
        profil.monthly_notified_at = now
        basket['monthly'] = True
    return basket
```

- [ ] **Step 4: Uruchom — mają przejść**

Run: `venv/bin/python -m pytest tests/test_pets_cron.py -q`
Expected: `13 passed`. Jeśli `test_poziom_raz_na_epizod_i_reset` pada na k3 (`chory`): sprawdź
rachunek — fun=0 od T0, zdrowie −1,39/h → po 30 h ≈ 58,3 (< 75 → chory) ✓; po resecie k4:
zdrowie 80 + regen (wszystko > 50) → ≥ 75 i brak zera → poziom 0 ✓.

- [ ] **Step 5: Commit**

```bash
git add modules/pets/notifications.py tests/test_pets_cron.py
git commit -m "$(cat <<'EOF'
feat(pupile): collect_for_user - koszyk powiadomien pod blokada profilu

Poziomy raz na epizod z resetem, odejscia z crona i z odczytu, jajko gotowe
i miesieczne raz na dostepnosc, przypomnienie o ratunkowym po 7 dniach.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Przebieg `run_tick`, wysyłka, porządki, komenda CLI

**Files:**
- Modify: `modules/pets/notifications.py` (dopisz `users_to_check`, `prune_events`, `run_tick`)
- Modify: `modules/pets/actions.py` (`anonymize_user_pets`: także `rescue_reminder_sent_at`)
- Modify: `app.py:1382-1400` (grupa `pets` + komenda `tick` obok grupy `achievements`)
- Test: `tests/test_pets_cron.py` (dopisz), `tests/test_pets_anonymize.py` (1 asercja)

**Interfaces:**
- Consumes: `PushManager.send_to_user(user_id, title, body, url, tag, notification_type) -> bool`;
  `utils.email_sender.send_email_batch_sync(messages) -> list[bool]`;
  `EmailManager.is_email_enabled(key)`; `_with_request_context` z `register_cli_commands`.
- Produces: `users_to_check(now, cfg) -> list[User]`, `prune_events(now, days=PRUNE_DAYS) -> int`,
  `run_tick(now=None, cfg=None, dry_run=False) -> dict` z kluczami `users`, `pushes`,
  `emails_prepared`, `emails_sent`, `deaths`, `eggs_ready`, `monthly`, `rescue_reminders`,
  `pruned`, `dry_run`; CLI `flask pets tick [--dry-run]`.

- [ ] **Step 1: Failujące testy**

Dopisz do `tests/test_pets_cron.py`:

```python
# --- przebieg ---

@pytest.fixture
def maile_zebrane(monkeypatch):
    """Przechwytuje send_email_batch_sync (tak jak test_dostawa_cron); domyślnie wszystko „wysłane"."""
    skrzynka = {'wiadomosci': [], 'wynik': None}

    def _sync(messages):
        skrzynka['wiadomosci'].extend(messages)
        return skrzynka['wynik'] if skrzynka['wynik'] is not None else [True] * len(messages)

    monkeypatch.setattr('utils.email_sender.send_email_batch_sync', _sync)
    return skrzynka


def _dzwonek(user_id):
    from modules.notifications.models import Notification
    return Notification.query.filter_by(user_id=user_id, notification_type='pet_updates').all()


def test_tick_jeden_push_na_uzytkownika_i_wpis_w_dzwonku(app, db, make_user, maile_zebrane):
    """Review Focus 1 i 5: bez subskrypcji push i bez wiersza preferencji — wpis w dzwonku, zero wyjątków."""
    from modules.pets.notifications import run_tick
    user = make_user()
    zaloz_profil(user)
    a = zaloz_pupila(user, species='kotek', name='Mruczek', fun=0.0)
    b = zaloz_pupila(user, species='mis', name='Puszek', clean=0.0)
    with app.test_request_context():
        wynik = run_tick(now=T0 + timedelta(hours=1), cfg=_cfg())
    assert wynik['users'] == 1 and wynik['pushes'] == 1 and wynik['emails_prepared'] == 0
    wpisy = _dzwonek(user.id)
    assert len(wpisy) == 1 and 'Mruczek' in wpisy[0].body and 'Puszek' in wpisy[0].body
    assert wpisy[0].url == '/client/pupile' and wpisy[0].tag == 'pets'
    assert maile_zebrane['wiadomosci'] == []


def test_tick_drugi_raz_w_tej_samej_godzinie_nic_nie_dubluje(app, db, make_user, maile_zebrane):
    """Review Focus 4."""
    from modules.pets.notifications import run_tick
    user = make_user()
    zaloz_profil(user)
    zaloz_pupila(user, species='kotek', hunger=0.0, health=10.0)      # krytyczny → push + mail
    zaloz_jajko(user, now=T0 - timedelta(hours=200))
    with app.test_request_context():
        w1 = run_tick(now=T0, cfg=_cfg())
        w2 = run_tick(now=T0 + timedelta(minutes=20), cfg=_cfg())
    assert w1['pushes'] == 1 and w1['emails_prepared'] == 1
    assert w2['pushes'] == 0 and w2['emails_prepared'] == 0 and w2['users'] == 0
    assert len(_dzwonek(user.id)) == 1 and len(maile_zebrane['wiadomosci']) == 1


def test_tick_mail_tylko_krytyczny_odejscie_ratunkowe(app, db, make_user, maile_zebrane):
    from modules.pets.notifications import run_tick
    smutny = make_user()
    zaloz_profil(smutny)
    zaloz_pupila(smutny, fun=0.0)
    krytyczny = make_user()
    zaloz_profil(krytyczny)
    zaloz_pupila(krytyczny, name='Mruczek', hunger=0.0, health=10.0)
    zalobnik = make_user()
    zaloz_profil(zalobnik)
    zmarly = zaloz_zmarlego(zalobnik, name='Puszek', died_at=T0 - timedelta(hours=1))
    with app.test_request_context():
        wynik = run_tick(now=T0 + timedelta(hours=1), cfg=_cfg())
    assert wynik['users'] == 3 and wynik['pushes'] == 3 and wynik['emails_prepared'] == 2 and wynik['emails_sent'] == 2
    odbiorcy = sorted(m.recipients[0] for m in maile_zebrane['wiadomosci'])
    assert odbiorcy == sorted([krytyczny.email, zalobnik.email])
    assert zmarly.death_notified_at == T0 + timedelta(hours=1)


def test_tick_pet_updates_wylaczone_zero_wpisow_i_maili(app, db, make_user, maile_zebrane):
    from modules.notifications.models import NotificationPreference
    from modules.pets.notifications import run_tick
    user = make_user()
    zaloz_profil(user)
    db.session.add(NotificationPreference(user_id=user.id, pet_updates=False))
    db.session.commit()
    pet = zaloz_pupila(user, hunger=0.0, health=10.0)
    with app.test_request_context():
        wynik = run_tick(now=T0 + timedelta(hours=1), cfg=_cfg())
    assert wynik['users'] == 1 and wynik['pushes'] == 0 and wynik['emails_prepared'] == 0
    assert _dzwonek(user.id) == [] and maile_zebrane['wiadomosci'] == []
    assert pet.notify_level == 3            # poziom i tak zapisany — epizod liczy się niezależnie od kanału


def test_tick_kill_switch_maila(app, db, make_user, maile_zebrane):
    from modules.auth.models import Settings
    from modules.pets.notifications import run_tick
    from utils.email_manager import EmailManager
    import json
    Settings.set_value('email_notifications_config', json.dumps({'notify_pet_alert': False}), type='json')
    db.session.commit()
    EmailManager.clear_email_config_cache()
    user = make_user()
    zaloz_profil(user)
    zaloz_pupila(user, hunger=0.0, health=10.0)
    with app.test_request_context():
        wynik = run_tick(now=T0 + timedelta(hours=1), cfg=_cfg())
    assert wynik['pushes'] == 1 and wynik['emails_prepared'] == 0 and maile_zebrane['wiadomosci'] == []


def test_tick_nieudany_mail_ratunkowy_powtarza_sie_odejscie_nie(app, db, make_user, maile_zebrane):
    """Review Focus 3."""
    from modules.pets.notifications import run_tick
    maile_zebrane['wynik'] = [False]
    user = make_user()
    zaloz_profil(user)
    stary = zaloz_zmarlego(user, species='mis', died_at=T0 - timedelta(days=8), death_notified_at=T0 - timedelta(days=8))
    with app.test_request_context():
        w1 = run_tick(now=T0, cfg=_cfg())
    assert w1['emails_prepared'] == 1 and w1['emails_sent'] == 0
    assert stary.rescue_reminder_sent_at is None             # powtórka następnym przebiegiem
    maile_zebrane['wynik'] = None
    with app.test_request_context():
        w2 = run_tick(now=T0 + timedelta(hours=1), cfg=_cfg())
    assert w2['emails_sent'] == 1 and stary.rescue_reminder_sent_at == T0 + timedelta(hours=1)
    # odejście: mail może paść, ale push/dzwonek wyszły → oznaczone
    maile_zebrane['wynik'] = [False]
    zalobnik = make_user()
    zaloz_profil(zalobnik)
    zmarly = zaloz_zmarlego(zalobnik, died_at=T0 + timedelta(hours=1))
    with app.test_request_context():
        run_tick(now=T0 + timedelta(hours=2), cfg=_cfg())
    assert zmarly.death_notified_at == T0 + timedelta(hours=2)


def test_tick_pomija_nieaktywnych_i_nieklientow(app, db, make_user, maile_zebrane):
    from modules.pets.notifications import run_tick
    nieaktywny = make_user()
    zaloz_profil(nieaktywny)
    zaloz_pupila(nieaktywny, fun=0.0)
    nieaktywny.is_active = False
    admin = make_user(role='admin')
    zaloz_profil(admin)
    zaloz_pupila(admin, fun=0.0)
    db.session.commit()
    with app.test_request_context():
        wynik = run_tick(now=T0 + timedelta(hours=1), cfg=_cfg())
    assert wynik['users'] == 0 and _dzwonek(nieaktywny.id) == [] and _dzwonek(admin.id) == []


def test_tick_dry_run_nic_nie_zapisuje(app, db, make_user, maile_zebrane):
    from modules.pets.notifications import run_tick
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=0.0)
    with app.test_request_context():
        wynik = run_tick(now=T0 + timedelta(hours=80), cfg=_cfg(), dry_run=True)
    assert wynik['dry_run'] is True and wynik['deaths'] == 1 and wynik['pushes'] == 0
    db.session.expire_all()
    assert pet.status == 'alive' and pet.notify_level == 0
    assert _dzwonek(user.id) == [] and maile_zebrane['wiadomosci'] == []


def test_prune_events_90_dni_z_wyjatkami(db, make_user):
    from modules.pets.notifications import prune_events
    from modules.pets.models import PetEvent
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user)
    stare = T0 - timedelta(days=91)
    for typ in ('feed', 'pat', 'light', 'warm', 'milestone', 'hatch_new', 'die', 'claim'):
        db.session.add(PetEvent(pet_id=pet.id, user_id=user.id, type=typ, created_at=stare))
    db.session.add(PetEvent(pet_id=pet.id, user_id=user.id, type='feed', created_at=T0 - timedelta(days=89)))
    db.session.commit()
    assert prune_events(T0) == 4
    zostaly = sorted(e.type for e in PetEvent.query.filter_by(pet_id=pet.id).all())
    assert zostaly == ['claim', 'die', 'feed', 'hatch_new', 'milestone']


def test_komenda_cli_pets_tick(app, db, make_user, maile_zebrane):
    user = make_user()
    zaloz_profil(user)
    zaloz_pupila(user, fun=0.0, now=T0 - timedelta(days=400))   # dawno temu → na pewno coś do zgłoszenia
    runner = app.test_cli_runner()
    sucho = runner.invoke(args=['pets', 'tick', '--dry-run'])
    assert sucho.exit_code == 0, sucho.output + str(sucho.exception)
    assert 'dry-run' in sucho.output.lower() and _dzwonek(user.id) == []
    wynik = runner.invoke(args=['pets', 'tick'])
    assert wynik.exit_code == 0, wynik.output + str(wynik.exception)
    assert 'Użytkowników: 1' in wynik.output
```

Dopisz do `tests/test_pets_anonymize.py` w `test_anonymize_user_pets` po asercji o `death_notified_at`:

```python
    assert zywy.rescue_reminder_sent_at == T0 + timedelta(days=1)   # cron nie przypomni o ratunkowym
```

- [ ] **Step 2: Uruchom — mają paść**

Run: `venv/bin/python -m pytest tests/test_pets_cron.py tests/test_pets_anonymize.py -q`
Expected: 10 FAIL w cronie (`ImportError: cannot import name 'run_tick'`/`prune_events`) + 1 w anonimizacji.

- [ ] **Step 3: Dopisz do `notifications.py`**

```python
# ---------------------------------------------------------------------------
# Przebieg crona (spec §3.6)
# ---------------------------------------------------------------------------

def users_to_check(now, cfg):
    """Jedno zapytanie o listę użytkowników, u których może być coś do zgłoszenia (bez yield_per)."""
    from sqlalchemy import and_, or_
    from modules.auth.models import User
    prog_ratunkowe = now - timedelta(days=int(cfg.rescue_reminder_days))
    z_pupilami = db.session.query(Pet.user_id).filter(or_(
        Pet.status.in_(('alive', 'egg')),
        and_(Pet.status == 'dead', Pet.death_notified_at.is_(None)),
        and_(Pet.status == 'dead', Pet.rescue_egg_claimed_at.is_(None),
             Pet.rescue_reminder_sent_at.is_(None), Pet.died_at <= prog_ratunkowe),
    )).distinct()
    z_miesiecznym = db.session.query(PetProfile.user_id).filter(
        PetProfile.monthly_notified_at.is_(None),
        PetProfile.last_monthly_egg_at <= now - timedelta(days=int(cfg.monthly_days)),
    )
    ids = {r[0] for r in z_pupilami.all()} | {r[0] for r in z_miesiecznym.all()}
    if not ids:
        return []
    return (User.query.filter(User.id.in_(ids), User.is_active == True, User.role == 'client')  # noqa: E712
            .order_by(User.id).all())


def prune_events(now, days=PRUNE_DAYS):
    """Porządki: zdarzenia akcji starsze niż `days`; trwałe (claim/grant/hatch/merge/die/rename/milestone) zostają."""
    prog = now - timedelta(days=days)
    usuniete = (PetEvent.query.filter(PetEvent.type.in_(PRUNABLE_EVENT_TYPES), PetEvent.created_at < prog)
                .delete(synchronize_session=False))
    db.session.commit()
    return int(usuniete or 0)


def _wyslij_push(user, basket):
    from utils.push_manager import PushManager
    tytul, tresc = build_push_text(basket)
    if not tresc:
        return False
    # Synchronicznie: _fire_and_forget to wątek daemon, który ginie z procesem CLI
    PushManager.send_to_user(user.id, tytul, tresc, url=PETS_URL_PATH, tag=PUSH_TAG,
                             notification_type=PREF_FIELD)
    return True


def run_tick(now=None, cfg=None, dry_run=False):
    """Godzinny przebieg: koszyki per użytkownik → push → jeden batch maili → flagi → porządki."""
    from utils.email_manager import EmailManager
    now, cfg = now_or(now), cfg_or(cfg)
    wynik = {'users': 0, 'pushes': 0, 'emails_prepared': 0, 'emails_sent': 0, 'deaths': 0,
             'eggs_ready': 0, 'monthly': 0, 'rescue_reminders': 0, 'pruned': 0, 'dry_run': dry_run,
             'koszyki': []}
    maile_wlaczone = EmailManager.is_email_enabled(EMAIL_SWITCH)
    do_wyslania = []   # (user, basket, Message)

    for user in users_to_check(now, cfg):
        basket = collect_for_user(user, now, cfg)
        if basket_is_empty(basket):
            # Mogły zostać zmiany bez powiadomienia (reset epizodu) — zapisujemy je mimo pustego koszyka
            if dry_run:
                db.session.rollback()
            else:
                db.session.commit()
            continue
        wynik['users'] += 1
        wynik['deaths'] += len(basket['deaths'])
        wynik['eggs_ready'] += len(basket['eggs_ready'])
        wynik['monthly'] += int(basket['monthly'])
        wynik['rescue_reminders'] += len(basket['rescue_reminders'])
        if dry_run:
            wynik['koszyki'].append((user.email, build_push_text(basket)[1], needs_email(basket)))
            db.session.rollback()
            continue
        db.session.commit()   # krok 2: zapis poziomów/odejść/flag jajek, zanim cokolwiek wyślemy

        if pet_updates_enabled(user.id):
            if _wyslij_push(user, basket):
                wynik['pushes'] += 1
            if maile_wlaczone and needs_email(basket):
                msg = build_email_message(user, basket)
                if msg is not None:
                    do_wyslania.append((user, basket, msg))
                    wynik['emails_prepared'] += 1
        # Odejście oznaczamy niezależnie od maila/preferencji — inaczej cron próbowałby co godzinę
        for pet in basket['deaths']:
            pet.death_notified_at = now
        db.session.commit()

    if dry_run:
        return wynik

    if do_wyslania:
        from utils.email_sender import send_email_batch_sync   # import w funkcji: testy monkeypatchują moduł
        wyniki = send_email_batch_sync([msg for _, _, msg in do_wyslania])
        for (user, basket, _), ok in zip(do_wyslania, wyniki):
            if ok:
                wynik['emails_sent'] += 1
                for pet in basket['rescue_reminders']:
                    pet.rescue_reminder_sent_at = now   # tylko po udanej wysyłce — jedyny kanał tego przypomnienia
        db.session.commit()

    wynik['pruned'] = prune_events(now)
    return wynik
```

Znaczenie liczników: `pushes` = użytkownicy, dla których zawołano `send_to_user` (wpis w dzwonku
powstaje także bez subskrypcji push); `emails_prepared` = zbudowane wiadomości, `emails_sent` =
potwierdzone przez SMTP.

W `modules/pets/actions.py` w `anonymize_user_pets` rozszerz pierwszy `update(...)`:

```python
    Pet.query.filter_by(user_id=user.id, status='alive').update(
        {'status': 'dead', 'died_at': now, 'notify_level': 4, 'death_notified_at': now,
         'rescue_reminder_sent_at': now},
        synchronize_session='fetch')
```

- [ ] **Step 4: Komenda CLI**

W `app.py`, w `register_cli_commands`, zaraz po grupie `achievements` (po `backfill`) dodaj:

```python
    # ============================================
    # PUPILE (tamagotchi) — cron co godzinę: 10 * * * *
    # ============================================
    @app.cli.group()
    def pets():
        """Pupile: zadania cron (powiadomienia, porządki)."""
        pass

    @pets.command('tick')
    @_with_request_context
    @click.option('--dry-run', is_flag=True, help='Tylko wypisz koszyki, nic nie zapisuj i nie wysyłaj')
    def pets_tick(dry_run):
        """Przebieg powiadomień o pupilach: zbiorczy push + mail per użytkownik, raz na epizod."""
        from modules.pets.notifications import run_tick
        wynik = run_tick(dry_run=dry_run)
        if dry_run:
            click.echo(f'[DRY-RUN] Użytkowników z czymś do zgłoszenia: {wynik["users"]}')
            for email, tresc, mail in wynik['koszyki']:
                click.echo(f'  {email}: {tresc}' + (' [+mail]' if mail else ''))
            return
        click.echo(
            f'Użytkowników: {wynik["users"]}, pushe: {wynik["pushes"]}, '
            f'maile: {wynik["emails_sent"]}/{wynik["emails_prepared"]}, odejścia: {wynik["deaths"]}, '
            f'jajka gotowe: {wynik["eggs_ready"]}, miesięczne: {wynik["monthly"]}, '
            f'przypomnienia o ratunkowym: {wynik["rescue_reminders"]}, porządki: {wynik["pruned"]}'
        )
```

- [ ] **Step 5: Uruchom — mają przejść**

Run: `venv/bin/python -m pytest tests/test_pets_cron.py tests/test_pets_anonymize.py -q`
Expected: `25 passed` (13 + 10 cron + 2 anonimizacja). Pułapki:
- `test_tick_jeden_push…` wymaga `app.test_request_context()` — `prepare_email` nie jest tu wołany,
  ale `send_to_user` loguje przez `current_app`; kontekst aplikacji daje fixture `app`.
- `test_komenda_cli_pets_tick`: `runner.invoke` tworzy własny kontekst; `_with_request_context`
  owija komendę. `'Użytkowników: 1'` — pupil sprzed 400 dni już odszedł (death) → `users == 1`.
- Jeśli `w2['users'] == 0` w teście powtórki pada: `users_to_check` celowo zwraca też użytkowników
  z żywymi pupilami (zawsze), więc `users` liczy tylko **niepuste koszyki** — sprawdź, że `wynik['users']`
  rośnie dopiero po `basket_is_empty(...) is False`.

- [ ] **Step 6: Commit**

```bash
git add modules/pets/notifications.py modules/pets/actions.py app.py tests/test_pets_cron.py tests/test_pets_anonymize.py
git commit -m "$(cat <<'EOF'
feat(pupile): flask pets tick - zbiorczy push, jeden batch maili, porzadki

users_to_check jednym zapytaniem (bez yield_per), koszyk per uzytkownik
z commitem przed wysylka, push synchronicznie po wlasnym sprawdzeniu
pet_updates, maile ze wszystkich uzytkownikow jednym send_email_batch_sync
z kill-switchem notify_pet_alert, death_notified_at zawsze,
rescue_reminder_sent_at tylko po udanej wysylce, prune 90 dni, --dry-run.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Integracja — pełna suita, instrukcja crona

**Files:**
- Create: `docs/superpowers/plans/2026-10-11-pupile-cron-instrukcja.md`

- [ ] **Step 1: Pełna suita** (wynik z pliku, nie przez `| tail`)

Run:
```bash
venv/bin/python -m pytest -q --no-header -p no:cacheprovider > /tmp/pupile_e3.txt 2>&1; echo "RC=$?"; tail -2 /tmp/pupile_e3.txt
```
Expected: `1963 (etap 2) + 3 (preferencje) + 2 (kill-switch) + 23 (cron) = 1991 passed`, 1 failed
(znany DST). Każda inna porażka = stop i diagnoza.

- [ ] **Step 2: Instrukcja crona**

```markdown
# Pupile — instrukcja crona (etap 3)

Komenda: `flask pets tick` (grupa `pets`), co godzinę o :10 — `:00` ma `check-payment-reminders`,
`:05` `check-delivery-confirmations` (limit połączeń SMTP Hostingera per IP).

Na serwerze (konto z dostępem do `/var/www/ThunderOrders`), `crontab -e`, dopisz na końcu:

```
# Pupile (tamagotchi): zbiorcze pushe/maile o stanie pupili, raz na epizod; porządki pet_events (task 869ffdb58)
10 * * * * cd /var/www/ThunderOrders && venv/bin/flask pets tick >> logs/cron-pets.log 2>&1
```

Przed pierwszym uruchomieniem na prodzie: `venv/bin/flask pets tick --dry-run` (wypisuje koszyki,
nic nie zapisuje i nie wysyła). Dopóki `pets_enabled=false`, nikt nie ma pupili, więc przebieg
jest pusty — linię można dopisać od razu po deployu etapu 3.

Co robi przebieg: dla każdego aktywnego klienta z pupilami liczy stan, zapisuje odejścia, wysyła
jeden push (jeśli ma włączone „Powiadomienia o pupilach") i jeden mail przy krytycznym /
odejściu / ratunkowym nieodebranym od 7 dni (jeśli włączony `notify_pet_alert` w ustawieniach
maili admina), kasuje zdarzenia akcji starsze niż 90 dni.
```

- [ ] **Step 3: Kontrole i commit**

- `grep -n "_fire_and_forget" modules/pets/notifications.py` → pusto (push synchroniczny).
- `grep -n "send_email_batch(" modules/pets/notifications.py` → pusto (tylko `_sync`).
- `git log --oneline main..feat/pupile | wc -l` → 28 + 6.

```bash
git add -f docs/superpowers/plans/2026-10-11-pupile-cron-instrukcja.md
git commit -m "$(cat <<'EOF'
docs(pupile): instrukcja crona flask pets tick (10 * * * *)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Raport dla Konrada + ClickUp** (status taska `869ffdb58` zostaje `in progress`; bez pusha).
