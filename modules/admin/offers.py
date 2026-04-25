"""
Admin Offers Pages Routes
Zarządzanie stronami ofert (Page Builder)
"""

from flask import render_template, redirect, url_for, flash, request, jsonify, abort, Response, current_app
from flask_login import login_required, current_user
from markupsafe import Markup
from modules.admin import admin_bp
from utils.decorators import admin_required, mod_required
from extensions import db
from modules.offers.models import OfferPage, OfferSection, OfferSetItem, OfferSetBonus, OfferBonusRequiredProduct
from modules.products.models import Product, ProductType, VariantGroup
from datetime import datetime
import json


# ============================================
# Lista stron Offers
# ============================================

@admin_bp.route('/offers')
@login_required
@admin_required
def offers_list():
    """Lista wszystkich stron sprzedaży"""
    pages = OfferPage.query.order_by(OfferPage.created_at.desc()).all()

    # Automatyczna aktualizacja statusów (scheduled->active, active->ended)
    for page in pages:
        page.check_and_update_status()

    return render_template(
        'admin/offers/list.html',
        title='Strony sprzedaży',
        pages=pages
    )


@admin_bp.route('/offers/settings')
@login_required
@admin_required
def offers_settings():
    """Ustawienia stron sprzedaży"""
    from modules.orders.models import OrderStatus
    from modules.auth.models import Settings

    statuses = OrderStatus.query.filter_by(is_active=True).all()

    def get_setting_value(key, default):
        setting = Settings.query.filter_by(key=key).first()
        return setting.value if setting else default

    offers_closure_settings = {
        'fully_fulfilled': get_setting_value('offers_closure_status_fully_fulfilled', 'oczekujace'),
        'partially_fulfilled': get_setting_value('offers_closure_status_partially_fulfilled', 'oczekujace'),
        'not_fulfilled': get_setting_value('offers_closure_status_not_fulfilled', 'anulowane')
    }

    auto_increase_settings = {
        'enabled': get_setting_value('auto_increase_enabled', 'false') == 'true',
        'product_threshold': int(get_setting_value('auto_increase_product_threshold', '100')),
        'set_threshold': int(get_setting_value('auto_increase_set_threshold', '50')),
        'amount': int(get_setting_value('auto_increase_amount', '1'))
    }

    # Payment reminder settings
    from modules.offers.reminder_models import PaymentReminderConfig

    reminder_rules_before = PaymentReminderConfig.query.filter_by(
        reminder_type='before_deadline', payment_stage='product', enabled=True
    ).order_by(PaymentReminderConfig.hours.desc()).all()

    reminder_rules_after = PaymentReminderConfig.query.filter_by(
        reminder_type='after_order_placed', payment_stage='product', enabled=True
    ).order_by(PaymentReminderConfig.hours.asc()).all()

    reminder_last_check = get_setting_value('payment_reminder_last_check', None)
    reminder_last_count = get_setting_value('payment_reminder_last_count', '0')

    return render_template(
        'admin/offers/settings.html',
        title='Ustawienia stron sprzedaży',
        statuses=statuses,
        offers_closure_settings=offers_closure_settings,
        auto_increase_settings=auto_increase_settings,
        reminder_rules_before=reminder_rules_before,
        reminder_rules_after=reminder_rules_after,
        reminder_last_check=reminder_last_check,
        reminder_last_count=reminder_last_count
    )


# ============================================
# Tworzenie nowej strony (modal submit)
# ============================================

