"""
Profile Routes
Endpointy zarządzania profilem użytkownika i avatarami
"""

from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from modules.profile import profile_bp
from modules.profile.models import AvatarSeries, Avatar
from modules.auth.models import User
from extensions import db
from utils.decorators import admin_required
from utils.image_processor import process_avatar, delete_avatar_file, delete_avatar_series_folder
import re


@profile_bp.route('/')
@login_required
def index():
    """
    Strona profilu użytkownika
    GET /profile
    """
    return render_template(
        'profile/index.html',
        title='Mój Profil'
    )


@profile_bp.route('/update', methods=['POST'])
@login_required
def update_profile():
    """
    Aktualizacja danych osobowych
    POST /profile/update
    """
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    phone = request.form.get('phone', '').strip()

    # Walidacja
    errors = []

    if not first_name:
        errors.append('Imię jest wymagane.')
    elif len(first_name) > 100:
        errors.append('Imię może mieć maksymalnie 100 znaków.')

    if not last_name:
        errors.append('Nazwisko jest wymagane.')
    elif len(last_name) > 100:
        errors.append('Nazwisko może mieć maksymalnie 100 znaków.')

    if phone and len(phone) > 20:
        errors.append('Numer telefonu może mieć maksymalnie 20 znaków.')

    if errors:
        for error in errors:
            flash(error, 'error')
        return redirect(url_for('profile.index'))

    # Aktualizacja danych (email nie jest edytowalny)
    try:
        current_user.first_name = first_name
        current_user.last_name = last_name
        current_user.phone = phone if phone else None

        db.session.commit()
        flash('Dane zostały zaktualizowane.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Wystąpił błąd podczas zapisywania: {str(e)}', 'error')

    return redirect(url_for('profile.index'))


@profile_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """
    Zmiana hasła
    POST /profile/change-password
    Returns JSON for AJAX requests, redirect for regular form submissions
    """
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    # Walidacja - zbieramy błędy per pole
    field_errors = {}

    if not current_password:
        field_errors['current_password'] = 'Obecne hasło jest wymagane.'
    elif not current_user.check_password(current_password):
        field_errors['current_password'] = 'Obecne hasło jest nieprawidłowe.'

    if not new_password:
        field_errors['new_password'] = 'Nowe hasło jest wymagane.'
    elif len(new_password) < 8:
        field_errors['new_password'] = 'Nowe hasło musi mieć co najmniej 8 znaków.'
    elif not re.search(r'[A-Z]', new_password):
        field_errors['new_password'] = 'Nowe hasło musi zawierać co najmniej jedną dużą literę.'
    elif not re.search(r'[a-z]', new_password):
        field_errors['new_password'] = 'Nowe hasło musi zawierać co najmniej jedną małą literę.'
    elif not re.search(r'\d', new_password):
        field_errors['new_password'] = 'Nowe hasło musi zawierać co najmniej jedną cyfrę.'

    if new_password and new_password != confirm_password:
        field_errors['confirm_password'] = 'Hasła nie są identyczne.'

    if field_errors:
        if is_ajax:
            return jsonify({'success': False, 'field_errors': field_errors}), 400
        for error in field_errors.values():
            flash(error, 'error')
        return redirect(url_for('profile.index'))

    # Zmiana hasła
    try:
        current_user.set_password(new_password)
        db.session.commit()

        if is_ajax:
            return jsonify({'success': True, 'message': 'Hasło zostało zmienione.'})

        flash('Hasło zostało zmienione.', 'success')

    except Exception as e:
        db.session.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': f'Wystąpił błąd: {str(e)}'}), 500
        flash(f'Wystąpił błąd podczas zmiany hasła: {str(e)}', 'error')

    return redirect(url_for('profile.index'))


# ============================================
# Avatar Management Routes (Admin only)
# ============================================

@profile_bp.route('/avatars')
@login_required
@admin_required
def avatars_admin():
    """
    Strona zarządzania avatarami (tylko admin)
    GET /profile/avatars
    """
    series_list = AvatarSeries.get_all_ordered()
    return render_template(
        'profile/avatars_admin.html',
        title='Zarządzanie avatarami',
        series_list=series_list
    )


@profile_bp.route('/avatars/series', methods=['POST'])
@login_required
@admin_required
def create_avatar_series():
    """
    Tworzenie nowej serii avatarów
    POST /profile/avatars/series
    """
    name = request.form.get('name', '').strip()
    slug = request.form.get('slug', '').strip().lower()

    # Walidacja
    if not name or not slug:
        flash('Nazwa i slug są wymagane.', 'error')
        return redirect(url_for('profile.avatars_admin'))

    if not re.match(r'^[a-z0-9-]+$', slug):
        flash('Slug może zawierać tylko małe litery, cyfry i myślniki.', 'error')
        return redirect(url_for('profile.avatars_admin'))

    # Sprawdź czy slug jest unikalny
    existing = AvatarSeries.get_by_slug(slug)
    if existing:
        flash('Seria o takim slug już istnieje.', 'error')
        return redirect(url_for('profile.avatars_admin'))

    try:
        # Pobierz najwyższy sort_order
        max_order = db.session.query(db.func.max(AvatarSeries.sort_order)).scalar() or 0

        series = AvatarSeries(
            name=name,
            slug=slug,
            sort_order=max_order + 1
        )
        db.session.add(series)
        db.session.commit()

        flash(f'Seria "{name}" została utworzona.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Błąd podczas tworzenia serii: {str(e)}', 'error')

    return redirect(url_for('profile.avatars_admin'))


