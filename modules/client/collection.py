"""
Collection Routes - Moja Kolekcja
==================================

Routes for managing user's K-pop collection.
"""

from flask import render_template, request, jsonify, current_app, abort
from flask_login import login_required, current_user
from modules.client import client_bp
from extensions import db


@client_bp.route('/collection')
@login_required
def collection_list():
    """Main collection page with grid/list view."""
    from modules.client.models import CollectionItem

    # Tryb widoku (grid / list / carousel)
    view = request.args.get('view', 'grid')
    if view not in ('grid', 'list', 'carousel'):
        view = 'grid'

    # Search
    search = request.args.get('search', '').strip()

    # Sort
    sort = request.args.get('sort', 'newest')

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 24

    # Build query
    query = CollectionItem.query.filter_by(user_id=current_user.id)

    if search:
        query = query.filter(CollectionItem.name.ilike(f'%{search}%'))

    # Sort
    if sort == 'oldest':
        query = query.order_by(CollectionItem.created_at.asc())
    elif sort == 'name_asc':
        query = query.order_by(CollectionItem.name.asc())
    elif sort == 'price_desc':
        query = query.order_by(
            db.case((CollectionItem.market_price.is_(None), 1), else_=0),
            CollectionItem.market_price.desc()
        )
    else:  # newest (default)
        query = query.order_by(CollectionItem.created_at.desc())

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    items = pagination.items

    # Stats
    total_items = CollectionItem.query.filter_by(user_id=current_user.id).count()
    total_value_result = db.session.query(
        db.func.sum(CollectionItem.market_price)
    ).filter(
        CollectionItem.user_id == current_user.id,
        CollectionItem.market_price.isnot(None)
    ).scalar()
    total_value = float(total_value_result) if total_value_result else 0

    # Konfiguracja publicznej strony
    from modules.client.models import PublicCollectionConfig
    public_config = PublicCollectionConfig.query.filter_by(user_id=current_user.id).first()

    return render_template('client/collection/index.html',
                           items=items,
                           pagination=pagination,
                           view=view,
                           search=search,
                           sort=sort,
                           total_items=total_items,
                           total_value=total_value,
                           public_config=public_config)


@client_bp.route('/collection/add', methods=['POST'])
@login_required
def collection_add():
    """Add a new collection item (AJAX with FormData)."""
    from modules.client.models import CollectionItem, CollectionItemImage
    from utils.image_processor import process_collection_upload

    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Nazwa jest wymagana'}), 400

    market_price = request.form.get('market_price', '').strip()
    notes = request.form.get('notes', '').strip()

    try:
        item = CollectionItem(
            user_id=current_user.id,
            name=name,
            market_price=float(market_price) if market_price else None,
            notes=notes if notes else None,
            source='manual'
        )
        db.session.add(item)
        db.session.flush()  # Get item.id

        # Handle images (max 3)
        files = request.files.getlist('images')
        for i, file in enumerate(files[:3]):
            if file and file.filename:
                result = process_collection_upload(file, current_user.id)
                image = CollectionItemImage(
                    collection_item_id=item.id,
                    filename=result['filename'],
                    path_original=result['path_original'],
                    path_compressed=result['path_compressed'],
                    is_primary=(i == 0),
                    sort_order=i
                )
                db.session.add(image)

        # Obsługa zdjęć z QR upload (temp_uploads)
        temp_session_token = request.form.get('qr_session_token', '').strip()
        if temp_session_token:
            from modules.client.models import CollectionUploadSession
            qr_session = CollectionUploadSession.query.filter_by(
                session_token=temp_session_token,
                user_id=current_user.id,
                status='uploaded'
            ).first()
            if qr_session and qr_session.temp_uploads:
                for temp in qr_session.temp_uploads:
                    if item.can_add_image:
                        img = CollectionItemImage(
                            collection_item_id=item.id,
                            filename=temp.filename,
                            path_original=temp.path_original,
                            path_compressed=temp.path_compressed,
                            is_primary=(item.images_count == 0),
                            sort_order=item.images_count
                        )
                        db.session.add(img)
                        db.session.flush()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Przedmiot dodany do kolekcji',
            'item_id': item.id
        })

    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Collection add error: {e}')
        return jsonify({'success': False, 'message': 'Wystąpił błąd podczas dodawania'}), 500


