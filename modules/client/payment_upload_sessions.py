"""
Payment Upload Session - QR code upload for payment confirmations.
Model + route to create QR sessions.
"""
import secrets
import io
import base64
import qrcode
from datetime import timedelta

from flask import request, jsonify, current_app
from flask_login import login_required, current_user
from extensions import db
from modules.client import client_bp
from modules.orders.models import get_local_now


class PaymentUploadSession(db.Model):
    """QR code upload session for payment confirmation photos. Expires after 15 minutes."""
    __tablename__ = 'payment_upload_sessions'

    id = db.Column(db.Integer, primary_key=True)
    session_token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='waiting', nullable=False)  # waiting, uploaded
    uploaded_filename = db.Column(db.String(255), nullable=True)  # filename after upload

    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

    user = db.relationship('User', backref=db.backref('payment_upload_sessions', lazy='dynamic'))

    @property
    def is_expired(self):
        return get_local_now() > self.expires_at

    @property
    def is_valid(self):
        return self.status == 'waiting' and not self.is_expired


@client_bp.route('/payment-confirmations/qr-session', methods=['POST'])
@login_required
def payment_qr_session_create():
    """Create QR upload session, return QR data URI + session token."""
    try:
        now = get_local_now()
        # Cleanup expired sessions
        expired = PaymentUploadSession.query.filter(
            PaymentUploadSession.user_id == current_user.id,
            PaymentUploadSession.expires_at < now
        ).all()
        for s in expired:
            db.session.delete(s)

        session_token = secrets.token_urlsafe(32)
        session = PaymentUploadSession(
            session_token=session_token,
            user_id=current_user.id,
            status='waiting',
            expires_at=now + timedelta(minutes=15)
        )
        db.session.add(session)
        db.session.commit()

        # Generate QR code
        upload_url = request.url_root.rstrip('/') + f'/payment/upload/{session_token}'
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(upload_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color='black', back_color='white')

        buffer = io.BytesIO()
        qr_img.save(buffer, format='PNG')
        qr_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        qr_data_uri = f'data:image/png;base64,{qr_base64}'

        return jsonify({
            'success': True,
            'session_token': session_token,
            'qr_data_uri': qr_data_uri,
            'upload_url': upload_url,
            'expires_in': 900
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Payment QR session create error: {e}')
        return jsonify({'success': False, 'message': 'Wystąpił błąd'}), 500