@profile_bp.route('/avatars/series/<int:series_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_avatar_series(series_id):
    """
    Usunięcie serii avatarów
    DELETE /profile/avatars/series/<id>
    """
    series = AvatarSeries.query.get_or_404(series_id)

    # Sprawdź czy któryś użytkownik używa avatara z tej serii
    avatars_in_use = Avatar.query.join(User, User.avatar_id == Avatar.id)\
        .filter(Avatar.series_id == series_id).count()

    if avatars_in_use > 0:
        return jsonify({
            'success': False,
            'message': f'Nie można usunąć serii - {avatars_in_use} użytkowników używa avatarów z tej serii.'
        }), 400

    try:
        slug = series.slug

        # Usuń serię z bazy (kaskadowo usunie avatary)
        db.session.delete(series)
        db.session.commit()

        # Usuń folder z plikami
        delete_avatar_series_folder(slug)

        return jsonify({
            'success': True,
            'message': f'Seria została usunięta.'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 500


@profile_bp.route('/avatars/series/<int:series_id>/upload', methods=['POST'])
@login_required
@admin_required
def upload_avatars(series_id):
    """
    Upload avatarów do serii
    POST /profile/avatars/series/<id>/upload
    """
    series = AvatarSeries.query.get_or_404(series_id)

    if 'files' not in request.files:
        flash('Nie wybrano plików.', 'error')
        return redirect(url_for('profile.avatars_admin'))

    files = request.files.getlist('files')

    if not files or all(f.filename == '' for f in files):
        flash('Nie wybrano plików.', 'error')
        return redirect(url_for('profile.avatars_admin'))

    uploaded_count = 0
    errors = []

    # Pobierz początkowy numer raz, przed pętlą
    next_number = series.get_next_avatar_number()

    for file in files:
        if file.filename == '':
            continue

        try:
            # Przetwórz i zapisz avatar
            filename = process_avatar(file, series.slug, next_number)

            # Dodaj do bazy
            avatar = Avatar(
                series_id=series.id,
                filename=filename,
                sort_order=next_number
            )
            db.session.add(avatar)
            uploaded_count += 1
            next_number += 1  # Zwiększ numer dla następnego pliku

        except ValueError as e:
            errors.append(f'{file.filename}: {str(e)}')
        except Exception as e:
            errors.append(f'{file.filename}: Nieoczekiwany błąd')

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Błąd zapisu do bazy: {str(e)}', 'error')
        return redirect(url_for('profile.avatars_admin'))

    if uploaded_count > 0:
        flash(f'Dodano {uploaded_count} avatarów do serii "{series.name}".', 'success')

    for error in errors:
        flash(error, 'error')

    return redirect(url_for('profile.avatars_admin'))


@profile_bp.route('/avatars/<int:avatar_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_avatar(avatar_id):
    """
    Usunięcie pojedynczego avatara
    DELETE /profile/avatars/<id>
    """
    avatar = Avatar.query.get_or_404(avatar_id)

    # Sprawdź czy ktoś używa tego avatara
    users_using = User.query.filter_by(avatar_id=avatar_id).count()

    if users_using > 0:
        return jsonify({
            'success': False,
            'message': f'Nie można usunąć - {users_using} użytkowników używa tego avatara.'
        }), 400

    try:
        series_slug = avatar.series.slug
        filename = avatar.filename

        # Usuń z bazy
        db.session.delete(avatar)
        db.session.commit()

        # Usuń plik
        delete_avatar_file(series_slug, filename)

        return jsonify({
            'success': True,
            'message': 'Avatar został usunięty.'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 500


# ============================================
# Avatar Selection Routes (All users)
# ============================================

@profile_bp.route('/select-avatar')
@login_required
def select_avatar():
    """
    Strona wyboru avatara (Netflix-style)
    GET /profile/select-avatar
    """
    series_list = AvatarSeries.get_all_ordered()

    # Sprawdź czy są jakiekolwiek avatary
    has_avatars = any(s.avatar_count > 0 for s in series_list)

    return render_template(
        'profile/select_avatar.html',
        title='Wybierz avatar',
        series_list=series_list,
        has_avatars=has_avatars,
        current_avatar_id=current_user.avatar_id
    )


@profile_bp.route('/select-avatar', methods=['POST'])
@login_required
def save_avatar():
    """
    Zapisanie wybranego avatara
    POST /profile/select-avatar
    """
    avatar_id = request.form.get('avatar_id', type=int)

    if not avatar_id:
        flash('Nie wybrano avatara.', 'error')
        return redirect(url_for('profile.select_avatar'))

    # Sprawdź czy avatar istnieje
    avatar = Avatar.query.get(avatar_id)
    if not avatar:
        flash('Wybrany avatar nie istnieje.', 'error')
        return redirect(url_for('profile.select_avatar'))

    try:
        current_user.avatar_id = avatar_id
        db.session.commit()

        flash('Avatar został zapisany.', 'success')

        # Przekieruj na odpowiedni dashboard
        if current_user.is_admin() or current_user.is_mod():
            return redirect(url_for('admin.dashboard'))
        else:
            return redirect(url_for('client.dashboard'))

    except Exception as e:
        db.session.rollback()
        flash(f'Błąd podczas zapisywania: {str(e)}', 'error')
        return redirect(url_for('profile.select_avatar'))
