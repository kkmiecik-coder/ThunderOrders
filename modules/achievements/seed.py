from extensions import db
from modules.achievements.models import Achievement, AchievementStat


ACHIEVEMENTS = [
    # === ZAMÓWIENIOWE (orders) ===
    {
        'slug': 'first-order', 'name': 'Pierwsze kroki',
        'description': 'Złóż swoje pierwsze zamówienie',
        'category': 'orders', 'rarity': 'common',
        'tier': 1, 'tier_group': 'order-count',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'orders_count', 'threshold': 1},
    },
    {
        'slug': 'orders-5', 'name': 'Stały bywalec',
        'description': 'Złóż 5 zamówień',
        'category': 'orders', 'rarity': 'common',
        'tier': 2, 'tier_group': 'order-count',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'orders_count', 'threshold': 5},
    },
    {
        'slug': 'orders-10', 'name': 'Wierny klient',
        'description': 'Złóż 10 zamówień',
        'category': 'orders', 'rarity': 'rare',
        'tier': 3, 'tier_group': 'order-count',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'orders_count', 'threshold': 10},
    },
    {
        'slug': 'orders-25', 'name': 'Zakupoholik',
        'description': 'Złóż 25 zamówień',
        'category': 'orders', 'rarity': 'epic',
        'tier': 4, 'tier_group': 'order-count',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'orders_count', 'threshold': 25},
    },
    {
        'slug': 'orders-50', 'name': 'Legenda zamówień',
        'description': 'Złóż 50 zamówień',
        'category': 'orders', 'rarity': 'legendary',
        'tier': 5, 'tier_group': 'order-count',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'orders_count', 'threshold': 50},
    },
    {
        'slug': 'orders-100', 'name': 'Sto razy tak!',
        'description': 'Złóż 100 zamówień',
        'category': 'orders', 'rarity': 'legendary',
        'tier': 6, 'tier_group': 'order-count',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'orders_count', 'threshold': 100},
    },
    {
        'slug': 'orders-150', 'name': 'Poza skalą',
        'description': 'Złóż 150 zamówień',
        'category': 'orders', 'rarity': 'legendary',
        'tier': 7, 'tier_group': 'order-count',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'orders_count', 'threshold': 150},
    },
    {
        'slug': 'orders-250', 'name': 'Instytucja',
        'description': 'Złóż 250 zamówień',
        'category': 'orders', 'rarity': 'cosmic',
        'tier': 8, 'tier_group': 'order-count',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'orders_count', 'threshold': 250},
    },
    {
        'slug': 'bulk-order', 'name': 'Hurtownik',
        'description': 'Złóż zamówienie z 10+ pozycjami',
        'category': 'orders', 'rarity': 'rare',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'single_order_items', 'threshold': 10},
    },
    {
        'slug': 'mega-order', 'name': 'Mega paczka',
        # Próg 25 był nieosiągalny: rekord na produkcji to 22 pozycje i nikt
        # nigdy tej odznaki nie zdobył. Przy 15 wpada 6 osób, a odstęp od
        # „Hurtownika" (10) zostaje wyraźny.
        'description': 'Złóż zamówienie z 15+ pozycjami',
        'category': 'orders', 'rarity': 'epic',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'single_order_items', 'threshold': 15},
    },
    {
        'slug': 'repeat-week', 'name': 'Powrót po więcej',
        'description': 'Złóż 2 zamówienia w ciągu jednego tygodnia',
        'category': 'orders', 'rarity': 'rare',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'orders_in_window', 'threshold': 2, 'window_days': 7},
    },

    # === KOLEKCJONERSKIE (collection) ===
    {
        'slug': 'collection-1', 'name': 'Początek kolekcji',
        'description': 'Dodaj pierwszy item do kolekcji',
        'category': 'collection', 'rarity': 'common',
        'tier': 1, 'tier_group': 'collection-size',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'collection_items', 'threshold': 1},
    },
    {
        'slug': 'collection-10', 'name': 'Rosnąca kolekcja',
        'description': 'Zgromadź 10 itemów w kolekcji',
        'category': 'collection', 'rarity': 'common',
        'tier': 2, 'tier_group': 'collection-size',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'collection_items', 'threshold': 10},
    },
    {
        'slug': 'collection-25', 'name': 'Kolekcjoner',
        'description': 'Zgromadź 25 itemów w kolekcji',
        'category': 'collection', 'rarity': 'rare',
        'tier': 3, 'tier_group': 'collection-size',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'collection_items', 'threshold': 25},
    },
    {
        'slug': 'collection-50', 'name': 'Muzeum K-pop',
        'description': 'Zgromadź 50 itemów w kolekcji',
        'category': 'collection', 'rarity': 'epic',
        'tier': 4, 'tier_group': 'collection-size',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'collection_items', 'threshold': 50},
    },
    {
        'slug': 'collection-100', 'name': 'Skarbiec',
        'description': 'Zgromadź 100 itemów w kolekcji',
        'category': 'collection', 'rarity': 'legendary',
        'tier': 5, 'tier_group': 'collection-size',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'collection_items', 'threshold': 100},
    },
    {
        'slug': 'photos-10', 'name': 'Fotograf',
        'description': 'Dodaj zdjęcia do 10 itemów w kolekcji',
        'category': 'collection', 'rarity': 'common',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'items_with_photos', 'threshold': 10},
    },
    {
        'slug': 'photos-50', 'name': 'Galeria sztuki',
        'description': 'Dodaj zdjęcia do 50 itemów w kolekcji',
        'category': 'collection', 'rarity': 'rare',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'items_with_photos', 'threshold': 50},
    },
    {
        'slug': 'collection-public', 'name': 'Chwalipięta',
        'description': 'Udostępnij swoją kolekcję publicznie',
        'category': 'collection', 'rarity': 'rare',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'collection_public', 'value': True},
    },

    # === LOJALNOŚCIOWE (loyalty) ===
    {
        'slug': 'member-30d', 'name': 'Świeżak',
        'description': 'Konto aktywne od 30 dni',
        'category': 'loyalty', 'rarity': 'common',
        'tier': 1, 'tier_group': 'account-age',
        'trigger_type': 'cron',
        'trigger_config': {'metric': 'account_age_days', 'threshold': 30},
    },
    {
        'slug': 'member-90d', 'name': 'Zadomowiony',
        'description': 'Konto aktywne od 90 dni',
        'category': 'loyalty', 'rarity': 'common',
        'tier': 2, 'tier_group': 'account-age',
        'trigger_type': 'cron',
        'trigger_config': {'metric': 'account_age_days', 'threshold': 90},
    },
    {
        'slug': 'member-180d', 'name': 'Pół roku razem',
        'description': 'Konto aktywne od 180 dni',
        'category': 'loyalty', 'rarity': 'rare',
        'tier': 3, 'tier_group': 'account-age',
        'trigger_type': 'cron',
        'trigger_config': {'metric': 'account_age_days', 'threshold': 180},
    },
    {
        'slug': 'member-365d', 'name': 'Rocznica',
        'description': 'Konto aktywne od roku!',
        'category': 'loyalty', 'rarity': 'epic',
        'tier': 4, 'tier_group': 'account-age',
        'trigger_type': 'cron',
        'trigger_config': {'metric': 'account_age_days', 'threshold': 365},
    },
    {
        'slug': 'member-545d', 'name': 'Półtora roku',
        # Dziura 365 → 730 to cały rok bez żadnego celu po drodze.
        'description': 'Z nami od półtora roku',
        'category': 'loyalty', 'rarity': 'epic',
        'tier': 5, 'tier_group': 'account-age',
        'trigger_type': 'cron',
        'trigger_config': {'metric': 'account_age_days', 'threshold': 545},
    },
    {
        'slug': 'member-730d', 'name': 'OG',
        'description': 'Z nami od 2 lat — jesteś legendą',
        'category': 'loyalty', 'rarity': 'legendary',
        'tier': 6, 'tier_group': 'account-age',
        'trigger_type': 'cron',
        'trigger_config': {'metric': 'account_age_days', 'threshold': 730},
    },
    {
        'slug': 'login-streak-7', 'name': 'Codziennik',
        'description': 'Zaloguj się 7 dni z rzędu',
        'category': 'loyalty', 'rarity': 'rare',
        'tier': 1, 'tier_group': 'login-streak',
        'trigger_type': 'cron',
        'trigger_config': {'metric': 'login_streak', 'threshold': 7},
    },
    {
        'slug': 'login-streak-14', 'name': 'Dwa tygodnie z rzędu',
        # Skok 7 → 30 był największy w całej drabince; przy rekordzie 40 dni
        # praktycznie nikt nie miał szans zobaczyć kolejnego progu.
        'description': 'Zaloguj się 14 dni z rzędu',
        'category': 'loyalty', 'rarity': 'rare',
        'tier': 2, 'tier_group': 'login-streak',
        'trigger_type': 'cron',
        'trigger_config': {'metric': 'login_streak', 'threshold': 14},
    },
    {
        'slug': 'login-streak-30', 'name': 'Nałogowiec',
        'description': 'Zaloguj się 30 dni z rzędu',
        'category': 'loyalty', 'rarity': 'epic',
        'tier': 3, 'tier_group': 'login-streak',
        'trigger_type': 'cron',
        'trigger_config': {'metric': 'login_streak', 'threshold': 30},
    },
    {
        'slug': 'login-streak-60', 'name': 'Żelazna konsekwencja',
        # Skok 30 → 90 przy rekordzie 40 dni oznaczał, że po „Nałogowcu" nie ma
        # już realnie nic. Próg 90 zostaje jako cel, ale nie jako następny krok.
        'description': 'Zaloguj się 60 dni z rzędu',
        'category': 'loyalty', 'rarity': 'epic',
        'tier': 4, 'tier_group': 'login-streak',
        'trigger_type': 'cron',
        'trigger_config': {'metric': 'login_streak', 'threshold': 60},
    },
    {
        'slug': 'login-streak-90', 'name': 'Niezniszczalny',
        'description': 'Zaloguj się 90 dni z rzędu — jesteś nie do zatrzymania!',
        'category': 'loyalty', 'rarity': 'legendary',
        'tier': 5, 'tier_group': 'login-streak',
        'trigger_type': 'cron',
        'trigger_config': {'metric': 'login_streak', 'threshold': 90},
    },

    # === SZYBKOŚCIOWE (speed) ===
    {
        'slug': 'early-bird', 'name': 'Early Bird',
        'description': 'Złóż zamówienie w ciągu 5 minut od otwarcia dropu',
        'category': 'speed', 'rarity': 'legendary',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'time_since_drop', 'max_minutes': 5},
    },
    {
        'slug': 'speed-order', 'name': 'Błyskawica',
        'description': 'Złóż zamówienie w ciągu 2 minut od wejścia na stronę',
        'category': 'speed', 'rarity': 'rare',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'time_since_page_visit', 'max_minutes': 2},
    },
    {
        'slug': 'night-owl', 'name': 'Nocny marek',
        'description': 'Złóż zamówienie między 00:00 a 5:00',
        'category': 'speed', 'rarity': 'rare',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'order_hour_range', 'start': 0, 'end': 5},
    },
    {
        'slug': 'weekend-warrior', 'name': 'Weekendowy wojownik',
        'description': 'Złóż 3 zamówienia w weekend (sob-niedz)',
        'category': 'speed', 'rarity': 'epic',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'orders_in_weekend', 'threshold': 3},
    },

    # === EXCLUSIVE ===
    {
        'slug': 'exclusive-first', 'name': 'Pierwszy drop',
        'description': 'Weź udział w pierwszym dropie exclusive',
        'category': 'exclusive', 'rarity': 'common',
        'tier': 1, 'tier_group': 'exclusive-count',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'exclusive_orders', 'threshold': 1},
    },
    {
        'slug': 'exclusive-5', 'name': 'Drop? Biorę!',
        'description': 'Weź udział w 5 dropach',
        'category': 'exclusive', 'rarity': 'rare',
        'tier': 2, 'tier_group': 'exclusive-count',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'exclusive_orders', 'threshold': 5},
    },
    {
        'slug': 'exclusive-10', 'name': 'VIP',
        'description': 'Weź udział w 10 dropach',
        'category': 'exclusive', 'rarity': 'epic',
        'tier': 3, 'tier_group': 'exclusive-count',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'exclusive_orders', 'threshold': 10},
    },
    {
        'slug': 'exclusive-25', 'name': 'Exclusive Elite',
        'description': 'Weź udział w 25 dropach',
        'category': 'exclusive', 'rarity': 'legendary',
        'tier': 4, 'tier_group': 'exclusive-count',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'exclusive_orders', 'threshold': 25},
    },
    {
        'slug': 'exclusive-veteran', 'name': 'Exclusive Veteran',
        # Do 09.2026 to była JEDYNA odznaka w tej grupie: próg 3 miało 108 z ~300
        # klientów, a rekordzista odwiedził 76 różnych dropów. Cała progresja
        # marnowała się w jednym progu.
        'description': 'Zamów z 3 różnych dropów exclusive',
        # rarity ZOSTAJE 'epic' — odznakę ma już 108 osób, a obniżenie do 'rare'
        # zmieniłoby im wygląd karty i kolor animacji za coś, co zdobyli dawno.
        # Dwa kolejne stopnie i tak są wyżej (legendary, cosmic).
        'category': 'exclusive', 'rarity': 'epic',
        'tier': 1, 'tier_group': 'exclusive-pages',
        'trigger_type': 'cron',
        'trigger_config': {'metric': 'distinct_exclusive_pages', 'threshold': 3},
    },
    {
        'slug': 'exclusive-pages-10', 'name': 'Stały bywalec dropów',
        'description': 'Zamów z 10 różnych dropów exclusive',
        'category': 'exclusive', 'rarity': 'epic',
        'tier': 2, 'tier_group': 'exclusive-pages',
        'trigger_type': 'cron',
        'trigger_config': {'metric': 'distinct_exclusive_pages', 'threshold': 10},
    },
    {
        'slug': 'exclusive-pages-25', 'name': 'Łowca dropów',
        'description': 'Zamów z 25 różnych dropów exclusive',
        'category': 'exclusive', 'rarity': 'legendary',
        'tier': 3, 'tier_group': 'exclusive-pages',
        'trigger_type': 'cron',
        'trigger_config': {'metric': 'distinct_exclusive_pages', 'threshold': 25},
    },
    {
        'slug': 'exclusive-pages-50', 'name': 'Nie przegapia nic',
        'description': 'Zamów z 50 różnych dropów exclusive',
        'category': 'exclusive', 'rarity': 'cosmic',
        'tier': 4, 'tier_group': 'exclusive-pages',
        'trigger_type': 'cron',
        'trigger_config': {'metric': 'distinct_exclusive_pages', 'threshold': 50},
    },

    # === SPOŁECZNOŚCIOWE (social) ===
    {
        'slug': 'first-share', 'name': 'Pierwszy share',
        'description': 'Udostępnij swoją pierwszą odznakę w social media',
        'category': 'social', 'rarity': 'common',
        'tier': 1, 'tier_group': 'shared-badges',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'shared_achievements', 'threshold': 1},
    },
    {
        'slug': 'share-5', 'name': 'Influencer',
        'description': 'Udostępnij 5 odznak',
        'category': 'social', 'rarity': 'rare',
        'tier': 2, 'tier_group': 'shared-badges',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'shared_achievements', 'threshold': 5},
    },
    {
        'slug': 'share-10', 'name': 'Głos społeczności',
        'description': 'Udostępnij 10 odznak',
        'category': 'social', 'rarity': 'epic',
        'tier': 3, 'tier_group': 'shared-badges',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'shared_achievements', 'threshold': 10},
    },
    {
        'slug': 'share-20', 'name': 'Twarz ThunderOrders',
        'description': 'Udostępnij 20 odznak',
        'category': 'social', 'rarity': 'legendary',
        'tier': 4, 'tier_group': 'shared-badges',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'shared_achievements', 'threshold': 20},
    },
    {
        'slug': 'share-all', 'name': 'Ambasador',
        'description': 'Udostępnij pełną kolekcję odznak',
        'category': 'social', 'rarity': 'epic',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'shared_full_collection', 'value': True},
    },
    # === FINANSOWE (financial) ===
    {
        'slug': 'spent-100', 'name': 'Pierwsze 100 zł',
        'description': 'Wydaj łącznie 100 zł',
        'category': 'financial', 'rarity': 'common',
        'tier': 1, 'tier_group': 'total-spent',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'total_spent', 'threshold': 100},
    },
    {
        'slug': 'spent-500', 'name': 'Pięć stów',
        'description': 'Wydaj łącznie 500 zł',
        'category': 'financial', 'rarity': 'common',
        'tier': 2, 'tier_group': 'total-spent',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'total_spent', 'threshold': 500},
    },
    {
        'slug': 'spent-1000', 'name': 'Tysięcznik',
        'description': 'Wydaj łącznie 1000 zł',
        'category': 'financial', 'rarity': 'rare',
        'tier': 3, 'tier_group': 'total-spent',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'total_spent', 'threshold': 1000},
    },
    {
        'slug': 'spent-5000', 'name': 'Portfel płacze',
        'description': 'Wydaj łącznie 5000 zł',
        'category': 'financial', 'rarity': 'epic',
        'tier': 4, 'tier_group': 'total-spent',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'total_spent', 'threshold': 5000},
    },
    {
        'slug': 'spent-10000', 'name': 'Sponsor ThunderOrders',
        'description': 'Wydaj łącznie 10 000 zł',
        'category': 'financial', 'rarity': 'legendary',
        'tier': 5, 'tier_group': 'total-spent',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'total_spent', 'threshold': 10000},
    },
    {
        'slug': 'spent-25000', 'name': 'Filar sklepu',
        'description': 'Wydaj łącznie 25 000 zł',
        'category': 'financial', 'rarity': 'legendary',
        'tier': 6, 'tier_group': 'total-spent',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'total_spent', 'threshold': 25000},
    },
    {
        'slug': 'spent-50000', 'name': 'Poza konkurencją',
        'description': 'Wydaj łącznie 50 000 zł',
        'category': 'financial', 'rarity': 'cosmic',
        'tier': 7, 'tier_group': 'total-spent',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'total_spent', 'threshold': 50000},
    },

    # === PROFILOWE (profile) ===
    {
        'slug': 'profile-complete', 'name': 'Nowy w mieście',
        'description': 'Uzupełnij swój profil (imię, nazwisko, telefon)',
        'category': 'profile', 'rarity': 'common',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'profile_completed', 'value': True},
    },
    {
        'slug': 'avatar-selected', 'name': 'Stylowy',
        'description': 'Wybierz avatar ze strony profilu',
        'category': 'profile', 'rarity': 'common',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'has_avatar', 'value': True},
    },
    {
        'slug': 'first-address', 'name': 'Gotowy do odbioru',
        'description': 'Dodaj swój pierwszy adres wysyłkowy',
        'category': 'profile', 'rarity': 'common',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'shipping_addresses', 'threshold': 1},
    },
    {
        'slug': 'email-verified', 'name': 'Zweryfikowany',
        'description': 'Zweryfikuj swój adres email',
        'category': 'profile', 'rarity': 'common',
        'trigger_type': 'event',
        'trigger_config': {'metric': 'email_verified', 'value': True},
    },
    {
        'slug': 'profile-all', 'name': 'Pełna gotowość',
        'description': 'Uzupełnij profil, avatar, adres i email — wszystko gotowe!',
        'category': 'profile', 'rarity': 'rare',
        'trigger_type': 'event',
        'trigger_config': {
            'metric': 'all_badges_unlocked',
            'slugs': ['profile-complete', 'avatar-selected', 'first-address', 'email-verified']
        },
    },
]

