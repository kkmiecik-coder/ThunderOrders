# Walidacja produktu-kompletu — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nie pozwolić zapisać strony ofertowej, w której produkt-komplet setu jest już przypisany do innej strony, i przestać przepisywać produkt-komplet przy duplikowaniu strony.

**Architecture:** Jedna nowa funkcja walidująca w `modules/admin/offers.py`, wołana raz na cały zapis sekcji (musi widzieć wszystkie sekcje naraz, żeby wykryć kolizję wewnątrz jednego żądania). Zgłasza `ValueError` z czytelnym komunikatem — tą samą drogą, którą już płyną pozostałe błędy walidacji sekcji. Druga, jednoliniowa zmiana w `offers_duplicate()`.

**Tech Stack:** Flask, SQLAlchemy, pytest. Testy na SQLite z wymuszonymi kluczami obcymi (patrz `tests/conftest.py`).

**Spec:** `docs/superpowers/specs/2026-09-21-walidacja-produktu-kompletu-design.md`

## Global Constraints

- Gałąź robocza: `fix/walidacja-produktu-kompletu`. **Nie wypychać niczego na GitHuba** — Karolina zatwierdza każdy push osobno.
- Testy uruchamiać przez `python -m pytest` (nie samo `pytest`).
- Komunikaty błędów po polsku, w cudzysłowach drukarskich „…", zwracane jako `ValueError`.
- Komentarze i nazwy zmiennych po polsku, zgodnie z resztą pliku.
- Nie ruszać schematu bazy — żadnych migracji.
- Nie zmieniać walidacji zwykłych produktów (`OfferSection.product_id`, `OfferSetItem.product_id`).

---

### Task 1: Walidacja unikalności produktu-kompletu

**Files:**
- Create: `tests/test_offers_produkt_komplet.py`
- Modify: `modules/admin/offers.py` — nowa funkcja `_validate_set_products_unique()` przed `_update_sections()` (ok. linii 626) oraz jej wywołanie na początku `_update_sections()` (ok. linii 636)

**Interfaces:**
- Consumes: `OfferPage`, `OfferSection`, `Product`, `db` — wszystkie już zaimportowane na górze `modules/admin/offers.py` (linie 11-13).
- Produces: `_validate_set_products_unique(page, sections_data) -> None`. `page` to obiekt `OfferPage`, `sections_data` to lista słowników z frontendu. Zgłasza `ValueError` z komunikatem po polsku przy kolizji; przy braku kolizji nie zwraca nic.

- [ ] **Step 1: Napisz testy, które mają nie przejść**

Utwórz `tests/test_offers_produkt_komplet.py`:

