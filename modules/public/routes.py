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
