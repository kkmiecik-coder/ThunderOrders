"""Klient przy tworzeniu zlecenia zapisuje sugestię opakowania i uwagi."""


def _addr(user, db):
    from modules.auth.models import ShippingAddress
    a = ShippingAddress(user_id=user.id, address_type='home', shipping_name='Jan',
                        shipping_address='Główna 1', shipping_postal_code='00-001',
                        shipping_city='Warszawa', is_active=True)
    db.session.add(a); db.session.commit()
    return a


def _order_ready(user, db, make_order):
    # status dozwolony do zlecenia; make_order tworzy zamówienie z customs_vat_sale_cost=0,
    # więc is_customs_vat_settled (property) zwraca True automatycznie — nie ustawiaj go ręcznie.
    return make_order(user, status='dostarczone_gom')


def test_create_saves_preference_and_notes(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    u = make_user()
    a = _addr(u, db)
    o = _order_ready(u, db, make_order)
    ok, err, req = validate_and_create_request(
        u, [o.id], a.id,
        client_package_preference='koperta',
        client_notes='Delikatna zawartość',
    )
    assert ok, err
    assert req.client_package_preference == 'koperta'
    assert req.client_notes == 'Delikatna zawartość'


def test_create_rejects_invalid_preference(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    u = make_user()
    a = _addr(u, db)
    o = _order_ready(u, db, make_order)
    ok, err, req = validate_and_create_request(
        u, [o.id], a.id, client_package_preference='paczka', client_notes='x' * 5000)
    assert ok
    assert req.client_package_preference is None       # spoza {karton,koperta} → None
    assert len(req.client_notes) <= 2000               # przycięte
