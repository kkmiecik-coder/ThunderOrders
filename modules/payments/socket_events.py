"""
Payment Confirmations — SocketIO Event Handlers
=================================================

Real-time WebSocket events for payment confirmation status changes.
Notifies clients when admin approves/rejects their payment confirmations.
"""

from flask import request as flask_request
from flask_socketio import join_room

from extensions import socketio

import logging
logger = logging.getLogger(__name__)


def _get_payment_room(user_id):
    """Return room name for a user's payment updates."""
    return f'payment_user_{user_id}'


@socketio.on('join_payment_room')
def handle_join_payment_room(data):
    """Client joins their payment updates room."""
    try:
        user_id = data.get('user_id')
        if not user_id:
            print(f"[PaymentSocket] join_payment_room: missing user_id")
            return {'success': False, 'error': 'Missing user_id'}

        room = _get_payment_room(user_id)
        join_room(room)
        print(f"[PaymentSocket] Client {flask_request.sid} joined room: {room}")
        return {'success': True}
    except Exception as e:
        print(f"[PaymentSocket] ERROR in join_payment_room: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}


def emit_payment_status_change(confirmation):
    """
    Emit payment_status_changed event to the client who owns the order.

    Args:
        confirmation: PaymentConfirmation object (must have order relationship loaded)
    """
    order = confirmation.order
    if not order or not order.user_id:
        print(f"[PaymentSocket] emit skipped: no order or user_id")
        return

    room = _get_payment_room(order.user_id)

    stage_names = {
        'product': 'Produkt',
        'korean_shipping': 'Wysyłka KR',
        'customs_vat': 'Cło/VAT',
        'domestic_shipping': 'Wysyłka PL',
    }

    data = {
        'order_id': order.id,
        'order_number': order.order_number,
        'payment_stage': confirmation.payment_stage,
        'payment_stage_name': stage_names.get(confirmation.payment_stage, confirmation.payment_stage),
        'status': confirmation.status,
        'ocr_score': confirmation.ocr_score,
        'amount': float(confirmation.amount) if confirmation.amount else 0,
    }

    print(f"[PaymentSocket] Emitting payment_status_changed to {room}: status={data['status']}, order={data['order_number']}")
    socketio.emit('payment_status_changed', data, to=room)
    print(f"[PaymentSocket] Emit done.")
