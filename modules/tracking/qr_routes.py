from flask import redirect, abort, request, make_response
from . import tracking_bp
from .models import QRCampaign, QRVisit, db
from .utils import (
    generate_visitor_id,
    generate_fingerprint,
    parse_user_agent,
    get_geolocation,
    get_client_ip,
)

COOKIE_NAME = 'thunderorders_qr_visitor'
COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # 1 year


@tracking_bp.route('/qr/<slug>')
def qr_redirect(slug):
    """Publiczny endpoint QR - rejestruje wizytę i przekierowuje"""
    campaign = QRCampaign.query.filter_by(slug=slug, is_deleted=False).first()
    if not campaign:
        abort(404)

    # Redirect bez trackingu jeśli kampania nieaktywna
    if not campaign.is_active:
        return redirect(campaign.target_url, code=302)

    # Identyfikacja odwiedzającego
    visitor_id = request.cookies.get(COOKIE_NAME)
    set_cookie = False

    if not visitor_id:
        # Fallback: fingerprint
        ip = get_client_ip(request)
        ua = request.headers.get('User-Agent', '')
        lang = request.headers.get('Accept-Language', '')
        visitor_id = generate_fingerprint(ua, ip, lang)
        set_cookie = True
        cookie_value = generate_visitor_id()
    else:
        cookie_value = visitor_id

    # Sprawdź unikalność
    is_unique = not QRVisit.query.filter_by(
        campaign_id=campaign.id,
        visitor_id=visitor_id
    ).first()

    # Parsuj User-Agent
    ua_string = request.headers.get('User-Agent', '')
    ua_info = parse_user_agent(ua_string)

    # Geolokalizacja
    client_ip = get_client_ip(request)
    geo = get_geolocation(client_ip)

    # Zapisz wizytę
    visit = QRVisit(
        campaign_id=campaign.id,
        visitor_id=visitor_id,
        is_unique=is_unique,
        ip_address=client_ip,
        user_agent=ua_string[:500] if ua_string else None,
        device_type=ua_info['device_type'],
        browser=ua_info['browser'],
        os=ua_info['os'],
        country=geo['country'],
        city=geo['city'],
        referer=request.headers.get('Referer', '')[:500] or None,
    )
    db.session.add(visit)
    db.session.commit()

    # Redirect z ustawieniem cookie
    response = make_response(redirect(campaign.target_url, code=302))
    if set_cookie:
        response.set_cookie(
            COOKIE_NAME,
            cookie_value,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite='Lax',
            secure=True,
        )

    return response