```python
"""
Unikalność produktu-kompletu (set_product_id) w sekcjach setu.

Ten sam produkt-komplet przypisany do dwóch stron ofertowych to zawsze błąd.
Tak powstał przypadek, w którym strona „Whos fans" wskazywała na OT8 z albumu
„Jump up": lista „Do zamówienia" agreguje po produkcie ponad stronami, więc
zsumowała dwie sztuki jednego OT8 i u dostawcy poszło zamówienie na zły album.
"""
import pytest


@pytest.fixture
def owner(make_user):
    """OfferPage.created_by jest NOT NULL."""
    return make_user(role='admin', email='owner@example.com', profile_completed=True)


@pytest.fixture
def make_page(db, owner):
    def _make(name):
        from modules.offers.models import OfferPage
        p = OfferPage(
            name=name,
            token=OfferPage.generate_token(),
            status='draft',
            created_by=owner.id,
        )
        db.session.add(p)
        db.session.commit()
        return p
    return _make


@pytest.fixture
def make_set_section(db):
    def _make(page, set_product_id, set_name='Set'):
        from modules.offers.models import OfferSection
        s = OfferSection(
            offer_page_id=page.id,
            section_type='set',
            sort_order=0,
            set_name=set_name,
            set_product_id=set_product_id,
        )
        db.session.add(s)
        db.session.commit()
        return s
    return _make


def _dane_sekcji_set(set_product_id, section_id=None, set_name='Set'):
    """Payload sekcji-setu w formacie, jaki przysyła page builder."""
    return {
        'id': section_id,
        'type': 'set',
        'set_name': set_name,
        'set_product_id': set_product_id,
        'set_items': [],
    }


def test_produkt_komplet_zajety_przez_inna_strone(app, db, make_page, make_product, make_set_section):
    """Kolizja z inną stroną: komunikat musi wskazać, gdzie szukać konfliktu."""
    from modules.admin.offers import _update_sections
    ot8 = make_product(name='GH5 - Jump up 1.0 (Album) Photobook ver - OT8')
    strona_a = make_page('Ateez GH5 - Jump up 1.0 (album) photobook ver')
    make_set_section(strona_a, ot8.id)
    strona_b = make_page('Ateez GH5 - Whos fans 1.0 (album) cheek heart ver')

    with pytest.raises(ValueError) as blad:
        _update_sections(strona_b, [_dane_sekcji_set(ot8.id)])

    komunikat = str(blad.value)
    assert 'Jump up 1.0 (album) photobook ver' in komunikat
    assert 'GH5 - Jump up 1.0 (Album) Photobook ver - OT8' in komunikat


def test_produkt_komplet_w_dwoch_setach_tej_samej_strony(app, db, make_page, make_product):
    """Kolizja wewnątrz jednego żądania — sekcje jeszcze nie istnieją w bazie."""
    from modules.admin.offers import _update_sections
    ot8 = make_product(name='GH5 - Jump up 1.0 (Album) Photobook ver - OT8')
    strona = make_page('Strona z dwoma setami')

    with pytest.raises(ValueError) as blad:
        _update_sections(strona, [
            _dane_sekcji_set(ot8.id, set_name='Set A'),
            _dane_sekcji_set(ot8.id, set_name='Set B'),
        ])

    assert 'dwóch setach' in str(blad.value)


def test_ponowny_zapis_wlasnej_strony_przechodzi(app, db, make_page, make_product, make_set_section):
    """Sekcja nie może blokować się na własnym produkcie-komplecie."""
    from modules.admin.offers import _update_sections
    ot8 = make_product(name='GH5 - Jump up 1.0 (Album) Photobook ver - OT8')
    strona = make_page('Ateez GH5 - Jump up 1.0 (album) photobook ver')
    sekcja = make_set_section(strona, ot8.id)

    _update_sections(strona, [_dane_sekcji_set(ot8.id, section_id=sekcja.id)])
    db.session.commit()

    assert sekcja.set_product_id == ot8.id


def test_sety_bez_produktu_kompletu_nie_koliduja(app, db, make_page):
    """Puste set_product_id nie jest kolizją — wiele setów może go nie mieć."""
    from modules.admin.offers import _update_sections
    strona = make_page('Strona bez kompletów')

    _update_sections(strona, [
        _dane_sekcji_set(None, set_name='Set A'),
        _dane_sekcji_set(None, set_name='Set B'),
    ])
    db.session.commit()

    assert strona.sections.count() == 2
```

- [ ] **Step 2: Uruchom testy i sprawdź, że padają**

Run: `python -m pytest tests/test_offers_produkt_komplet.py -v`

Expected: `test_produkt_komplet_zajety_przez_inna_strone` i `test_produkt_komplet_w_dwoch_setach_tej_samej_strony` padają na `Failed: DID NOT RAISE <class 'ValueError'>`. Dwa pozostałe testy przechodzą już teraz — to zamierzone, pilnują, żeby nowa walidacja nie zaczęła blokować poprawnych zapisów.

- [ ] **Step 3: Dopisz funkcję walidującą**

W `modules/admin/offers.py`, bezpośrednio **przed** `def _update_sections(page, sections_data):`:

