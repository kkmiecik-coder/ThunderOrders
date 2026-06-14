"""
Tests for private OfferPage publish notifications.
Prywatna strona → powiadomienia tylko do audytorium; publiczna → wszyscy klienci.
"""
import pytest


def test_private_audience_recipients(db, make_user, monkeypatch):
    """Dla prywatnej strony odbiorcy email = tylko audytorium z marketing_consent."""
    from modules.offers.models import OfferPage
    from modules.auth.models import UserGroup, User

    owner = User(email='owner@example.com', role='admin', is_active=True, email_verified=True)
    db.session.add(owner)
    db.session.commit()

    member = make_user(email='m@example.com', marketing_consent=True)
    outsider = make_user(email='o@example.com', marketing_consent=True)  # spoza audytorium
    g = UserGroup(name='Aud')
    g.members.append(member)
    db.session.add(g)
    db.session.commit()

    p = OfferPage(
        name='P',
        token=OfferPage.generate_token(),
        status='active',
        is_private=True,
        notify_clients_on_publish=True,
        created_by=owner.id,
    )
    p.allowed_groups.append(g)
    db.session.add(p)
    db.session.commit()

    captured = {}
    from utils.email_manager import EmailManager
    monkeypatch.setattr(
        EmailManager,
        'notify_new_offer_page',
        staticmethod(lambda page, recipients: captured.setdefault('emails', [r.email for r in recipients]) or len(recipients)),
    )
    import utils.push_manager as pm
    monkeypatch.setattr(pm.PushManager, 'notify_new_offer_page', staticmethod(lambda page, ids: None))

    p._send_publish_notifications()

    assert 'm@example.com' in captured['emails']
    assert 'o@example.com' not in captured['emails']


def test_public_audience_unchanged(db, make_user, monkeypatch):
    """Dla publicznej strony - wszyscy klienci z marketing_consent (jak dotad)."""
    from modules.offers.models import OfferPage
    from modules.auth.models import User

    owner = User(email='owner2@example.com', role='admin', is_active=True, email_verified=True)
    db.session.add(owner)
    db.session.commit()

    c1 = make_user(email='c1@example.com', marketing_consent=True)
    c2 = make_user(email='c2@example.com', marketing_consent=True)

    p = OfferPage(
        name='Pub',
        token=OfferPage.generate_token(),
        status='active',
        is_private=False,
        notify_clients_on_publish=True,
        created_by=owner.id,
    )
    db.session.add(p)
    db.session.commit()

    captured = {}
    from utils.email_manager import EmailManager
    monkeypatch.setattr(
        EmailManager,
        'notify_new_offer_page',
        staticmethod(lambda page, recipients: captured.setdefault('emails', sorted(r.email for r in recipients)) or len(recipients)),
    )
    import utils.push_manager as pm
    monkeypatch.setattr(pm.PushManager, 'notify_new_offer_page', staticmethod(lambda page, ids: None))

    p._send_publish_notifications()

    assert 'c1@example.com' in captured['emails']
    assert 'c2@example.com' in captured['emails']
