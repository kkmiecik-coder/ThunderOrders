"""Socket.IO events for payment confirmation QR upload."""
from flask_socketio import join_room
from extensions import socketio


@socketio.on('join_payment_upload')
def handle_join_payment_upload(data):
    """Desktop client joins room to listen for upload completion."""
    session_token = data.get('session_token')
    if session_token:
        join_room(f'payment_upload_{session_token}')


def notify_payment_uploaded(session_token, filename):
    """Called from upload route to notify desktop that file was uploaded."""
    socketio.emit('payment_photo_uploaded', {
        'session_token': session_token,
        'filename': filename,
    }, room=f'payment_upload_{session_token}')
