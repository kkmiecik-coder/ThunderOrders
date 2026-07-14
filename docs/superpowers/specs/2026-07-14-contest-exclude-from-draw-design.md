# Wykluczenie osoby z losowania zwycięzców konkursu

**Data:** 2026-07-14
**Moduł:** `modules/contests`
**Status:** zatwierdzony projekt (do implementacji)

## Cel

Umożliwić adminowi wskazanie w ustawieniach konkursu osób, które **nie mogą zostać
wybrane jako zwycięzcy** w finalnym losowaniu. Wykluczona osoba:

- **normalnie bierze udział** (kręci, zdobywa losy),
- **pojawia się w bębnie/ruletce** na ekranie losowania,
- ale w autorytatywnym wyborze zwycięzców (`draw_winners`) jest **usunięta z ważonej puli**,
  więc na 100% nie zostanie rozlosowana.

## Decyzje (ustalone z Konradem)

1. **Zakres:** lista wielu osób na konkurs (tabela wiele-do-wielu), nie pojedyncze pole.
2. **Wybór osoby:** dowolny użytkownik przez wyszukiwarkę (imię/nazwisko/email).
3. **Widok admina:** wykluczeni pokazani z etykietą „wykluczony" i `0%` szans;
   szanse pozostałych przeliczane z puli **bez** wykluczonych (realne).
4. **Endpoint wyszukiwarki:** reużycie istniejącego `/admin/users/api/search`
   (narzędzie jednoadminowe; moderator bez roli `admin` nie użyje pickera wykluczeń).

## Model danych

Nowa tabela `contest_excluded_users` (styl spójny z `ContestPrize`):

```python
class ContestExcludedUser(db.Model):
    __tablename__ = 'contest_excluded_users'
    id = db.Column(db.Integer, primary_key=True)
    contest_id = db.Column(db.Integer, db.ForeignKey('contests.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)
    user = db.relationship('User', foreign_keys=[user_id])
    __table_args__ = (db.UniqueConstraint('contest_id', 'user_id', name='uq_contest_excluded_user'),)
```

Na modelu `Contest`:

```python
excluded_entries = db.relationship('ContestExcludedUser', backref='contest',
                                   cascade='all, delete-orphan')

@property
def excluded_user_ids(self):
    return {e.user_id for e in self.excluded_entries}
```

**Migracja Flask-Migrate:** `flask db migrate -m "Dodaj wykluczonych z losowania konkursu"`,
weryfikacja wygenerowanego pliku (nowa tabela + FK + unique), `flask db upgrade` lokalnie,
commit migracji z kodem. Uwaga na nazwy FK w MariaDB (patrz reguła projektu o FK/indeksach —
przy tworzeniu tabeli problem nie występuje, dotyczy dropów).

**Dlaczego osobna tabela:** elastyczność (wiele osób), brak migracji przy kolejnych
wykluczeniach, kasowanie kaskadowe przy usunięciu konkursu.

## Logika losowania (`modules/contests/utils.py`)

`participants(contest)` **bez zmian** — nadal zwraca wszystkich uczestników z losami > 0
spełniających eligibility. Dzięki temu bęben/ruletka pokazuje również wykluczonych.

Nowy helper:

```python
def excluded_user_ids(contest):
    from modules.contests.models import ContestExcludedUser
    rows = db.session.query(ContestExcludedUser.user_id) \
        .filter(ContestExcludedUser.contest_id == contest.id).all()
    return {uid for (uid,) in rows}
```

W `draw_winners(contest, rng=None)`:

- `excluded = excluded_user_ids(contest)`,
- `drawable = [(u, t) for (u, t) in participants(contest) if u.id not in excluded]`,
- `initial_pool_total = sum(t for _, t in drawable)` — mianownik szans liczony **bez** wykluczonych,
- `n = min(contest.num_winners, len(drawable))`,
- ważony wybór bez powtórzeń **tylko z `drawable`** (reszta logiki, `_weighted_pick`, bez zmian),
- idempotencja i powiadomienia zwycięzców — bez zmian.

Wykluczona osoba nigdy nie trafi do `ContestWinner`.

Edge cases:
- wszyscy wykluczeni / `drawable` puste → `n = 0`, brak zwycięzców, `status = 'rozlosowany'`
  (zgodne z istniejącym zachowaniem przy braku uczestników);
