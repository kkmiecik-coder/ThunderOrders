"""EmailLog: log wysylki maili

Revision ID: 85499b0cafe0
Revises: e7a1c4b92d55
Create Date: 2026-08-14 21:56:03.203418

Tworzy tabelę `email_log` — trwały ślad po każdym mailu wychodzącym z systemu
(zakolejkowanie → wynik SMTP, z liczbą prób i czasem trwania).

UWAGA: autogenerate wyprodukował przy okazji kilkanaście operacji niezwiązanych
z tą zmianą (drop tabel `email_templates`/`order_templates`, przepinanie kluczy
obcych na `poland_orders`/`proxy_order_items`, kasowanie indeksów na
`wms_statuses`). To zastany dryf modeli względem produkcyjnej bazy, a nie skutek
tej migracji — wykonanie tamtych operacji skasowałoby dane i zerwało klucze obce.
Zostawiono wyłącznie tworzenie nowej tabeli.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '85499b0cafe0'
down_revision = 'e7a1c4b92d55'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'email_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recipient', sa.String(length=255), nullable=False),
        sa.Column('subject', sa.String(length=500), nullable=True),
        sa.Column('template', sa.String(length=100), nullable=True),
        sa.Column('entity_type', sa.String(length=50), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False,
                  server_default='queued'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_email_log_created_at', 'email_log', ['created_at'])
    op.create_index('ix_email_log_entity', 'email_log', ['entity_type', 'entity_id'])
    op.create_index('ix_email_log_recipient', 'email_log', ['recipient'])
    op.create_index('ix_email_log_status', 'email_log', ['status'])
    op.create_index('ix_email_log_template', 'email_log', ['template'])


def downgrade():
    # Same drop_table wystarczy — indeksy znikają razem z tabelą, a osobne
    # drop_index przed drop_table potrafi wywrócić deploy na MariaDB.
    op.drop_table('email_log')