@admin_bp.route('/offers/create', methods=['POST'])
@login_required
@admin_required
def offers_create():
    """Tworzy nową stronę offers (z modalu)"""
    name = request.form.get('name', '').strip()
    page_type = request.form.get('page_type', 'exclusive')
    starts_at_str = request.form.get('starts_at', '').strip()
    ends_at_str = request.form.get('ends_at', '').strip()

    # Walidacja
    if page_type not in ('exclusive', 'preorder'):
        flash('Nieprawidłowy typ strony.', 'error')
        return redirect(url_for('admin.offers_list'))

    if not name:
        flash('Nazwa strony jest wymagana.', 'error')
        return redirect(url_for('admin.offers_list'))

    # Parse dates
    starts_at = None
    ends_at = None

    if starts_at_str:
        try:
            starts_at = datetime.strptime(starts_at_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Nieprawidłowy format daty rozpoczęcia.', 'error')
            return redirect(url_for('admin.offers_list'))

    if ends_at_str:
        try:
            ends_at = datetime.strptime(ends_at_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Nieprawidłowy format daty zakończenia.', 'error')
            return redirect(url_for('admin.offers_list'))

    # Walidacja dat
    if starts_at and ends_at and starts_at >= ends_at:
        flash('Data zakończenia musi być późniejsza niż data rozpoczęcia.', 'error')
        return redirect(url_for('admin.offers_list'))

    # Tworzenie strony
    page = OfferPage(
        name=name,
        page_type=page_type,
        token=OfferPage.generate_token(),
        status='draft',
        starts_at=starts_at,
        ends_at=ends_at,
        created_by=current_user.id
    )

    db.session.add(page)
    db.session.commit()

    flash(f'Strona "{name}" została utworzona.', 'success')
    return redirect(url_for('admin.offers_edit', page_id=page.id))


# ============================================
# Edycja strony (Page Builder)
# ============================================

@admin_bp.route('/offers/<int:page_id>/edit')
@login_required
@admin_required
def offers_edit(page_id):
    """Page Builder - edycja strony offers"""
    page = OfferPage.query.get_or_404(page_id)
    sections = page.get_sections_ordered()

    # Pobierz produkty odpowiedniego typu
    type_slug = 'exclusive' if page.page_type == 'exclusive' else 'pre-order'
    offers_type = ProductType.query.filter_by(slug=type_slug).first()
    if offers_type:
        products = Product.query.filter_by(
            is_active=True,
            product_type_id=offers_type.id
        ).order_by(Product.name).all()
    else:
        products = []

    # Pobierz grupy wariantowe które mają produkty typu Offers
    variant_groups = []
    if offers_type:
        # Znajdź grupy wariantowe z produktami Offers
        from sqlalchemy import exists, and_
        from modules.products.models import variant_products

        variant_groups = VariantGroup.query.filter(
            VariantGroup.products.any(
                and_(
                    Product.is_active == True,
                    Product.product_type_id == offers_type.id
                )
            )
        ).order_by(VariantGroup.name).all()

    return render_template(
        'admin/offers/edit.html',
        title=f'Edycja: {page.name}',
        page=page,
        sections=sections,
        products=products,
        variant_groups=variant_groups
    )


# ============================================
# API - Zapisywanie strony (auto-save + manual)
# ============================================

@admin_bp.route('/offers/<int:page_id>/save', methods=['POST'])
@login_required
@admin_required
def offers_save(page_id):
    """
    Zapisuje stronę offers (AJAX)
    Obsługuje zarówno auto-save jak i ręczny zapis.

    Dodatkowo: jeśli payload zawiera notify_email_on_end_date_change
    lub notify_push_on_end_date_change i ends_at faktycznie się zmieniła,
    po commit'cie odpala dispatcher powiadomień w background thread.
    """
    page = OfferPage.query.get_or_404(page_id)
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'error': 'Brak danych'}), 400

    # Flagi powiadomień (opcjonalne — domyślnie False)
    notify_email = bool(data.get('notify_email_on_end_date_change', False))
    notify_push = bool(data.get('notify_push_on_end_date_change', False))

    # Zapamiętaj starą wartość zanim ją nadpiszemy
    old_ends_at = page.ends_at

    try:
        # Aktualizacja podstawowych danych strony
        if 'name' in data:
            page.name = data['name'].strip()

        if 'description' in data:
            page.description = data['description'].strip() if data['description'] else None

        if 'footer_content' in data:
            page.footer_content = data['footer_content'].strip() if data['footer_content'] else None

        if 'starts_at' in data:
            if data['starts_at']:
                new_starts_at = datetime.strptime(data['starts_at'], '%Y-%m-%dT%H:%M')
                page.starts_at = new_starts_at

                if page.status == 'active' and new_starts_at > datetime.now():
                    page.status = 'scheduled'
            else:
                page.starts_at = None

        if 'ends_at' in data:
            if data['ends_at']:
                page.ends_at = datetime.strptime(data['ends_at'], '%Y-%m-%dT%H:%M')
            else:
                page.ends_at = None

        if 'payment_stages' in data:
            payment_stages = int(data['payment_stages'])
            if payment_stages in (3, 4):
                page.payment_stages = payment_stages

        if 'notify_clients_on_publish' in data:
            page.notify_clients_on_publish = bool(data['notify_clients_on_publish'])

        # Aktualizacja sekcji
        limit_changes = []
        if 'sections' in data:
            limit_changes = _update_sections(page, data['sections'])

        page.updated_at = datetime.now()

        db.session.commit()

        # Po commit: powiadomienia dla sekcji ze zwiększonymi limitami (jak dotąd)
        if limit_changes:
            _send_notifications_for_limit_changes(page.id, limit_changes)

        # Po commit: powiadomienia o zmianie daty zakończenia
        ends_at_changed = (old_ends_at != page.ends_at)
        notifications_sent = {'email': 0, 'push': 0}

        if ends_at_changed and (notify_email or notify_push):
            # Resolver synchronicznie — żeby zwrócić liczby do frontendu
            recipients = _resolve_end_date_change_recipients(page)

            email_user_ids = [u.id for u in recipients['email_users']] if notify_email else []
            push_user_ids = recipients['push_user_ids'] if notify_push else []

            notifications_sent['email'] = len(email_user_ids)
            notifications_sent['push'] = len(push_user_ids)

            # Faktyczna wysyłka w tle
            _dispatch_end_date_change_notifications(
                app=current_app._get_current_object(),
                page_id=page.id,
                old_ends_at=old_ends_at,
                new_ends_at=page.ends_at,
                email_user_ids=email_user_ids,
                push_user_ids=push_user_ids,
            )
            current_app.logger.info(
                f"End date change dispatched for page={page.id} "
                f"({old_ends_at} → {page.ends_at}, "
                f"email={len(email_user_ids)}, push={len(push_user_ids)})"
            )

        return jsonify({
            'success': True,
            'message': 'Zapisano',
            'updated_at': page.updated_at.strftime('%H:%M:%S') if page.updated_at else None,
            'notifications_sent': notifications_sent,
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


def _validate_section_data(section_data):
    """
    Waliduje dane sekcji przed zapisem

    Args:
        section_data: Dane sekcji z frontendu

    Returns:
        tuple: (valid: bool, error: str or None)
    """
    section_type = section_data.get('type')

    # Walidacja sekcji "set"
    if section_type == 'set':
        set_product_id = section_data.get('set_product_id')

        # Sprawdź czy sekcja ma grupy wariantowe w set_items
        has_variant_groups = False
        for item in section_data.get('set_items', []):
            if item.get('variant_group_id'):
                has_variant_groups = True
                break

        # set_product_id wymagany TYLKO gdy sekcja ma grupy wariantowe
        if has_variant_groups:
            if not set_product_id:
                return False, 'Musisz wybrać produkt-komplet dla sekcji Set z grupami wariantowymi'

        # Jeśli set_product_id podany, zwaliduj produkt
        if set_product_id:
            product = Product.query.get(set_product_id)
            if not product:
                return False, 'Wybrany produkt nie istnieje'

            # Sprawdź typ produktu
            if product.product_type and product.product_type.slug != 'exclusive':
                return False, 'Produkt-komplet musi być typu Exclusive'

    # Walidacja bonusow w secie
    if section_type == 'set' and 'bonuses' in section_data:
        for bonus_data in section_data['bonuses']:
            bonus_product_id = bonus_data.get('bonus_product_id')
            trigger_type = bonus_data.get('trigger_type')

            if not bonus_product_id:
                return False, 'Bonus musi mieć wybrany produkt gratisowy'

            if trigger_type == 'buy_products':
                required = bonus_data.get('required_products', [])
                if not required or not any(rp.get('product_id') for rp in required):
                    return False, 'Bonus typu "Kup produkty" musi mieć co najmniej 1 wymagany produkt'

            elif trigger_type in ('price_threshold', 'quantity_threshold'):
                threshold = bonus_data.get('threshold_value')
                if not threshold or float(threshold) <= 0:
                    return False, 'Bonus progowy musi mieć wartość progu większą od 0'

    # Walidacja standalone bonus section
    if section_type == 'bonus':
        bonus_product_id = section_data.get('bonus_product_id')
        trigger_type = section_data.get('bonus_trigger_type', 'buy_products')

        if not bonus_product_id:
            return False, 'Sekcja Bonus musi mieć wybrany produkt gratisowy'

        if trigger_type == 'buy_products':
            required = section_data.get('bonus_required_products', [])
            if not required or not any(rp.get('product_id') for rp in required):
                return False, 'Bonus typu "Kup produkty" musi mieć co najmniej 1 wymagany produkt'

        elif trigger_type in ('price_threshold', 'quantity_threshold'):
            threshold = section_data.get('bonus_threshold_value')
            if not threshold or float(threshold) <= 0:
                return False, 'Bonus progowy musi mieć wartość progu większą od 0'

    return True, None


def _update_sections(page, sections_data):
    """
    Aktualizuje sekcje strony

    Args:
        page: OfferPage object
        sections_data: Lista danych sekcji z frontendu

    Returns:
        list: Lista krotek (section, old_max, new_max, section_type) dla sekcji z zmienionymi limitami
    """
    # Pobierz istniejące sekcje
    existing_sections = {s.id: s for s in page.sections.all()}
    existing_ids = set(existing_sections.keys())
    incoming_ids = set()

    # Śledzenie zmian limitów do powiadomień
    limit_changes = []

    for idx, section_data in enumerate(sections_data):
        # WALIDACJA - sprawdź dane sekcji przed zapisem
        valid, error = _validate_section_data(section_data)
        if not valid:
            raise ValueError(error)

        section_id = section_data.get('id')

        if section_id and section_id in existing_sections:
            # Aktualizacja istniejącej sekcji
            section = existing_sections[section_id]
            incoming_ids.add(section_id)

            # Zapamiętaj stare wartości przed zmianą
            old_max_quantity = section.max_quantity
            old_set_max_sets = section.set_max_sets
        else:
            # Nowa sekcja
            section = OfferSection(offer_page_id=page.id)
            db.session.add(section)
            old_max_quantity = None
            old_set_max_sets = None

        # Pobierz nowe wartości
        new_max_quantity = section_data.get('max_quantity')
        new_set_max_sets = section_data.get('set_max_sets')
        section_type = section_data.get('type', 'paragraph')

        # Aktualizacja danych sekcji
        section.section_type = section_type
        section.sort_order = idx
        section.content = section_data.get('content')
        section.product_id = section_data.get('product_id')
        section.min_quantity = section_data.get('min_quantity')
        section.max_quantity = new_max_quantity
        section.set_name = section_data.get('set_name')
        section.set_image = section_data.get('set_image')
        section.set_max_sets = new_set_max_sets
        # set_max_per_product: 0 oznacza brak limitu, wartość > 0 to limit sztuk na produkt
        max_per_product = section_data.get('set_max_per_product', 0)
        section.set_max_per_product = max_per_product if max_per_product and max_per_product > 0 else None
        section.variant_group_id = section_data.get('variant_group_id')
        section.set_product_id = section_data.get('set_product_id')  # NOWE: Produkt-komplet dla setu

        # Obsługa elementów setu
        if section.section_type == 'set' and 'set_items' in section_data:
            _update_set_items(section, section_data['set_items'])

        # Obsługa gratisów (bonusów) w secie
        if section.section_type == 'set' and 'bonuses' in section_data:
            _update_set_bonuses(section, section_data['bonuses'])

        # Obsługa standalone bonusu (sekcja typu 'bonus')
        if section.section_type == 'bonus':
            _update_standalone_bonus(section, section_data)

        # Zapisz zmiany limitów do późniejszego sprawdzenia powiadomień
        if section_type in ['product', 'variant_group']:
            if old_max_quantity is not None and new_max_quantity is not None:
                if new_max_quantity > old_max_quantity:
                    limit_changes.append((section, old_max_quantity, new_max_quantity, section_type))
        elif section_type == 'set':
            if old_set_max_sets is not None and new_set_max_sets is not None:
                if new_set_max_sets > old_set_max_sets:
                    limit_changes.append((section, old_set_max_sets, new_set_max_sets, section_type))

    # Usuń sekcje które nie są w incoming_ids
    sections_to_delete = existing_ids - incoming_ids
    for section_id in sections_to_delete:
        db.session.delete(existing_sections[section_id])

    # Zwróć informacje o zmianach limitów
    return limit_changes


def _update_set_items(section, items_data):
    """
    Aktualizuje elementy setu

    Args:
        section: OfferSection object (type='set')
        items_data: Lista danych elementów setu (mogą być produkty lub grupy wariantowe)
    """
    # Usuń istniejące elementy
    OfferSetItem.query.filter_by(section_id=section.id).delete()

    # Dodaj nowe
    for idx, item_data in enumerate(items_data):
        product_id = item_data.get('product_id')
        variant_group_id = item_data.get('variant_group_id')

        # Element musi mieć albo product_id albo variant_group_id
        if product_id or variant_group_id:
            item = OfferSetItem(
                section_id=section.id,
                product_id=product_id if product_id else None,
                variant_group_id=variant_group_id if variant_group_id else None,
                quantity_per_set=item_data.get('quantity_per_set', 1),
                sort_order=idx
            )
            db.session.add(item)


def _update_set_bonuses(section, bonuses_data):
    """
    Aktualizuje gratisy (bonusy) sekcji setu (delete-all + re-create).
    Strategia: delete all + re-create (jak _update_set_items).

    Args:
        section: OfferSection object (type='set')
        bonuses_data: Lista danych bonusow z frontendu
    """
    # Usun istniejace bonusy (ORM cascade usunie tez required_products)
    existing_bonuses = OfferSetBonus.query.filter_by(section_id=section.id).all()
    for bonus in existing_bonuses:
        db.session.delete(bonus)

    for idx, bonus_data in enumerate(bonuses_data):
        bonus_product_id = bonus_data.get('bonus_product_id')
        trigger_type = bonus_data.get('trigger_type')

        if not bonus_product_id or not trigger_type:
            continue

        threshold_value = bonus_data.get('threshold_value')
        if threshold_value is not None:
            try:
                threshold_value = float(threshold_value)
            except (ValueError, TypeError):
                threshold_value = None

        max_available = bonus_data.get('max_available')
        if max_available is not None:
            try:
                max_available = int(max_available)
                if max_available <= 0:
                    max_available = None
            except (ValueError, TypeError):
                max_available = None

        bonus = OfferSetBonus(
            section_id=section.id,
            trigger_type=trigger_type,
            threshold_value=threshold_value,
            bonus_product_id=int(bonus_product_id),
            bonus_quantity=max(1, int(bonus_data.get('bonus_quantity', 1))),
            max_available=max_available,
            when_exhausted=bonus_data.get('when_exhausted', 'hide'),
            count_full_set=bool(bonus_data.get('count_full_set', False)),
            repeatable=bool(bonus_data.get('repeatable', False)),
            is_active=bool(bonus_data.get('is_active', True)),
            sort_order=idx,
        )
        db.session.add(bonus)
        db.session.flush()  # Get bonus.id for required products

        # Dodaj wymagane produkty (tylko dla buy_products)
        if trigger_type == 'buy_products':
            for rp_data in bonus_data.get('required_products', []):
                rp_product_id = rp_data.get('product_id')
                if rp_product_id:
                    rp = OfferBonusRequiredProduct(
                        bonus_id=bonus.id,
                        product_id=int(rp_product_id),
                        min_quantity=max(1, int(rp_data.get('min_quantity', 1))),
                    )
                    db.session.add(rp)


def _update_standalone_bonus(section, section_data):
    """
    Aktualizuje standalone bonus (sekcja typu 'bonus').
    Jeden OfferSetBonus record na sekcję.

    Args:
        section: OfferSection object (type='bonus')
        section_data: Dane sekcji z frontendu
    """
    # Usuń istniejące bonusy i utwórz na nowo
    existing_bonuses = OfferSetBonus.query.filter_by(section_id=section.id).all()
    for bonus in existing_bonuses:
        db.session.delete(bonus)

    bonus_product_id = section_data.get('bonus_product_id')
    trigger_type = section_data.get('bonus_trigger_type', 'buy_products')

    if not bonus_product_id or not trigger_type:
        return

    threshold_value = section_data.get('bonus_threshold_value')
    if threshold_value is not None:
        try:
            threshold_value = float(threshold_value)
        except (ValueError, TypeError):
            threshold_value = None

    max_available = section_data.get('bonus_max_available')
    if max_available is not None:
        try:
            max_available = int(max_available)
            if max_available <= 0:
                max_available = None
        except (ValueError, TypeError):
            max_available = None

    bonus = OfferSetBonus(
        section_id=section.id,
        trigger_type=trigger_type,
        threshold_value=threshold_value,
        bonus_product_id=int(bonus_product_id),
        bonus_quantity=max(1, int(section_data.get('bonus_quantity', 1))),
        max_available=max_available,
        when_exhausted=section_data.get('bonus_when_exhausted', 'hide'),
        count_full_set=False,
        repeatable=bool(section_data.get('bonus_repeatable', False)),
        is_active=bool(section_data.get('bonus_is_active', True)),
        sort_order=0,
    )
    db.session.add(bonus)
    db.session.flush()

    # Dodaj wymagane produkty (tylko dla buy_products)
    if trigger_type == 'buy_products':
        for rp_data in section_data.get('bonus_required_products', []):
            rp_product_id = rp_data.get('product_id')
            if rp_product_id:
                rp = OfferBonusRequiredProduct(
                    bonus_id=bonus.id,
                    product_id=int(rp_product_id),
                    min_quantity=max(1, int(rp_data.get('min_quantity', 1))),
                )
                db.session.add(rp)


def _send_notifications_for_limit_changes(page_id, limit_changes):
    """
    Wysyła powiadomienia o dostępności dla sekcji z zwiększonymi limitami.

    Args:
        page_id (int): ID strony offers
        limit_changes (list): Lista krotek (section, old_max, new_max, section_type)
    """
    try:
        from utils.offer_notifications import (
            check_and_send_notifications_for_section,
            check_and_send_notifications_for_product_section
        )

        for section, old_max, new_max, section_type in limit_changes:
            try:
                if section_type == 'set':
                    # Dla sekcji typu 'set' używamy funkcji sprawdzającej całą sekcję
                    sent = check_and_send_notifications_for_section(
                        page_id=page_id,
                        section_id=section.id,
                        old_max=old_max,
                        new_max=new_max
                    )
                else:
                    # Dla sekcji typu 'product' lub 'variant_group'
                    sent = check_and_send_notifications_for_product_section(
                        page_id=page_id,
                        section=section,
                        old_max_quantity=old_max
                    )

                if sent > 0:
                    print(f"[NOTIFICATIONS] Sent {sent} back-in-stock notifications for section {section.id}")
            except Exception as e:
                print(f"[NOTIFICATIONS] Failed to send notifications for section {section.id}: {e}")
    except Exception as e:
        print(f"[NOTIFICATIONS] Failed to import notification module: {e}")


# ============================================
# Zmiana statusu strony
# ============================================

@admin_bp.route('/offers/<int:page_id>/status', methods=['POST'])
@login_required
@admin_required
def offers_change_status(page_id):
    """Zmienia status strony offers"""
    page = OfferPage.query.get_or_404(page_id)
    data = request.get_json()
    action = data.get('action')

    if action == 'publish':
        # Publikuj natychmiast
        page.publish()
        message = 'Strona została opublikowana.'

        # Wyślij powiadomienie do klientów jeśli toggle włączony
        if page.notify_clients_on_publish:
            page._send_publish_notifications()
            message += ' Wysłano powiadomienie do klientów.'

    elif action == 'schedule':
        # Zaplanuj na datę startu
        if not page.starts_at:
            return jsonify({'success': False, 'error': 'Brak daty rozpoczęcia'}), 400
        page.schedule()
        message = f'Sprzedaż zaplanowana na {page.starts_at.strftime("%d.%m.%Y %H:%M")}.'

    elif action == 'pause':
        # Wstrzymaj sprzedaż
        page.pause()
        message = 'Sprzedaż została wstrzymana.'

    elif action == 'resume':
        # Wznów sprzedaż
        page.resume()
        message = 'Sprzedaż została wznowiona.'

    elif action == 'end':
        # Zakończ sprzedaż
        page.end()
        message = 'Sprzedaż została zakończona.'

    elif action == 'draft':
        # Cofnij do draftu
        page.status = 'draft'
        message = 'Strona została cofnięta do wersji roboczej.'

    else:
        return jsonify({'success': False, 'error': 'Nieznana akcja'}), 400

    db.session.commit()

    # Broadcast zmiany statusu do kupujących przez SocketIO
    try:
        from modules.offers.socket_events import broadcast_page_status
        broadcast_page_status(
            page.id,
            page.status,
            ends_at=page.ends_at.isoformat() if page.ends_at else None
        )
    except Exception:
        pass

    return jsonify({
        'success': True,
        'message': message,
        'status': page.status
    })


# ============================================
# Usuwanie strony
# ============================================

@admin_bp.route('/offers/<int:page_id>/orders-count')
@login_required
@admin_required
def offers_orders_count(page_id):
    """Zwraca liczbę zamówień powiązanych ze stroną (AJAX)"""
    page = OfferPage.query.get_or_404(page_id)
    return jsonify({
        'success': True,
        'orders_count': page.orders.count()
    })


@admin_bp.route('/offers/<int:page_id>/delete', methods=['POST'])
@login_required
@admin_required
def offers_delete(page_id):
    """Usuwa stronę offers wraz z powiązanymi elementami"""
    import os
    from flask import current_app
    from utils.activity_logger import log_activity

    page = OfferPage.query.get_or_404(page_id)
    name = page.name
    page_id_for_log = page.id

    # 1. Zlicz zamówienia powiązane (przed usunięciem)
    orders_count = page.orders.count()

    # 2. Usuń pliki graficzne setów
    for section in page.sections:
        if section.set_image:
            # set_image może być ścieżką względną np. "uploads/offers/xxx.jpg"
            file_path = os.path.join(current_app.static_folder, section.set_image)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass  # Ignoruj błędy usuwania plików

    # 3. Usuń stronę (CASCADE zajmie się sekcjami, rezerwacjami, powiadomieniami)
    db.session.delete(page)
    db.session.commit()

    # 4. Zaloguj aktywność
    log_activity(
        user=current_user,
        action='offer_deleted',
        entity_type='offer',
        entity_id=page_id_for_log,
        old_value={'name': name, 'orders_count': orders_count},
        new_value=None
    )

    # Sprawdź czy to AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'redirect': url_for('admin.offers_list'),
            'orders_affected': orders_count,
            'message': f'Strona "{name}" została usunięta.'
        })

    # Dla non-AJAX - użyj flash
    flash(f'Strona "{name}" została usunięta.', 'success')
    return redirect(url_for('admin.offers_list'))


