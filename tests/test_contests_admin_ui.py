"""
Testy integracyjne — admin UI dla modułu konkursów.
"""
import pytest


def _admin(make_user):
    return make_user(role='admin')


def test_form_page_renders(client, make_user, login):
    login(_admin(make_user))
    resp = client.get('/admin/konkursy/nowy')
    assert resp.status_code == 200
    assert b'prizeSearch' in resp.data  # picker obecny


def test_list_renders_with_pills(client, db, make_user, make_product, login):
    from modules.contests.models import Contest
    login(_admin(make_user))
    prod = make_product()
    db.session.add(Contest(
        name='Pokaz',
        prize_product_id=prod.id,
        ticket_min=1,
        ticket_max=50,
        status='aktywny',
    ))
    db.session.commit()
    resp = client.get('/admin/konkursy')
    assert resp.status_code == 200
    assert b'Pokaz' in resp.data


def test_draw_screen_renders(client, db, make_user, make_product, login):
    from modules.contests.models import Contest
    login(_admin(make_user))
    prod = make_product()
    c = Contest(name='DoLos', prize_product_id=prod.id, ticket_min=1, ticket_max=50, status='aktywny')
    db.session.add(c)
    db.session.commit()
    resp = client.get(f'/admin/konkursy/{c.id}/losowanie')
    assert resp.status_code == 200
    assert b'btnDraw' in resp.data


def test_list_renders_empty(client, make_user, login):
    """Lista bez żadnych konkursów nie powinna rzucać wyjątku."""
    login(_admin(make_user))
    resp = client.get('/admin/konkursy')
    assert resp.status_code == 200


def test_edit_form_renders_existing(client, db, make_user, make_product, login):
    """Formularz edycji ładuje się z danymi istniejącego konkursu."""
    from modules.contests.models import Contest
    login(_admin(make_user))
    prod = make_product()
    c = Contest(name='EditTest', prize_product_id=prod.id, ticket_min=1, ticket_max=10, status='szkic')
    db.session.add(c)
    db.session.commit()
    resp = client.get(f'/admin/konkursy/{c.id}/edytuj')
    assert resp.status_code == 200
    assert b'EditTest' in resp.data
    assert b'prizeSearch' in resp.data


def test_results_page_renders(client, db, make_user, make_product, login):
    """Strona wyników renderuje się poprawnie (bez zwycięzców)."""
    from modules.contests.models import Contest
    login(_admin(make_user))
    prod = make_product()
    c = Contest(name='WynikTest', prize_product_id=prod.id, ticket_min=1, ticket_max=10, status='rozlosowany')
    db.session.add(c)
    db.session.commit()
    resp = client.get(f'/admin/konkursy/{c.id}/wyniki')
    assert resp.status_code == 200
    assert b'WynikTest' in resp.data
