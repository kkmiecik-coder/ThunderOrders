import os

from flask import current_app
from extensions import db
from modules.achievements.models import Achievement, UserAchievement, AchievementStat
from modules.achievements.checkers import get_metric_value
from modules.auth.models import User, get_local_now

# Cache: slug -> bool (file exists on disk)
_icon_cache = {}


def has_achievement_icon(slug):
    """Check if an achievement icon file exists on disk (cached)."""
    if slug in _icon_cache:
        return _icon_cache[slug]
    upload_dir = os.path.join(current_app.static_folder, 'uploads', 'achievements')
    exists = os.path.isfile(os.path.join(upload_dir, f'{slug}@256.png'))
    _icon_cache[slug] = exists
    return exists


# Maps event types to the metrics that should be checked
EVENT_METRICS = {
    'order_placed': [
        'orders_count', 'single_order_items', 'total_spent',
        'order_hour_range', 'orders_in_window', 'orders_in_weekend',
        'time_since_drop', 'time_since_page_visit', 'exclusive_orders',
    ],
    'collection_add': ['collection_items'],
    'photo_upload': ['items_with_photos'],
    'collection_public_toggle': ['collection_public'],
    'profile_update': ['profile_completed', 'all_badges_unlocked'],
    'avatar_change': ['has_avatar', 'all_badges_unlocked'],
    'address_added': ['shipping_addresses', 'all_badges_unlocked'],
    'email_verify': ['email_verified', 'all_badges_unlocked'],
    'achievement_shared': ['shared_achievements', 'shared_full_collection'],
}