# ============================================
# API - Pobieranie produktów (dla selecta)
# ============================================

@admin_bp.route('/offers/api/products')
@login_required
@admin_required
def offers_api_products():
    """Zwraca listę produktów do selecta (AJAX), filtrowane po page_type"""
    query = request.args.get('q', '').strip()
    page_type = request.args.get('page_type', 'exclusive')

    # Filtruj po odpowiednim typie produktu
    type_slug = 'exclusive' if page_type == 'exclusive' else 'pre-order'
    offers_type = ProductType.query.filter_by(slug=type_slug).first()
    if not offers_type:
        return jsonify([])

    products_query = Product.query.filter_by(
        is_active=True,
        product_type_id=offers_type.id
    )

    if query:
        products_query = products_query.filter(
            db.or_(
                Product.name.ilike(f'%{query}%'),
                Product.sku.ilike(f'%{query}%')
            )
        )

    products = products_query.order_by(Product.name).limit(50).all()

    return jsonify([{
        'id': p.id,
        'name': p.name,
        'sku': p.sku,
        'price': float(p.sale_price) if p.sale_price else 0,
        'image': url_for('static', filename=p.primary_image.path_compressed) if p.primary_image else None
    } for p in products])


# ============================================
# API - Pobieranie grup wariantowych
# ============================================

