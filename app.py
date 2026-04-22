import sys
_is_flask_cli = bool(sys.argv) and sys.argv[0].endswith('/flask')
if sys.platform != 'darwin' and not _is_flask_cli:
    import eventlet
    eventlet.monkey_patch()

import os
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import Flask, render_template, redirect, url_for as flask_url_for, request, abort
url_for = flask_url_for  # alias dla reszty kodu w app.py

# Sentry - error tracking (inicjalizacja przed create_app)
import sentry_sdk

sentry_dsn = os.getenv('SENTRY_DSN')
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=0.2,
        environment=os.getenv('FLASK_ENV', 'production'),
        send_default_pii=False,
    )

# Import rozszerzeń z extensions.py (rozwiązuje circular imports)
from extensions import db, migrate, login_manager, mail, csrf, executor, limiter, socketio

# Strefa czasowa dla Polski
POLAND_TZ = ZoneInfo('Europe/Warsaw')


def create_app(config_name=None):
    """
    Application Factory Pattern
    Tworzy i konfiguruje instancję aplikacji Flask
    """
    app = Flask(__name__)

    # Konfiguracja logowania - upewnij się że logi INFO trafiają do stdout (Gunicorn/journalctl)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Załaduj konfigurację
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    from config import config
    app.config.from_object(config[config_name])

    # Inicjalizuj rozszerzenia
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    executor.init_app(app)
    limiter.init_app(app)
    socketio_origins = app.config.get('SOCKETIO_CORS_ORIGINS', ['https://thunderorders.cloud', 'http://localhost:5001'])
    async_mode = 'eventlet' if 'eventlet' in sys.modules else 'threading'
    socketio.init_app(app, async_mode=async_mode, cors_allowed_origins=socketio_origins,
                      ping_timeout=60, ping_interval=25)

    # OAuth (Google, Facebook login)
    from utils.oauth import init_oauth
    init_oauth(app)

    # Konfiguracja Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Zaloguj się, aby uzyskać dostęp do tej strony.'
    login_manager.login_message_category = 'warning'

    # User loader dla Flask-Login (zostanie uzupełniony w module auth)
    @login_manager.user_loader
    def load_user(user_id):
        # Import tutaj aby uniknąć circular imports
        from modules.auth.models import User
        return User.query.get(int(user_id))

    # Rejestracja blueprintów (modułów)
    register_blueprints(app)

    # Error handlers (strony błędów)
    register_error_handlers(app)

    # Context processors (zmienne globalne w templates)
    register_context_processors(app)

    # Template filters (filtry Jinja2)
    register_template_filters(app)

    # Utwórz folder uploads jeśli nie istnieje
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # CLI commands
    register_cli_commands(app)

    # Sentry - identyfikacja użytkownika przy błędach
    @app.before_request
    def sentry_set_user():
        from flask_login import current_user
        if current_user.is_authenticated:
            sentry_sdk.set_user({
                'id': current_user.id,
                'role': current_user.role,
            })
        else:
            sentry_sdk.set_user(None)

    # Maintenance mode check (cache dostępny globalnie przez app.maintenance_cache)
    app.maintenance_cache = {'enabled': False, 'checked_at': 0}

    @app.before_request
    def check_maintenance_mode():
        import time
        from flask_login import current_user
        from flask import g

        # Cache na 10 sekund (nie bije w DB na każdym requeście)
        now = time.time()
        if now - app.maintenance_cache['checked_at'] > 10:
            from modules.auth.models import Settings
            app.maintenance_cache['enabled'] = Settings.get_value('maintenance_mode', False)
            app.maintenance_cache['checked_at'] = now

        g.maintenance_mode = app.maintenance_cache['enabled']

        if not app.maintenance_cache['enabled']:
            return None

        # Przepuść statyczne pliki i auth endpointy
        path = request.path
        if (path.startswith('/static/') or
            path in ('/auth/login', '/auth/logout') or
            path.startswith('/auth/callback')):
            return None

        # Przepuść adminów i moderatorów
        if current_user.is_authenticated and current_user.role in ('admin', 'mod'):
            return None

        # Blokuj — AJAX/API → JSON, reszta → HTML
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from modules.auth.models import Settings
            msg = Settings.get_value('maintenance_message', '') or 'Strona w przerwie technicznej. Wrócimy wkrótce!'
            return jsonify({'maintenance': True, 'message': msg}), 503

        from modules.auth.models import Settings
        msg = Settings.get_value('maintenance_message', '')
        eta = Settings.get_value('maintenance_eta', '')
        return render_template('errors/503.html',
                               maintenance_message=msg,
                               maintenance_eta=eta), 503

    # Security headers
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'

        # HSTS — wymuszaj HTTPS przez 1 rok (tylko w produkcji)
        if not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        # Content-Security-Policy
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
                "https://www.googletagmanager.com https://www.google-analytics.com "
                "https://unpkg.com https://challenges.cloudflare.com "
                "https://cdn.jsdelivr.net https://cdn.socket.io https://cdnjs.cloudflare.com https://cdn.quilljs.com "
                "https://browser.sentry-cdn.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.quilljs.com https://unpkg.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob: https://www.google-analytics.com https://*.googleusercontent.com https://*.basemaps.cartocdn.com; "
            "connect-src 'self' wss://thunderorders.cloud ws://localhost:* "
                "https://www.google-analytics.com https://analytics.google.com https://region1.google-analytics.com https://challenges.cloudflare.com "
                "https://*.ingest.sentry.io https://*.ingest.de.sentry.io; "
            "frame-src 'self' https://challenges.cloudflare.com; "
            "object-src 'none'; "
            "base-uri 'self'"
        )
        response.headers['Content-Security-Policy'] = csp

        # Allow Service Worker to control the entire site
        if request.path.endswith('/sw.js'):
            response.headers['Service-Worker-Allowed'] = '/'
        return response

    return app