@client_bp.route('/collection/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def collection_edit(item_id):
    """GET: return item data as JSON. POST: edit item."""
    from modules.client.models import CollectionItem

    item = CollectionItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        abort(403)

    if request.method == 'GET':
        images = []
        for img in item.images:
            images.append({
                'id': img.id,
                'url': f'/static/{img.path_compressed}',
                'is_primary': img.is_primary,
                'source': 'collection'
            })
        # Fallback: include product images if no collection images and product is linked
        if not images and item.product_id and item.product:
            for img in item.product.images:
                images.append({
                    'id': img.id,
                    'url': f'/static/{img.path_compressed}',
                    'is_primary': img.is_primary,
                    'source': 'product'
                })
        return jsonify({
            'success': True,
            'item': {
                'id': item.id,
                'name': item.name,
                'market_price': float(item.market_price) if item.market_price else None,
                'notes': item.notes,
                'images': images,
                'can_add_image': item.can_add_image
            }
        })

    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Nazwa jest wymagana'}), 400

    market_price = request.form.get('market_price', '').strip()
    notes = request.form.get('notes', '').strip()

    try:
        item.name = name
        item.market_price = float(market_price) if market_price else None
        item.notes = notes if notes else None

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Przedmiot zaktualizowany'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Collection edit error: {e}')
        return jsonify({'success': False, 'message': 'Wystąpił błąd podczas edycji'}), 500


@client_bp.route('/collection/<int:item_id>/delete', methods=['DELETE'])
@login_required
def collection_delete(item_id):
    """Delete a collection item and its files."""
    from modules.client.models import CollectionItem
    from utils.image_processor import delete_collection_image_files

    item = CollectionItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        abort(403)

    try:
        # Delete image files
        for image in item.images:
            delete_collection_image_files(image.path_original, image.path_compressed)

        db.session.delete(item)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Przedmiot usunięty z kolekcji'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Collection delete error: {e}')
        return jsonify({'success': False, 'message': 'Wystąpił błąd podczas usuwania'}), 500


@client_bp.route('/collection/<int:item_id>/images', methods=['POST'])
@login_required
def collection_add_image(item_id):
    """Upload additional image to a collection item."""
    from modules.client.models import CollectionItem, CollectionItemImage
    from utils.image_processor import process_collection_upload

    item = CollectionItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        abort(403)

    if not item.can_add_image:
        return jsonify({'success': False, 'message': 'Maksymalnie 3 zdjęcia na przedmiot'}), 400

    file = request.files.get('image')
    if not file or not file.filename:
        return jsonify({'success': False, 'message': 'Nie wybrano pliku'}), 400

    try:
        result = process_collection_upload(file, current_user.id)
        is_primary = item.images_count == 0

        image = CollectionItemImage(
            collection_item_id=item.id,
            filename=result['filename'],
            path_original=result['path_original'],
            path_compressed=result['path_compressed'],
            is_primary=is_primary,
            sort_order=item.images_count
        )
        db.session.add(image)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Zdjęcie dodane',
            'image': {
                'id': image.id,
                'url': f'/static/{image.path_compressed}',
                'is_primary': image.is_primary
            }
        })

    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Collection image upload error: {e}')
        return jsonify({'success': False, 'message': 'Wystąpił błąd podczas uploadu'}), 500


@client_bp.route('/collection/<int:item_id>/images/<int:image_id>', methods=['DELETE'])
@login_required
def collection_delete_image(item_id, image_id):
    """Delete a single image from a collection item."""
    from modules.client.models import CollectionItem, CollectionItemImage
    from utils.image_processor import delete_collection_image_files

    item = CollectionItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        abort(403)

    image = CollectionItemImage.query.get_or_404(image_id)
    if image.collection_item_id != item.id:
        abort(404)

    try:
        was_primary = image.is_primary
        delete_collection_image_files(image.path_original, image.path_compressed)

        db.session.delete(image)
        db.session.flush()

        # If deleted image was primary, set next one as primary
        if was_primary and item.images:
            item.images[0].is_primary = True

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Zdjęcie usunięte'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Collection image delete error: {e}')
        return jsonify({'success': False, 'message': 'Wystąpił błąd podczas usuwania'}), 500


