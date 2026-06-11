"""Trasy auth + meta (health, app-version) dla mobilnego API."""

from flask import current_app
from . import api_mobile_bp
from .helpers import json_ok


@api_mobile_bp.route('/health', methods=['GET'])
def health():
    return json_ok({'status': 'ok'})


@api_mobile_bp.route('/app-version', methods=['GET'])
def app_version():
    return json_ok({
        'min_version': current_app.config['MOBILE_MIN_APP_VERSION'],
        'latest_version': current_app.config['MOBILE_LATEST_APP_VERSION'],
    })