def register_blueprints(app):
    """
    Rejestruje wszystkie blueprinty (moduły aplikacji)
    Lazy loading - blueprinty są ładowane tylko gdy potrzebne
    """

    # Import blueprintów (zostaną stworzone w kolejnych etapach)
    # Na razie są zakomentowane - odkomentujemy gdy je stworzymy

    # Auth module
    from modules.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # Client module
    from modules.client import client_bp
    app.register_blueprint(client_bp, url_prefix='/client')

    # Admin module
    from modules.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Products module
    from modules.products import products_bp
    app.register_blueprint(products_bp)

    # Orders module
    from modules.orders import orders_bp
    app.register_blueprint(orders_bp)

    # Offers module (publiczne strony sprzedaży — exclusive, pre-order)
    # CSRF exempt per-endpoint (reserve, release, extend, restore, place-order, subscribe-notification)
    from modules.offers import offers_bp
    app.register_blueprint(offers_bp)

    # API module (AJAX requests — JS sends X-CSRFToken header from meta tag)
    from modules.api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    # Analytics API (JS sends X-CSRFToken header)
    from modules.api.analytics import analytics_bp
    app.register_blueprint(analytics_bp)

    # Imports module (JS sends X-CSRFToken header)
    from modules.imports import imports_bp
    app.register_blueprint(imports_bp)

    # Public module (strony publiczne bez logowania - kolekcja, QR upload)
    from modules.public import public_bp
    csrf.exempt(public_bp)
    app.register_blueprint(public_bp)

    # Profile module (wspólny dla wszystkich ról)
    from modules.profile import profile_bp
    app.register_blueprint(profile_bp, url_prefix='/profile')

    # Payments module
    from modules.payments import payments_bp
    app.register_blueprint(payments_bp)

    # Feedback module (ankiety i zbieranie opinii)
    from modules.feedback import feedback_bp
    app.register_blueprint(feedback_bp)

    # Notifications module (CSRF exempt per-endpoint: subscribe, unsubscribe)
    from modules.notifications import notifications_bp
    app.register_blueprint(notifications_bp, url_prefix='/notifications')

    # Tracking module (QR campaign tracking & analytics)
    from modules.tracking import tracking_bp
    app.register_blueprint(tracking_bp)

    # Achievements module (JS sends X-CSRFToken header)
    from modules.achievements import achievements_bp
    app.register_blueprint(achievements_bp, url_prefix='/achievements')

    # Shop module (client on-hand shop — no url_prefix, routes have full paths)
    from modules.client.shop import shop_bp
    app.register_blueprint(shop_bp)

    # Deploy webhook (GitHub auto-deploy) - exempt from CSRF (uses HMAC signature)
    from modules.deploy import deploy_bp
    app.register_blueprint(deploy_bp)
    csrf.exempt(deploy_bp)

    # Service Worker served from root scope
    @app.route('/sw.js')
    def service_worker():
        from flask import send_from_directory, make_response
        response = make_response(send_from_directory(app.static_folder, 'sw.js'))
        response.headers['Content-Type'] = 'application/javascript'
        response.headers['Service-Worker-Allowed'] = '/'
        response.headers['Cache-Control'] = 'no-cache'
        return response

    # Offline page (for Service Worker fallback)
    @app.route('/offline')
    def offline():
        return render_template('errors/offline.html')

    # Strona główna - smart redirect
    @app.route('/')
    def index():
        """
        Strona główna:
        - Przed datą premiery (1 kwietnia 2026) → Countdown page
        - Po premierze, niezalogowany → Strona logowania
        - Po premierze, zalogowany → Dashboard
        """
        from flask_login import current_user
        from datetime import datetime

        LAUNCH_DATE = datetime(2026, 4, 4, 20, 0, 0, tzinfo=POLAND_TZ)

        if datetime.now(POLAND_TZ) < LAUNCH_DATE:
            return render_template('public/countdown.html')

        if current_user.is_authenticated:
            # Redirect zalogowanych użytkowników na dashboard
            if current_user.role in ['admin', 'mod']:
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('client.dashboard'))
        else:
            # Pokaż stronę logowania dla niezalogowanych
            return redirect(url_for('auth.login'))

    # URL shortcuts
    @app.route('/login')
    def login_shortcut():
        return redirect(url_for('auth.login'))

    @app.route('/register')
    def register_shortcut():
        return redirect(url_for('auth.register'))

    # Polityka Prywatności (RODO-compliant)
    @app.route('/privacy-policy')
    def privacy_policy():
        """
        Strona polityki prywatności (RODO/GDPR compliance)
        Dostępna publicznie dla wszystkich użytkowników
        """
        return render_template('legal/privacy_policy.html')

    # Przełączanie widoku admin ↔ klient
    @app.route('/switch-view')
    def switch_view():
        """
        Przełącza admin/mod między widokiem admina a widokiem klienta.
        Zamienia prefix /admin/ ↔ /client/ w bieżącym URL.
        Jeśli docelowa strona nie istnieje, przekierowuje na dashboard.
        """
        from flask_login import current_user
        from werkzeug.exceptions import NotFound
        from urllib.parse import urlparse

        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        if current_user.role not in ('admin', 'mod'):
            abort(403)

        referrer = request.args.get('next') or request.referrer or '/'
        parsed = urlparse(referrer)
        path = parsed.path

        if path.startswith('/admin'):
            # Przełącz na widok klienta
            new_path = '/client' + path[len('/admin'):]
            fallback = url_for('client.dashboard')
        elif path.startswith('/client'):
            # Przełącz na widok admina
            new_path = '/admin' + path[len('/client'):]
            fallback = url_for('admin.dashboard')
        else:
            # Strona bez prefixu - przejdź na dashboard przeciwnego widoku
            return redirect(url_for('client.dashboard'))

        # Sprawdź czy docelowa ścieżka istnieje
        adapter = app.url_map.bind('')
        try:
            adapter.match(new_path)
            return redirect(new_path)
        except NotFound:
            return redirect(fallback)
        except Exception:
            return redirect(new_path)