```python
def _validate_set_products_unique(page, sections_data):
    """
    Pilnuje, żeby jeden produkt-komplet nalezal do dokladnie jednej sekcji setu.

    W danych nie ma nic, co wiazaloby produkt-komplet z albumem: produkty roznych
    albumow maja te sama serie, kategorie, producenta i typ, a grupa wariantowa nie
    trzyma odniesienia do swojego OT8. Jedyna pewna regula jest strukturalna —
    ten sam produkt-komplet na dwoch stronach to zawsze pomylka (zwykle niedokonczona
    edycja po zduplikowaniu strony). Kosztuje to tyle, ze lista „Do zamowienia"
    agreguje po produkcie PONAD stronami, wiec taka pomylka konczy sie zlym
    zamowieniem u dostawcy.

    Args:
        page: OfferPage, ktora wlasnie jest zapisywana
        sections_data: lista danych sekcji z frontendu

    Raises:
        ValueError: gdy produkt-komplet jest uzyty dwa razy
    """
    # Sekcje setu z wybranym produktem-kompletem: [(id sekcji lub None, id produktu)]
    wybrane = []
    for section_data in sections_data:
        if section_data.get('type') != 'set':
            continue
        set_product_id = section_data.get('set_product_id')
        if set_product_id:
            wybrane.append((section_data.get('id'), int(set_product_id)))

    if not wybrane:
        return

    def _nazwa_produktu(product_id):
        produkt = db.session.get(Product, product_id)
        return produkt.name if produkt else f'#{product_id}'

    # 1. Kolizja w obrebie zapisywanej strony — sekcje moga jeszcze nie istniec
    #    w bazie, wiec porownujemy same przychodzace dane.
    widziane = set()
    for _, set_product_id in wybrane:
        if set_product_id in widziane:
            raise ValueError(
                f'Produkt-komplet „{_nazwa_produktu(set_product_id)}" jest wybrany '
                'w dwóch setach na tej stronie. Każdy komplet może należeć tylko '
                'do jednego setu.'
            )
        widziane.add(set_product_id)

    # 2. Kolizja z inna strona. Sekcje tej samej strony pomijamy: albo wlasnie je
    #    zapisujemy, albo zostana skasowane na koncu _update_sections().
    kolizja = db.session.query(OfferSection, OfferPage).join(
        OfferPage, OfferPage.id == OfferSection.offer_page_id
    ).filter(
        OfferSection.set_product_id.in_([pid for _, pid in wybrane]),
        OfferSection.offer_page_id != page.id,
    ).first()

    if kolizja:
        sekcja, strona_kolidujaca = kolizja
        raise ValueError(
            f'Produkt-komplet „{_nazwa_produktu(sekcja.set_product_id)}" jest już '
            f'użyty na stronie „{strona_kolidujaca.name}". Każdy komplet może '
            'należeć tylko do jednej strony.'
        )
```

- [ ] **Step 4: Wepnij wywołanie w zapis sekcji**

W `modules/admin/offers.py`, w `_update_sections()`, zaraz po docstringu a przed `# Pobierz istniejące sekcje`:

```python
    # Unikalnosc produktu-kompletu sprawdzamy raz dla calego zapisu, a nie per
    # sekcja — kolizja moze byc miedzy dwiema sekcjami tego samego zadania.
    _validate_set_products_unique(page, sections_data)

    # Pobierz istniejące sekcje
```

- [ ] **Step 5: Uruchom testy i sprawdź, że przechodzą**

Run: `python -m pytest tests/test_offers_produkt_komplet.py -v`

Expected: 4 passed.

- [ ] **Step 6: Uruchom testy stron ofertowych, żeby nic nie pękło**

Run: `python -m pytest tests/test_admin_offers_split.py tests/test_client_offer_filter.py tests/test_offers_bulk_report.py -v`

Expected: wszystkie przechodzą.

- [ ] **Step 7: Commit**

