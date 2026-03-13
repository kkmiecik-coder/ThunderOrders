"""
Public Routes - Publiczne strony
=================================

Strony dostępne bez logowania:
- /collection/<token> - publiczna strona kolekcji
- /collection/upload/<session_token> - strona uploadu z telefonu (QR)
"""

from flask import render_template, request, jsonify, current_app, abort
from modules.public import public_bp
from extensions import db


@public_bp.route('/collection/<token>')
def public_collection(token):
    """Publiczna strona kolekcji użytkownika."""
    from modules.client.models import PublicCollectionConfig, CollectionItem

    config = PublicCollectionConfig.query.filter_by(token=token).first()
    if not config:
        abort(404)

    if not config.is_active:
        return render_template('public/collection_inactive.html',
                               user=config.user)

    # Pobierz itemy oznaczone jako publiczne
    items = CollectionItem.query.filter_by(
        user_id=config.user_id,
        is_public=True
    ).order_by(CollectionItem.created_at.desc()).all()

    # Widok (grid / carousel)
    view = request.args.get('view', 'grid')
    if view not in ('grid', 'carousel'):
        view = 'grid'

    user = config.user

    return render_template('public/collection.html',
                           config=config,
                           items=items,
                           view=view,
                           user=user,
                           show_prices=config.show_prices)


@public_bp.route('/collection/upload/<session_token>', methods=['GET'])
def upload_page(session_token):
    """Strona mobilna do uploadu zdjęcia z QR code."""
    from modules.client.models import CollectionUploadSession

    session = CollectionUploadSession.query.filter_by(session_token=session_token).first()
    if not session:
        abort(404)

    if session.is_expired:
        return render_template('public/upload.html', expired=True, session=session)

    if session.status == 'uploaded':
        return render_template('public/upload.html', already_uploaded=True, session=session)

    return render_template('public/upload.html', session=session, expired=False, already_uploaded=False)


@public_bp.route('/collection/upload/<session_token>', methods=['POST'])
def upload_photo(session_token):
    """Upload zdjęcia z telefonu (QR code flow)."""
    from modules.client.models import CollectionUploadSession, CollectionTempUpload, CollectionItemImage
    from utils.image_processor import process_collection_upload

    session = CollectionUploadSession.query.filter_by(session_token=session_token).first()
    if not session:
        return jsonify({'success': False, 'message': 'Nieprawidłowa sesja'}), 404

    if session.is_expired:
        return jsonify({'success': False, 'message': 'Sesja wygasła'}), 410

    if session.status == 'uploaded':
        return jsonify({'success': False, 'message': 'Zdjęcie już zostało przesłane'}), 409

    file = request.files.get('image')
    if not file or not file.filename:
        return jsonify({'success': False, 'message': 'Nie wybrano pliku'}), 400

    try:
        result = process_collection_upload(file, session.user_id)

        if session.collection_item_id:
            # Item już istnieje - dodaj bezpośrednio jako CollectionItemImage
            from modules.client.models import CollectionItem
            item = CollectionItem.query.get(session.collection_item_id)
            if item and item.can_add_image:
                image = CollectionItemImage(
                    collection_item_id=item.id,
                    filename=result['filename'],
                    path_original=result['path_original'],
                    path_compressed=result['path_compressed'],
                    is_primary=(item.images_count == 0),
                    sort_order=item.images_count
                )
                db.session.add(image)
        else:
            # Item jeszcze nie istnieje - zapisz do temp_uploads
            temp = CollectionTempUpload(
                session_id=session.id,
                filename=result['filename'],
                path_original=result['path_original'],
                path_compressed=result['path_compressed']
            )
            db.session.add(temp)

        session.status = 'uploaded'
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Zdjęcie przesłane!',
            'image_url': f'/static/{result["path_compressed"]}'
        })

    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'QR upload error: {e}')
        return jsonify({'success': False, 'message': 'Wystąpił błąd podczas uploadu'}), 500


@public_bp.route('/payment/upload/<session_token>', methods=['GET'])
def payment_upload_page(session_token):
    """Mobile page for uploading payment confirmation via QR code."""
    from modules.client.payment_upload_sessions import PaymentUploadSession

    session = PaymentUploadSession.query.filter_by(session_token=session_token).first()
    if not session:
        abort(404)

    if session.is_expired:
        return render_template('public/payment_upload.html', expired=True, session=session)

    if session.status == 'uploaded':
        return render_template('public/payment_upload.html', already_uploaded=True, session=session)

    return render_template('public/payment_upload.html', session=session, expired=False, already_uploaded=False)


@public_bp.route('/payment/upload/<session_token>', methods=['POST'])
def payment_upload_photo(session_token):
    """Handle payment confirmation file upload from mobile."""
    import os
    import uuid
    from werkzeug.utils import secure_filename
    from modules.client.payment_upload_sessions import PaymentUploadSession
    from modules.client.payment_socket_events import notify_payment_uploaded

    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf'}
    MAX_SIZE = 5 * 1024 * 1024  # 5MB

    session = PaymentUploadSession.query.filter_by(session_token=session_token).first()
    if not session:
        return jsonify({'success': False, 'message': 'Nieprawidłowa sesja'}), 404

    if session.is_expired:
        return jsonify({'success': False, 'message': 'Sesja wygasła'}), 410

    if session.status == 'uploaded':
        return jsonify({'success': False, 'message': 'Plik już został przesłany'}), 409

    file = request.files.get('proof_file')
    if not file or not file.filename:
        return jsonify({'success': False, 'message': 'Nie wybrano pliku'}), 400

    # Validate extension
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'success': False, 'message': 'Dozwolone formaty: JPG, PNG, PDF'}), 400

    # Validate size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > MAX_SIZE:
        return jsonify({'success': False, 'message': 'Plik za duży. Max 5MB.'}), 400

    try:
        # Save file to uploads/payment_confirmations/
        original_filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{original_filename}"

        upload_folder = os.path.join(
            current_app.root_path, 'uploads', 'payment_confirmations'
        )
        os.makedirs(upload_folder, exist_ok=True)
        file.save(os.path.join(upload_folder, unique_filename))

        # Update session
        session.status = 'uploaded'
        session.uploaded_filename = unique_filename
        db.session.commit()

        # Notify desktop via Socket.IO
        current_app.logger.info(f'[PaymentQR] Upload success, calling notify for token: {session_token}')
        notify_payment_uploaded(session_token, unique_filename)
        current_app.logger.info(f'[PaymentQR] Notify completed for token: {session_token}')

        return jsonify({
            'success': True,
            'message': 'Potwierdzenie przesłane!'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Payment QR upload error: {e}')
        import traceback
        current_app.logger.error(f'Payment QR upload traceback: {traceback.format_exc()}')
        return jsonify({'success': False, 'message': 'Wystąpił błąd podczas uploadu'}), 500