@client_bp.route('/collection/<int:item_id>/images/<int:image_id>/primary', methods=['POST'])
@login_required
def collection_set_primary_image(item_id, image_id):
    """Set an image as the primary image for a collection item."""
    from modules.client.models import CollectionItem, CollectionItemImage

    item = CollectionItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        abort(403)

    image = CollectionItemImage.query.get_or_404(image_id)
    if image.collection_item_id != item.id:
        abort(404)

    try:
        # Unset all primary flags
        for img in item.images:
            img.is_primary = False

        # Set new primary
        image.is_primary = True
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Zdjęcie główne zmienione'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Collection set primary error: {e}')
        return jsonify({'success': False, 'message': 'Wystąpił błąd'}), 500


# ===== PUBLICZNA STRONA KOLEKCJI =====

@client_bp.route('/collection/public/create', methods=['POST'])
@login_required
def collection_public_create():
    """Utwórz konfigurację publicznej strony kolekcji."""
    from modules.client.models import PublicCollectionConfig

    existing = PublicCollectionConfig.query.filter_by(user_id=current_user.id).first()
    if existing:
        return jsonify({'success': False, 'message': 'Publiczna strona już istnieje'}), 409

    try:
        token = PublicCollectionConfig.generate_token()
        config = PublicCollectionConfig(
            user_id=current_user.id,
            token=token,
            show_prices=True,
            is_active=True
        )
        db.session.add(config)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Publiczna strona utworzona',
            'token': config.token,
            'url': f'/collection/{config.token}'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Public config create error: {e}')
        return jsonify({'success': False, 'message': 'Wystąpił błąd'}), 500


@client_bp.route('/collection/public/config', methods=['GET'])
@login_required
def collection_public_config_get():
    """Pobierz konfigurację publicznej strony."""
    from modules.client.models import PublicCollectionConfig, CollectionItem

    config = PublicCollectionConfig.query.filter_by(user_id=current_user.id).first()
    if not config:
        return jsonify({'success': False, 'exists': False})

    # Lista itemów z flagą is_public
    items = CollectionItem.query.filter_by(user_id=current_user.id)\
        .order_by(CollectionItem.name.asc()).all()
    items_data = [{
        'id': item.id,
        'name': item.name,
        'is_public': item.is_public,
        'image_url': item.image_url
    } for item in items]

    return jsonify({
        'success': True,
        'exists': True,
        'config': {
            'token': config.token,
            'show_prices': config.show_prices,
            'is_active': config.is_active,
            'url': f'/collection/{config.token}'
        },
        'items': items_data
    })


@client_bp.route('/collection/public/config', methods=['POST'])
@login_required
def collection_public_config_update():
    """Aktualizuj konfigurację publicznej strony."""
    from modules.client.models import PublicCollectionConfig

    config = PublicCollectionConfig.query.filter_by(user_id=current_user.id).first()
    if not config:
        return jsonify({'success': False, 'message': 'Brak konfiguracji'}), 404

    data = request.get_json()
    if data is None:
        return jsonify({'success': False, 'message': 'Brak danych'}), 400

    try:
        if 'show_prices' in data:
            config.show_prices = bool(data['show_prices'])
        if 'is_active' in data:
            config.is_active = bool(data['is_active'])

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Ustawienia zapisane'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Public config update error: {e}')
        return jsonify({'success': False, 'message': 'Wystąpił błąd'}), 500