def register_cli_commands(app):
    """Rejestruje komendy CLI (do użycia z cron)"""

    import click
    import functools
    from flask import current_app

    def _with_request_context(fn):
        """Owija CLI command w test_request_context, żeby url_for(_external=True) działał poza HTTP requestem."""
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            base_url = os.getenv('APP_BASE_URL', 'https://thunderorders.cloud')
            with current_app.test_request_context(base_url=base_url):
                return fn(*args, **kwargs)
        return wrapper

    @app.cli.command('check-payment-reminders')
    @_with_request_context
    @click.option('--dry-run', is_flag=True, help='Tylko wyświetl, nie wysyłaj')
    def check_payment_reminders(dry_run):
        """Sprawdza i wysyła przypomnienia o płatnościach (uruchamiany co godzinę przez cron)."""
        from modules.orders.models import Order, get_local_now
        from modules.offers.models import OfferPage
        from modules.offers.reminder_models import PaymentReminderConfig, PaymentReminderLog
        from modules.auth.models import Settings
        from utils.email_manager import EmailManager
        from utils.push_manager import PushManager
        from utils.activity_logger import log_activity
        from datetime import timedelta

        now = get_local_now()
        sent_count = 0

        # Pobierz aktywne reguły
        rules = PaymentReminderConfig.query.filter_by(enabled=True).all()
        click.echo(f"Aktywnych reguł: {len(rules)}")

        for rule in rules:
            if rule.reminder_type == 'before_deadline':
                if rule.payment_stage == 'product':
                    # Pobierz zamknięte OfferPages z deadline
                    pages = OfferPage.query.filter(
                        OfferPage.payment_deadline.isnot(None),
                        OfferPage.is_fully_closed == True
                    ).all()

                    for page in pages:
                        trigger_time = page.payment_deadline - timedelta(hours=rule.hours)
                        if trigger_time > now:
                            continue  # Za wcześnie

                        orders = Order.query.filter(
                            Order.offer_page_id == page.id,
                            Order.status != 'anulowane'
                        ).all()

                        for order in orders:
                            if order.product_payment_status not in ('none', 'rejected'):
                                continue

                            already_sent = PaymentReminderLog.query.filter_by(
                                order_id=order.id, config_id=rule.id
                            ).first()
                            if already_sent:
                                continue

                            if dry_run:
                                click.echo(f"  [DRY RUN] {order.order_number} <- {rule.hours}h przed deadline")
                                sent_count += 1
                                continue

                            success = EmailManager.notify_payment_reminder(
                                order, payment_deadline=page.payment_deadline,
                                reminder_context='before_deadline'
                            )
                            if success:
                                PushManager.notify_payment_reminder(
                                    order, payment_deadline=page.payment_deadline
                                )
                                db.session.add(PaymentReminderLog(
                                    order_id=order.id, config_id=rule.id
                                ))
                                log_activity(
                                    action='payment_reminder_sent',
                                    entity_type='order',
                                    entity_id=order.id,
                                    new_value=f'Wysłano przypomnienie ({rule.hours}h przed terminem)'
                                )
                                sent_count += 1
                                click.echo(f"  Wysłano: {order.order_number} ({rule.hours}h przed deadline)")

                elif rule.payment_stage == 'shipping_kr':
                    # E2: Wysyłka KR - sprawdź deadline'y PolandOrder
                    from modules.products.models import PolandOrder
                    poland_orders = PolandOrder.query.filter(
                        PolandOrder.payment_deadline.isnot(None),
                        PolandOrder.status != 'anulowane'
                    ).all()

                    for po in poland_orders:
                        trigger_time = po.payment_deadline - timedelta(hours=rule.hours)
                        if trigger_time > now:
                            continue

                        for po_item in po.items:
                            order = po_item.order
                            if not order:
                                continue
                            if order.status == 'anulowane':
                                continue
                            if order.stage_2_status not in ('none', 'rejected'):
                                continue

                            already_sent = PaymentReminderLog.query.filter_by(
                                order_id=order.id, config_id=rule.id
                            ).first()
                            if already_sent:
                                continue

                            if dry_run:
                                click.echo(f"  [DRY RUN] {order.order_number} <- {rule.hours}h przed deadline wysyłki KR")
                                sent_count += 1
                                continue

                            success = EmailManager.notify_payment_reminder(
                                order, payment_deadline=po.payment_deadline,
                                reminder_context='before_deadline'
                            )
                            if success:
                                PushManager.notify_payment_reminder(
                                    order, payment_deadline=po.payment_deadline
                                )
                                db.session.add(PaymentReminderLog(
                                    order_id=order.id, config_id=rule.id
                                ))
                                log_activity(
                                    action='payment_reminder_sent',
                                    entity_type='order',
                                    entity_id=order.id,
                                    new_value=f'Wysłano przypomnienie ({rule.hours}h przed terminem wysyłki KR)'
                                )
                                sent_count += 1
                                click.echo(f"  Wysłano: {order.order_number} ({rule.hours}h przed deadline wysyłki KR)")

            elif rule.reminder_type == 'after_order_placed':
                if rule.payment_stage != 'product':
                    continue  # after_order_placed dotyczy tylko etapu product

                # Tylko On-hand i Pre-order
                orders = Order.query.filter(
                    Order.order_type.in_(['on_hand', 'preorder']),
                    Order.status != 'anulowane'
                ).all()

                for order in orders:
                    if order.product_payment_status not in ('none', 'rejected'):
                        continue

                    trigger_time = order.created_at + timedelta(hours=rule.hours)
                    if trigger_time > now:
                        continue

                    already_sent = PaymentReminderLog.query.filter_by(
                        order_id=order.id, config_id=rule.id
                    ).first()
                    if already_sent:
                        continue

                    payment_deadline = None
                    if order.offer_page:
                        payment_deadline = order.offer_page.payment_deadline

                    if dry_run:
                        click.echo(f"  [DRY RUN] {order.order_number} <- {rule.hours}h po złożeniu")
                        sent_count += 1
                        continue

                    success = EmailManager.notify_payment_reminder(
                        order, payment_deadline=payment_deadline,
                        reminder_context='after_order_placed'
                    )
                    if success:
                        PushManager.notify_payment_reminder(order, payment_deadline=payment_deadline)
                        db.session.add(PaymentReminderLog(
                            order_id=order.id, config_id=rule.id
                        ))
                        log_activity(
                            action='payment_reminder_sent',
                            entity_type='order',
                            entity_id=order.id,
                            new_value=f'Wysłano przypomnienie ({rule.hours}h po złożeniu zamówienia)'
                        )
                        sent_count += 1
                        click.echo(f"  Wysłano: {order.order_number} ({rule.hours}h po złożeniu)")

        # Sprawdź przekroczone deadline'y
        exceeded_pages = OfferPage.query.filter(
            OfferPage.payment_deadline.isnot(None),
            OfferPage.payment_deadline < now,
            OfferPage.is_fully_closed == True
        ).all()

        exceeded_count = 0
        exceeded_orders_by_page = {}

        for page in exceeded_pages:
            orders = Order.query.filter(
                Order.offer_page_id == page.id,
                Order.status != 'anulowane'
            ).all()
            for order in orders:
                if order.product_payment_status not in ('none', 'rejected'):
                    continue

                already_notified = PaymentReminderLog.query.filter_by(
                    order_id=order.id, config_id=None, reminder_type='deadline_exceeded'
                ).first()
                if already_notified:
                    continue

                if not dry_run:
                    db.session.add(PaymentReminderLog(
                        order_id=order.id, config_id=None, reminder_type='deadline_exceeded'
                    ))
                    log_activity(
                        action='payment_deadline_exceeded',
                        entity_type='order',
                        entity_id=order.id,
                        new_value='Przekroczono termin płatności — powiadomiono administrację'
                    )

                if page.id not in exceeded_orders_by_page:
                    exceeded_orders_by_page[page.id] = {'page': page, 'orders': []}
                exceeded_orders_by_page[page.id]['orders'].append(order)
                exceeded_count += 1

        if exceeded_orders_by_page and not dry_run:
            for page_data in exceeded_orders_by_page.values():
                EmailManager.notify_admin_deadline_exceeded(
                    page_data['page'], page_data['orders']
                )

        if exceeded_count > 0:
            click.echo(f"  Przekroczone deadline: {exceeded_count} zamówień")

        # Commit
        if not dry_run:
            db.session.commit()

            def set_setting(key, value):
                setting = Settings.query.filter_by(key=key).first()
                if setting:
                    setting.value = str(value)
                else:
                    setting = Settings(key=key, value=str(value), type='string')
                    db.session.add(setting)

            set_setting('payment_reminder_last_check', now.strftime('%d/%m/%Y %H:%M'))
            set_setting('payment_reminder_last_count', str(sent_count))
            db.session.commit()

        click.echo(f"\nGotowe. Wysłano przypomnień: {sent_count}, Przekroczone deadline: {exceeded_count}")

    @app.cli.command('backfill-set-numbers')
    @click.option('--dry-run', is_flag=True, help='Tylko wyświetl bez zapisywania')
    def backfill_set_numbers(dry_run):
        """Uzupełnia set_number i set_section_id dla istniejących zamówień ze stron sprzedaży."""
        from modules.orders.models import Order, OrderItem
        from modules.offers.models import OfferSection, OfferPage
        from sqlalchemy import func as sql_func

        pages = OfferPage.query.all()
        total_updated = 0

        for page in pages:
            set_sections = OfferSection.query.filter_by(
                offer_page_id=page.id, section_type='set'
            ).all()
            if not set_sections:
                continue

            # Build product → set info mapping
            product_set_info = {}
            for sec in set_sections:
                for set_item in sec.set_items:
                    qps = set_item.quantity_per_set or 1
                    for prod in set_item.get_products():
                        product_set_info[prod.id] = {'section_id': sec.id, 'quantity_per_set': qps}

            if not product_set_info:
                continue

            # Get all orders for this page chronologically
            orders = Order.query.filter_by(
                offer_page_id=page.id
            ).filter(Order.status != 'anulowane').order_by(Order.created_at.asc()).all()

            # Track cumulative ordered quantities
            cumulative = {}  # product_id → total ordered so far

            for order in orders:
                for item in order.items:
                    if item.product_id not in product_set_info:
                        continue

                    info = product_set_info[item.product_id]
                    qps = info['quantity_per_set']
                    prev = cumulative.get(item.product_id, 0)
                    set_num = (prev // qps) + 1 if qps > 0 else 1

                    if item.set_number != set_num or item.set_section_id != info['section_id']:
                        if not dry_run:
                            item.set_number = set_num
                            item.set_section_id = info['section_id']
                        total_updated += 1
                        click.echo(f"  {order.order_number} | {item.product_name} → Set {set_num}")

                    cumulative[item.product_id] = prev + item.quantity

            if not dry_run:
                db.session.commit()

        click.echo(f"\n{'[DRY RUN] ' if dry_run else ''}Zaktualizowano: {total_updated} pozycji")

    @app.cli.command('refresh-rates')
    def refresh_rates():
        """Odświeża kursy walut KRW i USD z NBP API (do użycia z cron)."""
        from utils.currency import fetch_nbp_rate, cache_rate
        from modules.auth.models import Settings

        click.echo('Pobieranie kursów walut z NBP API...')

        updated = {}
        for currency in ('KRW', 'USD'):
            try:
                rate = fetch_nbp_rate(currency)
                cache_rate(currency, rate)
                updated[currency] = rate
                click.echo(f'  {currency} → PLN: {rate}')
            except Exception as e:
                click.echo(f'  BŁĄD {currency}: {e}')

        if updated:
            now = datetime.now(tz=POLAND_TZ).strftime('%Y-%m-%d %H:%M:%S')
            Settings.set_value('warehouse_currency_last_update', now, type='string')
            Settings.set_value('warehouse_currency_last_update_source', 'auto-cron', type='string')
            db.session.commit()
            click.echo(f'\nGotowe. Zaktualizowano {len(updated)} kurs(y) o {now}')
        else:
            click.echo('\nNie udało się pobrać żadnego kursu.')

    @app.cli.group()
    def achievements():
        """Achievement management commands."""
        pass

    @achievements.command('seed')
    def seed_command():
        """Seed all 47 achievements into the database."""
        from modules.achievements.seed import seed_achievements
        created, updated = seed_achievements()
        click.echo(f'Achievements seeded: {created} created, {updated} updated.')

    @achievements.command('check-daily')
    def check_daily_command():
        """Run daily cron checks for time-based achievements."""
        from modules.achievements.services import AchievementService
        service = AchievementService()
        results = service.run_daily_checks()
        click.echo(f'Daily check complete: {results["unlocked"]} new unlocks, stats updated.')

    @achievements.command('backfill')
    def backfill_command():
        """One-time retroactive check — unlock achievements for existing users."""
        from modules.achievements.services import AchievementService
        service = AchievementService()
        results = service.backfill_all()
        click.echo(f'Backfill complete: {results["unlocked"]} achievements unlocked for {results["users"]} users.')

    @app.cli.command('process-account-deletions')
    @click.option('--dry-run', is_flag=True, help='Tylko wyświetl konta do anonimizacji, nie wykonuj')
    def process_account_deletions(dry_run):
        """Anonimizuje konta z żądaniem usunięcia starszym niż 30 dni (RODO art. 17)."""
        from modules.auth.models import User
        from datetime import datetime, timedelta

        cutoff = datetime.now() - timedelta(days=30)

        pending = User.query.filter(
            User.deletion_requested_at.isnot(None),
            User.deletion_requested_at < cutoff,
            ~User.email.endswith('@thunderorders.local')
        ).all()

        click.echo(f'Znaleziono {len(pending)} kont do anonimizacji (cooling period > 30 dni)')

        if not pending:
            click.echo('Brak kont do przetworzenia.')
            return

        for user in pending:
            click.echo(f'  #{user.id} — żądanie z {user.deletion_requested_at.strftime("%d.%m.%Y")}', nl=False)
            if dry_run:
                click.echo(' [DRY RUN — pominięto]')
            else:
                try:
                    user.anonymize()
                    db.session.commit()
                    click.echo(' — zanonimizowano')
                except Exception as e:
                    db.session.rollback()
                    click.echo(f' — BŁĄD: {e}')

        click.echo(f'\nGotowe.')

    @app.cli.command('send-registration-reminders')
    @click.option('--dry-run', is_flag=True, help='Tylko wyświetl, nie wysyłaj')
    @click.option('--hours', default=24, help='Wyślij po N godzinach od rejestracji (domyślnie 24)')
    def send_registration_reminders(dry_run, hours):
        """Wysyła jednorazowe przypomnienie do użytkowników, którzy nie dokończyli rejestracji."""
        from modules.auth.models import User, get_local_now
        from utils.email_sender import send_email
        from datetime import timedelta

        now = get_local_now()
        cutoff = now - timedelta(hours=hours)

        # Użytkownicy z niekompletnym profilem, zarejestrowani > N godzin temu, bez wysłanego przypomnienia
        users = User.query.filter(
            User.profile_completed == False,
            User.is_active == True,
            User.created_at < cutoff,
            User.registration_reminder_sent_at.is_(None)
        ).all()

        click.echo(f'Znaleziono {len(users)} użytkowników do przypomnienia')

        if not users:
            return

        sent = 0
        for user in users:
            email_verified = user.email_verified
            user_name = user.first_name or None

            base_url = app.config.get('BASE_URL', 'https://thunderorders.cloud')
            login_url = f'{base_url}/auth/login'

            if not email_verified:
                message = 'Zauważyliśmy, że Twoja rejestracja nie została dokończona. Zaloguj się, żeby zweryfikować email i uzupełnić profil.'
                action_text = 'Zaloguj się'
                action_url = login_url
            else:
                message = 'Twoje konto jest prawie gotowe! Zaloguj się, żeby uzupełnić dane i zacząć korzystać z ThunderOrders.'
                action_text = 'Dokończ rejestrację'
                action_url = login_url

            click.echo(f'  #{user.id} {user.email} (verified={email_verified})', nl=False)

            if dry_run:
                click.echo(' [DRY RUN]')
            else:
                try:
                    send_email(
                        to=user.email,
                        subject='Dokończ rejestrację - ThunderOrders',
                        template='registration_reminder',
                        user_name=user_name,
                        message=message,
                        action_text=action_text,
                        action_url=action_url
                    )
                    user.registration_reminder_sent_at = now
                    db.session.commit()
                    sent += 1
                    click.echo(' — wysłano')
                except Exception as e:
                    db.session.rollback()
                    click.echo(f' — BŁĄD: {e}')

        click.echo(f'\nWysłano {sent}/{len(users)} przypomnień.')

    @app.cli.command('cleanup-payment-proofs')
    @click.option('--days', default=30, help='Usuwaj pliki starsze niż N dni od zatwierdzenia')
    @click.option('--dry-run', is_flag=True, help='Tylko wyświetl pliki do usunięcia, nie usuwaj')
    def cleanup_payment_proofs(days, dry_run):
        """Usuwa pliki potwierdzeń płatności zatwierdzonych ponad N dni temu (domyślnie 30)."""
        import os
        from modules.orders.models import PaymentConfirmation, get_local_now
        from datetime import timedelta

        cutoff = get_local_now() - timedelta(days=days)
        upload_folder = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'uploads', 'payment_confirmations'
        )

        confirmations = PaymentConfirmation.query.filter(
            PaymentConfirmation.status == 'approved',
            PaymentConfirmation.updated_at < cutoff,
            PaymentConfirmation.proof_file.isnot(None)
        ).all()

        click.echo(f'Znaleziono {len(confirmations)} potwierdzeń starszych niż {days} dni')

        deleted_count = 0
        skipped_count = 0
        freed_bytes = 0

        for pc in confirmations:
            filepath = os.path.join(upload_folder, pc.proof_file)

            if not os.path.exists(filepath):
                skipped_count += 1
                continue

            file_size = os.path.getsize(filepath)

            if dry_run:
                click.echo(f'  [DRY RUN] {pc.proof_file} ({file_size / 1024:.1f} KB) — zamówienie #{pc.order_id}')
                deleted_count += 1
                freed_bytes += file_size
                continue

            try:
                os.remove(filepath)
                pc.proof_file = None
                deleted_count += 1
                freed_bytes += file_size
            except OSError as e:
                click.echo(f'  BŁĄD: {pc.proof_file} — {e}')
                skipped_count += 1

        if not dry_run:
            db.session.commit()

        prefix = '[DRY RUN] ' if dry_run else ''
        click.echo(f'\n{prefix}Gotowe. Usunięto: {deleted_count} plików ({freed_bytes / 1024 / 1024:.2f} MB), '
                   f'Pominięto: {skipped_count}')


    @app.cli.command('reprocess-ocr')
    @click.option('--dry-run', is_flag=True, help='Tylko wyświetl potwierdzenia do przetworzenia, nie uruchamiaj OCR')
    @click.option('--all', 'reprocess_all', is_flag=True, help='Przetwórz WSZYSTKIE potwierdzenia (nie tylko score=0/NULL)')
    def reprocess_ocr(dry_run, reprocess_all):
        """Ponownie przetwarza OCR dla potwierdzeń płatności z wynikiem 0% lub NULL."""
        import json as _json
        from modules.orders.models import PaymentConfirmation, Order, get_local_now
        from modules.payments.models import PaymentMethod
        from utils.ocr_verifier import verify_payment_proof, TESSERACT_AVAILABLE

        if not TESSERACT_AVAILABLE:
            click.echo('BŁĄD: Tesseract OCR nie jest dostępny. Zainstaluj: apt install tesseract-ocr tesseract-ocr-pol')
            return

        upload_folder = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'uploads', 'payment_confirmations'
        )

        # Znajdź potwierdzenia do przetworzenia
        query = PaymentConfirmation.query.filter(
            PaymentConfirmation.proof_file.isnot(None)
        )
        if not reprocess_all:
            query = query.filter(
                db.or_(
                    PaymentConfirmation.ocr_score.is_(None),
                    PaymentConfirmation.ocr_score == 0
                )
            )

        confirmations = query.all()
        click.echo(f'Znaleziono {len(confirmations)} potwierdzeń do przetworzenia')

        if not confirmations:
            return

        # Grupuj po proof_file (jeden plik może mieć wiele confirmation records)
        by_file = {}
        for conf in confirmations:
            if conf.proof_file not in by_file:
                by_file[conf.proof_file] = []
            by_file[conf.proof_file].append(conf)

        # Wszystkie aktywne metody płatności (do fallback)
        all_methods = PaymentMethod.get_active()

        processed = 0
        skipped = 0
        errors = 0

        for filename, confs in by_file.items():
            filepath = os.path.join(upload_folder, filename)

            if not os.path.exists(filepath):
                click.echo(f'  POMINIĘTO: {filename} — plik nie istnieje')
                skipped += len(confs)
                continue

            # Zbierz dane do weryfikacji z pierwszego confirmation
            first_conf = confs[0]
            order = first_conf.order

            # Zbierz numery zamówień powiązane z tym plikiem
            order_numbers = list(set(c.order.order_number for c in confs if c.order))

            # Oblicz łączną oczekiwaną kwotę
            total_expected = sum(c.amount for c in confs if c.amount)

            # Metoda płatności
            pm_obj = first_conf.payment_method

            if dry_run:
                click.echo(f'  [DRY RUN] {filename} — {len(confs)} rekord(ów), '
                           f'zamówienia: {", ".join(order_numbers)}, '
                           f'kwota: {total_expected} PLN')
                processed += len(confs)
                continue

            # Uruchom OCR
            try:
                result = verify_payment_proof(
                    filepath=filepath,
                    expected_amount=total_expected,
                    order_numbers=order_numbers,
                    payment_method=pm_obj,
                    all_payment_methods=all_methods
                )

                score = result.get('score')
                details_json = _json.dumps(result.get('details', {}), ensure_ascii=False)

                for conf in confs:
                    conf.ocr_score = score
                    conf.ocr_details = details_json

                processed += len(confs)

                # Podgląd wyniku
                raw_preview = result.get('details', {}).get('raw_text_preview', '')[:80]
                click.echo(f'  OK: {filename} — score: {score}%, '
                           f'zamówienia: {", ".join(order_numbers)}, '
                           f'tekst: "{raw_preview}..."')

            except Exception as e:
                click.echo(f'  BŁĄD: {filename} — {e}')
                errors += len(confs)

        if not dry_run:
            db.session.commit()

        prefix = '[DRY RUN] ' if dry_run else ''
        click.echo(f'\n{prefix}Gotowe. Przetworzono: {processed}, Pominięto: {skipped}, Błędów: {errors}')


    @app.cli.command('audit-offer-images')
    @click.option('--clear-db', is_flag=True,
                  help='Wyzeruj set_image w bazie dla rekordów wskazujących na nieistniejący plik')
    def audit_offer_images(clear_db):
        """Sprawdza spójność OfferSection.set_image — wykrywa "ghost paths" (rekord w bazie, brak pliku na dysku)."""
        from modules.offers.models import OfferSection, OfferPage

        sections = OfferSection.query.filter(OfferSection.set_image.isnot(None)).all()
        click.echo(f'Sprawdzam {len(sections)} sekcji z ustawionym set_image...\n')

        ok = []
        ghosts = []
        for section in sections:
            file_path = os.path.join(app.static_folder, section.set_image)
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                ok.append(section)
            else:
                ghosts.append(section)

        click.echo(f'OK: {len(ok)} pliki istnieją')
        click.echo(f'GHOST: {len(ghosts)} rekordów wskazuje na brakujący plik\n')

        if ghosts:
            click.echo('Lista ghost paths:')
            click.echo('-' * 100)
            for section in ghosts:
                page = OfferPage.query.get(section.offer_page_id)
                page_name = page.name if page else '?'
                click.echo(f'  section_id={section.id:>5}  page="{page_name}"  '
                           f'type={section.section_type}  path={section.set_image}')
            click.echo('-' * 100)

            if clear_db:
                for section in ghosts:
                    section.set_image = None
                db.session.commit()
                click.echo(f'\nWyzerowano set_image dla {len(ghosts)} rekordów. '
                           'Adminowie mogą ponownie wgrać obrazki przez page builder.')
            else:
                click.echo('\nUruchom z --clear-db aby wyzerować set_image w bazie '
                           '(po tym admin musi ponownie wgrać obrazki).')