@admin_bp.route('/offers/api/variant-groups')
@login_required
@admin_required
def offers_api_variant_groups():
    """Zwraca listę grup wariantowych z produktami odpowiedniego typu (AJAX)"""
    from sqlalchemy import and_

    page_type = request.args.get('page_type', 'exclusive')
    type_slug = 'exclusive' if page_type == 'exclusive' else 'pre-order'
    offers_type = ProductType.query.filter_by(slug=type_slug).first()
    if not offers_type:
        return jsonify([])

    # Znajdź grupy wariantowe z produktami Offers
    variant_groups = VariantGroup.query.filter(
        VariantGroup.products.any(
            and_(
                Product.is_active == True,
                Product.product_type_id == offers_type.id
            )
        )
    ).order_by(VariantGroup.name).all()

    result = []
    for vg in variant_groups:
        # Pobierz produkty Offers z tej grupy
        offers_products = [p for p in vg.products
                             if p.is_active and p.product_type_id == offers_type.id]

        result.append({
            'id': vg.id,
            'name': vg.name,
            'product_count': len(offers_products),
            'products': [{
                'id': p.id,
                'name': p.name,
                'sku': p.sku,
                'price': float(p.sale_price) if p.sale_price else 0,
                'image': url_for('static', filename=p.primary_image.path_compressed) if p.primary_image else None
            } for p in offers_products]
        })

    return jsonify(result)