@client_bp.route('/collection/<int:item_id>/toggle-public', methods=['POST'])
@login_required
def collection_toggle_public(item_id):
    """Przełącz widoczność itemu na publicznej stronie."""
    from modules.client.models import CollectionItem

    item = CollectionItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        abort(403)

    try:
        item.is_public = not item.is_public
        db.session.commit()

        return jsonify({
            'success': True,
            'is_public': item.is_public
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Wystąpił błąd'}), 500


@client_bp.route('/collection/public/toggle-all', methods=['POST'])
@login_required
def collection_toggle_all_public():
    """Zaznacz/odznacz wszystkie itemy jako publiczne."""
    from modules.client.models import CollectionItem

    data = request.get_json()
    if data is None:
        return jsonify({'success': False, 'message': 'Brak danych'}), 400

    is_public = bool(data.get('is_public', True))

    try:
        CollectionItem.query.filter_by(user_id=current_user.id).update(
            {'is_public': is_public}
        )
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Wszystkie przedmioty zaktualizowane'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Wystąpił błąd'}), 500


# ===== QR UPLOAD =====

@client_bp.route('/collection/qr-session', methods=['POST'])
@login_required
def collection_qr_session_create():
    """Utwórz sesję uploadu QR (zwraca session_token + QR data URI)."""
    import secrets
    import io
    import base64
    import qrcode
    from modules.client.models import CollectionUploadSession, get_local_now
    from datetime import timedelta

    data = request.get_json() or {}
    item_id = data.get('item_id')

    # Walidacja item_id jeśli podany
    if item_id:
        from modules.client.models import CollectionItem
        item = CollectionItem.query.get(item_id)
        if not item or item.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Nieprawidłowy przedmiot'}), 400
        if not item.can_add_image:
            return jsonify({'success': False, 'message': 'Maksymalnie 3 zdjęcia'}), 400

    try:
        # Wyczyść stare wygasłe sesje tego użytkownika
        now = get_local_now()
        expired = CollectionUploadSession.query.filter(
            CollectionUploadSession.user_id == current_user.id,
            CollectionUploadSession.expires_at < now
        ).all()
        for s in expired:
            db.session.delete(s)

        # Utwórz nową sesję
        session_token = secrets.token_urlsafe(32)
        session = CollectionUploadSession(
            session_token=session_token,
            user_id=current_user.id,
            collection_item_id=item_id,
            status='waiting',
            expires_at=now + timedelta(minutes=15)
        )
        db.session.add(session)
        db.session.commit()

        # Generuj QR code
        upload_url = request.url_root.rstrip('/') + f'/collection/upload/{session_token}'
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(upload_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color='black', back_color='white')

        # Konwertuj na base64 data URI
        buffer = io.BytesIO()
        qr_img.save(buffer, format='PNG')
        qr_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        qr_data_uri = f'data:image/png;base64,{qr_base64}'

        return jsonify({
            'success': True,
            'session_token': session_token,
            'qr_data_uri': qr_data_uri,
            'upload_url': upload_url,
            'expires_in': 900  # 15 minut w sekundach
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'QR session create error: {e}')
        return jsonify({'success': False, 'message': 'Wystąpił błąd'}), 500


@client_bp.route('/collection/qr-session/<token>/status', methods=['GET'])
@login_required
def collection_qr_session_status(token):
    """Polling - sprawdź czy upload się pojawił."""
    from modules.client.models import CollectionUploadSession

    session = CollectionUploadSession.query.filter_by(
        session_token=token,
        user_id=current_user.id
    ).first()

    if not session:
        return jsonify({'success': False, 'message': 'Sesja nie znaleziona'}), 404

    if session.is_expired:
        return jsonify({
            'success': True,
            'status': 'expired'
        })

    if session.status == 'uploaded':
        # Znajdź URL uploadu
        image_url = None
        if session.collection_item_id:
            # Bezpośrednio dodane do itemu - pobierz ostatni obraz
            from modules.client.models import CollectionItemImage
            img = CollectionItemImage.query.filter_by(
                collection_item_id=session.collection_item_id
            ).order_by(CollectionItemImage.id.desc()).first()
            if img:
                image_url = f'/static/{img.path_compressed}'
        elif session.temp_uploads:
            image_url = f'/static/{session.temp_uploads[0].path_compressed}'

        return jsonify({
            'success': True,
            'status': 'uploaded',
            'image_url': image_url
        })

    return jsonify({
        'success': True,
        'status': 'waiting'
    })