def register_error_handlers(app):
    """Rejestruje handlery dla błędów HTTP"""

    @app.errorhandler(403)
    def forbidden(error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def page_not_found(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(429)
    def too_many_requests(error):
        return render_template('errors/429.html'), 429

    @app.errorhandler(500)
    def internal_server_error(error):
        db.session.rollback()  # Rollback na wypadek błędu bazy danych
        return render_template('errors/500.html'), 500

    @app.after_request
    def sanitize_error_responses(response):
        """
        W produkcji ukrywa szczegóły błędów w JSON responses (500).
        Zapobiega wyciekowi informacji o systemie (ścieżki, SQL, stack trace).
        W development zostawia szczegóły dla debugowania.
        """
        if app.debug or response.status_code < 500:
            return response
        if response.content_type and 'application/json' in response.content_type:
            try:
                import json
                data = json.loads(response.get_data(as_text=True))
                changed = False
                for key in ('error', 'message'):
                    if key in data and isinstance(data[key], str):
                        # Loguj oryginalny błąd
                        original = data[key]
                        if original and original not in ('Wystąpił błąd serwera.', 'Wystąpił błąd.'):
                            app.logger.error(f'API error (sanitized): {original}')
                            data[key] = 'Wystąpił błąd serwera.'
                            changed = True
                if changed:
                    response.set_data(json.dumps(data, ensure_ascii=False))
            except (ValueError, TypeError):
                pass
        return response


def register_context_processors(app):
    """
    Rejestruje context processors
    Zmienne/funkcje dostępne globalnie we wszystkich templates
    """

    @app.context_processor
    def override_url_for():
        """Cache-busting: dodaje ?v=<mtime> do URL-i plików statycznych"""
        return dict(url_for=dated_url_for)

    def dated_url_for(endpoint, **values):
        if endpoint == 'static':
            filename = values.get('filename', '')
            if filename:
                file_path = os.path.join(app.static_folder, filename)
                try:
                    values['v'] = int(os.path.getmtime(file_path))
                except OSError:
                    pass
        return flask_url_for(endpoint, **values)

    @app.context_processor
    def inject_globals():
        """Wstrzykuje zmienne globalne do wszystkich szablonów"""
        from modules.payments.models import PaymentMethod

        def get_active_payment_methods():
            """Pomocnicza funkcja do pobierania aktywnych metod płatności"""
            return PaymentMethod.get_active()

        from flask import g
        return {
            'app_name': 'ThunderOrders',
            'app_version': '1.0.0-MVP',
            'get_active_payment_methods': get_active_payment_methods,
            'maintenance_mode': getattr(g, 'maintenance_mode', False),
        }


def register_template_filters(app):
    """
    Rejestruje filtry Jinja2 do użycia w szablonach
    """

    @app.template_filter('sanitize_html')
    def sanitize_html_filter(value):
        """
        Sanityzuje HTML — zostawia bezpieczne tagi, usuwa skrypty i eventy.
        Użycie: {{ content|sanitize_html|safe }}
        """
        if not value:
            return ''
        import bleach
        allowed_tags = [
            'p', 'br', 'strong', 'em', 'b', 'i', 'u', 's', 'a',
            'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'span', 'div', 'img', 'blockquote', 'hr', 'table', 'thead',
            'tbody', 'tr', 'th', 'td', 'pre', 'code', 'sup', 'sub',
        ]
        allowed_attrs = {
            'a': ['href', 'title', 'target', 'rel'],
            'img': ['src', 'alt', 'width', 'height', 'style'],
            'span': ['style', 'class'],
            'div': ['style', 'class'],
            'p': ['style', 'class'],
            'td': ['style', 'class', 'colspan', 'rowspan'],
            'th': ['style', 'class', 'colspan', 'rowspan'],
            'table': ['style', 'class'],
        }
        from bleach.css_sanitizer import CSSSanitizer
        css_sanitizer = CSSSanitizer(allowed_css_properties=[
            'color', 'background-color', 'font-size', 'font-weight', 'font-style',
            'text-align', 'text-decoration', 'padding', 'margin', 'border',
            'width', 'height', 'max-width', 'max-height', 'display',
        ])
        return bleach.clean(value, tags=allowed_tags, attributes=allowed_attrs,
                            css_sanitizer=css_sanitizer, strip=True)

    @app.template_filter('to_poland_tz')
    def to_poland_tz_filter(dt):
        """
        Konwertuje datetime UTC na czas polski (Europe/Warsaw).
        Użycie w template: {{ date|to_poland_tz }}
        """
        if dt is None:
            return None
        # Jeśli datetime nie ma timezone, zakładamy że jest UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(POLAND_TZ)

    @app.template_filter('format_datetime')
    def format_datetime_filter(dt, fmt='%Y-%m-%d %H:%M'):
        """
        Formatuje datetime.
        Naive datetime traktowany jako czas polski (nie konwertujemy).
        Aware datetime konwertowany na czas polski.
        Użycie: {{ date|format_datetime }} lub {{ date|format_datetime('%d.%m.%Y %H:%M') }}
        """
        if dt is None:
            return ''
        # Naive datetime = już czas polski, nie konwertujemy
        if dt.tzinfo is not None:
            dt = dt.astimezone(POLAND_TZ)
        return dt.strftime(fmt)

    @app.template_filter('format_date')
    def format_date_filter(dt, fmt='%Y-%m-%d'):
        """
        Formatuje tylko datę.
        Naive datetime traktowany jako czas polski (nie konwertujemy).
        Użycie: {{ date|format_date }} lub {{ date|format_date('%d.%m.%Y') }}
        """
        if dt is None:
            return ''
        # Naive datetime = już czas polski, nie konwertujemy
        if dt.tzinfo is not None:
            dt = dt.astimezone(POLAND_TZ)
        return dt.strftime(fmt)

    @app.template_filter('format_time')
    def format_time_filter(dt, fmt='%H:%M'):
        """
        Formatuje tylko godzinę.
        Naive datetime traktowany jako czas polski (nie konwertujemy).
        Użycie: {{ date|format_time }} lub {{ date|format_time('%H:%M:%S') }}
        """
        if dt is None:
            return ''
        # Naive datetime = już czas polski, nie konwertujemy
        if dt.tzinfo is not None:
            dt = dt.astimezone(POLAND_TZ)
        return dt.strftime(fmt)

    @app.template_filter('format_datetime_local')
    def format_datetime_local_filter(dt):
        """
        Formatuje datetime dla input type="datetime-local".
        Naive datetime traktowany jako czas polski (nie konwertujemy).
        Użycie: {{ date|format_datetime_local }}
        """
        if dt is None:
            return ''
        # Naive datetime = już czas polski, nie konwertujemy
        if dt.tzinfo is not None:
            dt = dt.astimezone(POLAND_TZ)
        return dt.strftime('%Y-%m-%dT%H:%M')

    @app.template_filter('format_currency')
    def format_currency_filter(value, currency='PLN'):
        """
        Formatuje kwotę jako walutę.
        Użycie: {{ amount|format_currency }} lub {{ amount|format_currency('USD') }}
        """
        if value is None:
            return '0,00 PLN'

        # Konwertuj do float jeśli potrzeba
        try:
            value = float(value)
        except (ValueError, TypeError):
            return '0,00 PLN'

        # Formatuj z przecinkiem jako separator dziesiętny (polski standard)
        formatted = f"{value:,.2f}".replace(',', ' ').replace('.', ',')

        return f"{formatted} {currency}"

    @app.template_filter('reject_key')
    def reject_key_filter(d, key):
        """
        Zwraca kopię słownika bez podanego klucza.
        Użycie: {{ request.args|reject_key('status') }}
        """
        if not isinstance(d, dict):
            # Dla ImmutableMultiDict (request.args)
            result = {}
            for k in d.keys():
                if k != key:
                    # Pobierz wszystkie wartości dla klucza (dla multi-value)
                    values = d.getlist(k)
                    if len(values) == 1:
                        result[k] = values[0]
                    else:
                        result[k] = values
            return result
        return {k: v for k, v in d.items() if k != key}

    @app.template_filter('reject_status')
    def reject_status_filter(d, status_to_remove):
        """
        Usuwa pojedynczą wartość statusu z listy statusów w request.args.
        Użycie: {{ request.args|reject_status('nowe') }}
        """
        result = {}
        for k in d.keys():
            values = d.getlist(k)
            if k == 'status':
                # Filtruj listę statusów, usuwając wskazany
                filtered = [v for v in values if v != status_to_remove]
                if filtered:
                    if len(filtered) == 1:
                        result[k] = filtered[0]
                    else:
                        result[k] = filtered
            else:
                if len(values) == 1:
                    result[k] = values[0]
                else:
                    result[k] = values
        return result


# Uruchomienie aplikacji (tylko dla development)
if __name__ == '__main__':
    app = create_app()
    socketio.run(app, host='0.0.0.0', port=5001, debug=True,
                 allow_unsafe_werkzeug=True)
