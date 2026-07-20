"""Testy nowych pól ShippingRequest: materiał, sugestia opakowania, uwagi klienta."""


def test_new_fields_persist(db):
    from modules.orders.models import ShippingRequest
    from modules.orders.wms_models import PackagingMaterial
    mat = PackagingMaterial(name='Karton A', type='karton', sale_price=19.49, size_category='A')
    db.session.add(mat)
    db.session.commit()

    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        packaging_material_id=mat.id,
        client_package_preference='koperta',
        client_notes='Proszę o dodatkowe zabezpieczenie',
        parcel_size='mini',
    )
    db.session.add(sr)
    db.session.commit()
    db.session.refresh(sr)

    assert sr.packaging_material.id == mat.id
    assert sr.packaging_material.sale_price is not None
    assert sr.client_package_preference == 'koperta'
    assert sr.client_notes == 'Proszę o dodatkowe zabezpieczenie'
    assert sr.parcel_size == 'mini'
