from datetime import datetime, timedelta
from extensions import db


def get_metric_value(user, metric, config, context=None):
    """
    Get current value for a metric. Returns (current_value, meets_condition).

    Args:
        user: User object
        metric: string metric name from trigger_config
        config: full trigger_config dict
        context: optional dict with event-specific data (e.g., order info)

    Returns:
        tuple: (current_value: int/float/bool, meets_condition: bool)
    """
    evaluator = METRIC_EVALUATORS.get(metric)
    if not evaluator:
        return (0, False)
    return evaluator(user, config, context)


def _orders_count(user, config, context):
    from modules.orders.models import Order
    count = Order.query.filter_by(user_id=user.id).count()
    return (count, count >= config['threshold'])


def _collection_items(user, config, context):
    from modules.client.models import CollectionItem
    count = CollectionItem.query.filter_by(user_id=user.id).count()
    return (count, count >= config['threshold'])


def _items_with_photos(user, config, context):
    from modules.client.models import CollectionItem, CollectionItemImage
    count = db.session.query(CollectionItem.id).filter(
        CollectionItem.user_id == user.id
    ).join(CollectionItemImage).distinct().count()
    return (count, count >= config['threshold'])


def _total_spent(user, config, context):
    from modules.orders.models import Order
    result = db.session.query(db.func.coalesce(db.func.sum(Order.total_amount), 0)).filter(
        Order.user_id == user.id
    ).scalar()
    total = float(result)
    return (total, total >= config['threshold'])


def _login_streak(user, config, context):
    streak = user.login_streak or 0
    return (streak, streak >= config['threshold'])


def _account_age_days(user, config, context):
    if not user.created_at:
        return (0, False)
    days = (datetime.now() - user.created_at).days
    return (days, days >= config['threshold'])


def _single_order_items(user, config, context):
    if not context or 'items_count' not in context:
        return (0, False)
    count = context['items_count']
    return (count, count >= config['threshold'])


def _order_hour_range(user, config, context):
    now = datetime.now()
    hour = now.hour
    start, end = config['start'], config['end']
    in_range = start <= hour < end
    return (hour, in_range)


def _orders_in_window(user, config, context):
    from modules.orders.models import Order
    window_start = datetime.now() - timedelta(days=config['window_days'])
    count = Order.query.filter(
        Order.user_id == user.id,
        Order.created_at >= window_start
    ).count()
    return (count, count >= config['threshold'])


def _orders_in_weekend(user, config, context):
    from modules.orders.models import Order
    now = datetime.now()
    weekday = now.weekday()  # 0=Mon, 5=Sat, 6=Sun
    if weekday == 5:  # Saturday
        weekend_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif weekday == 6:  # Sunday
        weekend_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        return (0, False)  # Not a weekend

    count = Order.query.filter(
        Order.user_id == user.id,
        Order.created_at >= weekend_start
    ).count()
    return (count, count >= config['threshold'])


def _time_since_drop(user, config, context):
    if not context or 'offer_page_starts_at' not in context:
        return (0, False)
    starts_at = context['offer_page_starts_at']
    if not starts_at:
        return (0, False)
    now = datetime.now()
    minutes_diff = (now - starts_at).total_seconds() / 60
    return (minutes_diff, minutes_diff <= config['max_minutes'])


def _time_since_page_visit(user, config, context):
    if not context or 'page_entered_at' not in context:
        return (0, False)
    try:
        entered_at = datetime.fromtimestamp(context['page_entered_at'] / 1000)
        now = datetime.now()
        minutes_diff = (now - entered_at).total_seconds() / 60
        return (minutes_diff, minutes_diff <= config['max_minutes'])
    except (ValueError, TypeError, OSError):
        return (0, False)


def _offer_orders(user, config, context):
    """Liczba zamówień ze stron sprzedaży (exclusive + preorder)"""
    from modules.orders.models import Order
    count = Order.query.filter(
        Order.user_id == user.id,
        Order.offer_page_id.isnot(None)
    ).count()
    return (count, count >= config['threshold'])


def _distinct_offer_pages(user, config, context):
    """Liczba unikalnych stron sprzedaży na których użytkownik złożył zamówienie"""
    from modules.orders.models import Order
    count = db.session.query(db.func.count(db.func.distinct(Order.offer_page_id))).filter(
        Order.user_id == user.id,
        Order.offer_page_id.isnot(None)
    ).scalar()
    return (count, count >= config['threshold'])


def _profile_completed(user, config, context):
    val = bool(user.profile_completed)
    return (val, val == config['value'])


def _email_verified(user, config, context):
    val = bool(user.email_verified)
    return (val, val == config['value'])


def _has_avatar(user, config, context):
    val = user.avatar_id is not None
    return (val, val == config['value'])


def _collection_public(user, config, context):
    from modules.client.models import PublicCollectionConfig
    public = PublicCollectionConfig.query.filter_by(user_id=user.id).first()
    val = public is not None
    return (val, val == config['value'])


def _shipping_addresses(user, config, context):
    count = user.shipping_addresses.count() if hasattr(user.shipping_addresses, 'count') else len(user.shipping_addresses)
    return (count, count >= config['threshold'])


def _shared_achievements(user, config, context):
    from modules.achievements.models import UserAchievement
    count = UserAchievement.query.filter_by(user_id=user.id, shared=True).count()
    return (count, count >= config['threshold'])


def _shared_full_collection(user, config, context):
    if not context or not context.get('is_full_share'):
        return (False, False)
    return (True, True)


def _all_badges_unlocked(user, config, context):
    from modules.achievements.models import Achievement, UserAchievement
    required_slugs = config['slugs']
    unlocked_slugs = db.session.query(Achievement.slug).join(UserAchievement).filter(
        UserAchievement.user_id == user.id,
        Achievement.slug.in_(required_slugs)
    ).all()
    unlocked_set = {s[0] for s in unlocked_slugs}
    all_unlocked = unlocked_set >= set(required_slugs)
    return (len(unlocked_set), all_unlocked)


METRIC_EVALUATORS = {
    'orders_count': _orders_count,
    'collection_items': _collection_items,
    'items_with_photos': _items_with_photos,
    'total_spent': _total_spent,
    'login_streak': _login_streak,
    'account_age_days': _account_age_days,
    'single_order_items': _single_order_items,
    'order_hour_range': _order_hour_range,
    'orders_in_window': _orders_in_window,
    'orders_in_weekend': _orders_in_weekend,
    'time_since_drop': _time_since_drop,
    'time_since_page_visit': _time_since_page_visit,
    'exclusive_orders': _offer_orders,  # backward compat alias
    'offer_orders': _offer_orders,
    'distinct_offer_pages': _distinct_offer_pages,
    'profile_completed': _profile_completed,
    'email_verified': _email_verified,
    'has_avatar': _has_avatar,
    'collection_public': _collection_public,
    'shipping_addresses': _shipping_addresses,
    'shared_achievements': _shared_achievements,
    'shared_full_collection': _shared_full_collection,
    'all_badges_unlocked': _all_badges_unlocked,
}
