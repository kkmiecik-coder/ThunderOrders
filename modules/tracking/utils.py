import hashlib
import uuid
import os
from user_agents import parse as parse_ua
from flask import current_app


def generate_visitor_id():
    """Generuje losowy UUID v4 jako visitor_id dla cookie"""
    return uuid.uuid4().hex


def generate_fingerprint(user_agent, ip_address, accept_language):
    """Generuje SHA-256 fingerprint jako fallback gdy brak cookie"""
    raw = f'{user_agent}|{ip_address}|{accept_language}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def parse_user_agent(ua_string):
    """Parsuje User-Agent string i zwraca dict z device_type, browser, os"""
    if not ua_string:
        return {'device_type': 'unknown', 'browser': 'unknown', 'os': 'unknown'}

    ua = parse_ua(ua_string)

    if ua.is_mobile:
        device_type = 'mobile'
    elif ua.is_tablet:
        device_type = 'tablet'
    else:
        device_type = 'desktop'

    browser = ua.browser.family or 'unknown'
    os_name = ua.os.family or 'unknown'

    return {
        'device_type': device_type,
        'browser': browser,
        'os': os_name,
    }


def get_geolocation(ip_address):
    """Geolokalizacja IP z bazy GeoLite2. Zwraca dict z country, city."""
    result = {'country': None, 'city': None}

    if not ip_address or ip_address in ('127.0.0.1', '::1'):
        return result

    db_path = current_app.config.get('GEOIP_DB_PATH')
    if not db_path or not os.path.exists(db_path):
        return result

    try:
        import geoip2.database
        with geoip2.database.Reader(db_path) as reader:
            response = reader.city(ip_address)
            result['country'] = response.country.name
            result['city'] = response.city.name
    except Exception:
        pass

    return result


def get_client_ip(request):
    """Pobiera prawdziwy IP klienta (uwzglednia proxy/nginx)"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers['X-Forwarded-For'].split(',')[0].strip()
    if request.headers.get('X-Real-Ip'):
        return request.headers['X-Real-Ip']
    return request.remote_addr
