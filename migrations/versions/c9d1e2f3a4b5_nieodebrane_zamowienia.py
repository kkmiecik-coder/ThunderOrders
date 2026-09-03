"""Kolumny pod listę nieodebranych zamówień.

`orders.status_changed_at` — moment wejścia w obecny status; źródło kolumny
„leży X dni". Nullable i BEZ backfillu: dla zamówień sprzed wdrożenia wiek liczy
się z `activity_log`, a wpisanie im tu daty migracji byłoby cichym kłamstwem
(wszystkie zaległości wyglądałyby na świeże).

`orders.pickup_reminder_sent_at` — kiedy ostatnio poszło przypomnienie o odbiorze.
Nullable, bo przed wdrożeniem żadne nie poszło.

`ix_activity_log_entity` — fallback wieku zaległości (`wiek_zaleglosci` w
unclaimed_service.py) filtruje `activity_log` po `action` + `entity_type` +
`entity_id IN (...)` przy KAŻDYM otwarciu ekranu „Nieodebrane". Bez indeksu to
pełny skan tabeli, która rośnie z każdą akcją w systemie — ten sam wzorzec co
`ix_email_log_entity` na `email_log`. UWAGA dla wdrażającego: `activity_log` na
produkcji jest już spora (rośnie od dawna, na bieżąco), więc `CREATE INDEX` na
MariaDB przy tej migracji sam w sobie potrwa — nie jest to natychmiastowe jak
`add_column` powyżej.

Podpięte pod 6b335dbff596 — to była wtedy najnowsza (head) rewizja na gałęzi.
Sprawdzone przy tej poprawce (`flask db heads`, 2026-09): repo ma dziś JEDNĄ
głowę, `c9d1e2f3a4b5` — nie ma tu żadnego rozgałęzienia do scalania.

Revision ID: c9d1e2f3a4b5
Revises: 6b335dbff596
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d1e2f3a4b5'
down_revision = '6b335dbff596'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('status_changed_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('pickup_reminder_sent_at', sa.DateTime(), nullable=True))
    # Patrz uwaga w docstringu modułu — na dużym `activity_log` to najwolniejszy
    # krok tej migracji.
    op.create_index('ix_activity_log_entity', 'activity_log', ['entity_type', 'entity_id'])


def downgrade():
    op.drop_index('ix_activity_log_entity', table_name='activity_log')
    op.drop_column('orders', 'pickup_reminder_sent_at')
    op.drop_column('orders', 'status_changed_at')