class AchievementService:

    def check_event(self, user, event_type, context=None):
        """
        Check all event-triggered achievements relevant to this event.
        Called from route handlers after successful actions.
        Returns list of newly unlocked Achievement objects.
        """
        if not user or not user.is_authenticated:
            return []

        relevant_metrics = EVENT_METRICS.get(event_type, [])
        if not relevant_metrics:
            return []

        # Get achievements for these metrics that user hasn't unlocked yet
        already_unlocked = db.session.query(UserAchievement.achievement_id).filter_by(
            user_id=user.id
        ).scalar_subquery()

        candidates = Achievement.query.filter(
            Achievement.trigger_type == 'event',
            Achievement.is_active == True,  # noqa: E712
            Achievement.id.notin_(already_unlocked),
        ).all()

        # Filter to candidates whose metric matches the event
        relevant_candidates = [
            a for a in candidates
            if a.trigger_config.get('metric') in relevant_metrics
        ]

        # Sort: non-meta first, meta last (so profile-all is checked after individual profile badges)
        relevant_candidates.sort(key=lambda a: a.trigger_config.get('metric') == 'all_badges_unlocked')

        newly_unlocked = []
        for achievement in relevant_candidates:
            config = achievement.trigger_config
            metric = config.get('metric')
            _, meets = get_metric_value(user, metric, config, context)
            if meets:
                self.unlock(user, achievement)
                newly_unlocked.append(achievement)

        return newly_unlocked

    def run_daily_checks(self):
        """
        Run cron-based checks for all active users.
        Called by `flask achievements check-daily`.
        """
        cron_achievements = Achievement.query.filter_by(
            trigger_type='cron', is_active=True
        ).all()

        users = User.query.filter_by(is_active=True, role='client').all()
        total_unlocked = 0

        for user in users:
            already_unlocked_ids = {
                ua.achievement_id
                for ua in UserAchievement.query.filter_by(user_id=user.id).all()
            }

            for achievement in cron_achievements:
                if achievement.id in already_unlocked_ids:
                    continue
                config = achievement.trigger_config
                metric = config.get('metric')
                _, meets = get_metric_value(user, metric, config)
                if meets:
                    self.unlock(user, achievement)
                    total_unlocked += 1

        # Update stats
        self.recalculate_stats()

        return {'unlocked': total_unlocked}

    def backfill_all(self):
        """
        One-time retroactive check for all users against all achievements.
        Marks unlocked achievements as seen=True (no animation for past achievements).
        """
        all_achievements = Achievement.query.filter_by(is_active=True).all()
        users = User.query.filter_by(is_active=True).all()
        total_unlocked = 0
        users_affected = set()

        for user in users:
            already_unlocked_ids = {
                ua.achievement_id
                for ua in UserAchievement.query.filter_by(user_id=user.id).all()
            }

            for achievement in all_achievements:
                if achievement.id in already_unlocked_ids:
                    continue
                config = achievement.trigger_config
                metric = config.get('metric')
                _, meets = get_metric_value(user, metric, config)
                if meets:
                    self.unlock(user, achievement, seen=True)
                    total_unlocked += 1
                    users_affected.add(user.id)

        self.recalculate_stats()
        return {'unlocked': total_unlocked, 'users': len(users_affected)}

    def unlock(self, user, achievement, seen=False):
        """Create UserAchievement record."""
        existing = UserAchievement.query.filter_by(
            user_id=user.id, achievement_id=achievement.id
        ).first()
        if existing:
            return  # Already unlocked

        try:
            ua = UserAchievement(
                user_id=user.id,
                achievement_id=achievement.id,
                seen=seen,
            )
            db.session.add(ua)
            db.session.flush()
        except Exception:
            db.session.rollback()
            return  # Duplicate from race condition, safe to ignore

    def get_unseen(self, user):
        """Get unseen achievements for unlock animation."""
        return UserAchievement.query.filter_by(
            user_id=user.id, seen=False
        ).join(Achievement).order_by(UserAchievement.unlocked_at.asc()).all()

    def mark_seen(self, user, achievement_ids):
        """Mark achievements as seen after animation is shown."""
        UserAchievement.query.filter(
            UserAchievement.user_id == user.id,
            UserAchievement.achievement_id.in_(achievement_ids),
        ).update({'seen': True}, synchronize_session='fetch')
        db.session.commit()

    def get_user_achievements(self, user):
        """
        Get all achievements with user's progress.
        Returns list of dicts with achievement info + unlock status + progress.
        """
        all_achievements = Achievement.query.filter_by(is_active=True).order_by(
            Achievement.sort_order
        ).all()

        unlocked_map = {
            ua.achievement_id: ua
            for ua in UserAchievement.query.filter_by(user_id=user.id).all()
        }

        stats_map = {
            s.achievement_id: s
            for s in AchievementStat.query.all()
        }

        result = []
        for a in all_achievements:
            ua = unlocked_map.get(a.id)
            stat = stats_map.get(a.id)
            config = a.trigger_config
            metric = config.get('metric')

            # Calculate progress for locked achievements
            progress = None
            if not ua and metric and 'threshold' in config:
                current_val, _ = get_metric_value(user, metric, config)
                progress = {
                    'current': current_val,
                    'target': config['threshold'],
                    'percent': min(100, int((current_val / config['threshold']) * 100)) if config['threshold'] else 0,
                }

            result.append({
                'id': a.id,
                'slug': a.slug,
                'name': a.name,
                'description': a.description,
                'category': a.category,
                'rarity': a.rarity,
                'has_icon': has_achievement_icon(a.slug),
                'tier': a.tier,
                'tier_group': a.tier_group,
                'unlocked': ua is not None,
                'unlocked_at': ua.unlocked_at.isoformat() if ua else None,
                'shared': ua.shared if ua else False,
                'progress': progress,
                'stat_percentage': stat.percentage if stat else 0,
                'stat_total': stat.total_unlocked if stat else 0,
            })

        return result

    def recalculate_stats(self):
        """Recalculate percentage for all achievements and invalidate share image cache."""
        total_clients = User.query.filter_by(is_active=True, role='client').count()
        if total_clients == 0:
            return

        achievements = Achievement.query.filter_by(is_active=True).all()
        for a in achievements:
            unlocked_count = (
                UserAchievement.query
                .join(User, UserAchievement.user_id == User.id)
                .filter(
                    UserAchievement.achievement_id == a.id,
                    User.is_active == True,
                    User.role == 'client',
                )
                .count()
            )
            stat = AchievementStat.query.filter_by(achievement_id=a.id).first()
            if not stat:
                stat = AchievementStat(achievement_id=a.id)
                db.session.add(stat)
            stat.total_unlocked = unlocked_count
            stat.percentage = min(round((unlocked_count / total_clients) * 100, 1), 100.0)

        db.session.commit()

        # Invalidate share image cache (percentages changed)
        try:
            from modules.achievements.share import invalidate_share_cache
            invalidate_share_cache()
        except Exception:
            pass  # Non-critical, share.py may not exist yet
