"""Przebudowa PaymentMethod - osobne kolumny zamiast details

Revision ID: 3ad9fb792ebb
Revises: bd63c2b332c0
Create Date: 2026-02-16 22:25:10.447245

"""
import re
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '3ad9fb792ebb'
down_revision = 'bd63c2b332c0'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Dodaj nowe kolumny (nullable na czas migracji danych)
    op.add_column('payment_methods', sa.Column('method_type', sa.String(length=20), nullable=True,
                  comment="Typ: 'transfer' (przelew), 'instant' (BLIK), 'online' (PayPal/Revolut), 'other'"))
    op.add_column('payment_methods', sa.Column('recipient', sa.String(length=200), nullable=True,
                  comment='Odbiorca przelewu (imię nazwisko / firma)'))
    op.add_column('payment_methods', sa.Column('account_number', sa.String(length=100), nullable=True,
                  comment='Numer konta / telefon / email'))
    op.add_column('payment_methods', sa.Column('code', sa.String(length=100), nullable=True,
                  comment='Kod Revolut / SWIFT / BIC'))
    op.add_column('payment_methods', sa.Column('transfer_title', sa.String(length=200), nullable=True,
                  comment='Szablon tytułu przelewu (np. [NUMER ZAMÓWIENIA])'))
    op.add_column('payment_methods', sa.Column('additional_info', sa.Text(), nullable=True,
                  comment='Dodatkowe informacje (opcjonalne)'))

    # 2. Migracja danych ze starej kolumny 'details' do nowych kolumn
    connection = op.get_bind()
    result = connection.execute(sa.text("SELECT id, name, details FROM payment_methods"))

    for row in result:
        method_id = row[0]
        name = row[1] or ""
        details = row[2] or ""
        name_lower = name.lower()

        # Domyślne wartości
        method_type = 'other'
        recipient = None
        account_number = None
        code_val = None
        transfer_title = None
        additional_info = details if details else None

        # BLIK - szukaj telefonu
        if 'blik' in name_lower:
            method_type = 'instant'
            phone_match = re.search(r'\+?[\d\s]{9,15}', details)
            if phone_match:
                account_number = phone_match.group(0).strip()
            title_match = re.search(r'[Tt]ytu[łl].*?:\s*(.+)', details)
            if title_match:
                transfer_title = title_match.group(1).strip()

        # Przelew tradycyjny
        elif 'przelew' in name_lower or 'transfer' in name_lower or 'bank' in name_lower:
            method_type = 'transfer'
            account_match = re.search(r'\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}', details)
            if account_match:
                account_number = account_match.group(0).strip()
            recipient_match = re.search(r'[Oo]dbiorca.*?:\s*(.+)', details)
            if recipient_match:
                recipient = recipient_match.group(1).strip()
            title_match = re.search(r'[Tt]ytu[łl].*?:\s*(.+)', details)
            if title_match:
                transfer_title = title_match.group(1).strip()

        # PayPal / Revolut
        elif 'paypal' in name_lower or 'revolut' in name_lower:
            method_type = 'online'
            email_match = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.\w+', details)
            if email_match:
                account_number = email_match.group(0).strip()
            if 'revolut' in name_lower:
                code_match = re.search(r'[Kk]od.*?:\s*(\S+)', details)
                if code_match:
                    code_val = code_match.group(1).strip()
            title_match = re.search(r'[Tt]ytu[łl].*?:\s*(.+)', details)
            if title_match:
                transfer_title = title_match.group(1).strip()

        connection.execute(
            sa.text("""
                UPDATE payment_methods
                SET method_type = :method_type,
                    recipient = :recipient,
                    account_number = :account_number,
                    code = :code,
                    transfer_title = :transfer_title,
                    additional_info = :additional_info
                WHERE id = :id
            """),
            {
                'method_type': method_type,
                'recipient': recipient,
                'account_number': account_number,
                'code': code_val,
                'transfer_title': transfer_title,
                'additional_info': additional_info,
                'id': method_id
            }
        )

    # 3. Ustaw method_type jako NOT NULL (teraz już wszystkie rekordy mają wartość)
    with op.batch_alter_table('payment_methods', schema=None) as batch_op:
        batch_op.alter_column('method_type',
                              existing_type=sa.String(length=20),
                              nullable=False)

    # 4. Usuń starą kolumnę details
    with op.batch_alter_table('payment_methods', schema=None) as batch_op:
        batch_op.drop_column('details')


def downgrade():
    # 1. Przywróć kolumnę details
    op.add_column('payment_methods', sa.Column('details', mysql.TEXT(), nullable=True))

    # 2. Zmigruj dane z powrotem
    connection = op.get_bind()
    result = connection.execute(sa.text("""
        SELECT id, recipient, account_number, code, transfer_title, additional_info
        FROM payment_methods
    """))

    for row in result:
        details_parts = []
        if row[1]:  # recipient
            details_parts.append(f"Odbiorca: {row[1]}")
        if row[2]:  # account_number
            details_parts.append(f"Numer: {row[2]}")
        if row[3]:  # code
            details_parts.append(f"Kod: {row[3]}")
        if row[4]:  # transfer_title
            details_parts.append(f"Tytuł: {row[4]}")
        if row[5]:  # additional_info
            details_parts.append(row[5])

        details = "\n".join(details_parts) if details_parts else ""

        connection.execute(
            sa.text("UPDATE payment_methods SET details = :details WHERE id = :id"),
            {'details': details, 'id': row[0]}
        )

    # 3. Ustaw details jako NOT NULL
    with op.batch_alter_table('payment_methods', schema=None) as batch_op:
        batch_op.alter_column('details',
                              existing_type=mysql.TEXT(),
                              nullable=False)

    # 4. Usuń nowe kolumny
    with op.batch_alter_table('payment_methods', schema=None) as batch_op:
        batch_op.drop_column('additional_info')
        batch_op.drop_column('transfer_title')
        batch_op.drop_column('code')
        batch_op.drop_column('account_number')
        batch_op.drop_column('recipient')
        batch_op.drop_column('method_type')
