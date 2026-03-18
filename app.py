import sys
if sys.platform != 'darwin':
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
    socketio.init_app(app, async_mode='eventlet', cors_allowed_origins=socketio_origins)

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
                "https://cdn.jsdelivr.net https://cdn.socket.io https://cdnjs.cloudflare.com https://cdn.quilljs.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.quilljs.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob: https://www.google-analytics.com https://*.googleusercontent.com; "
            "connect-src 'self' wss://thunderorders.cloud ws://localhost:* "
                "https://www.google-analytics.com https://analytics.google.com https://challenges.cloudflare.com; "
            "frame-src https://challenges.cloudflare.com; "
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

    # Exclusive module (publiczne strony zamówień pre-order)
    # CSRF exempt per-endpoint (reserve, release, extend, restore, place-order, subscribe-notification)
    from modules.exclusive import exclusive_bp
    app.register_blueprint(exclusive_bp)

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

        LAUNCH_DATE = datetime(2026, 3, 17, 0, 0, 0)

        if datetime.now() < LAUNCH_DATE:
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

    @app.cli.command('send-payment-reminders')
    @click.option('--days', default=3, help='Minimalny odstęp w dniach między przypomnieniami')
    @click.option('--dry-run', is_flag=True, help='Tylko wyświetl zamówienia, nie wysyłaj emaili')
    def send_payment_reminders(days, dry_run):
        """Wysyła przypomnienia o niezapłaconych etapach zamówień."""
        from modules.orders.models import Order, get_local_now
        from utils.email_manager import EmailManager
        from datetime import timedelta

        now = get_local_now()
        cutoff = now - timedelta(days=days)

        # Statusy, w których zamówienie jest aktywne i wymaga płatności
        active_statuses = [
            'oczekujace', 'dostarczone_proxy', 'w_drodze_polska',
            'urzad_celny', 'dostarczone_gom', 'spakowane'
        ]

        # Znajdź zamówienia: aktywne, przypomnienie niewyslane lub starsze niż X dni
        orders = Order.query.filter(
            Order.status.in_(active_statuses)
        ).filter(
            db.or_(
                Order.payment_reminder_sent_at.is_(None),
                Order.payment_reminder_sent_at < cutoff
            )
        ).all()

        click.echo(f"Znaleziono {len(orders)} zamówień do sprawdzenia (odstęp: {days} dni)")

        sent_count = 0
        skipped_count = 0

        for order in orders:
            # Sprawdź czy są niezapłacone etapy
            has_unpaid = False

            # E1: Produkt
            if order.product_payment_status in ('none', 'rejected'):
                has_unpaid = True

            # E2: Wysyłka KR (4-płatnościowe)
            if (order.payment_stages == 4 and order.proxy_shipping_cost
                    and float(order.proxy_shipping_cost) > 0
                    and order.stage_2_status in ('none', 'rejected')):
                has_unpaid = True

            # E3: Cło/VAT
            if (order.customs_vat_sale_cost
                    and float(order.customs_vat_sale_cost) > 0
                    and order.stage_3_status in ('none', 'rejected')):
                has_unpaid = True

            # E4: Wysyłka krajowa
            if (order.shipping_cost
                    and float(order.shipping_cost) > 0
                    and order.stage_4_status in ('none', 'rejected')):
                has_unpaid = True

            if not has_unpaid:
                skipped_count += 1
                continue

            if dry_run:
                click.echo(f"  [DRY RUN] {order.order_number} → {order.customer_email}")
                sent_count += 1
                continue

            success = EmailManager.notify_payment_reminder(order)
            if success:
                from utils.push_manager import PushManager
                PushManager.notify_payment_reminder(order)
                order.payment_reminder_sent_at = now
                db.session.commit()
                sent_count += 1
                click.echo(f"  Wysłano: {order.order_number} → {order.customer_email}")
            else:
                skipped_count += 1

        click.echo(f"\nGotowe. Wysłano: {sent_count}, Pominięto: {skipped_count}")

    @app.cli.command('backfill-set-numbers')
    @click.option('--dry-run', is_flag=True, help='Tylko wyświetl bez zapisywania')
    def backfill_set_numbers(dry_run):
        """Uzupełnia set_number i set_section_id dla istniejących zamówień exclusive."""
        from modules.orders.models import Order, OrderItem
        from modules.exclusive.models import ExclusiveSection, ExclusivePage
        from sqlalchemy import func as sql_func

        pages = ExclusivePage.query.all()
        total_updated = 0

        for page in pages:
            set_sections = ExclusiveSection.query.filter_by(
                exclusive_page_id=page.id, section_type='set'
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
                exclusive_page_id=page.id
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