# ============================================
# API - Pobieranie pojedynczej grupy wariantowej
# ============================================

@admin_bp.route('/offers/api/variant-group/<int:group_id>')
@login_required
@admin_required
def offers_api_variant_group(group_id):
    """Zwraca pojedynczą grupę wariantową z produktami odpowiedniego typu (AJAX)"""
    from sqlalchemy import and_

    page_type = request.args.get('page_type', 'exclusive')
    type_slug = 'exclusive' if page_type == 'exclusive' else 'pre-order'
    offers_type = ProductType.query.filter_by(slug=type_slug).first()
    if not offers_type:
        return jsonify({'error': 'Typ Offers nie istnieje'}), 404

    variant_group = VariantGroup.query.get(group_id)
    if not variant_group:
        return jsonify({'error': 'Grupa wariantowa nie istnieje'}), 404

    # Pobierz produkty Offers z tej grupy
    offers_products = [p for p in variant_group.products
                         if p.is_active and p.product_type_id == offers_type.id]

    return jsonify({
        'id': variant_group.id,
        'name': variant_group.name,
        'product_count': len(offers_products),
        'products': [{
            'id': p.id,
            'name': p.name,
            'sku': p.sku,
            'price': float(p.sale_price) if p.sale_price else 0,
            'image': url_for('static', filename=p.primary_image.path_compressed) if p.primary_image else None
        } for p in offers_products]
    })


# ============================================
# API - Upload obrazka seta
# ============================================

@admin_bp.route('/offers/api/upload-image', methods=['POST'])
@login_required
@admin_required
def offers_upload_image():
    """Upload obrazka dla seta lub innego elementu"""
    import os
    import uuid
    from flask import current_app

    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'Brak pliku'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Nie wybrano pliku'}), 400

    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''

    if file_ext not in allowed_extensions:
        return jsonify({'success': False, 'error': 'Niedozwolony typ pliku'}), 400

    unique_name = f"{uuid.uuid4().hex}.{file_ext}"
    relative_path = f'uploads/offers/{unique_name}'

    # ABSOLUTNA ścieżka do zapisu — uniezależnia od CWD gunicorna
    upload_folder = os.path.join(current_app.static_folder, 'uploads', 'offers')
    file_path = os.path.join(upload_folder, unique_name)

    try:
        os.makedirs(upload_folder, exist_ok=True)
        file.save(file_path)

        # WERYFIKACJA — czy plik faktycznie wylądował na dysku
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            current_app.logger.error(
                f"[OFFER UPLOAD] file.save() nie zapisało pliku: {file_path} "
                f"(user={current_user.id}, original={file.filename})"
            )
            return jsonify({
                'success': False,
                'error': 'Plik nie zapisał się na dysku — spróbuj ponownie'
            }), 500

        # Kompresja (best-effort — jeśli pęknie, zostawiamy oryginał)
        try:
            from utils.image_processor import compress_image
            compress_image(file_path, max_size=1600, quality=85)
        except Exception as compress_err:
            current_app.logger.warning(
                f"[OFFER UPLOAD] compress_image fail dla {relative_path}: {compress_err}"
            )

        # Druga weryfikacja — po kompresji plik nadal jest na miejscu
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            current_app.logger.error(
                f"[OFFER UPLOAD] plik zniknął/zerowy po kompresji: {file_path}"
            )
            return jsonify({
                'success': False,
                'error': 'Plik został uszkodzony podczas kompresji'
            }), 500

        current_app.logger.info(
            f"[OFFER UPLOAD] OK {relative_path} "
            f"({os.path.getsize(file_path)} bytes, user={current_user.id})"
        )

        return jsonify({
            'success': True,
            'path': relative_path,
            'url': url_for('static', filename=relative_path)
        })

    except Exception as e:
        # Sprzątanie po częściowo zapisanym pliku
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        current_app.logger.exception(
            f"[OFFER UPLOAD] wyjątek dla user={current_user.id}: {e}"
        )
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# Duplikowanie strony
# ============================================

