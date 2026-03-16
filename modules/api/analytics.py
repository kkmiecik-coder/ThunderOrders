"""
API Module - Privacy Consent
Endpointy do zarządzania zgodami użytkownika (cookies analityczne, marketing) - RODO-compliant
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from datetime import datetime

analytics_bp = Blueprint('analytics_api', __name__, url_prefix='/api')


@analytics_bp.route('/analytics-consent', methods=['POST'])
@login_required
def update_analytics_consent():
    """
    Aktualizuj zgodę użytkownika na cookies analityczne

    POST Body (JSON):
        {
            "consent": true/false
        }

    Returns (JSON):
        {
            "success": true,
            "consent": true/false,
            "message": "Zgoda została zapisana"
        }

    Example:
        fetch('/api/analytics-consent', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ consent: true })
        })
    """
    try:
        data = request.get_json()

        if data is None:
            return jsonify({
                'success': False,
                'error': 'Brak danych JSON'
            }), 400

        consent = data.get('consent')

        # Walidacja
        if consent is None:
            return jsonify({
                'success': False,
                'error': 'Pole "consent" jest wymagane'
            }), 400

        if not isinstance(consent, bool):
            return jsonify({
                'success': False,
                'error': 'Pole "consent" musi być typu boolean (true/false)'
            }), 400

        # Zapisz zgodę i datę
        current_user.analytics_consent = consent
        current_user.analytics_consent_date = datetime.now()
        db.session.commit()

        message = 'Zgoda na cookies została zapisana' if consent else 'Zgoda na cookies została wycofana'

        return jsonify({
            'success': True,
            'consent': consent,
            'message': message
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Wystąpił błąd: {str(e)}'
        }), 500


@analytics_bp.route('/marketing-consent', methods=['POST'])
@login_required
def update_marketing_consent():
    """
    Aktualizuj zgodę użytkownika na komunikację marketingową (nowe dropy, back-in-stock, broadcasty).
    """
    try:
        data = request.get_json()

        if data is None:
            return jsonify({'success': False, 'error': 'Brak danych JSON'}), 400

        consent = data.get('consent')

        if not isinstance(consent, bool):
            return jsonify({'success': False, 'error': 'Pole "consent" musi być typu boolean'}), 400

        current_user.marketing_consent = consent
        db.session.commit()

        message = 'Zgoda marketingowa została zapisana' if consent else 'Zgoda marketingowa została wycofana'

        return jsonify({
            'success': True,
            'consent': consent,
            'message': message
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Wystąpił błąd: {str(e)}'}), 500
