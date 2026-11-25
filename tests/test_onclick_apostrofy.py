"""Nazwy z apostrofami nie mogą psuć przycisków onclick.

Błąd z 25.11.2026: produkt „KQ ATEEZ 2027 SEASON'S GREETINGS 'TEEZVERSE'”.
Szablon wstawiał nazwę jako '{{ name|e }}'. Przeglądarka zamienia &#39; z powrotem
na ' jeszcze przed uruchomieniem JS, więc apostrof zamykał napis i powstawał błąd
„missing ) after argument list”. Przez to przycisk „Dodaj do koszyka” nie działał.
"""
import json
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest
from flask import render_template

from modules.offers.models import OfferPage, OfferSection

ROOT = Path(__file__).resolve().parent.parent
NAZWA = "KQ ATEEZ 2027 SEASON'S GREETINGS 'TEEZVERSE' \"x\" </script>"


class _Onclicki(HTMLParser):
    def __init__(self):
        super().__init__()
        self.onclicki = []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k == 'onclick' and v:
                self.onclicki.append(v)  # HTMLParser już rozkodował encje, jak przeglądarka


def _onclicki(html, nazwa_funkcji):
    p = _Onclicki()
    p.feed(html)
    return [o for o in p.onclicki if o.startswith(nazwa_funkcji + '(')]


def _js_przyjmuje(onclick, nazwa_funkcji):
    """Uruchamia onclick w node z atrapą funkcji. Zwraca argumenty jako listę."""
    skrypt = (
        f"let wynik; function {nazwa_funkcji}(...a) {{ wynik = a.slice(0, 3); }}\n"
        f"(function() {{ {onclick} }}).call(null);\n"
        "process.stdout.write(JSON.stringify(wynik));"
    )
    out = subprocess.run(['node', '-e', skrypt], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_szablon_preorder_nie_wstawia_nazwy_w_apostrofach():
    src = (ROOT / 'templates/offers/order_page_preorder.html').read_text(encoding='utf-8')
    assert "'{{ section.product.name" not in src
    assert "'{{ product.name" not in src


@pytest.mark.skipif(shutil.which('node') is None, reason='brak node')
def test_dodaj_do_koszyka_dziala_z_apostrofami_w_nazwie(app, db, make_user, make_product):
    autor = make_user(role='admin', email='autor-apostrof@example.com')
    produkt = make_product(name=NAZWA, sale_price=148.00)
    page = OfferPage(name='Drop', token=OfferPage.generate_token(), status='active',
                     page_type='preorder', created_by=autor.id)
    db.session.add(page)
    db.session.flush()
    sekcja = OfferSection(offer_page_id=page.id, section_type='product', sort_order=0,
                          product_id=produkt.id)
    db.session.add(sekcja)
    db.session.commit()

    with app.test_request_context():
        html = render_template('offers/order_page_preorder.html', page=page,
                               sections=[sekcja], bonuses_config_json='{}')

    onclicki = _onclicki(html, 'addToPreorderCart')
    assert onclicki, 'brak przycisku Dodaj do koszyka'
    for onclick in onclicki:
        args = _js_przyjmuje(onclick, 'addToPreorderCart')
        assert args[0] == produkt.id
        assert args[1] == NAZWA
        assert float(args[2]) == 148.0
    assert '</script> ' not in html.split('addToPreorderCart(', 1)[1].split('>', 1)[0]
