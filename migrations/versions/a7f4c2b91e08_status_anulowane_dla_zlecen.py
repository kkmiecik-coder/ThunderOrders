"""Status 'anulowane' dla zleceń wysyłki

Słownik statusów zlecenia nie miał stanu negatywnego, więc jedyną operacją
destrukcyjną było fizyczne skasowanie rekordu — znikał ślad po anulowaniu
(kto, kiedy, dlaczego) i powstawały dziury w numeracji WYS/N (na produkcji
19 dziur przy 62 żywych zleceniach w chwili wprowadzania tej zmiany).

Migracja DANYCH słownikowych, nie schematu: dokłada jeden wiersz do
`shipping_request_statuses`. Idempotentna — pomija wstawienie, gdy slug już
istnieje (np. gdy ktoś dodał go wcześniej ręcznie z panelu ustawień).

Revision ID: a7f4c2b91e08
Revises: 4c3570400e6c
Create Date: 2026-08-21
"""
from alembic import op
import sqlalchemy as sa


revision = 'a7f4c2b91e08'
down_revision = '4c3570400e6c'
branch_labels = None
depends_on = None


# sort_order 9, nie 8: zostawia miejsce na ewentualny stan pośredni przed
# anulowaniem, a jednocześnie trzyma status na końcu listy w panelu.
SLUG = 'anulowane'
NAZWA = 'Anulowane'
KOLOR = '#9E9E9E'
SORT_ORDER = 9


def upgrade():
    polaczenie = op.get_bind()
    istnieje = polaczenie.execute(
        sa.text('SELECT COUNT(*) FROM shipping_request_statuses WHERE slug = :slug'),
        {'slug': SLUG},
    ).scalar()
    if istnieje:
        return

    polaczenie.execute(
        sa.text('''
            INSERT INTO shipping_request_statuses
                (slug, name, badge_color, sort_order, is_active, is_initial,
                 created_at, updated_at)
            VALUES (:slug, :name, :kolor, :sort_order, 1, 0, NOW(), NOW())
        '''),
        {'slug': SLUG, 'name': NAZWA, 'kolor': KOLOR, 'sort_order': SORT_ORDER},
    )


def downgrade():
    polaczenie = op.get_bind()
    # Nie kasujemy statusu, którego używają żywe zlecenia — `shipping_requests.status`
    # to FK na `slug`, więc DELETE wywróciłby się na ograniczeniu, a wcześniej
    # zostawiłby bazę w stanie nie do odtworzenia.
    w_uzyciu = polaczenie.execute(
        sa.text('SELECT COUNT(*) FROM shipping_requests WHERE status = :slug'),
        {'slug': SLUG},
    ).scalar()
    if w_uzyciu:
        raise RuntimeError(
            f'Nie można wycofać migracji: {w_uzyciu} zleceń ma status „{SLUG}". '
            f'Najpierw przenieś je na inny status.'
        )

    polaczenie.execute(
        sa.text('DELETE FROM shipping_request_statuses WHERE slug = :slug'),
        {'slug': SLUG},
    )
