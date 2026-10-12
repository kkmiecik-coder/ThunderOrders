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