@admin_bp.route('/offers/<int:page_id>/duplicate', methods=['POST'])
@login_required
@admin_required
def offers_duplicate(page_id):
    """Duplikuje stronę offers"""
    original = OfferPage.query.get_or_404(page_id)

    # Nowa strona
    new_page = OfferPage(
        name=f'{original.name} (kopia)',
        description=original.description,
        token=OfferPage.generate_token(),
        status='draft',
        page_type=original.page_type,
        footer_content=original.footer_content,
        payment_stages=original.payment_stages,
        created_by=current_user.id
    )
    db.session.add(new_page)
    db.session.flush()  # Aby uzyskać ID

    # Kopiuj sekcje
    for section in original.get_sections_ordered():
        new_section = OfferSection(
            offer_page_id=new_page.id,
            section_type=section.section_type,
            sort_order=section.sort_order,
            content=section.content,
            product_id=section.product_id,
            min_quantity=section.min_quantity,
            max_quantity=section.max_quantity,
            set_name=section.set_name,
            set_image=section.set_image,
            set_max_sets=section.set_max_sets,
            set_max_per_product=section.set_max_per_product,
            set_product_id=section.set_product_id,
            variant_group_id=section.variant_group_id
        )
        db.session.add(new_section)
        db.session.flush()

        # Kopiuj elementy setu
        if section.section_type == 'set':
            for item in section.get_set_items_ordered():
                new_item = OfferSetItem(
                    section_id=new_section.id,
                    product_id=item.product_id,
                    variant_group_id=item.variant_group_id,
                    quantity_per_set=item.quantity_per_set,
                    sort_order=item.sort_order
                )
                db.session.add(new_item)

            # Kopiuj bonusy (gratisy)
            for bonus in section.bonuses.order_by(OfferSetBonus.sort_order).all():
                new_bonus = OfferSetBonus(
                    section_id=new_section.id,
                    trigger_type=bonus.trigger_type,
                    threshold_value=bonus.threshold_value,
                    bonus_product_id=bonus.bonus_product_id,
                    bonus_quantity=bonus.bonus_quantity,
                    max_available=bonus.max_available,
                    when_exhausted=bonus.when_exhausted,
                    count_full_set=bonus.count_full_set,
                    repeatable=bonus.repeatable,
                    is_active=bonus.is_active,
                    sort_order=bonus.sort_order,
                )
                db.session.add(new_bonus)
                db.session.flush()

                # Kopiuj wymagane produkty
                for rp in bonus.required_products:
                    new_rp = OfferBonusRequiredProduct(
                        bonus_id=new_bonus.id,
                        product_id=rp.product_id,
                        min_quantity=rp.min_quantity,
                    )
                    db.session.add(new_rp)

    db.session.commit()

    flash(f'Strona została zduplikowana jako "{new_page.name}".', 'success')
    return redirect(url_for('admin.offers_edit', page_id=new_page.id))


# ============================================
# Całkowite zamknięcie strony Offers
# ============================================

@admin_bp.route('/offers/<int:page_id>/close-complete', methods=['POST'])
@login_required
@admin_required
def offers_close_complete(page_id):
    """
    Całkowicie zamyka stronę Offers.

    Wykonuje:
    1. Algorytm alokacji setów (pierwsi zamawiający dostają produkty)
    2. Ustawia flagę is_fully_closed
    3. Opcjonalnie wysyła emaile do klientów

    Tylko Admin może wykonać tę operację.
    """
    from utils.offer_closure import close_offer_page

    page = OfferPage.query.get_or_404(page_id)

    # Sprawdź warunki
    if page.status != 'ended':
        return jsonify({
            'success': False,
            'error': 'Strona musi mieć status "Zakończona" (ended) aby ją całkowicie zamknąć.'
        }), 400

    if page.is_fully_closed:
        return jsonify({
            'success': False,
            'error': 'Ta strona została już całkowicie zamknięta.'
        }), 400

    # Pobierz dane z request
    data = request.get_json() or {}
    payment_deadline_str = data.get('payment_deadline')

    # Walidacja deadline (wymagany)
    if not payment_deadline_str:
        return jsonify({
            'success': False,
            'error': 'Termin płatności jest wymagany.'
        }), 400

    from datetime import datetime
    try:
        payment_deadline = datetime.fromisoformat(payment_deadline_str)
    except (ValueError, TypeError):
        return jsonify({
            'success': False,
            'error': 'Nieprawidłowy format daty terminu płatności.'
        }), 400

    from modules.offers.models import get_local_now
    if payment_deadline <= get_local_now():
        return jsonify({
            'success': False,
            'error': 'Termin płatności musi być w przyszłości.'
        }), 400

    # Zapisz deadline na OfferPage
    page.payment_deadline = payment_deadline

    # Pre-order: uproszczone zamknięcie (bez kompletowania setów, bez maili)
    if page.page_type == 'preorder':
        from utils.activity_logger import log_activity
        page.is_fully_closed = True
        page.closed_at = get_local_now()
        page.closed_by_id = current_user.id
        db.session.commit()

        log_activity(
            user=current_user,
            action='offer_closed',
            entity_type='offer',
            entity_id=page.id,
            new_value=page.name,
        )

        return jsonify({
            'success': True,
            'message': 'Strona pre-order została zamknięta.',
            'redirect': url_for('admin.offers_list')
        })

    # Exclusive: full closure with set allocation
    # Pobierz opcję wysyłki emaili
    send_emails = data.get('send_emails', True)

    try:
        result = close_offer_page(
            page_id=page_id,
            user_id=current_user.id,
            send_emails=send_emails
        )

        return jsonify({
            'success': True,
            'message': 'Strona została całkowicie zamknięta.',
            'allocation': result.get('allocation'),
            'redirect': url_for('admin.offers_summary', page_id=page_id)
        })

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Wystąpił błąd: {str(e)}'
        }), 500


# ============================================
# Podsumowanie zamkniętej strony Offers
# ============================================

@admin_bp.route('/offers/<int:page_id>/live')
@login_required
@mod_required
def offers_live(page_id):
    """
    LIVE Dashboard — statystyki w czasie rzeczywistym dla aktywnych stron Offers.
    Dostępny gdy strona NIE jest is_fully_closed.
    """
    from utils.offer_closure import get_live_summary

    page = OfferPage.query.get_or_404(page_id)

    # Tylko dla niezamkniętych stron
    if page.is_fully_closed:
        flash('Ta strona jest już zamknięta. Użyj podsumowania.', 'info')
        return redirect(url_for('admin.offers_summary', page_id=page_id))

    include_financials = current_user.role == 'admin'
    summary = get_live_summary(page_id, include_financials=include_financials)

    # Serializacja zamówień do JSON
    orders_json_list = []
    for o in summary.get('orders', []):
        orders_json_list.append({
            'order_id': o['order_id'],
            'order_number': o['order_number'],
            'customer_name': o['customer_name'] or '-',
            'customer_email': o['customer_email'] or '',
            'customer_phone': o.get('customer_phone') or '',
            'created_at': o['created_at'].strftime('%d.%m.%Y %H:%M') if o['created_at'] else '',
            'total_amount': o['total_amount'],
            'item_count': sum(item['quantity'] for item in o['order_items']),
            'items': o['order_items'],
        })

    return render_template(
        'admin/offers/live_dashboard.html',
        title=f'LIVE: {page.name}',
        page=page,
        summary=summary,
        include_financials=include_financials,
        orders_json=json.dumps(orders_json_list, default=str),
    )


