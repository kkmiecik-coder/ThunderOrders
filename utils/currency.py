"""
Currency Exchange Rate Utility
Fetches exchange rates from NBP API (free, no API key required)
"""

import requests
from datetime import datetime, timedelta
from flask import current_app
from extensions import db


def get_exchange_rate(currency_code):
    """
    Get exchange rate for given currency to PLN

    Args:
        currency_code (str): Currency code (KRW, USD, EUR, etc.)

    Returns:
        dict: {
            'rate': float,
            'currency': str,
            'date': str,
            'cached': bool,
            'cached_at': str or None
        }

    Raises:
        Exception: If API request fails and no cached rate available
    """

    # Check if rate is cached and fresh (less than 24h old)
    cached_rate = get_cached_rate(currency_code)

    if cached_rate:
        return cached_rate

    # Fetch fresh rate from NBP API
    try:
        rate = fetch_nbp_rate(currency_code)

        # Cache the rate
        cache_rate(currency_code, rate)

        return {
            'rate': rate,
            'currency': currency_code,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'cached': False,
            'cached_at': None
        }

    except Exception as e:
        # If API fails, try to return stale cached rate (older than 24h)
        stale_cached = get_cached_rate(currency_code, allow_stale=True)

        if stale_cached:
            stale_cached['warning'] = f'API unavailable, using stale cache: {str(e)}'
            return stale_cached

        raise Exception(f'Cannot fetch exchange rate for {currency_code}: {str(e)}')


def fetch_nbp_rate(currency_code):
    """
    Fetch current exchange rate from NBP API

    NBP API Documentation: https://api.nbp.pl/

    Args:
        currency_code (str): Currency code (KRW, USD, EUR, etc.)

    Returns:
        float: Exchange rate (1 unit of currency = X PLN)

    Raises:
        Exception: If API request fails
    """

    # NBP API endpoint
    # Table A - most common currencies (USD, EUR, etc.)
    # Table C - exotic currencies (KRW, etc.)

    # Try Table A first
    try:
        url = f'https://api.nbp.pl/api/exchangerates/rates/a/{currency_code}/?format=json'
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            rate = data['rates'][0]['mid']
            return float(rate)

    except requests.exceptions.RequestException:
        pass

    # If not in Table A, try Table C
    try:
        url = f'https://api.nbp.pl/api/exchangerates/rates/c/{currency_code}/?format=json'
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            rate = data['rates'][0]['mid']
            return float(rate)

    except requests.exceptions.RequestException as e:
        raise Exception(f'NBP API request failed: {str(e)}')

    raise Exception(f'Currency {currency_code} not found in NBP API')


def get_cached_rate(currency_code, allow_stale=False):
    """
    Get cached exchange rate from database (warehouse settings)

    Args:
        currency_code (str): Currency code
        allow_stale (bool): If True, return even if older than cache frequency

    Returns:
        dict or None: Cached rate data or None if not cached/expired
    """

    try:
        from modules.auth.models import Settings

        # Try to get rate from warehouse settings first (preferred)
        warehouse_key = f'warehouse_currency_{currency_code.lower()}_rate'
        rate_value = Settings.get_value(warehouse_key, None)

        # Get update frequency from settings (default 24h)
        update_frequency = Settings.get_value('warehouse_currency_update_frequency', 24)

        # Get last update timestamp from warehouse settings
        last_update = Settings.get_value('warehouse_currency_last_update', None)

        if rate_value and last_update:
            # Parse timestamp
            try:
                cached_at = datetime.strptime(last_update, '%Y-%m-%d %H:%M:%S')
            except:
                # Try ISO format as fallback
                cached_at = datetime.fromisoformat(last_update)

            age = datetime.now() - cached_at

            # Check if cache is still fresh based on update frequency
            if not allow_stale and age > timedelta(hours=update_frequency):
                return None

            return {
                'rate': float(rate_value),
                'currency': currency_code,
                'date': cached_at.strftime('%Y-%m-%d'),
                'cached': True,
                'cached_at': last_update,
                'cache_age_hours': int(age.total_seconds() / 3600)
            }

        # Fallback to old exchange_rate_* keys for backward compatibility
        key = f'exchange_rate_{currency_code.lower()}'
        rate_setting = Settings.query.filter_by(key=key).first()

        if not rate_setting:
            return None

        # Get cached timestamp
        timestamp_key = f'exchange_rate_{currency_code.lower()}_timestamp'
        timestamp_setting = Settings.query.filter_by(key=timestamp_key).first()

        if not timestamp_setting:
            return None

        # Check if cache is fresh based on update frequency
        cached_at = datetime.fromisoformat(timestamp_setting.value)
        age = datetime.now() - cached_at

        if not allow_stale and age > timedelta(hours=update_frequency):
            return None

        return {
            'rate': float(rate_setting.value),
            'currency': currency_code,
            'date': cached_at.strftime('%Y-%m-%d'),
            'cached': True,
            'cached_at': timestamp_setting.value,
            'cache_age_hours': int(age.total_seconds() / 3600)
        }

    except Exception as e:
        current_app.logger.error(f'Error reading cached rate: {str(e)}')
        return None


def cache_rate(currency_code, rate):
    """
    Cache exchange rate in database (warehouse settings + legacy keys)

    Args:
        currency_code (str): Currency code
        rate (float): Exchange rate
    """

    try:
        from modules.auth.models import Settings

        timestamp_value = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Cache in warehouse settings (preferred location)
        warehouse_key = f'warehouse_currency_{currency_code.lower()}_rate'
        Settings.set_value(warehouse_key, str(rate), type='string')
        Settings.set_value('warehouse_currency_last_update', timestamp_value, type='string')

        # Also cache in legacy keys for backward compatibility
        key = f'exchange_rate_{currency_code.lower()}'
        rate_setting = Settings.query.filter_by(key=key).first()

        if rate_setting:
            rate_setting.value = str(rate)
        else:
            rate_setting = Settings(
                key=key,
                value=str(rate),
                type='string',
                description=f'Exchange rate for {currency_code} to PLN (legacy)'
            )
            db.session.add(rate_setting)

        # Cache timestamp in legacy key
        timestamp_key = f'exchange_rate_{currency_code.lower()}_timestamp'
        timestamp_setting = Settings.query.filter_by(key=timestamp_key).first()

        if timestamp_setting:
            timestamp_setting.value = datetime.now().isoformat()
        else:
            timestamp_setting = Settings(
                key=timestamp_key,
                value=datetime.now().isoformat(),
                type='string',
                description=f'Timestamp of last {currency_code} rate update (legacy)'
            )
            db.session.add(timestamp_setting)

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error caching rate: {str(e)}')


def convert_to_pln(amount, currency_code):
    """
    Convert amount from given currency to PLN

    Args:
        amount (float): Amount in original currency
        currency_code (str): Currency code (KRW, USD, PLN)

    Returns:
        float: Amount in PLN
    """

    if currency_code == 'PLN':
        return float(amount)

    rate_data = get_exchange_rate(currency_code)
    rate = rate_data['rate']

    return float(amount) * rate


def calculate_margin(sale_price, purchase_price_pln):
    """
    Calculate margin percentage

    Args:
        sale_price (float): Sale price in PLN
        purchase_price_pln (float): Purchase price in PLN

    Returns:
        float: Margin percentage (rounded to 2 decimal places)
    """

    if not purchase_price_pln or purchase_price_pln == 0:
        return None

    margin = ((float(sale_price) - float(purchase_price_pln)) / float(purchase_price_pln)) * 100
    return round(margin, 2)
