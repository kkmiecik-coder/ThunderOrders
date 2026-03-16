"""
RODO Data Export (art. 20) — Generowanie PDF z danymi użytkownika
Używa WeasyPrint (HTML → PDF) dla ładnego renderingu
"""

import os
import platform

# WeasyPrint wymaga systemowych bibliotek (pango/gobject)
# Na macOS z Homebrew trzeba wskazać ścieżkę
if platform.system() == 'Darwin':
    homebrew_lib = '/opt/homebrew/lib'
    if os.path.isdir(homebrew_lib):
        current = os.environ.get('DYLD_FALLBACK_LIBRARY_PATH', '')
        if homebrew_lib not in current:
            os.environ['DYLD_FALLBACK_LIBRARY_PATH'] = f'{homebrew_lib}:{current}' if current else homebrew_lib

from flask import render_template
from extensions import db


def generate_user_data_pdf(user):
    """Generuje PDF z danymi użytkownika. Zwraca bytes."""
    from weasyprint import HTML
    from modules.orders.models import Order, OrderComment, ShippingRequest
    from modules.client.models import CollectionItem
    from modules.notifications.models import NotificationPreference
    from modules.achievements.models import UserAchievement, Achievement
    from modules.auth.models import ShippingAddress
    from datetime import datetime

    # Pobierz dane
    orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
    addresses = ShippingAddress.query.filter_by(user_id=user.id, is_active=True).all()
    collection_items = CollectionItem.query.filter_by(user_id=user.id).order_by(CollectionItem.created_at.desc()).all()
    user_achievements = db.session.query(UserAchievement, Achievement).join(
        Achievement, UserAchievement.achievement_id == Achievement.id
    ).filter(UserAchievement.user_id == user.id).all()
    notif_prefs = NotificationPreference.query.filter_by(user_id=user.id).first()
    comments = OrderComment.query.filter_by(user_id=user.id).order_by(OrderComment.created_at.desc()).all()
    shipping_requests = ShippingRequest.query.filter_by(user_id=user.id).order_by(ShippingRequest.created_at.desc()).all()

    # Renderuj HTML
    html_content = render_template(
        'profile/data_export_pdf.html',
        user=user,
        orders=orders,
        addresses=addresses,
        collection_items=collection_items,
        user_achievements=user_achievements,
        notif_prefs=notif_prefs,
        comments=comments,
        shipping_requests=shipping_requests,
        export_date=datetime.now()
    )

    # Generuj PDF
    return HTML(string=html_content).write_pdf()