```bash
git add tests/test_offers_produkt_komplet.py modules/admin/offers.py
git commit -m "fix(offers): jeden produkt-komplet moze nalezec tylko do jednej strony

Lista \"Do zamowienia\" agreguje po produkcie ponad stronami, wiec ten sam
produkt-komplet na dwoch stronach konczy sie zlym zamowieniem u dostawcy.
Walidacja lapie kolizje miedzy stronami i w obrebie jednego zapisu.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Duplikowanie strony nie przepisuje produktu-kompletu

**Files:**
- Modify: `modules/admin/offers.py:1652` — w `offers_duplicate()`, w konstruktorze `OfferSection`
- Modify: `tests/test_offers_produkt_komplet.py` — dopisz test na końcu pliku

**Interfaces:**
- Consumes: `_validate_set_products_unique()` z Task 1 nie jest tu wołana — duplikowanie tworzy sekcje bezpośrednio, z pominięciem `_update_sections()`. Dlatego czyszczenie pola jest konieczne: bez niego kopia rodziłaby się z kolizją.
- Produces: nic — zmiana zamknięta w `offers_duplicate()`.

- [ ] **Step 1: Napisz test, który ma nie przejść**

Dopisz na końcu `tests/test_offers_produkt_komplet.py`:

```python
def test_duplikowanie_strony_czysci_produkt_komplet(
    app, db, client, login, owner, make_page, make_product, make_set_section
):
    """
    Kopia nie dziedziczy produktu-kompletu — to tu powstal blad z OT8.

    Pozostale pola sekcji maja sie skopiowac normalnie, wiec test pilnuje takze
    grupy wariantowej: czyscimy jedno pole, nie kaleczymy calego duplikowania.
    """
    from modules.offers.models import OfferPage, OfferSetItem
    from modules.products.models import VariantGroup

    grupa = VariantGroup(name='GH5 Jump up 1.0 Photobook ver')
    db.session.add(grupa)
    db.session.commit()

    ot8 = make_product(name='GH5 - Jump up 1.0 (Album) Photobook ver - OT8')
    strona = make_page('Ateez GH5 - Jump up 1.0 (album) photobook ver')
    sekcja = make_set_section(strona, ot8.id)
    db.session.add(OfferSetItem(
        section_id=sekcja.id,
        variant_group_id=grupa.id,
        quantity_per_set=1,
        sort_order=0,
    ))
    db.session.commit()

    login(owner)
    odpowiedz = client.post(f'/admin/offers/{strona.id}/duplicate')
    assert odpowiedz.status_code in (200, 302)

    kopia = OfferPage.query.filter(
        OfferPage.name.like('%(kopia)')
    ).one()
    sekcja_kopii = kopia.sections.first()

    assert sekcja_kopii.set_product_id is None
    assert sekcja_kopii.get_set_items_ordered()[0].variant_group_id == grupa.id
```

- [ ] **Step 2: Uruchom test i sprawdź, że pada**

Run: `python -m pytest tests/test_offers_produkt_komplet.py::test_duplikowanie_strony_czysci_produkt_komplet -v`

Expected: FAIL na `assert sekcja_kopii.set_product_id is None` — kopia dostaje id produktu zamiast `None`.

- [ ] **Step 3: Przestań kopiować produkt-komplet**

W `modules/admin/offers.py`, w `offers_duplicate()`, w konstruktorze `OfferSection` zamień linię:

```python
            set_product_id=section.set_product_id,
```

na:

```python
            # Produkt-komplet celowo NIE jest kopiowany: kazdy moze nalezec tylko
            # do jednej strony (_validate_set_products_unique). Kopia z przepisanym
            # OT8 nie przeszlaby zapisu, a gdy ktos podmieni same produkty setu
            # i zapomni o tym polu, blad idzie dalej — tak powstal przypadek
            # „Whos fans" wskazujacego na OT8 z „Jump up".
            set_product_id=None,
```

- [ ] **Step 4: Uruchom test i sprawdź, że przechodzi**

Run: `python -m pytest tests/test_offers_produkt_komplet.py -v`

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_offers_produkt_komplet.py modules/admin/offers.py
git commit -m "fix(offers): duplikowanie strony nie przepisuje produktu-kompletu

Kopia strony dostawala stary produkt-komplet, wiec przy podmianie produktow
setu latwo bylo go przeoczyc. Teraz pole zostaje puste i trzeba wybrac
swiadomie — walidacja i tak wymaga go przy setach z grupami wariantowymi.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Pełny przebieg testów

**Files:** brak zmian — wyłącznie weryfikacja.

**Interfaces:**
- Consumes: efekt Task 1 i Task 2.
- Produces: nic.

- [ ] **Step 1: Uruchom cały zestaw testów**

Run: `python -m pytest -q`

Expected: brak nowych błędów względem stanu sprzed zmian. Jeśli coś pada, sprawdź najpierw, czy pada także na `main` — projekt bywa przełączany między gałęziami przez Konrada.

- [ ] **Step 2: Zgłoś wynik Karolinie**

Podaj liczbę testów, które przeszły, i ewentualne błędy. **Nie wypychaj niczego na GitHuba** — Karolina decyduje o każdym pushu osobno.
