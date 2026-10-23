"""CLI `resend-reconcile-notifications`: --since/--until to czas polski, porównywany z kolumną UTC."""
import json
from datetime import datetime, timezone


def _log_zmiany(db, order, kiedy_utc):
    from modules.admin.models import ActivityLog

    db.session.add(ActivityLog(
        action='order_status_auto_updated', entity_type='order', entity_id=order.id,
        old_value=json.dumps({'status': 'nowe'}), new_value=json.dumps({'status': order.status}),
        created_at=kiedy_utc,
    ))
    db.session.commit()


def test_since_until_to_czas_polski(app, db, make_user, make_order):
    w_oknie = make_order(make_user())
    poza_oknem = make_order(make_user())
    # 19.09 (CEST, UTC+2): okno 15:39-15:41 czasu polskiego = 13:39-13:41 UTC
    _log_zmiany(db, w_oknie, datetime(2026, 9, 19, 13, 40, tzinfo=timezone.utc))
    # 15:40 UTC = 17:40 w Polsce — poza oknem, choć „15:40" mieści się w nim jako tekst
    _log_zmiany(db, poza_oknem, datetime(2026, 9, 19, 15, 40, tzinfo=timezone.utc))

    wynik = app.test_cli_runner().invoke(args=[
        'resend-reconcile-notifications', '--dry-run',
        '--since', '2026-09-19 15:39:00', '--until', '2026-09-19 15:41:00',
    ])

    assert wynik.exit_code == 0, wynik.output + repr(wynik.exception)
    assert w_oknie.order_number in wynik.output
    assert poza_oknem.order_number not in wynik.output
    assert 'Zamowien do powiadomienia: 1' in wynik.output


def test_zly_format_czasu_to_czytelny_blad(app, db):
    wynik = app.test_cli_runner().invoke(args=[
        'resend-reconcile-notifications', '--dry-run', '--since', '2026-09-19T15:39',
    ])

    assert wynik.exit_code == 2
    assert 'RRRR-MM-DD GG:MM:SS' in wynik.output
    assert not isinstance(wynik.exception, AttributeError)
