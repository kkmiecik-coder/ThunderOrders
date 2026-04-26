"""
Admin CRUD for achievements (manual badges).
"""
import os
import re
from flask import current_app, request, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from PIL import Image

from extensions import db
from modules.admin import admin_bp
from modules.achievements.models import Achievement, UserAchievement
from modules.achievements import services as achievements_services
from modules.auth.models import User
from utils.decorators import admin_required


ALLOWED_IMAGE_MIMES = {'image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif'}
SLUG_RE = re.compile(r'^[a-z0-9-]+$')
MAX_ICON_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MIN_ICON_DIMENSION = 64


def _slugify(name):
    """Bardzo prosta slugifikacja PL → ASCII bez polskich znaków."""
    pl_map = str.maketrans({
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
        'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
        'Ą': 'a', 'Ć': 'c', 'Ę': 'e', 'Ł': 'l', 'Ń': 'n',
        'Ó': 'o', 'Ś': 's', 'Ź': 'z', 'Ż': 'z',
    })
    s = name.translate(pl_map).lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:80] or 'badge'


def _ensure_unique_slug(base_slug, exclude_id=None):
    """Zwraca slug + ewentualny suffix -2, -3, jeśli kolizja."""
    slug = base_slug
    n = 2
    while True:
        q = Achievement.query.filter_by(slug=slug)
        if exclude_id is not None:
            q = q.filter(Achievement.id != exclude_id)
        if not q.first():
            return slug
        slug = f'{base_slug}-{n}'
        n += 1


def _process_icon_upload(file_storage, slug):
    """
    Waliduje obraz i zapisuje go do TYMCZASOWEGO pliku obok docelowego.
    Zwraca tuple (tmp_path, final_path). Wywołujący musi:
    - po sukcesie DB: os.replace(tmp_path, final_path) + invalidate cache
    - po porażce: os.unlink(tmp_path)
    Rzuca ValueError przy błędzie walidacji.
    """
    if not file_storage or not file_storage.filename:
        raise ValueError('Brak pliku ikony')

    if file_storage.mimetype not in ALLOWED_IMAGE_MIMES:
        raise ValueError(f'Nieobsługiwany format: {file_storage.mimetype}')

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > MAX_ICON_SIZE_BYTES:
        raise ValueError(f'Plik za duży ({size} B), max {MAX_ICON_SIZE_BYTES} B')

    try:
        img = Image.open(file_storage.stream)
        img.verify()
    except Exception as e:
        raise ValueError(f'Nieprawidłowy plik obrazu: {e}')

    file_storage.stream.seek(0)
    img = Image.open(file_storage.stream).convert('RGBA')

    if img.width < MIN_ICON_DIMENSION or img.height < MIN_ICON_DIMENSION:
        raise ValueError(f'Obraz za mały ({img.width}×{img.height}), min {MIN_ICON_DIMENSION}×{MIN_ICON_DIMENSION}')

    img.thumbnail((256, 256), Image.LANCZOS)
    canvas = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    x = (256 - img.width) // 2
    y = (256 - img.height) // 2
    canvas.paste(img, (x, y), img)

    if not SLUG_RE.match(slug):
        raise ValueError(f'Nieprawidłowy slug: {slug}')

    upload_dir = os.path.join(current_app.static_folder, 'uploads', 'achievements')
    os.makedirs(upload_dir, exist_ok=True)
    final_path = os.path.join(upload_dir, f'{slug}@256.png')
    tmp_path = os.path.join(upload_dir, f'.{slug}@256.tmp.png')
    canvas.save(tmp_path, 'PNG', optimize=True)

    return tmp_path, final_path


def _commit_icon_upload(tmp_path, final_path, slug):
    """Atomically replace final_path with tmp_path; invalidate cache."""
    os.replace(tmp_path, final_path)
    from modules.achievements.services import _icon_cache
    _icon_cache.pop(slug, None)


def _abort_icon_upload(tmp_path):
    """Cleanup tmp file after failed DB commit."""
    try:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
    except OSError:
        pass  # Best-effort cleanup


# ========== ENDPOINTY ==========

@admin_bp.route('/achievements')
@login_required
@admin_required
def achievements_list():
    achievements = Achievement.query.order_by(
        Achievement.trigger_type.desc(),  # 'manual' first ('manual' > 'event' > 'cron')
        Achievement.sort_order
    ).all()
    holders_count = {
        ach.id: UserAchievement.query.filter_by(achievement_id=ach.id).count()
        for ach in achievements
    }
    return render_template(
        'admin/achievements/list.html',
        achievements=achievements,
        holders_count=holders_count,
    )


@admin_bp.route('/achievements/new', methods=['GET', 'POST'])
@login_required
@admin_required
def achievements_new():
    if request.method == 'POST':
        return _save_achievement(achievement=None)
    return render_template('admin/achievements/form.html', achievement=None, holders_count=0)


