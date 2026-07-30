"""Dodaje kolumnę stage do payment_reminder_logs i poszerza unikalność o etap

Revision ID: 18128f2dca91
Revises: 90fb5ad1c7b6
Create Date: 2026-07-30 15:01:28.981410

Bez tej kolumny jedna wspólna reguła przypomnień obejmująca wszystkie 4 etapy
płatności blokowałaby się sama — dedup po (order_id, config_id) uznawałby
przypomnienie o etapie produktu za "już wysłane dla tego zamówienia i reguły",
co blokowałoby wysyłkę przypomnienia o zupełnie innym etapie (np. cle) tego
samego zamówienia pod tą samą regułą.

Istniejące wiersze (sprzed rozszerzenia na wszystkie etapy) zostają z NULL —
dotyczyły wyłącznie etapu produktu, ale nie zapisywały tego jawnie.

Kolejność operacji (najpierw utwórz nowy unique constraint, potem usuń stary)
jest celowa: `order_id` ma klucz obcy do `orders`, a jedynym indeksem, który
go dziś pokrywa, jest właśnie stary constraint `uq_reminder_log_order_config`
(order_id jest jego lewą kolumną). Gdyby usunąć go pierwszy, MariaDB odmawia
(błąd 1553 — "needed in a foreign key constraint"), bo FK zostałby bez
wspierającego indeksu. Nowy constraint zaczyna się też od order_id, więc od
razu przejmuje tę rolę i pozwala bezpiecznie usunąć stary.

Uwaga (naprawione po zgłoszeniu błędu na innym środowisku): łączenie tych
trzech operacji w jednym bloku `batch_alter_table` renderuje się na części
instalacji MariaDB jako JEDEN wieloklauzulowy `ALTER TABLE`, w którym walidacja
"czy FK ma wspierający indeks" dla klauzuli DROP INDEX bywa liczona względem
stanu tabeli SPRZED całej instrukcji, a nie względem stanu po wcześniejszych
klauzulach tego samego `ALTER TABLE` — mimo że w kodzie CREATE jest przed DROP,
serwer i tak zgłaszał błąd 1553. Rozdzielenie na trzy osobne bloki
`batch_alter_table` wymusza trzy oddzielne instrukcje `ALTER TABLE`
wykonywane sekwencyjnie, więc druga faktycznie kończy się i zatwierdza nowy
indeks zanim trzecia usunie stary.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '18128f2dca91'
down_revision = '90fb5ad1c7b6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('payment_reminder_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stage', sa.String(length=30), nullable=True))
    with op.batch_alter_table('payment_reminder_logs', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uq_reminder_log_order_config_stage', ['order_id', 'config_id', 'stage']
        )
    with op.batch_alter_table('payment_reminder_logs', schema=None) as batch_op:
        batch_op.drop_constraint('uq_reminder_log_order_config', type_='unique')


def downgrade():
    with op.batch_alter_table('payment_reminder_logs', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uq_reminder_log_order_config', ['order_id', 'config_id']
        )
    with op.batch_alter_table('payment_reminder_logs', schema=None) as batch_op:
        batch_op.drop_constraint('uq_reminder_log_order_config_stage', type_='unique')
    with op.batch_alter_table('payment_reminder_logs', schema=None) as batch_op:
        batch_op.drop_column('stage')