@admin_bp.route('/offers/<int:page_id>/summary')
@login_required
@mod_required
def offers_summary(page_id):
    """
    Wyświetla podsumowanie sprzedaży dla zamkniętej strony Offers.

    Admin widzi pełne dane finansowe, Mod widzi wersję bez finansów.
    """
    from utils.offer_closure import get_page_summary

    page = OfferPage.query.get_or_404(page_id)

    # Sprawdź czy strona jest zamknięta
    if not page.is_fully_closed:
        flash('Ta strona nie została jeszcze całkowicie zamknięta.', 'warning')
        return redirect(url_for('admin.offers_list'))

    # Pobierz podsumowanie (Admin z finansami, Mod bez)
    include_financials = current_user.role == 'admin'
    summary = get_page_summary(page_id, include_financials=include_financials)

    # Serializacja zamówień do JSON dla JS (search, pagination)
    import json
    orders_json_list = []
    for o in summary.get('orders', []):
        orders_json_list.append({
            'order_id': o['order_id'],
            'order_number': o['order_number'],
            'customer_name': o['customer_name'] or '-',
            'customer_email': o['customer_email'] or '',
            'customer_phone': o.get('customer_phone') or '',
            'created_at': o['created_at'].strftime('%d.%m.%Y %H:%M') if o['created_at'] else '',
            'total_amount': o['total_amount'],
            'item_count': sum(item['quantity'] for item in o['order_items']),
            'items': o['order_items'],
        })

    return render_template(
        'admin/offers/summary.html',
        title=f'Podsumowanie: {page.name}',
        page=page,
        summary=summary,
        include_financials=include_financials,
        orders_json=json.dumps(orders_json_list, default=str),
        sets_json=json.dumps(summary.get('sets', []), default=str),
    )


# ============================================
# Aktualizacja ustawień Offers Closure
# ============================================

@admin_bp.route('/offers/settings', methods=['POST'])
@login_required
@admin_required
def update_offers_closure_settings():
    """Update offers closure settings"""
    from modules.auth.models import Settings
    from utils.activity_logger import log_activity
    import json

    # Get form data
    fully_fulfilled = request.form.get('offers_closure_status_fully_fulfilled')
    partially_fulfilled = request.form.get('offers_closure_status_partially_fulfilled')
    not_fulfilled = request.form.get('offers_closure_status_not_fulfilled')

    # Validate
    if not all([fully_fulfilled, partially_fulfilled, not_fulfilled]):
        flash('Wszystkie statusy muszą być wybrane.', 'error')
        return redirect(url_for('admin.offers_settings'))

    # Helper function to set setting value
    def set_setting_value(key, value):
        setting = Settings.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = Settings(key=key, value=value, type='string')
            db.session.add(setting)

    # Update settings
    set_setting_value('offers_closure_status_fully_fulfilled', fully_fulfilled)
    set_setting_value('offers_closure_status_partially_fulfilled', partially_fulfilled)
    set_setting_value('offers_closure_status_not_fulfilled', not_fulfilled)
    db.session.commit()

    # Log activity
    log_activity(
        user=current_user,
        action='offers_closure_settings_updated',
        entity_type='offers_settings',
        entity_id=None,
        new_value=json.dumps({
            'fully_fulfilled': fully_fulfilled,
            'partially_fulfilled': partially_fulfilled,
            'not_fulfilled': not_fulfilled
        })
    )

    flash('Ustawienia automatycznego przenoszenia zostały zaktualizowane.', 'success')
    return redirect(url_for('admin.offers_settings'))


# ============================================
# Aktualizacja globalnych ustawień Auto-zwiększania max
# ============================================

@admin_bp.route('/offers/settings/auto-increase', methods=['POST'])
@login_required
@admin_required
def update_global_auto_increase_settings():
    """Update global auto-increase settings (stored in settings table)"""
    from utils.activity_logger import log_activity
    from modules.auth.models import Settings
    import json

    # Get form data
    auto_increase_enabled = request.form.get('auto_increase_enabled') == 'true'
    auto_increase_product_threshold = request.form.get('auto_increase_product_threshold', type=int)
    auto_increase_set_threshold = request.form.get('auto_increase_set_threshold', type=int)
    auto_increase_amount = request.form.get('auto_increase_amount', type=int)

    # Validate
    if auto_increase_product_threshold is None or auto_increase_product_threshold < 0 or auto_increase_product_threshold > 100:
        return jsonify({'success': False, 'error': 'Próg wyprzedania produktu musi być między 0 a 100'}), 400

    if auto_increase_set_threshold is None or auto_increase_set_threshold < 0 or auto_increase_set_threshold > 100:
        return jsonify({'success': False, 'error': 'Próg wyprzedanych produktów w secie musi być między 0 a 100'}), 400

    if auto_increase_amount is None or auto_increase_amount < 1:
        return jsonify({'success': False, 'error': 'Zwiększenie max musi być co najmniej 1'}), 400

    # Helper function to update or create setting
    def update_setting(key, value):
        setting = Settings.query.filter_by(key=key).first()
        if setting:
            setting.value = str(value)
        else:
            setting = Settings(key=key, value=str(value), type='string')
            db.session.add(setting)

    # Store old values for activity log
    def get_setting_value(key, default):
        setting = Settings.query.filter_by(key=key).first()
        return setting.value if setting else default

    old_values = {
        'enabled': get_setting_value('auto_increase_enabled', 'false') == 'true',
        'product_threshold': int(get_setting_value('auto_increase_product_threshold', '100')),
        'set_threshold': int(get_setting_value('auto_increase_set_threshold', '50')),
        'amount': int(get_setting_value('auto_increase_amount', '1'))
    }

    # Update settings in database
    update_setting('auto_increase_enabled', 'true' if auto_increase_enabled else 'false')
    update_setting('auto_increase_product_threshold', str(auto_increase_product_threshold))
    update_setting('auto_increase_set_threshold', str(auto_increase_set_threshold))
    update_setting('auto_increase_amount', str(auto_increase_amount))

    db.session.commit()

    # Log activity
    log_activity(
        user=current_user,
        action='global_auto_increase_settings_updated',
        entity_type='Settings',
        entity_id=None,
        old_value=json.dumps(old_values),
        new_value=json.dumps({
            'enabled': auto_increase_enabled,
            'product_threshold': auto_increase_product_threshold,
            'set_threshold': auto_increase_set_threshold,
            'amount': auto_increase_amount
        })
    )

    return jsonify({
        'success': True,
        'message': 'Ustawienia auto-zwiększania zostały zapisane.'
    })


# ============================================
# Payment Reminder Rules CRUD
# ============================================

@admin_bp.route('/offers/settings/payment-reminders/add', methods=['POST'])
@login_required
@admin_required
def add_payment_reminder_rule():
    """Dodaje nową regułę przypomnienia o płatności."""
    from modules.offers.reminder_models import PaymentReminderConfig
    from utils.activity_logger import log_activity
    import json

    data = request.get_json() or {}
    reminder_type = data.get('reminder_type')
    hours = data.get('hours')

    if reminder_type not in ('before_deadline', 'after_order_placed'):
        return jsonify({'success': False, 'error': 'Nieprawidłowy typ przypomnienia.'}), 400

    if not hours or not isinstance(hours, int) or hours < 1:
        return jsonify({'success': False, 'error': 'Liczba godzin musi być liczbą całkowitą >= 1.'}), 400

    existing = PaymentReminderConfig.query.filter_by(
        reminder_type=reminder_type, hours=hours, payment_stage='product', enabled=True
    ).first()
    if existing:
        return jsonify({'success': False, 'error': 'Taka reguła już istnieje.'}), 400

    rule = PaymentReminderConfig(
        reminder_type=reminder_type,
        hours=hours,
        payment_stage='product',
        enabled=True
    )
    db.session.add(rule)
    db.session.commit()

    log_activity(
        user=current_user,
        action='payment_reminder_rule_added',
        entity_type='payment_reminder_config',
        entity_id=rule.id,
        new_value=json.dumps({'type': reminder_type, 'hours': hours})
    )

    return jsonify({
        'success': True,
        'rule': {'id': rule.id, 'reminder_type': rule.reminder_type, 'hours': rule.hours}
    })


