"""Etap 5: widget na dashboardzie i towarzysz — kontekst SSR, gating flagą, celebracja po endpointcie."""
import json

from tests.pets_helpers import zaloz_profil, zaloz_pupila
from tests.test_pets_routes import _wlacz


def _stan_widgetu(html):
    import re
    from html import unescape
    m = re.search(r'id="petsWidget"[^>]*data-state=\'([^\']*)\'', html)
    assert m, 'brak #petsWidget z data-state'
    return json.loads(unescape(m.group(1)))


def test_most_in_need_pet_id_w_stanie(db, make_user):
    from modules.pets.service import state_for_user
    user = make_user()
    zaloz_profil(user)
    szczesliwy = zaloz_pupila(user, species='kotek')
    glodny = zaloz_pupila(user, species='mis', name='Głodek', hunger=20.0)
    _wlacz(db)
    stan = state_for_user(user)
    assert stan['most_in_need_pet_id'] == glodny.id and glodny.id != szczesliwy.id


def test_most_in_need_none_bez_zywych(db, make_user):
    from modules.pets.service import state_for_user
    user = make_user()
    _wlacz(db)
    assert state_for_user(user)['most_in_need_pet_id'] is None


def test_dashboard_widget_tylko_z_flaga(client, login, make_user, db):
    user = make_user(profile_completed=True)
    login(user)
    r = client.get('/client/dashboard')
    assert r.status_code == 200 and b'id="petsWidget"' not in r.data and b'id="petCompanion"' not in r.data
    _wlacz(db)
    r = client.get('/client/dashboard')
    html = r.data.decode()
    assert r.status_code == 200 and 'id="petsWidget"' in html and 'id="petCompanion"' in html
    stan = _stan_widgetu(html)
    assert stan['eggs_available'] == [{'source': 'start'}] and stan['pets'] == [] and stan['most_in_need_pet_id'] is None
    assert 'js/pet/pets-core.js' in html and 'js/pages/client/pets-widget.js' in html
    assert 'data-mode="walk"' in html and 'data-user-id="%d"' % user.id in html


def test_dashboard_widget_to_mini_pokoj(client, login, make_user, db):
    """Spec v3 §7: widget rysuje mini-pokój z room.js (tryb compact); karta pupila (pet-card.js,
    bez wariantu `mini`) nie jest już ładowana na dashboardzie."""
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    html = client.get('/client/dashboard').data.decode()
    assert 'js/pet/world/room.js' in html and 'css/components/pet-room.css' in html
    assert 'js/components/pet-card.js' not in html and 'css/components/pet-card.css' not in html
    # room.js przed skryptem widgetu (widget woła PetRoom.mount przy starcie)
    assert html.index('js/pet/world/room.js') < html.index('js/pages/client/pets-widget.js')


def test_dashboard_widget_z_pupilem(client, login, make_user, db):
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    zaloz_profil(user)
    pet = zaloz_pupila(user, species='kroliczek', name='Puszek', fun=10.0)
    html = client.get('/client/dashboard').data.decode()
    stan = _stan_widgetu(html)
    assert stan['most_in_need_pet_id'] == pet.id and stan['pets'][0]['name'] == 'Puszek'


def test_towarzysz_gosc_na_stronie_oferty_nic_nie_widzi(client, db, strona_sprzedazy):
    # Osobny test (świeża aplikacja): w jednym teście żądanie gościa i późniejsze `login` tego samego
    # procesu dzielą stan uwierzytelnienia (quirk środowiska testowego), więc nie mieszamy ich.
    _wlacz(db)
    r = client.get(f'/offer/{strona_sprzedazy.token}/thank-you')
    assert r.status_code == 200 and b'id="petCompanion"' not in r.data
    assert b'pet-companion.css' not in r.data      # gość nie ładuje CSS towarzysza (minor recenzji)


def test_towarzysz_na_stronie_oferty_siedzi_i_celebruje(client, login, make_user, db, strona_sprzedazy):
    strona = strona_sprzedazy
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    html = client.get(f'/offer/{strona.token}/thank-you').data.decode()
    assert 'id="petCompanion"' in html and 'data-mode="sit"' in html and 'data-celebrate="1"' in html
    assert 'js/pet/pets-core.js' in html and 'js/components/pet-companion.js' in html


def test_towarzysz_bez_celebrate_na_zwyklej_stronie(client, login, make_user, db):
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    html = client.get('/client/dashboard').data.decode()
    assert 'data-celebrate="0"' in html


def test_pet_companion_css_ladowany_na_stronie_bez_super(app, client, login, make_user, db):
    """Recenzja etapu 4 (paczka A): 11 szablonów nadpisuje extra_css bez super() — link musi być poza blokiem."""
    from flask import url_for
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    with app.test_request_context():
        url = url_for('orders.client_list')
    html = client.get(url).data.decode()
    assert 'css/components/pet-companion.css' in html and 'id="petCompanion"' in html


def test_towarzysz_podaje_adres_css_rigu_do_leniwego_ladowania(app, client, login, make_user, db, strona_sprzedazy):
    """Panel i oferty nie ładują pet-rig.css — towarzysz dociąga go sam (leniwie, dopiero gdy ma kogo
    pokazać) i potrzebuje dokładnego adresu z wersją pliku (url_for dokleja ?v=mtime per plik)."""
    import re
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    for url in ('/client/orders', f'/offer/{strona_sprzedazy.token}/thank-you'):
        html = client.get(url, follow_redirects=True).data.decode()
        m = re.search(r'id="petCompanion"[^>]*data-rig-css="([^"]+)"', html, re.S)
        assert m and '/static/css/components/pet-rig.css' in m.group(1), url
        assert '<link rel="stylesheet" href="' + m.group(1) not in html, url   # nie ładujemy go z góry


