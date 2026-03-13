# modules/achievements/routes.py
from flask import render_template, request, jsonify, send_file
from flask_login import login_required, current_user
from modules.achievements import achievements_bp
from modules.achievements.services import AchievementService

service = AchievementService()


@achievements_bp.route('/')
@login_required
def gallery():
    """Gallery page — all achievements with progress."""
    return render_template('achievements/gallery.html')


@achievements_bp.route('/api/unseen')
@login_required
def api_unseen():
    """Get unseen achievements for unlock animation."""
    unseen = service.get_unseen(current_user)
    return jsonify({
        'success': True,
        'achievements': [
            {
                'id': ua.achievement.id,
                'slug': ua.achievement.slug,
                'name': ua.achievement.name,
                'description': ua.achievement.description,
                'rarity': ua.achievement.rarity,
                'icon_filename': ua.achievement.icon_filename,
                'category': ua.achievement.category,
                'tier': ua.achievement.tier,
                'stat_percentage': ua.achievement.stat.percentage if ua.achievement.stat else 0,
            }
            for ua in unseen
        ],
    })


@achievements_bp.route('/api/mark-seen', methods=['POST'])
@login_required
def api_mark_seen():
    """Mark achievements as seen after animation."""
    data = request.get_json(silent=True) or {}
    achievement_ids = data.get('achievement_ids', [])
    if achievement_ids:
        service.mark_seen(current_user, achievement_ids)
    return jsonify({'success': True})


@achievements_bp.route('/api/my')
@login_required
def api_my():
    """Full achievements list with progress."""
    achievements = service.get_user_achievements(current_user)
    unlocked = sum(1 for a in achievements if a['unlocked'])
    total = len(achievements)
    return jsonify({
        'success': True,
        'achievements': achievements,
        'summary': {
            'unlocked': unlocked,
            'total': total,
            'percent': round((unlocked / total) * 100) if total else 0,
        },
    })


@achievements_bp.route('/api/<int:achievement_id>/share', methods=['POST'])
@login_required
def api_share(achievement_id):
    """Mark achievement as shared."""
    from modules.achievements.models import UserAchievement
    from extensions import db

    ua = UserAchievement.query.filter_by(
        user_id=current_user.id, achievement_id=achievement_id
    ).first()
    if not ua:
        return jsonify({'success': False, 'error': 'Achievement not unlocked'}), 404

    if not ua.shared:
        ua.shared = True
        db.session.commit()
        service.check_event(current_user, 'achievement_shared', {
            'is_full_share': False,
        })

    return jsonify({'success': True})


@achievements_bp.route('/api/<int:achievement_id>/share-image')
@login_required
def api_share_image(achievement_id):
    """Generate and return share image as PNG."""
    from modules.achievements.models import UserAchievement
    from modules.achievements.share import generate_share_image

    ua = UserAchievement.query.filter_by(
        user_id=current_user.id, achievement_id=achievement_id
    ).first()
    if not ua:
        return jsonify({'success': False, 'error': 'Achievement not unlocked'}), 404

    fmt = request.args.get('format', '1:1')
    if fmt not in ('1:1', '9:16', '3:4'):
        fmt = '1:1'

    buf = generate_share_image(
        ua.achievement,
        fmt=fmt,
        unlocked_at=ua.unlocked_at,
        stat_percentage=ua.achievement.stat.percentage if ua.achievement.stat else 0,
    )

    filename = f'{ua.achievement.slug}-{fmt.replace(":", "x")}.png'
    return send_file(buf, mimetype='image/png', download_name=filename)
