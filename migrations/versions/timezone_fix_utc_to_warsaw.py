"""Timezone fix: Convert all datetime fields from UTC to Europe/Warsaw

Revision ID: timezone_fix_001
Revises: 8948dd27c6db
Create Date: 2025-12-27 20:00:00.000000

UWAGA: Ta migracja konwertuje wszystkie istniejące daty w bazie z UTC na czas polski (Europe/Warsaw).
Dodaje +1h (CET) lub +2h (CEST) w zależności od daty.

DST Rules for Poland (Europe/Warsaw):
- CEST (UTC+2): ostatnia niedziela marca 2:00 → ostatnia niedziela października 3:00
- CET (UTC+1): reszta roku

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = 'timezone_fix_001'
down_revision = '8948dd27c6db'
branch_labels = None
depends_on = None


def is_dst(dt):
    """
    Sprawdza czy podana data jest w czasie letnim (CEST) dla Polski.

    Args:
        dt: datetime object or None

    Returns:
        bool: True jeśli CEST (UTC+2), False jeśli CET (UTC+1)
    """
    if not dt or not isinstance(dt, datetime):
        # Jeśli nie ma daty lub typ nieprawidłowy, zakładamy CET (+1h)
        return False

    year = dt.year

    # Ostatnia niedziela marca
    march_last_day = 31
    while datetime(year, 3, march_last_day).weekday() != 6:  # 6 = Sunday
        march_last_day -= 1
    dst_start = datetime(year, 3, march_last_day, 2, 0, 0)  # 2:00 local time (1:00 UTC)

    # Ostatnia niedziela października
    oct_last_day = 31
    while datetime(year, 10, oct_last_day).weekday() != 6:
        oct_last_day -= 1
    dst_end = datetime(year, 10, oct_last_day, 3, 0, 0)  # 3:00 local time (1:00 UTC)

    return dst_start <= dt < dst_end


def upgrade():
    """
    Konwertuje wszystkie datetime pola z UTC na Europe/Warsaw.

    Dodaje +1h (CET) lub +2h (CEST) do wszystkich dat.
    """

    connection = op.get_bind()

    # Lista tabel i ich kolumn datetime do konwersji
    # Format: (table_name, [column_names])
    tables_to_update = [
        # Users & Auth
        ('users', ['last_login', 'created_at', 'updated_at', 'deactivated_at',
                   'password_reset_expires', 'email_verification_code_expires',
                   'email_verification_code_sent_at', 'email_verification_locked_until']),
        ('settings', ['updated_at']),
        ('activity_log', ['created_at']),

        # Orders
        ('orders', ['created_at', 'updated_at', 'shipping_requested_at']),
        ('order_items', ['created_at', 'picked_at']),
        ('order_comments', ['created_at']),
        ('order_refunds', ['completed_at', 'created_at']),
        ('order_shipments', ['created_at', 'shipped_at']),

        # Products
        ('products', ['created_at', 'updated_at']),
        ('product_images', ['uploaded_at']),
        ('stock_orders', ['order_date', 'received_date', 'created_at']),
        ('categories', ['created_at', 'updated_at']),
        ('tags', ['created_at']),
        ('manufacturers', ['created_at', 'updated_at']),
        ('product_series', ['created_at', 'updated_at']),
        ('suppliers', ['created_at', 'updated_at']),

        # Exclusive
        ('exclusive_pages', ['created_at', 'updated_at', 'starts_at', 'ends_at', 'closed_at']),
        # ('exclusive_reservations', ['reserved_at', 'expires_at']),  # Pomiń - używa Unix timestamp zamiast datetime

        # Admin
        ('admin_tasks', ['created_at', 'updated_at', 'due_date', 'completed_at']),
        ('admin_task_assignments', ['assigned_at']),

        # Imports
        ('csv_imports', ['created_at']),

        # Profile
        ('avatars', ['created_at']),
        ('avatar_series', ['created_at']),
    ]

    print("\n🕐 Rozpoczynam konwersję stref czasowych UTC → Europe/Warsaw...")
    print("=" * 70)

    total_updated = 0

    for table_name, columns in tables_to_update:
        # Sprawdź czy tabela istnieje
        result = connection.execute(sa.text(
            f"SHOW TABLES LIKE '{table_name}'"
        ))
        if not result.fetchone():
            print(f"⚠️  Tabela {table_name} nie istnieje - pomijam")
            continue

        for column in columns:
            # Sprawdź czy kolumna istnieje
            result = connection.execute(sa.text(
                f"SHOW COLUMNS FROM {table_name} LIKE '{column}'"
            ))
            if not result.fetchone():
                print(f"⚠️  Kolumna {table_name}.{column} nie istnieje - pomijam")
                continue

            # Pobierz wszystkie rekordy z datą w tej kolumnie
            result = connection.execute(sa.text(
                f"SELECT id, {column} FROM {table_name} WHERE {column} IS NOT NULL"
            ))

            rows = result.fetchall()
            if not rows:
                continue

            updated_count = 0

            # Konwertuj każdy rekord
            for row in rows:
                record_id = row[0]
                utc_datetime = row[1]

                if not utc_datetime:
                    continue

                # Określ offset (+1h lub +2h)
                offset_hours = 2 if is_dst(utc_datetime) else 1

                # SQL: ADDTIME(datetime, 'HH:MM:SS')
                connection.execute(sa.text(
                    f"UPDATE {table_name} SET {column} = ADDTIME({column}, '{offset_hours}:00:00') "
                    f"WHERE id = :id"
                ).bindparams(id=record_id))

                updated_count += 1

            if updated_count > 0:
                print(f"✓ {table_name}.{column}: zaktualizowano {updated_count} rekordów (+{offset_hours}h)")
                total_updated += updated_count

    print("=" * 70)
    print(f"✅ Konwersja zakończona! Łącznie zaktualizowano {total_updated} rekordów.")
    print()


def downgrade():
    """
    Odwraca konwersję - konwertuje z Europe/Warsaw z powrotem na UTC.

    Odejmuje -1h (CET) lub -2h (CEST) od wszystkich dat.
    """

    connection = op.get_bind()

    # Te same tabele co w upgrade()
    tables_to_update = [
        ('users', ['last_login', 'created_at', 'updated_at', 'deactivated_at',
                   'password_reset_expires', 'email_verification_code_expires',
                   'email_verification_code_sent_at', 'email_verification_locked_until']),
        ('settings', ['updated_at']),
        ('activity_log', ['created_at']),
        ('orders', ['created_at', 'updated_at', 'shipping_requested_at']),
        ('order_items', ['created_at', 'picked_at']),
        ('order_comments', ['created_at']),
        ('order_refunds', ['completed_at', 'created_at']),
        ('order_shipments', ['created_at', 'shipped_at']),
        ('products', ['created_at', 'updated_at']),
        ('product_images', ['uploaded_at']),
        ('stock_orders', ['order_date', 'received_date', 'created_at']),
        ('categories', ['created_at', 'updated_at']),
        ('tags', ['created_at']),
        ('manufacturers', ['created_at', 'updated_at']),
        ('product_series', ['created_at', 'updated_at']),
        ('suppliers', ['created_at', 'updated_at']),
        ('exclusive_pages', ['created_at', 'updated_at', 'starts_at', 'ends_at', 'closed_at']),
        # ('exclusive_reservations', ['reserved_at', 'expires_at']),  # Pomiń - używa Unix timestamp zamiast datetime
        ('admin_tasks', ['created_at', 'updated_at', 'due_date', 'completed_at']),
        ('admin_task_assignments', ['assigned_at']),
        ('csv_imports', ['created_at']),
        ('avatars', ['created_at']),
        ('avatar_series', ['created_at']),
    ]

    print("\n🕐 Rozpoczynam odwrócenie konwersji Europe/Warsaw → UTC...")
    print("=" * 70)

    total_updated = 0

    for table_name, columns in tables_to_update:
        # Sprawdź czy tabela istnieje
        result = connection.execute(sa.text(
            f"SHOW TABLES LIKE '{table_name}'"
        ))
        if not result.fetchone():
            continue

        for column in columns:
            # Sprawdź czy kolumna istnieje
            result = connection.execute(sa.text(
                f"SHOW COLUMNS FROM {table_name} LIKE '{column}'"
            ))
            if not result.fetchone():
                continue

            # Pobierz wszystkie rekordy z datą
            result = connection.execute(sa.text(
                f"SELECT id, {column} FROM {table_name} WHERE {column} IS NOT NULL"
            ))

            rows = result.fetchall()
            if not rows:
                continue

            updated_count = 0

            # Konwertuj każdy rekord (odejmij offset)
            for row in rows:
                record_id = row[0]
                poland_datetime = row[1]

                if not poland_datetime:
                    continue

                # Określ offset (-1h lub -2h)
                offset_hours = 2 if is_dst(poland_datetime) else 1

                # SQL: SUBTIME(datetime, 'HH:MM:SS')
                connection.execute(sa.text(
                    f"UPDATE {table_name} SET {column} = SUBTIME({column}, '{offset_hours}:00:00') "
                    f"WHERE id = :id"
                ).bindparams(id=record_id))

                updated_count += 1

            if updated_count > 0:
                print(f"✓ {table_name}.{column}: zaktualizowano {updated_count} rekordów (-{offset_hours}h)")
                total_updated += updated_count

    print("=" * 70)
    print(f"✅ Odwrócenie zakończone! Łącznie zaktualizowano {total_updated} rekordów.")
    print()
