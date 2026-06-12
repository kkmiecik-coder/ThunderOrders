"""Trasy stron ofertowych (exclusive + preorder read + availability) dla mobilnego API — E3."""
from flask import request
from flask_jwt_extended import jwt_required
from extensions import limiter
from . import api_mobile_bp
from .helpers import json_ok, json_err, json_page, to_grosze, absolute_static_url
from .validators import parse_int
from modules.offers.models import OfferPage
from modules.client import shop_service

# Mapowanie kontrakt → enum bazy (D1: live obejmuje active + paused)
_STATUS_MAP = {
    'live': ('active', 'paused'),
    'upcoming': ('scheduled',),
    'closed': ('ended',),
}


def _public_status(page):
    if page.status in ('active', 'paused'):
        return 'live'
    if page.status == 'scheduled':
        return 'upcoming'
    return 'closed'  # ended


def _serialize_page_summary(page):
    return {
        'token': page.token,
        'name': page.name,
        'page_type': page.page_type,
        'status': _public_status(page),
        'can_order': page.can_order,
        'starts_at': page.starts_at.isoformat() if page.starts_at else None,
        'ends_at': page.ends_at.isoformat() if page.ends_at else None,
        'payment_stages': page.payment_stages,
    }


# ---------------------------------------------------------------------------
# Task 4: GET /offers/offer-pages (lista + mapowanie statusów)
# ---------------------------------------------------------------------------

@api_mobile_bp.route('/offers/offer-pages', methods=['GET'])
@jwt_required()
def offer_pages_list():
    status = (request.args.get('status') or 'live').strip().lower()
    if status not in _STATUS_MAP:
        return json_err(
            'invalid_input',
            'Nieobsługiwany status. Dozwolone: live, upcoming, closed.',
            400,
        )
    page = parse_int(request.args.get('page'), 'page', default=1, min_value=1)
    per_page = min(
        parse_int(request.args.get('per_page'), 'per_page', default=12, min_value=1),
        48,
    )

    q = OfferPage.query.filter(
        OfferPage.status.in_(_STATUS_MAP[status])   # draft nigdy nie wchodzi
    ).order_by(OfferPage.id.desc())                 # deterministyczny sort (sqlite-safe)
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    return json_page(
        [_serialize_page_summary(p) for p in pagination.items],
        page=pagination.page,
        per_page=pagination.per_page,
        total=pagination.total,
        has_next=pagination.has_next,
    )
