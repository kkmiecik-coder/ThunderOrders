"""Update SR statuses: add oplacone, spakowane; reactivate wyslane, dostarczone

Revision ID: a1f8b2c3d4e5
Revises: cbd7795a46ed
Create Date: 2026-03-04 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1f8b2c3d4e5'
down_revision = 'cbd7795a46ed'
branch_labels = None
depends_on = None


def upgrade():
    """
    Full 6-status chain for ShippingRequests:
    1. czeka_na_wycene   (exists, keep as-is)
    2. czeka_na_oplacenie (exists, keep as-is)
    3. oplacone           (NEW)
    4. spakowane          (NEW or rename do_wyslania)
    5. wyslane            (reactivate)
    6. dostarczone        (reactivate)
    """
    conn = op.get_bind()

    # --- 1. Handle 'oplacone' status ---
    existing = conn.execute(
        sa.text("SELECT id FROM shipping_request_statuses WHERE slug = 'oplacone'")
    ).fetchone()

    if existing:
        conn.execute(sa.text(
            "UPDATE shipping_request_statuses SET "
            "name = 'Opłacone', badge_color = '#10B981', sort_order = 4, "
            "is_active = 1, is_initial = 0 "
            "WHERE slug = 'oplacone'"
        ))
    else:
        conn.execute(sa.text(
            "INSERT INTO shipping_request_statuses (slug, name, badge_color, sort_order, is_active, is_initial) "
            "VALUES ('oplacone', 'Opłacone', '#10B981', 4, 1, 0)"
        ))

    # --- 2. Handle 'spakowane' status ---
    # Check if 'do_wyslania' exists — rename it to 'spakowane'
    do_wyslania = conn.execute(
        sa.text("SELECT id FROM shipping_request_statuses WHERE slug = 'do_wyslania'")
    ).fetchone()

    spakowane_exists = conn.execute(
        sa.text("SELECT id FROM shipping_request_statuses WHERE slug = 'spakowane'")
    ).fetchone()

    if do_wyslania and not spakowane_exists:
        # Rename do_wyslania → spakowane
        conn.execute(sa.text(
            "UPDATE shipping_request_statuses SET "
            "slug = 'spakowane', name = 'Spakowane', badge_color = '#8B5CF6', "
            "sort_order = 5, is_active = 1, is_initial = 0 "
            "WHERE slug = 'do_wyslania'"
        ))
        # Also update any existing shipping_requests that reference do_wyslania
        conn.execute(sa.text(
            "UPDATE shipping_requests SET status = 'spakowane' WHERE status = 'do_wyslania'"
        ))
    elif spakowane_exists:
        conn.execute(sa.text(
            "UPDATE shipping_request_statuses SET "
            "name = 'Spakowane', badge_color = '#8B5CF6', sort_order = 5, "
            "is_active = 1, is_initial = 0 "
            "WHERE slug = 'spakowane'"
        ))
    else:
        conn.execute(sa.text(
            "INSERT INTO shipping_request_statuses (slug, name, badge_color, sort_order, is_active, is_initial) "
            "VALUES ('spakowane', 'Spakowane', '#8B5CF6', 5, 1, 0)"
        ))

    # --- 3. Reactivate 'wyslane' ---
    wyslane = conn.execute(
        sa.text("SELECT id FROM shipping_request_statuses WHERE slug = 'wyslane'")
    ).fetchone()

    if wyslane:
        conn.execute(sa.text(
            "UPDATE shipping_request_statuses SET "
            "name = 'Wysłane', badge_color = '#3B82F6', sort_order = 6, "
            "is_active = 1, is_initial = 0 "
            "WHERE slug = 'wyslane'"
        ))
    else:
        conn.execute(sa.text(
            "INSERT INTO shipping_request_statuses (slug, name, badge_color, sort_order, is_active, is_initial) "
            "VALUES ('wyslane', 'Wysłane', '#3B82F6', 6, 1, 0)"
        ))

    # --- 4. Reactivate 'dostarczone' ---
    dostarczone = conn.execute(
        sa.text("SELECT id FROM shipping_request_statuses WHERE slug = 'dostarczone'")
    ).fetchone()

    if dostarczone:
        conn.execute(sa.text(
            "UPDATE shipping_request_statuses SET "
            "name = 'Dostarczone', badge_color = '#059669', sort_order = 7, "
            "is_active = 1, is_initial = 0 "
            "WHERE slug = 'dostarczone'"
        ))
    else:
        conn.execute(sa.text(
            "INSERT INTO shipping_request_statuses (slug, name, badge_color, sort_order, is_active, is_initial) "
            "VALUES ('dostarczone', 'Dostarczone', '#059669', 7, 1, 0)"
        ))

    # --- 5. Update sort_order for existing statuses ---
    conn.execute(sa.text(
        "UPDATE shipping_request_statuses SET sort_order = 1 WHERE slug = 'czeka_na_wycene'"
    ))
    conn.execute(sa.text(
        "UPDATE shipping_request_statuses SET sort_order = 2 WHERE slug = 'czeka_na_oplacenie'"
    ))

    # --- 6. Deactivate old 'nowe' status if exists ---
    conn.execute(sa.text(
        "UPDATE shipping_request_statuses SET is_active = 0 WHERE slug = 'nowe'"
    ))


def downgrade():
    conn = op.get_bind()

    # Deactivate new statuses
    conn.execute(sa.text(
        "UPDATE shipping_request_statuses SET is_active = 0 WHERE slug IN ('oplacone', 'spakowane', 'wyslane', 'dostarczone')"
    ))

    # Restore original sort orders
    conn.execute(sa.text(
        "UPDATE shipping_request_statuses SET sort_order = 2 WHERE slug = 'czeka_na_wycene'"
    ))
    conn.execute(sa.text(
        "UPDATE shipping_request_statuses SET sort_order = 3 WHERE slug = 'czeka_na_oplacenie'"
    ))
