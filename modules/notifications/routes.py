"""
Notification API endpoints for push subscriptions, preferences, and notification center.
"""

from flask import request, jsonify, current_app
from flask_login import login_required, current_user

from extensions import db, csrf
from . import notifications_bp
from .models import PushSubscription, NotificationPreference, Notification


@notifications_bp.route('/vapid-public-key', methods=['GET'])
def vapid_public_key():
    """Return the VAPID public key for client-side subscription."""
    key = current_app.config.get('VAPID_PUBLIC_KEY', '')
    if not key:
        return jsonify({'error': 'Push notifications not configured'}), 503
    return jsonify({'public_key': key})


@notifications_bp.route('/subscribe', methods=['POST'])
@csrf.exempt
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
@csrf.exempt
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
        'new_exclusive_pages', 'cost_added', 'sale_date_changes', 'admin_alerts',
        'order_supplier_ordered'
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


# ========================================
# NOTIFICATION CENTER ENDPOINTS
# ========================================

@notifications_bp.route('/list', methods=['GET'])
@login_required
def notification_list():
    """
    Get notifications for the current user.
    Returns all unread + fills remaining with read ones up to limit.
    If unread count > limit, returns ALL unread.
    """
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 10, type=int)
    limit = min(limit, 50)  # cap at 50

    uid = current_user.id

    # Get all unread notifications (no limit)
    unread = Notification.query.filter_by(
        user_id=uid, is_read=False
    ).order_by(Notification.created_at.desc()).all()

    unread_count = len(unread)

    if unread_count >= limit:
        # More unread than limit - return all unread, no read ones
        items = [n.to_dict() for n in unread]
        has_more = Notification.query.filter_by(
            user_id=uid, is_read=True
        ).count() > 0
    else:
        # Fill remaining slots with read notifications
        remaining = limit - unread_count
        read_query = Notification.query.filter_by(
            user_id=uid, is_read=True
        ).order_by(Notification.created_at.desc())

        if offset > 0:
            # When paginating, offset only applies to read notifications
            read_query = read_query.offset(offset)

        read = read_query.limit(remaining + 1).all()
        has_more = len(read) > remaining
        read = read[:remaining]

        items = [n.to_dict() for n in unread] + [n.to_dict() for n in read]

    return jsonify({
        'notifications': items,
        'unread_count': unread_count,
        'has_more': has_more,
    })


@notifications_bp.route('/mark-read', methods=['POST'])
@login_required
def mark_read():
    """Mark specific notifications as read. Body: {ids: [1,2,3]}."""
    data = request.get_json()
    if not data or 'ids' not in data:
        return jsonify({'error': 'Missing ids'}), 400

    ids = data['ids']
    if not isinstance(ids, list) or not ids:
        return jsonify({'error': 'ids must be a non-empty list'}), 400

    # Only mark notifications belonging to current user
    Notification.query.filter(
        Notification.id.in_(ids),
        Notification.user_id == current_user.id,
        Notification.is_read == False  # noqa: E712
    ).update({'is_read': True}, synchronize_session=False)
    db.session.commit()

    # Return new unread count
    unread_count = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).count()

    return jsonify({'success': True, 'unread_count': unread_count})


@notifications_bp.route('/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    """Mark ALL unread notifications as read for current user."""
    Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).update({'is_read': True}, synchronize_session=False)
    db.session.commit()
    return jsonify({'success': True, 'unread_count': 0})


@notifications_bp.route('/delete', methods=['POST'])
@login_required
def delete_notification():
    """Delete a single notification. Body: {id: 123}."""
    data = request.get_json()
    if not data or 'id' not in data:
        return jsonify({'error': 'Missing id'}), 400

    notif = Notification.query.filter_by(
        id=data['id'], user_id=current_user.id
    ).first()

    if notif:
        was_unread = not notif.is_read
        db.session.delete(notif)
        db.session.commit()
    else:
        was_unread = False

    unread_count_val = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).count()

    return jsonify({'success': True, 'unread_count': unread_count_val})


@notifications_bp.route('/clear-all', methods=['POST'])
@login_required
def clear_all():
    """Delete ALL notifications for current user."""
    Notification.query.filter_by(user_id=current_user.id).delete(
        synchronize_session=False
    )
    db.session.commit()
    return jsonify({'success': True, 'unread_count': 0})


@notifications_bp.route('/unread-count', methods=['GET'])
@login_required
def unread_count():
    """Lightweight endpoint for polling the badge count."""
    count = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).count()
    return jsonify({'count': count})


@notifications_bp.route('/has-active', methods=['GET'])
@login_required
def has_active_subscription():
    """Check if the current user has any active push subscriptions in the database.
    Used by the frontend health check when localStorage is cleared."""
    has = PushSubscription.query.filter_by(
        user_id=current_user.id, is_active=True
    ).first() is not None
    return jsonify({'has_active': has})
