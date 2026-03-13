"""Socket.IO events for payment confirmation QR upload."""
import logging
from flask import request
from flask_socketio import join_room
from extensions import socketio

logger = logging.getLogger(__name__)


@socketio.on('join_payment_upload')
def handle_join_payment_upload(data):
    """Desktop client joins room to listen for upload completion."""
    session_token = data.get('session_token')
    if session_token:
        room = f'payment_upload_{session_token}'
        join_room(room)
        logger.info(f'[PaymentQR] Desktop joined room: {room}, sid={request.sid}')
    else:
        logger.warning('[PaymentQR] join_payment_upload called without session_token')


def notify_payment_uploaded(session_token, filename):
    """Called from upload route to notify desktop that file was uploaded."""
    room = f'payment_upload_{session_token}'
    logger.info(f'[PaymentQR] Emitting payment_photo_uploaded to room: {room}, filename: {filename}')
    socketio.emit('payment_photo_uploaded', {
        'session_token': session_token,
        'filename': filename,
    }, room=room)
    logger.info(f'[PaymentQR] Emit completed for room: {room}')