@admin_bp.route('/offers/settings/payment-reminders/delete', methods=['POST'])
@login_required
@admin_required
def delete_payment_reminder_rule():
    """Usuwa regułę przypomnienia o płatności."""
    from modules.offers.reminder_models import PaymentReminderConfig
    from utils.activity_logger import log_activity
    import json

    data = request.get_json() or {}
    rule_id = data.get('rule_id')

    if not rule_id:
        return jsonify({'success': False, 'error': 'Brak ID reguły.'}), 400

    rule = PaymentReminderConfig.query.get(rule_id)
    if not rule:
        return jsonify({'success': False, 'error': 'Reguła nie istnieje.'}), 404

    log_activity(
        user=current_user,
        action='payment_reminder_rule_deleted',
        entity_type='payment_reminder_config',
        entity_id=rule.id,
        old_value=json.dumps({'type': rule.reminder_type, 'hours': rule.hours})
    )

    db.session.delete(rule)
    db.session.commit()

    return jsonify({'success': True})


# ============================================
# Export Excel zamkniętej strony Offers
# ============================================

@admin_bp.route('/offers/<int:page_id>/live/export-excel')
@login_required
@admin_required
def offers_live_export_excel(page_id):
    """
    Generuje i pobiera plik Excel z danymi LIVE dla aktywnej strony Offers.
    Tylko Admin może pobrać Excel.
    """
    from utils.excel_export import generate_offer_live_excel
    from utils.offer_closure import get_live_summary

    page = OfferPage.query.get_or_404(page_id)

    try:
        summary = get_live_summary(page_id, include_financials=True)
        excel_buffer = generate_offer_live_excel(page, summary)

        safe_name = "".join(c for c in page.name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')[:50]
        filename = f'offers_LIVE_{safe_name}_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'

        return Response(
            excel_buffer.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f'Błąd generowania pliku Excel: {str(e)}', 'error')
        return redirect(url_for('admin.offers_live', page_id=page_id))


@admin_bp.route('/offers/<int:page_id>/export-excel')
@login_required
@admin_required
def offers_export_excel(page_id):
    """
    Generuje i pobiera plik Excel z zamówieniami dla zamkniętej strony Offers.

    Tylko Admin może pobrać Excel.
    """
    from utils.excel_export import generate_offer_closure_excel
    from utils.offer_closure import get_page_summary

    page = OfferPage.query.get_or_404(page_id)

    # Sprawdź czy strona jest zamknięta
    if not page.is_fully_closed:
        flash('Ta strona nie została jeszcze całkowicie zamknięta.', 'warning')
        return redirect(url_for('admin.offers_list'))

    try:
        summary = get_page_summary(page_id, include_financials=True)
        excel_buffer = generate_offer_closure_excel(page, summary)

        # Generuj nazwę pliku
        safe_name = "".join(c for c in page.name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')[:50]  # Max 50 znaków
        filename = f'offers_{safe_name}_{page.closed_at.strftime("%Y%m%d")}.xlsx'

        return Response(
            excel_buffer.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }
        )

    except Exception as e:
        flash(f'Błąd generowania pliku Excel: {str(e)}', 'error')
        return redirect(url_for('admin.offers_summary', page_id=page_id))


# ============================================
# Powiadomienia o zmianie daty zakończenia
# ============================================

def _resolve_end_date_change_recipients(page):
    """
    Rozwiązuje listy odbiorców powiadomień o zmianie daty zakończenia sprzedaży.

    E-mail (zgodnie z RODO):
        - Klienci z aktywnym (nieanulowanym) zamówieniem na tej stronie
          → mail transakcyjny (wykonanie umowy)
        - Klienci z marketing_consent=True
          → mail informacyjny
        - Wynik = unia obu zbiorów (po User.id, bez duplikatów)
        - Filtr bazowy: User.role='client', User.is_active=True

    Push:
        - Wszyscy aktywni klienci z włączoną kategorią sale_date_changes

    Returns:
        dict: {'email_users': [User, ...], 'push_user_ids': [int, ...]}
    """
    from modules.auth.models import User
    from modules.orders.models import Order
    from modules.notifications.models import NotificationPreference
    from sqlalchemy import or_

    # E-mail recipients
    buyer_ids_subq = (
        db.session.query(Order.user_id)
        .filter(
            Order.offer_page_id == page.id,
            Order.user_id.isnot(None),
            Order.status != 'anulowane',
        )
        .distinct()
        .subquery()
    )

    email_users = (
        User.query
        .filter(User.role == 'client', User.is_active == True)
        .filter(or_(
            User.marketing_consent == True,
            User.id.in_(buyer_ids_subq),
        ))
        .all()
    )

    # Push recipients
    push_users = (
        db.session.query(User.id)
        .join(NotificationPreference, NotificationPreference.user_id == User.id)
        .filter(
            User.role == 'client',
            User.is_active == True,
            NotificationPreference.sale_date_changes == True,
        )
        .all()
    )
    push_user_ids = [row[0] for row in push_users]

    return {
        'email_users': email_users,
        'push_user_ids': push_user_ids,
    }


def _dispatch_end_date_change_notifications(app, page_id, old_ends_at, new_ends_at,
                                             email_user_ids, push_user_ids):
    """
    Uruchamia wysyłki w background thread. Każdy kanał ma osłonę try/except,
    błąd jednego nie zatrzymuje drugiego.

    Args:
        app: Flask app instance (do app_context w threadzie)
        page_id (int): ID strony (re-load wewnątrz threadu, bo obiekty SA
                       z głównego requestu mogą być detached)
        old_ends_at: datetime lub None
        new_ends_at: datetime lub None
        email_user_ids: lista ID Userów do wysyłki e-mail (puste = pomiń kanał)
        push_user_ids: lista ID Userów do wysyłki push (puste = pomiń kanał)
    """
    import threading

    def _run():
        with app.app_context():
            try:
                from modules.auth.models import User
                page = OfferPage.query.get(page_id)
                if not page:
                    return

                if email_user_ids:
                    try:
                        from utils.email_manager import EmailManager
                        users = User.query.filter(User.id.in_(email_user_ids)).all()
                        EmailManager.notify_sale_end_date_changed(
                            page, old_ends_at, new_ends_at, users
                        )
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(
                            f"Email channel failed for end date change (page={page_id}): {e}"
                        )

                if push_user_ids:
                    try:
                        from utils.push_manager import PushManager
                        PushManager.notify_sale_end_date_changed(
                            page, new_ends_at, push_user_ids
                        )
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(
                            f"Push channel failed for end date change (page={page_id}): {e}"
                        )
            except Exception as e:
                from flask import current_app
                current_app.logger.error(
                    f"Dispatcher fatal error for end date change (page={page_id}): {e}"
                )

    thread = threading.Thread(target=_run)
    thread.daemon = True
    thread.start()
