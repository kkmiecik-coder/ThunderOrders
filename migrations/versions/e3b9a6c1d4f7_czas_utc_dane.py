"""Czas w UTC: przeliczenie zapisanych dat z czasu polskiego na UTC (tylko dane)

Revision ID: e3b9a6c1d4f7
Revises: c7a4d1e9f2b6
Create Date: 2026-10-23

Odwrócenie `timezone_fix_001` (2025-12-27). Kod od tej wersji czyta naiwne wartości
z bazy jako UTC, a dotąd `get_local_now()` zapisywał naiwny czas polski. Migracja
przelicza kolumny z `KOLUMNY` niżej. Schemat bez zmian.

ZAMROŻONA KOPIA: lista kolumn i konwersja są wpisane tutaj (bez importów z aplikacji), żeby
migracja dawała ten sam wynik niezależnie od późniejszych zmian modeli i `utils/`. Po
wdrożeniu NIE EDYTOWAĆ. Lista powstała z modeli i ze wszystkich miejsc zapisu w kodzie sprzed
zmiany (commit `d681efb9`; serwer i sesja MariaDB w UTC):
    - kolumna pisana wyłącznie przez `get_local_now()` albo wpisywana przez admina — czas
      polski, konwersja,
    - pisana wyłącznie zegarem UTC (`datetime.now()`, `utcnow`, `db.func.now()`) — pominięta
      (lista z powodami: `WYKLUCZONE` w `tests/test_czas_migracja.py`),
    - mieszana — konwersja (przesunięcie części starych wartości o 1–2 h zaakceptowane).
Kolumna dodana po tej migracji jest od początku w UTC — dopisuje się ją do `WYKLUCZONE`
w teście, nigdy tutaj.

- wsadami po `WSAD` wierszy według `id` (każdy wiersz dokładnie raz — konwersja nie jest
  idempotentna), jeden UPDATE na wiersz ze wszystkimi kolumnami tabeli naraz,
- NULL zostaje NULL; wartość, która nie jest datetime (np. zerowa data MariaDB), przerywa
  migrację z nazwą tabeli, kolumny i id,
- MariaDB: kolumny z `ON UPDATE CURRENT_TIMESTAMP` spoza listy są przypinane (`kol = kol`),
  żeby UPDATE nie nadpisał ich bieżącym czasem,
- zmiany czasu przez `zoneinfo` (nie stały offset): podwójna jesienna godzina to pierwsze
  wystąpienie (`fold=0`), nieistniejąca wiosenna 2:30 -> 1:30 UTC,
- `downgrade()` to konwersja odwrotna. upgrade + downgrade odtwarza każdą wartość poza
  nieistniejącą wiosenną godziną (2:xx wraca jako 3:xx); downgrade + upgrade — poza drugim
  wystąpieniem jesiennej godziny (wraca 1 h wcześniej). Obie straty są z natury rzeczy.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e3b9a6c1d4f7'
down_revision = 'c7a4d1e9f2b6'
branch_labels = None
depends_on = None

WSAD = 1000
PL_TZ = ZoneInfo('Europe/Warsaw')


def pl_naive_to_utc_naive(dt: datetime) -> datetime:
    """Naiwny czas polski -> naiwny UTC (podwójna godzina: pierwsze wystąpienie, `fold=0`)."""
    if dt.tzinfo is not None:
        raise ValueError(f'pl_naive_to_utc_naive: oczekiwano naiwnego czasu polskiego, jest {dt!r}')
    return dt.replace(tzinfo=PL_TZ, fold=0).astimezone(timezone.utc).replace(tzinfo=None)


def utc_naive_to_pl_naive(dt: datetime) -> datetime:
    """Naiwny UTC -> naiwny czas polski (do `downgrade()`)."""
    if dt.tzinfo is not None:
        raise ValueError(f'utc_naive_to_pl_naive: oczekiwano naiwnego UTC, jest {dt!r}')
    return dt.replace(tzinfo=timezone.utc).astimezone(PL_TZ).replace(tzinfo=None)


# Tabela -> kolumny w czasie polskim do przeliczenia. Każda tabela ma klucz `id`.
KOLUMNY: dict[str, list[str]] = {
    'achievement': ['created_at'],
    'achievement_stat': ['updated_at'],
    'activity_log': ['created_at'],
    'admin_broadcasts': ['created_at'],
    'admin_task_assignments': ['assigned_at'],
    'admin_task_comments': ['created_at'],
    'admin_tasks': ['due_date', 'created_at', 'updated_at', 'completed_at'],   # due_date — wpis admina
    'avatar_series': ['created_at'],
    'avatars': ['created_at'],
    'categories': ['created_at'],
    'collection_item_images': ['uploaded_at'],
    'collection_items': ['created_at', 'updated_at'],
    'collection_temp_uploads': ['uploaded_at'],
    'collection_upload_sessions': ['created_at', 'expires_at'],
    'contest_excluded_users': ['created_at'],
    'contest_spins': ['created_at'],
    'contest_winners': ['drawn_at'],
    'contests': ['starts_at', 'ends_at', 'created_at', 'updated_at'],          # starts_at/ends_at — wpis admina
    'csv_imports': ['created_at'],
    'delivery_reviews': ['created_at', 'updated_at'],
    'email_log': ['created_at', 'sent_at'],
    'feedback_answers': ['created_at'],
    'feedback_questions': ['created_at'],
    'feedback_responses': ['submitted_at'],
    'feedback_surveys': ['closes_at', 'created_at', 'updated_at'],             # closes_at — wpis admina
    'manufacturers': ['created_at', 'updated_at'],
    'mobile_device': ['last_used_at', 'created_at'],                           # last_used_at mieszana (utcnow w push_manager)
    'mobile_idempotency_keys': ['created_at'],
    'mobile_token_blocklist': ['expires_at', 'created_at'],                    # expires_at z JWT przeliczone na Europe/Warsaw
    'notifications': ['created_at'],
    'offer_auto_increase_log': ['triggered_at'],
    'offer_pages': ['starts_at', 'ends_at', 'created_at', 'updated_at', 'closed_at', 'payment_deadline'],
    # ^ starts_at/ends_at/payment_deadline — wpis admina; updated_at i closed_at mieszane (datetime.now())
    'offer_product_notifications': ['notified_at', 'created_at'],
    'offer_set_bonuses': ['created_at'],
    'order_comments': ['created_at'],
    'order_items': ['picked_at', 'created_at'],
    'order_refunds': ['completed_at', 'created_at'],
    'order_shipments': ['created_at'],
    'order_statuses': ['created_at', 'updated_at'],                            # słownik; część wierszy z CURRENT_TIMESTAMP (UTC)
    'order_types': ['created_at', 'updated_at'],                               # j.w.
    'orders': ['shipping_requested_at', 'wms_locked_at', 'packed_at', 'created_at', 'updated_at',
               'status_changed_at', 'pickup_reminder_sent_at'],                # updated_at mieszana (datetime.now())
    'packaging_materials': ['created_at', 'updated_at'],
    'payment_confirmations': ['uploaded_at', 'created_at', 'updated_at'],
    'payment_reminder_configs': ['created_at'],
    'payment_reminder_logs': ['sent_at'],
    'payment_upload_sessions': ['created_at', 'expires_at'],
    'pet_events': ['created_at'],
    'pet_peek_images': ['created_at'],
    'pet_profiles': ['start_egg_claimed_at', 'last_monthly_egg_at', 'monthly_notified_at', 'created_at'],
    'pets': ['egg_progress_at', 'boost_until', 'egg_ready_notified_at', 'hatched_at', 'state_at', 'awake_until',
             'last_heal_at', 'hospital_since', 'hospital_healed_at', 'hospital_ready_notified_at', 'died_at',
             'death_notified_at', 'rescue_egg_claimed_at', 'rescue_reminder_sent_at', 'created_at'],
    'poland_order_item_orders': ['created_at'],
    'poland_order_items': ['created_at'],
    'poland_orders': ['payment_deadline', 'customs_payment_deadline', 'created_at', 'updated_at', 'shipped_at',
                      'delivered_at'],                                         # terminy — wpis admina
    'popup_views': ['created_at'],
    'popups': ['created_at', 'updated_at'],
    'product_images': ['uploaded_at'],
    'product_series': ['created_at', 'updated_at'],
    'product_types': ['created_at'],
    'products': ['created_at', 'updated_at'],                                  # updated_at mieszana (import CSV: datetime.now())
    'proxy_order_items': ['created_at'],
    'proxy_orders': ['order_date', 'expected_delivery_date', 'actual_delivery_date', 'created_at', 'updated_at'],
    'public_collection_configs': ['created_at', 'updated_at'],
    'qr_campaigns': ['created_at', 'updated_at'],
    'qr_visits': ['visited_at'],
    'settings': ['updated_at'],                                                # mieszana (datetime.now() w ustawieniach zleceń)
    'shipping_addresses': ['created_at', 'updated_at'],
    'shipping_request_orders': ['created_at'],
    'shipping_request_statuses': ['created_at', 'updated_at'],                 # mieszane (NOW() z migracji, datetime.now())
    'shipping_requests': ['payment_deadline', 'shipped_at', 'delivered_at', 'delivery_reminder_sent_at',
                          'created_at', 'updated_at'],                         # payment_deadline — wpis admina
    'sizes': ['created_at'],
    'suppliers': ['created_at', 'updated_at'],
    'tags': ['created_at'],
    'user_achievement': ['unlocked_at', 'created_at'],
    'user_group_members': ['added_at'],
    'user_groups': ['created_at', 'updated_at'],
    'users': ['deactivated_at', 'deletion_requested_at', 'password_reset_expires', 'email_verification_code_expires',
              'email_verification_code_sent_at', 'email_verification_locked_until', 'password_reset_code_expires',
              'password_reset_code_sent_at', 'password_reset_locked_until', 'last_login',
              'registration_reminder_sent_at', 'created_at', 'updated_at'],
    'variant_groups': ['created_at', 'updated_at'],
    'variant_products': ['added_at'],
    'wms_session_orders': ['picking_started_at', 'picking_completed_at', 'packing_completed_at'],
    'wms_sessions': ['phone_connected_at', 'desktop_connected_at', 'created_at', 'completed_at'],
    'wms_statuses': ['created_at', 'updated_at'],                              # słownik; część wierszy z CURRENT_TIMESTAMP (UTC)
}


def upgrade():
    _przelicz(pl_naive_to_utc_naive, 'czas polski -> UTC')


def downgrade():
    _przelicz(utc_naive_to_pl_naive, 'UTC -> czas polski')


def _przelicz(konwersja, opis):
    polaczenie = op.get_bind()
    inspektor = sa.inspect(polaczenie)
    print(f'Migracja czasu ({opis}) — przeliczone wartości per kolumna:')
    for tabela, kolumny in KOLUMNY.items():
        klucz = inspektor.get_pk_constraint(tabela)['constrained_columns']
        if klucz != ['id']:
            raise RuntimeError(f'{tabela}: klucz główny {klucz}, migracja obsługuje tylko `id`')
        przypiete = _kolumny_on_update(polaczenie, tabela, kolumny)
        liczniki = _przelicz_tabele(polaczenie, tabela, kolumny, przypiete, konwersja)
        for kolumna in kolumny:
            print(f'  {tabela}.{kolumna}: {liczniki[kolumna]}')
        if przypiete:
            print(f'  ({tabela}: bez zmian ON UPDATE {", ".join(przypiete)})')


def _kolumny_on_update(polaczenie, tabela, kolumny):
    """Kolumny MariaDB z `ON UPDATE CURRENT_TIMESTAMP`, których migracja sama nie ustawia."""
    if polaczenie.dialect.name not in ('mysql', 'mariadb'):
        return []
    wynik = polaczenie.execute(sa.text(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tabela AND LOWER(EXTRA) LIKE '%on update%'"
    ), {'tabela': tabela})
    return [nazwa for (nazwa,) in wynik if nazwa not in kolumny]


def _przelicz_tabele(polaczenie, tabela, kolumny, przypiete, konwersja):
    t = sa.table(tabela, sa.column('id', sa.Integer),
                 *(sa.column(k, sa.DateTime) for k in [*kolumny, *przypiete]))
    zapytanie = (sa.select(t.c.id, *(t.c[k] for k in kolumny))
                 .where(sa.or_(*(t.c[k].isnot(None) for k in kolumny)))
                 .order_by(t.c.id)
                 .limit(WSAD))
    aktualizacja = (sa.update(t)
                    .where(t.c.id == sa.bindparam('_id'))
                    .values({**{t.c[k]: sa.bindparam(f'_n_{k}') for k in kolumny},
                             **{t.c[k]: t.c[k] for k in przypiete}}))

    liczniki = dict.fromkeys(kolumny, 0)
    ostatnie_id = None
    while True:
        wsad = zapytanie if ostatnie_id is None else zapytanie.where(t.c.id > ostatnie_id)
        wiersze = polaczenie.execute(wsad).all()
        if not wiersze:
            return liczniki
        parametry = []
        for wiersz in wiersze:
            nowe = {'_id': wiersz[0]}
            for kolumna, wartosc in zip(kolumny, wiersz[1:]):
                if wartosc is not None:
                    if not isinstance(wartosc, datetime):
                        raise RuntimeError(f'{tabela}.{kolumna} id={wiersz[0]}: {wartosc!r} to nie datetime')
                    wartosc = konwersja(wartosc)
                    liczniki[kolumna] += 1
                nowe[f'_n_{kolumna}'] = wartosc
            parametry.append(nowe)
        polaczenie.execute(aktualizacja, parametry)
        ostatnie_id = wiersze[-1][0]