def test_towarzysz_podaje_adresy_domku_i_szpitala_dla_dymka(client, login, make_user, db):
    """Spec v3 §3.1: link w dymku opieki prowadzi tam, gdzie da się pomóc (domek z panelem / szpital),
    a nie zawsze na mapę świata — JS bierze adresy z data-* (url_for), nie skleja ich na ślepo."""
    import re
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    html = client.get('/client/dashboard').data.decode()
    m = re.search(r'<div class="pet-companion" id="petCompanion"[^>]*>', html, re.S)
    assert m, 'brak #petCompanion'
    tag = m.group(0)
    assert 'data-house-url="/client/pupile/domek"' in tag
    assert 'data-hospital-url="/client/pupile/szpital"' in tag
    assert 'data-ward-url="/client/pupile/szpital/izba-przyjec"' in tag
    assert 'data-home-url="/client/pupile"' in tag


def test_widget_podaje_adresy_sal_szpitala(client, login, make_user, db):
    """Spec v3.1 §5: widget prowadzi prosto do sali (pupil w szpitalu → izba, jajka → inkubatorium)."""
    import re
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    zaloz_profil(user)
    zaloz_pupila(user)
    html = client.get('/client/dashboard').data.decode()
    m = re.search(r'<div class="dashboard-section pets-widget" id="petsWidget"[^>]*>', html, re.S)
    assert m, 'brak #petsWidget'
    tag = m.group(0)
    assert 'data-hospital-url="/client/pupile/szpital"' in tag
    assert 'data-ward-url="/client/pupile/szpital/izba-przyjec"' in tag
    assert 'data-incubator-url="/client/pupile/szpital/inkubatorium"' in tag


# --- Układ dashboardu: widget pupili w rzędzie z „Moimi odznakami” (feedback Konrada 10/2026) ---------

_PUSTE_TAGI = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}


class _Wezel:
    def __init__(self, tag, attrs, rodzic):
        self.tag = tag
        self.attrs = dict(attrs)
        self.rodzic = rodzic
        self.dzieci = []

    def klasy(self):
        return (self.attrs.get('class') or '').split()


def _drzewo(html):
    """Minimalne drzewo DOM na stdlib (bez bs4): węzły z rodzicem i dziećmi, indeks po id
    i kolejność otwarcia. Zamknięcie bez pary jest ignorowane, a zamknięcie tagu głębiej
    w stosie domyka po drodze niedomknięte — wystarcza na nasze szablony."""
    from html.parser import HTMLParser

    class _Parser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.korzen = _Wezel('#root', [], None)
            self.stos = [self.korzen]
            self.po_id = {}
            self.porzadek = []

        def handle_starttag(self, tag, attrs):
            w = _Wezel(tag, attrs, self.stos[-1])
            self.stos[-1].dzieci.append(w)
            self.porzadek.append(w)
            if w.attrs.get('id'):
                self.po_id.setdefault(w.attrs['id'], w)
            if tag not in _PUSTE_TAGI:
                self.stos.append(w)

        def handle_endtag(self, tag):
            for i in range(len(self.stos) - 1, 0, -1):
                if self.stos[i].tag == tag:
                    del self.stos[i:]
                    return

    p = _Parser()
    p.feed(html)
    p.close()
    return p


def test_widget_pupili_na_dole_w_rzedzie_z_odznakami(client, login, make_user, db):
    """Feedback Konrada: widget pupili jest wielkości innych widgetów i dzieli rząd na pół z „Moimi
    odznakami” na dole dashboardu (wcześniej: cała szerokość zaraz pod banerem konkursu)."""
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    zaloz_profil(user)
    zaloz_pupila(user)
    d = _drzewo(client.get('/client/dashboard').data.decode())
    pupile, odznaki = d.po_id['petsWidget'], d.po_id['achievements-widget']
    rzad = pupile.rodzic
    assert rzad is odznaki.rodzic, 'pupile i odznaki muszą stać w jednym wspólnym rzędzie'
    assert rzad.dzieci == [pupile, odznaki]           # pupile z lewej (na telefonie wyżej), odznaki obok
    assert 'dashboard-pair' in rzad.klasy() and 'dashboard-pair--split' in rzad.klasy()
    # Rząd stoi na dole strony: po siatce wykres + „Ostatnie zamówienia”, a nie pod konkursem
    assert 'client-dashboard' in rzad.rodzic.klasy()
    siatka = d.po_id['recentOrdersWidget']
    while 'dashboard-grid' not in siatka.klasy():
        siatka = siatka.rodzic
    sekcje = rzad.rodzic.dzieci
    assert sekcje.index(siatka) < sekcje.index(rzad)
    assert d.porzadek.index(d.po_id['recentOrdersWidget']) < d.porzadek.index(pupile)


def test_odznaki_bez_pupili_na_cala_szerokosc(client, login, make_user, db):
    """Bez widgetu pupili (funkcja wyłączona / poza rolloutem) „Moje odznaki” zostają na całą szerokość."""
    user = make_user(profile_completed=True)
    login(user)
    for wlaczone in (False, True):
        if wlaczone:
            _wlacz(db, pct=0)          # flaga włączona, ale użytkownik poza rolloutem
        d = _drzewo(client.get('/client/dashboard').data.decode())
        assert 'petsWidget' not in d.po_id
        odznaki = d.po_id['achievements-widget']
        assert odznaki.rodzic.dzieci == [odznaki]
        assert 'dashboard-pair--split' not in odznaki.rodzic.klasy()


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