# sort_order wynika z KOLEJNOŚCI na liście powyżej. Wcześniej każdy wpis miał
# numer wpisany ręcznie, więc dołożenie poziomu w środku drabinki wymagałoby
# przenumerowania wszystkiego poniżej — i tego nie robiono: w numeracji brakowało
# 37, a login-streak-90 miał 48 i odrywał się w galerii od swojej grupy.
for _pozycja, _odznaka in enumerate(ACHIEVEMENTS, start=1):
    _odznaka['sort_order'] = _pozycja


def seed_achievements():
    """Seed or update all achievements. Safe to re-run."""
    created = 0
    updated = 0

    for data in ACHIEVEMENTS:
        existing = Achievement.query.filter_by(slug=data['slug']).first()
        if existing:
            for key, value in data.items():
                setattr(existing, key, value)
            updated += 1
        else:
            achievement = Achievement(**data)
            db.session.add(achievement)
            created += 1

    db.session.commit()

    # Create AchievementStat for any achievements that don't have one
    achievements_without_stat = Achievement.query.outerjoin(AchievementStat).filter(
        AchievementStat.id.is_(None)
    ).all()
    for a in achievements_without_stat:
        db.session.add(AchievementStat(achievement_id=a.id))
    db.session.commit()

    return created, updated