- `num_winners` > `len(drawable)` → już obsłużone przez `min(...)`.

## Widok admina (`modules/contests/routes.py`)

Zarówno `admin_distribution` (GET `/rozklad`) jak i breakdown w `admin_draw` (POST `/losuj`):

- pobierają `excluded = cu.excluded_user_ids(c)`,
- liczą pulę „do losowania" (suma losów uczestników **bez** wykluczonych) jako mianownik %,
- dla każdego uczestnika zwracają pole `excluded: bool`,
- `chance_pct` / `pct`: `0` dla wykluczonych, w przeciwnym razie `tickets / drawable_pool * 100`.

`pool` całkowity (`cu.get_pool`) pozostaje bez zmian jako liczba informacyjna;
procenty szans liczone są z puli bez wykluczonych.

Ekran losowania `admin_draw_screen` i `participant_names` — **bez zmian** (bęben pokazuje wszystkich).

Frontend admina (rozkład/wynik) oznacza wiersze `excluded` badge'em „wykluczony" (light + dark mode).

## UI ustawień (`templates/admin/contests/form.html`)

Nowa karta **„Wykluczeni z losowania zwycięzców"** (w kolumnie bocznej `aside`, przy „Kryteria udziału"):

- inline wyszukiwarka (input, min. 2 znaki) → `GET /admin/users/api/search?q=...`,
- lista wyników do dodania; wybrani renderowani jako „chipy" z przyciskiem × (usuń),
- stan trzymany w ukrytym polu `excluded_json` (tablica ID użytkowników),
- prefill przy edycji z `contest.excluded_entries` (id + nazwa + email),
- helper: *„Te osoby normalnie biorą udział i pojawiają się w ruletce, ale nie zostaną
  wybrane jako zwycięzcy."*

Bez modala — inline picker w karcie, więc `modals.css` nie jest dotykany.
CSS w `static/css/pages/admin/contests.css` (light + dark mode).
JS dopisany do istniejącego `static/js/pages/admin/contest-form.js`.

## Przetwarzanie po stronie serwera (`modules/contests/routes.py`)

Nowy helper `_apply_excluded(contest)` (wzorzec jak `_apply_prizes`):

- czyta `request.form.get('excluded_json')`, parsuje JSON (tablica ID),
- `contest.excluded_entries.clear()` (cascade delete-orphan usuwa stare wiersze),
- dla każdego ID: waliduje, że użytkownik istnieje (`db.session.get(User, id)`), pomija duplikaty,
- dodaje `ContestExcludedUser(user_id=...)` do `contest.excluded_entries`.

Wywoływany w `admin_new` i `admin_edit` obok `_apply_prizes`.
Prefill do szablonu: serwer przekazuje listę wykluczonych (id/nazwa/email) do `form.html`
(np. przez zmienną kontekstową lub filtr `tojson`), aby JS mógł zbudować chipy przy edycji.

## Bezpieczeństwo / uprawnienia

- Trasy konkursów: `role_required('admin', 'mod')` — bez zmian.
- Wyszukiwarka `/admin/users/api/search`: `@admin_required` — reużyta, świadomie
  (moderator bez roli admin nie skorzysta z pickera; to narzędzie jednoadminowe).
- Walidacja ID użytkowników po stronie serwera (nie ufamy `excluded_json`).

## Testy

- `draw_winners` wyklucza wskazanego usera z puli mimo wysokiej liczby losów (rng wstrzykiwany).
- `initial_pool_total` / `chance_pct` liczone bez wykluczonych (szanse pozostałych realne).
- `n = min(num_winners, len(drawable))` gdy wykluczenia zmniejszają pulę.
- Edge: wszyscy uczestnicy wykluczeni → brak zwycięzców, status `rozlosowany`.
- `participants()` nadal zwraca wykluczonych (bęben ich pokazuje).
- `_apply_excluded` pomija nieistniejących userów i duplikaty; rebuild działa (dodanie/usunięcie).

## Poza zakresem (YAGNI)

- Powiadamianie wykluczonej osoby (ma nie wiedzieć).
- Wykluczanie na poziomie globalnym (per użytkownik, nie per konkurs).
- Historia/audyt zmian listy wykluczeń.