@admin_bp.route('/achievements/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def achievements_edit(id):
    achievement = Achievement.query.get_or_404(id)
    holders_count = UserAchievement.query.filter_by(achievement_id=id).count()
    if request.method == 'POST':
        return _save_achievement(achievement=achievement)
    return render_template(
        'admin/achievements/form.html',
        achievement=achievement,
        holders_count=holders_count,
    )


def _save_achievement(achievement):
    """Wspólna logika save dla new i edit."""
    is_new = achievement is None
    holders_count = 0 if is_new else UserAchievement.query.filter_by(achievement_id=achievement.id).count()

    name = (request.form.get('name') or '').strip()
    description = (request.form.get('description') or '').strip()
    category = request.form.get('category', 'special')
    rarity = request.form.get('rarity', 'cosmic')
    is_hidden = bool(request.form.get('is_hidden_until_unlocked'))
    is_active = bool(request.form.get('is_active'))
    slug_input = (request.form.get('slug') or '').strip().lower()

    # Walidacja
    errors = []
    if not name or len(name) > 120:
        errors.append('Nazwa wymagana, max 120 znaków.')
    if not description or len(description) > 255:
        errors.append('Opis wymagany, max 255 znaków.')
    if category not in ('orders', 'collection', 'loyalty', 'speed', 'exclusive',
                        'social', 'financial', 'profile', 'special'):
        errors.append('Nieprawidłowa kategoria.')
    if rarity not in ('common', 'rare', 'epic', 'legendary', 'cosmic'):
        errors.append('Nieprawidłowa rzadkość.')

    # Slug — auto-gen jeśli puste
    if not slug_input:
        slug_input = _slugify(name)
    if not SLUG_RE.match(slug_input):
        errors.append('Slug może zawierać tylko a-z, 0-9, „-".')

    # Edycja: pola zablokowane gdy są posiadacze
    if not is_new and holders_count > 0:
        if slug_input != achievement.slug:
            errors.append('Nie można zmienić slug — odznaka ma posiadaczy.')
        if category != achievement.category:
            errors.append('Nie można zmienić kategorii — odznaka ma posiadaczy.')

    if errors:
        for err in errors:
            flash(err, 'error')
        return render_template(
            'admin/achievements/form.html',
            achievement=achievement,
            holders_count=holders_count,
        ), 400

    # Slug uniqueness
    final_slug = _ensure_unique_slug(slug_input, exclude_id=None if is_new else achievement.id)

    # Upload ikony — najpierw waliduj i zapisz do tymczasowego pliku
    icon_file = request.files.get('icon')
    if is_new and (not icon_file or not icon_file.filename):
        flash('Ikona jest wymagana przy tworzeniu odznaki.', 'error')
        return render_template('admin/achievements/form.html', achievement=achievement, holders_count=holders_count), 400

    tmp_icon_path = None
    final_icon_path = None
    if icon_file and icon_file.filename:
        try:
            tmp_icon_path, final_icon_path = _process_icon_upload(icon_file, final_slug)
        except ValueError as e:
            flash(f'Błąd ikony: {e}', 'error')
            return render_template('admin/achievements/form.html', achievement=achievement, holders_count=holders_count), 400

    # Save do DB — jeśli padnie, czyścimy tmp file
    try:
        if is_new:
            achievement = Achievement(
                slug=final_slug,
                name=name,
                description=description,
                category=category,
                rarity=rarity,
                trigger_type='manual',
                trigger_config={},
                is_hidden_until_unlocked=is_hidden,
                is_active=is_active,
                sort_order=999,  # manual badges sortuj na końcu domyślnie
            )
            db.session.add(achievement)
        else:
            achievement.name = name
            achievement.description = description
            achievement.rarity = rarity
            achievement.is_hidden_until_unlocked = is_hidden
            achievement.is_active = is_active
            if holders_count == 0:
                achievement.slug = final_slug
                achievement.category = category

        db.session.commit()
    except Exception:
        db.session.rollback()
        _abort_icon_upload(tmp_icon_path)
        current_app.logger.exception(f'Failed to save achievement (is_new={is_new})')
        flash('Błąd zapisu odznaki w bazie. Sprawdź logi.', 'error')
        return render_template('admin/achievements/form.html', achievement=achievement, holders_count=holders_count), 500

    # Po sukcesie commit'u — atomic rename tmp -> final
    if tmp_icon_path and final_icon_path:
        try:
            _commit_icon_upload(tmp_icon_path, final_icon_path, final_slug)
        except OSError as e:
            current_app.logger.exception(f'Failed to finalize icon upload for slug={final_slug}: {e}')
            flash('Odznaka zapisana, ale wystąpił problem z zapisem ikony — wgraj ją ponownie.', 'warning')

    flash(f'Odznaka „{achievement.name}" zapisana.', 'success')
    return redirect(url_for('admin.achievements_list'))


@admin_bp.route('/achievements/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def achievements_delete(id):
    """Soft-delete: is_active=False."""
    achievement = Achievement.query.get_or_404(id)
    achievement.is_active = False
    db.session.commit()
    flash(f'Odznaka „{achievement.name}" dezaktywowana.', 'success')
    return redirect(url_for('admin.achievements_list'))


@admin_bp.route('/achievements/<int:id>/holders')
@login_required
@admin_required
def achievements_holders(id):
    achievement = Achievement.query.get_or_404(id)
    holders = (UserAchievement.query
               .filter_by(achievement_id=id)
               .join(User, UserAchievement.user_id == User.id)
               .order_by(UserAchievement.unlocked_at.desc())
               .all())
    return render_template(
        'admin/achievements/holders.html',
        achievement=achievement,
        holders=holders,
    )


@admin_bp.route('/achievements/<int:id>/holders/<int:user_id>/revoke', methods=['POST'])
@login_required
@admin_required
def achievements_revoke_holder(id, user_id):
    achievement = Achievement.query.get_or_404(id)
    user = User.query.get_or_404(user_id)

    if achievement.trigger_type != 'manual':
        flash('Można odbierać tylko odznaki ręczne.', 'error')
        return redirect(url_for('admin.achievements_holders', id=id))

    service = achievements_services.AchievementService()
    if service.revoke_manual(user, achievement, revoked_by=current_user):
        flash(f'Odebrano „{achievement.name}" od {user.email}.', 'success')
    else:
        flash('Klient nie posiadał tej odznaki.', 'warning')
    return redirect(url_for('admin.achievements_holders', id=id))
