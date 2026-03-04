"""
Notification API endpoints for push subscriptions and preferences.
"""

from flask import request, jsonify, current_app
from flask_login import login_required, current_user

from extensions import db
from . import notifications_bp
from .models import PushSubscription, NotificationPreference


@notifications_bp.route('/vapid-public-key', methods=['GET'])
def vapid_public_key():
    """Return the VAPID public key for client-side subscription."""
    key = current_app.config.get('VAPID_PUBLIC_KEY', '')
    if not key:
        return jsonify({'error': 'Push notifications not configured'}), 503
    return jsonify({'public_key': key})


@notifications_bp.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    """Save a push subscription for the current user."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Missing JSON body'}), 400

    endpoint = data.get('endpoint')
    keys = data.get('keys', {})
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')
    device_name = data.get('device_name', '')

    if not endpoint or not p256dh or not auth:
        return jsonify({'error': 'Missing subscription data'}), 400

    # Upsert: reactivate if same endpoint exists
    existing = PushSubscription.query.filter_by(
        user_id=current_user.id, endpoint=endpoint
    ).first()

    if existing:
        existing.p256dh_key = p256dh
        existing.auth_key = auth
        existing.is_active = True
        existing.failed_count = 0
        if device_name:
            existing.device_name = device_name
    else:
        sub = PushSubscription(
            user_id=current_user.id,
            endpoint=endpoint,
            p256dh_key=p256dh,
            auth_key=auth,
            device_name=device_name
        )
        db.session.add(sub)

    db.session.commit()
    return jsonify({'success': True, 'message': 'Subskrypcja zapisana'})


@notifications_bp.route('/unsubscribe', methods=['POST'])
@login_required
def unsubscribe():
    """Deactivate a push subscription."""
    data = request.get_json()
    endpoint = data.get('endpoint') if data else None

    if not endpoint:
        return jsonify({'error': 'Missing endpoint'}), 400

    sub = PushSubscription.query.filter_by(
        user_id=current_user.id, endpoint=endpoint
    ).first()

    if sub:
        sub.is_active = False
        db.session.commit()

    return jsonify({'success': True, 'message': 'Subskrypcja wyłączona'})


@notifications_bp.route('/subscriptions', methods=['GET'])
@login_required
def list_subscriptions():
    """List active subscriptions (devices) for the current user."""
    subs = PushSubscription.query.filter_by(
        user_id=current_user.id, is_active=True
    ).all()

    return jsonify({
        'subscriptions': [{
            'id': s.id,
            'device_name': s.device_name or 'Nieznane urządzenie',
            'created_at': s.created_at.isoformat() if s.created_at else None,
            'last_used_at': s.last_used_at.isoformat() if s.last_used_at else None,
        } for s in subs]
    })


@notifications_bp.route('/preferences', methods=['GET'])
@login_required
def get_preferences():
    """Get notification preferences for the current user."""
    pref = NotificationPreference.query.filter_by(user_id=current_user.id).first()
    if not pref:
        # Return defaults (all True)
        return jsonify({
            'order_status_changes': True,
            'payment_updates': True,
            'shipping_updates': True,
            'new_exclusive_pages': True,
            'cost_added': True,
            'admin_alerts': True,
        })
    return jsonify(pref.to_dict())


@notifications_bp.route('/preferences', methods=['POST'])
@login_required
def update_preferences():
    """Update notification preferences for the current user."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Missing JSON body'}), 400

    pref = NotificationPreference.query.filter_by(user_id=current_user.id).first()
    if not pref:
        pref = NotificationPreference(user_id=current_user.id)
        db.session.add(pref)

    allowed_fields = [
        'order_status_changes', 'payment_updates', 'shipping_updates',
        'new_exclusive_pages', 'cost_added', 'admin_alerts'
    ]
    for field in allowed_fields:
        if field in data:
            setattr(pref, field, bool(data[field]))

    db.session.commit()
    return jsonify({'success': True, 'message': 'Preferencje zapisane'})


@notifications_bp.route('/test', methods=['POST'])
@login_required
def send_test():
    """Send a test push notification to the current user."""
    from utils.push_manager import PushManager
    sent = PushManager.send_to_user(
        user_id=current_user.id,
        title='Test powiadomienia',
        body='To jest testowe powiadomienie push z ThunderOrders.',
        url='/',
        tag='test',
        notification_type=None  # bypass preference check
    )
    if sent:
        return jsonify({'success': True, 'message': 'Testowe powiadomienie wysłane'})
    return jsonify({'success': False, 'message': 'Brak aktywnych subskrypcji push'}), 400
