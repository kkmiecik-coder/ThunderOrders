"""
Migracja danych czasu polskiego na UTC — konwersja i lista kolumn.
===================================================================

Do gałęzi `feat/czas-utc` baza trzymała chwile jako naiwny czas polski (`get_local_now()`),
a od niej trzyma naiwny UTC (kolumny `UTCDateTime`). Migracja
`migrations/versions/e3b9a6c1d4f7_czas_utc_dane.py` przelicza istniejące wartości funkcjami
z tego modułu, po kolumnach z `KOLUMNY`.

Listy powstały z modeli i ze WSZYSTKICH miejsc zapisu w kodzie sprzed zmiany (commit
`d681efb9`). Produkcja (serwer i sesja MariaDB) chodzi w UTC, więc:
    - kolumna pisana wyłącznie przez `get_local_now()` albo wpisywana przez admina — czas
      polski, konwersja,
    - pisana wyłącznie przez `datetime.now()`, `datetime.utcnow()`, `datetime.now(timezone.utc)`
      albo `db.func.now()` — już UTC, `WYKLUCZONE`,
    - pisana przez jedno i drugie (oznaczone „mieszana") — konwersja; przesunięcie o 1–2 h części
      starych wartości jest świadomie zaakceptowane (decyzja Konrada, spec „runda 2").

Listy są ZAMROŻONE na stan bazy z chwili migracji. Kolumna dodana później jest od początku
w UTC — dopisz ją do `WYKLUCZONE`, nigdy do `KOLUMNY` (test `test_czas_migracja.py` pilnuje,
żeby każda kolumna `UTCDateTime` była w jednej z list).

Zmiany czasu: podwójna jesienna godzina (2:00–2:59 w ostatnią niedzielę października) to
pierwsze wystąpienie (`fold=0`, CEST); nieistniejąca wiosenna (2:00–2:59 w ostatnią niedzielę
marca) liczy się offsetem sprzed zmiany (CET), np. 2:30 -> 1:30 UTC.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PL_TZ = ZoneInfo('Europe/Warsaw')


def pl_naive_to_utc_naive(dt: datetime) -> datetime:
    """Naiwny czas polski -> naiwny UTC (podwójna godzina: pierwsze wystąpienie, `fold=0`)."""
    if dt.tzinfo is not None:
        raise ValueError(f'pl_naive_to_utc_naive: oczekiwano naiwnego czasu polskiego, jest {dt!r}')
    return dt.replace(tzinfo=PL_TZ, fold=0).astimezone(timezone.utc).replace(tzinfo=None)


def utc_naive_to_pl_naive(dt: datetime) -> datetime:
    """Naiwny UTC -> naiwny czas polski (odwrotność do `downgrade()`).

    Drugie wystąpienie jesiennej godziny traci `fold`, więc ponowny upgrade cofa je o 1 h —
    jedyne miejsce, gdzie downgrade + upgrade nie odtwarza wartości.
    """
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

# Tabela -> kolumny już w UTC (bez konwersji). Powód przy każdej.
WYKLUCZONE: dict[str, list[str]] = {
    # default=db.func.now() i onupdate=db.func.now() — czas sesji MariaDB (UTC)
    'cart_items': ['created_at', 'updated_at'],
    # jedyny zapis: csv_processor.py `completed_at = datetime.now()` (wcześniej utcnow)
    'csv_imports': ['completed_at'],
    # default=datetime.now — serwer w UTC
    'offer_section_images': ['created_at'],
    # default=datetime.now — serwer w UTC
    'offer_sections': ['created_at'],
    # default/onupdate=datetime.now(timezone.utc)
    'payment_methods': ['created_at', 'updated_at'],
    # default=db.func.now() — czas sesji MariaDB (UTC)
    'product_interactions': ['created_at'],
    # created_at: default=datetime.utcnow; last_used_at: push_manager `datetime.utcnow()`
    'push_subscriptions': ['created_at', 'last_used_at'],
    # jedyny zapis: api/analytics.py `analytics_consent_date = datetime.now()` (poza NULL przy anonimizacji)
    'users': ['analytics_consent_date'],
}
