import os
import secrets

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from extensions import db
from modules.auth.models import User
from modules.gift_cards import gift_cards_bp
from modules.gift_cards.emails import send_invites, send_results
from modules.gift_cards.export import build_distribution_excel
from modules.gift_cards.models import (
    KIND_GRATIS, KIND_PURCHASE,
    STATUS_APPROVED, STATUS_CLOSED, STATUS_DRAFT, STATUS_OPEN, STATUS_DISTRIBUTED, STATUS_FINISHED_MANUAL,
    GiftAssignment, GiftCampaign, GiftCampaignPage, GiftCampaignPool, GiftCardType, GiftParticipant,
    GiftPoolStock,
)
from modules.gift_cards.service import (
    GiftCardsError, _valid_ranking, can_revert, compute_entitlements, distribution_problems, pool_breakdown, queue_order,
    queue_position,
    approve, finish_manual, reopen_manual, revert_approval, run_distribution, swap_assignment, type_usage,
)
from modules.offers.models import OfferPage, OfferSection, OfferSetBonus
from modules.orders.models import Order, OrderItem
from modules.products.models import Product
from utils.decorators import role_required
from utils.timeutil import format_pl_input, parse_pl_input, to_pl, utcnow

STATUS_LABELS = {
    STATUS_DRAFT: 'Szkic',
    STATUS_OPEN: 'Otwarta',
    STATUS_CLOSED: 'Zamknięta',
    STATUS_DISTRIBUTED: 'Rozdzielona',
    STATUS_APPROVED: 'Zatwierdzona',
    STATUS_FINISHED_MANUAL: 'Zakończona (rozdział ręczny)',
}


def _get_campaign(cid):
    campaign = db.session.get(GiftCampaign, cid)
    if campaign is None:
        abort(404)
    return campaign


def _detail_redirect(cid):
    return redirect(url_for('gift_cards.admin_detail', cid=cid))


# --------------------------------------------------------------------------- #
# Lista                                                                       #
# --------------------------------------------------------------------------- #

@gift_cards_bp.route('/admin/rozdzial-gratisow')
@login_required
@role_required('admin', 'mod')
def admin_list():
    campaigns = GiftCampaign.query.order_by(GiftCampaign.created_at.desc(), GiftCampaign.id.desc()).all()
    items = [{'c': c, 'entitled': sum(e.total for e in compute_entitlements(c).values()),
              'status_label': STATUS_LABELS.get(c.status, c.status)}
             for c in campaigns]
    return render_template('admin/gift_cards/list.html', items=items)


# --------------------------------------------------------------------------- #
# Formularz                                                                   #
# --------------------------------------------------------------------------- #

def _delete_type_image(relative_path):
    """Usuwa grafikę rodzaju — wyłącznie plik leżący wewnątrz static/uploads/gift_cards."""
    if not relative_path:
        return
    base = os.path.realpath(os.path.join(current_app.root_path, 'static', 'uploads', 'gift_cards'))
    path = os.path.realpath(os.path.join(current_app.root_path, 'static', relative_path.replace('\\', '/')))
    if os.path.commonpath([base, path]) != base or path == base:
        return
    try:
        if os.path.isfile(path):
            os.remove(path)
    except Exception as exc:
        current_app.logger.warning('[gift_cards] nie usunięto %s: %s', path, exc)


def _save_type_image(file):
    """Zapisuje grafikę rodzaju karty (jak Contest.image_path). Zwraca ścieżkę względem static/ albo None."""
    from utils.image_processor import allowed_file, compress_image
    from PIL import Image, ImageOps
    import shutil

    if not file or not file.filename or not allowed_file(file.filename):
        return None
    ext = file.filename.rsplit('.', 1)[1].lower()
    fname = secrets.token_urlsafe(16) + '.' + ext
    static_dir = os.path.join(current_app.root_path, 'static')
    orig_dir = os.path.join(static_dir, 'uploads', 'gift_cards', 'original')
    comp_dir = os.path.join(static_dir, 'uploads', 'gift_cards', 'compressed')
    os.makedirs(orig_dir, exist_ok=True)
    os.makedirs(comp_dir, exist_ok=True)
    orig_path = os.path.join(orig_dir, fname)
    comp_path = os.path.join(comp_dir, fname)
    try:
        file.save(orig_path)
        img = ImageOps.exif_transpose(Image.open(orig_path))
        img.save(orig_path)
        shutil.copy2(orig_path, comp_path)
        compress_image(comp_path)
        return os.path.join('uploads', 'gift_cards', 'compressed', fname)
    except Exception as exc:
        current_app.logger.warning('[gift_cards] błąd uploadu: %s', exc)
        for path in (orig_path, comp_path):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        flash('Nie udało się zapisać grafiki karty — spróbuj ponownie lub wybierz inny plik.', 'error')
        return None


def _bonus_products():
    """Produkty do wyboru jako gratis akcji.

    Ustawione jako gratis na stronach ofert ORAZ te, które kiedykolwiek trafiły do zamówień
    jako gratis (dodane ręcznie albo ze starszych ofert) — uprawnienia i tak liczymy
    z gratisowych pozycji zamówień, więc lista musi je obejmować.
    """
    from_offers = (db.session.query(OfferSetBonus.bonus_product_id)
                   .filter(OfferSetBonus.bonus_product_id.isnot(None)))
    from_orders = (db.session.query(OrderItem.product_id)
                   .filter(OrderItem.is_bonus.is_(True), OrderItem.product_id.isnot(None)))
    return (Product.query
            .filter(or_(Product.id.in_(from_offers), Product.id.in_(from_orders)))
            .order_by(Product.name).all())


def _purchase_products(keep_ids=()):
    """Produkty do wyboru w akcji „kupione produkty”: kupione (zwykłe pozycje) w zamówieniach ze stron ofert.

    `keep_ids` — już wybrane produkty zostają na liście, nawet gdy nikt ich jeszcze nie kupił.
    """
    bought = (db.session.query(OrderItem.product_id)
              .join(Order, Order.id == OrderItem.order_id)
              .filter(OrderItem.is_bonus.is_(False), OrderItem.product_id.isnot(None),
                      Order.offer_page_id.isnot(None)))
    conditions = [Product.id.in_(bought)]
    if keep_ids:
        conditions.append(Product.id.in_(list(keep_ids)))
    return Product.query.filter(or_(*conditions)).order_by(Product.name).all()


def _read_form(campaign=None):
    """Odczyt pól formularza do słownika; błędy trafiają do listy errors.

    `type_existing_image` przyjmujemy tylko, gdy to grafika obecnego rodzaju tej akcji —
    inna wartość z formularza jest ignorowana (nie wolno wskazać dowolnego pliku).
    """
    errors = []
    kind = request.form.get('kind')
    if kind not in (KIND_GRATIS, KIND_PURCHASE):
        kind = KIND_GRATIS
    name = (request.form.get('name') or '').strip()
    if not name:
        errors.append('Podaj nazwę akcji.')

    race_at = None
    raw_race = (request.form.get('race_at') or '').strip()
    if raw_race:
        try:
            race_at = parse_pl_input(raw_race)
        except ValueError:
            errors.append('Niepoprawna data i godzina startu zgłoszeń.')

    page_ids = []
    for raw in request.form.getlist('offer_page_ids'):
        if raw.isdigit() and int(raw) not in page_ids and db.session.get(OfferPage, int(raw)):
            page_ids.append(int(raw))

    bonus_ids = []
    for raw in request.form.getlist('bonus_product_ids'):
        if raw.isdigit() and int(raw) not in bonus_ids and db.session.get(Product, int(raw)):
            bonus_ids.append(int(raw))

    names = [n.strip() for n in request.form.getlist('type_name')]
    allowed_images = {t.image_path for t in campaign.card_types if t.image_path} if campaign else set()
    existing = [v if v in allowed_images else '' for v in request.form.getlist('type_existing_image')]
    files = request.files.getlist('type_image')
    # Ilości: osobna lista pól na każdy wybrany gratis (pulę), wyrównana z wierszami rodzajów.
    raw_quantities = {pid: [q.strip() for q in request.form.getlist(f'type_quantity_{pid}')]
                      for pid in bonus_ids}
    rows = []
    for i, type_name in enumerate(names):
        if not type_name:
            continue
        quantities, raws = {}, {}
        for pid in bonus_ids:
            raw_qty = raw_quantities[pid][i] if i < len(raw_quantities[pid]) else ''
            raws[pid] = raw_qty
            quantities[pid] = None
            if raw_qty:
                if raw_qty.isdigit():
                    quantities[pid] = int(raw_qty)
                else:
                    errors.append(f'Ilość dla „{type_name}” musi być liczbą całkowitą od 0 (albo zostaw puste).')
        rows.append({
            'name': type_name,
            'existing_image': existing[i] if i < len(existing) else '',
            'file': files[i] if i < len(files) else None,
            'quantities': quantities,
            'raw_quantities': raws,
        })
    return {'kind': kind, 'name': name, 'race_at': race_at, 'raw_race': raw_race, 'page_ids': page_ids,
            'bonus_ids': bonus_ids, 'rows': rows, 'errors': errors}


def _pages_with_gratis(keep_ids=()):
    """Strony ofert, które mają gratis: ustawiony w secie albo dany w zamówieniach z tej strony.

    `keep_ids` — strony już wybrane w akcji zostają na liście, nawet gdy gratisu nie mają,
    żeby edycja nie gubiła ich po cichu.
    """
    from_sets = (db.session.query(OfferSection.offer_page_id)
                 .join(OfferSetBonus, OfferSetBonus.section_id == OfferSection.id)
                 .filter(OfferSetBonus.bonus_product_id.isnot(None)))
    from_orders = (db.session.query(Order.offer_page_id)
                   .join(OrderItem, OrderItem.order_id == Order.id)
                   .filter(OrderItem.is_bonus.is_(True), Order.offer_page_id.isnot(None)))
    conditions = [OfferPage.id.in_(from_sets), OfferPage.id.in_(from_orders)]
    if keep_ids:
        conditions.append(OfferPage.id.in_(list(keep_ids)))
    return OfferPage.query.filter(or_(*conditions)).order_by(OfferPage.created_at.desc()).all()


def _sync_pools(campaign, bonus_ids):
    """Pule akcji = wybrane gratisy, w tej kolejności; istniejące pule zostają (z ich ilościami)."""
    existing = {pool.bonus_product_id: pool for pool in campaign.pools}
    pools = []
    for order, pid in enumerate(bonus_ids):
        pool = existing.get(pid) or GiftCampaignPool(bonus_product_id=pid)
        pool.sort_order = order
        pools.append(pool)
    campaign.pools = pools


def _render_form(campaign, data=None):
    if data is None:
        data = {
            'kind': campaign.kind if campaign else KIND_GRATIS,
            'name': campaign.name if campaign else '',
            'raw_race': format_pl_input(campaign.race_at) if campaign and campaign.race_at else '',
            'page_ids': campaign.offer_page_ids if campaign else [],
            'bonus_ids': campaign.bonus_product_ids if campaign else [],
            'rows': [],
        }
        if campaign:
            stock = campaign.stock_map()
            for t in campaign.card_types:
                raws = {}
                for pool in campaign.pools:
                    if pool.bonus_product_id is not None:
                        q = stock.get((pool.id, t.id))
                        raws[pool.bonus_product_id] = '' if q is None else str(q)
                data['rows'].append({'name': t.name, 'existing_image': t.image_path or '',
                                     'raw_quantities': raws})
    locked = bool(campaign and campaign.status != STATUS_DRAFT)
    kind = data['kind']
    if locked:  # po publikacji rodzaj się nie zmienia — pokazujemy ten zapisany
        kind = campaign.kind
    keep = set(data['page_ids']) | (set(campaign.offer_page_ids) if campaign else set())
    # Dwa zestawy list (gratisy / kupione produkty); formularz pokazuje zestaw wybranego rodzaju.
    gratis_pages = _pages_with_gratis(keep if kind == KIND_GRATIS else ())
    gratis_products = _bonus_products()
    purchase_pages = OfferPage.query.order_by(OfferPage.created_at.desc()).all()
    purchase_products = _purchase_products(data['bonus_ids'] if kind == KIND_PURCHASE else ())
    if kind == KIND_GRATIS:
        by_id = {p.id: p for p in gratis_products}
        for pid in data['bonus_ids']:  # wybrany gratis zostaje na liście, nawet gdy zniknął z ofert
            if pid not in by_id:
                product = db.session.get(Product, pid)
                if product:
                    by_id[pid] = product
                    gratis_products.append(product)
    else:
        by_id = {p.id: p for p in purchase_products}
    selected = [by_id[pid] for pid in data['bonus_ids'] if pid in by_id]
    return render_template('admin/gift_cards/form.html', campaign=campaign, data=data, kind=kind,
                           kinds=[
                               {'value': KIND_GRATIS, 'label': 'Gratisy', 'pages': gratis_pages,
                                'products': gratis_products},
                               {'value': KIND_PURCHASE, 'label': 'Kupione produkty', 'pages': purchase_pages,
                                'products': purchase_products},
                           ],
                           selected_products=selected, locked=locked)


@gift_cards_bp.route('/admin/rozdzial-gratisow/nowa', methods=['GET', 'POST'])
@gift_cards_bp.route('/admin/rozdzial-gratisow/<int:cid>/edytuj', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def admin_form(cid=None):
    campaign = _get_campaign(cid) if cid else None
    if campaign and campaign.status == STATUS_APPROVED:
        flash('Zatwierdzonej akcji nie można edytować — najpierw cofnij zatwierdzenie.', 'error')
        return _detail_redirect(campaign.id)
    if request.method == 'GET':
        return _render_form(campaign)

    data = _read_form(campaign)
    editing_structure = campaign is None or campaign.status == STATUS_DRAFT
    if editing_structure:
        if not data['page_ids']:
            data['errors'].append('Wybierz co najmniej jedną stronę ofert.')
        if not data['bonus_ids']:
            data['errors'].append('Wybierz co najmniej jeden produkt-gratis.' if data['kind'] == KIND_GRATIS
                                  else 'Wybierz co najmniej jeden kupiony produkt.')
        if not data['rows']:
            data['errors'].append('Dodaj co najmniej jeden rodzaj karty.')
    if data['errors']:
        for message in data['errors']:
            flash(message, 'error')
        return _render_form(campaign, data)

    if campaign is None:
        campaign = GiftCampaign(status=STATUS_DRAFT, created_by_admin_id=current_user.id)
        db.session.add(campaign)
    campaign.name = data['name']
    campaign.race_at = data['race_at']
    if editing_structure:
        campaign.kind = data['kind']
        _sync_pools(campaign, data['bonus_ids'])
        wanted = set(data['page_ids'])
        for page_row in list(campaign.pages):
            if page_row.offer_page_id not in wanted:
                campaign.pages.remove(page_row)
        have = {p.offer_page_id for p in campaign.pages}
        for pid in data['page_ids']:
            if pid not in have:
                campaign.pages.append(GiftCampaignPage(offer_page_id=pid))
        kept = {row['existing_image'] for row in data['rows'] if row['existing_image']}
        for old in campaign.card_types:
            if old.image_path and old.image_path not in kept:
                _delete_type_image(old.image_path)
        for pool in campaign.pools:
            pool.stock = []
        new_types = []
        pools_by_product = {pool.bonus_product_id: pool for pool in campaign.pools}
        for order, row in enumerate(data['rows']):
            image = _save_type_image(row['file']) or row['existing_image'] or None
            card_type = GiftCardType(name=row['name'], image_path=image, sort_order=order)
            for pid, quantity in row['quantities'].items():
                GiftPoolStock(pool=pools_by_product[pid], card_type=card_type, quantity=quantity)
            new_types.append(card_type)
        campaign.card_types = new_types
    db.session.commit()
    flash('Zapisano akcję.', 'success')
    return _detail_redirect(campaign.id)


# --------------------------------------------------------------------------- #
# Szczegóły                                                                   #
# --------------------------------------------------------------------------- #

@gift_cards_bp.route('/admin/rozdzial-gratisow/<int:cid>')
@login_required
@role_required('admin', 'mod')
def admin_detail(cid):
    campaign = _get_campaign(cid)
    rows, entitlements, assignments, has_assignments = _detail_rows(campaign)

    entitled_total = sum(e.total for e in entitlements.values())
    stock = campaign.stock_map()
    quantities = [stock.get((pool.id, t.id)) for pool in campaign.pools for t in campaign.card_types]
    available = sum(quantities) if quantities and all(isinstance(q, int) for q in quantities) else None
    duplicates = sum(1 for lst in assignments.values() for a in lst if a.is_duplicate)
    revert_ok = can_revert(campaign) if campaign.status == STATUS_APPROVED else True
    usage = _usage(campaign) if has_assignments else []
    return render_template(
        'admin/gift_cards/detail.html', campaign=campaign, rows=rows, has_assignments=has_assignments,
        entitled_total=entitled_total, available=available, duplicates=duplicates,
        revert_ok=revert_ok, status_label=STATUS_LABELS.get(campaign.status, campaign.status),
        quantities_editable=campaign.status in (STATUS_CLOSED, STATUS_DISTRIBUTED),
        problems=distribution_problems(campaign), usage=usage, stock=stock,
        several_pools=len(campaign.pools) > 1,
    )


@gift_cards_bp.route('/admin/rozdzial-gratisow/<int:cid>/excel')
@login_required
@role_required('admin', 'mod')
def admin_excel(cid):
    campaign = _get_campaign(cid)
    if campaign.status == STATUS_DRAFT:
        flash('Plik Excel będzie dostępny po opublikowaniu akcji.', 'error')
        return _detail_redirect(cid)
    rows, _, _, has_assignments = _detail_rows(campaign)
    buffer = build_distribution_excel(campaign, rows, _usage(campaign) if has_assignments else [],
                                      STATUS_LABELS.get(campaign.status, campaign.status))
    safe = ''.join(ch for ch in campaign.name if ch.isalnum() or ch in ' -_').strip().replace(' ', '_')[:50]
    prefix = 'karty' if campaign.is_purchase else 'gratisy'
    filename = f'{prefix}_{safe or campaign.id}_{to_pl(utcnow()).strftime("%Y%m%d")}.xlsx'
    return send_file(buffer, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def _usage(campaign):
    """[{'pool', 'items': [{'type', 'assigned', 'quantity', 'over'}]}] — w kolejności pul i rodzajów."""
    grouped = {}
    for pool, t, assigned, quantity in type_usage(campaign):
        grouped.setdefault(pool.id, {'pool': pool, 'items': []})['items'].append(
            {'type': t, 'assigned': assigned, 'quantity': quantity, 'over': max(assigned - quantity, 0)})
    return list(grouped.values())


def _detail_rows(campaign):
    """Wiersze tabeli „Uprawnieni” — wspólne dla strony szczegółów i pliku Excel."""
    entitlements = compute_entitlements(campaign)
    assignments = {}
    for a in (GiftAssignment.query.filter_by(campaign_id=campaign.id)
              .order_by(GiftAssignment.round_no, GiftAssignment.id).all()):
        assignments.setdefault(a.user_id, []).append(a)
    # Wiersze z uprawnionych ORAZ z przydziałów — osoba, która straciła uprawnienie po rozdziale
    # (np. anulowane zamówienie), nadal widnieje w tabeli razem ze swoimi kartami.
    order = queue_order(campaign, entitlements)
    orphans = sorted(uid for uid in assignments if uid not in entitlements)
    uids = order + orphans
    users = {u.id: u for u in User.query.filter(User.id.in_(uids)).all()} if uids else {}
    participants = {p.user_id: p for p in
                    GiftParticipant.query.filter_by(campaign_id=campaign.id).all()}

    has_assignments = campaign.status in (STATUS_DISTRIBUTED, STATUS_APPROVED)
    type_ids = [t.id for t in campaign.card_types]
    type_names = {t.id: t.name for t in campaign.card_types}
    rows = []
    pool_order = {pool.id: i for i, pool in enumerate(campaign.pools)}
    for index, uid in enumerate(uids, start=1):
        participant = participants.get(uid)
        cards = sorted(assignments.get(uid, []), key=lambda a: (pool_order.get(a.pool_id, 0), a.round_no, a.id))
        total = entitlements[uid].total if uid in entitlements else 0
        rows.append({
            'place': index if uid in entitlements else None,
            'user': users.get(uid),
            'total': total,
            'entitled': uid in entitlements,
            'race_position': queue_position(campaign, uid),
            'has_ranking': bool(participant and participant.ranking),
            'cards': cards,
            'missing': max(total - len(cards), 0) if has_assignments else 0,
            'breakdown': pool_breakdown(campaign, entitlements.get(uid)),
            'notes': (participant.notes or '').strip() if participant else '',
            'ranking_text': ', '.join(f'{i}. {type_names[tid]}' for i, tid in
                                      enumerate(_valid_ranking(participant, type_ids), start=1)),
        })
    return rows, entitlements, assignments, has_assignments


# --------------------------------------------------------------------------- #
# Akcje                                                                       #
# --------------------------------------------------------------------------- #

@gift_cards_bp.route('/admin/rozdzial-gratisow/<int:cid>/publikuj', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_publish(cid):
    campaign = _get_campaign(cid)
    if campaign.status != STATUS_DRAFT:
        flash('Akcja została już opublikowana.', 'error')
        return _detail_redirect(cid)
    if not campaign.card_types or not campaign.pages or not campaign.pools:
        flash('Uzupełnij strony ofert, produkt-gratis i rodzaje kart przed publikacją.', 'error')
        return _detail_redirect(cid)
    if campaign.race_at is None:
        flash('Ustaw datę i godzinę startu zgłoszeń przed publikacją.', 'error')
        return _detail_redirect(cid)
    # Warunkowa zmiana statusu: przy dwóch równoczesnych kliknięciach maile wyjdą tylko raz.
    changed = (GiftCampaign.query.filter_by(id=cid, status=STATUS_DRAFT)
               .update({'status': STATUS_OPEN}, synchronize_session=False))
    db.session.commit()
    if changed != 1:
        flash('Akcja została już opublikowana.', 'error')
        return _detail_redirect(cid)
    sent = send_invites(campaign)
    flash(f'Wysłano {sent} zaproszeń.', 'success')
    return _detail_redirect(cid)


@gift_cards_bp.route('/admin/rozdzial-gratisow/<int:cid>/zamknij', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_close(cid):
    campaign = _get_campaign(cid)
    if campaign.status != STATUS_OPEN:
        flash('Zgłoszenia można zamknąć tylko w otwartej akcji.', 'error')
        return _detail_redirect(cid)
    campaign.status = STATUS_CLOSED
    db.session.commit()
    flash('Zgłoszenia zamknięte.', 'success')
    return _detail_redirect(cid)


@gift_cards_bp.route('/admin/rozdzial-gratisow/<int:cid>/ilosci', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_quantities(cid):
    campaign = _get_campaign(cid)
    if campaign.status not in (STATUS_CLOSED, STATUS_DISTRIBUTED):
        flash('Ilości można wpisać po zamknięciu zgłoszeń, przed zatwierdzeniem.', 'error')
        return _detail_redirect(cid)
    several = len(campaign.pools) > 1
    values = {}
    for pool in campaign.pools:
        for card_type in campaign.card_types:
            raw = (request.form.get(f'quantity_{pool.id}_{card_type.id}') or '').strip()
            if not raw.isdigit():
                label = f'{card_type.name} ({pool.label})' if several else card_type.name
                flash(f'Podaj ilość (liczbę całkowitą, od 0) dla: {label}.', 'error')
                return _detail_redirect(cid)
            values[(pool.id, card_type.id)] = int(raw)
    rows = {(s.pool_id, s.card_type_id): s for pool in campaign.pools for s in pool.stock}
    for pool in campaign.pools:
        for card_type in campaign.card_types:
            row = rows.get((pool.id, card_type.id))
            if row is None:
                row = GiftPoolStock(pool=pool, card_type=card_type)
                db.session.add(row)  # SQLAlchemy 2: backref nie dodaje obiektu do sesji sam
            row.quantity = values[(pool.id, card_type.id)]
    db.session.commit()
    flash('Zapisano ilości kart.', 'success')
    return _detail_redirect(cid)


@gift_cards_bp.route('/admin/rozdzial-gratisow/<int:cid>/rozdziel', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_distribute(cid):
    campaign = _get_campaign(cid)
    try:
        run_distribution(campaign)
    except GiftCardsError as exc:
        flash(str(exc), 'error')
        return _detail_redirect(cid)
    flash('Karty rozdzielone. Sprawdź przydział i zatwierdź.', 'success')
    return _detail_redirect(cid)


@gift_cards_bp.route('/admin/rozdzial-gratisow/<int:cid>/zamien', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_swap(cid):
    _get_campaign(cid)
    payload = request.get_json(silent=True) or {}
    assignment_id, type_id = payload.get('assignment_id'), payload.get('type_id')
    if not isinstance(assignment_id, int) or not isinstance(type_id, int):
        return jsonify({'success': False, 'error': 'Niepoprawne dane zamiany.'}), 400
    assignment = db.session.get(GiftAssignment, assignment_id)
    if assignment is None or assignment.campaign_id != cid:
        return jsonify({'success': False, 'error': 'Nie znaleziono przydziału.'}), 404
    try:
        swap_assignment(assignment_id, type_id)
    except GiftCardsError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(exc)}), 400
    return jsonify({'success': True})


@gift_cards_bp.route('/admin/rozdzial-gratisow/<int:cid>/zatwierdz', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_approve(cid):
    campaign = _get_campaign(cid)
    silent = request.form.get('bez_maili') == '1'
    try:
        approve(campaign, hide_results=silent)
    except GiftCardsError as exc:
        flash(str(exc), 'error')
        return _detail_redirect(cid)
    if silent:
        flash('Zatwierdzono bez maili. Klientki nie widzą przydziału.', 'success')
        return _detail_redirect(cid)
    sent = send_results(campaign)
    flash(f'Zatwierdzono. Wysłano {sent} maili z wynikiem.', 'success')
    return _detail_redirect(cid)


@gift_cards_bp.route('/admin/rozdzial-gratisow/<int:cid>/zakoncz', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_finish(cid):
    campaign = _get_campaign(cid)
    try:
        finish_manual(campaign)
    except GiftCardsError as exc:
        flash(str(exc), 'error')
        return _detail_redirect(cid)
    flash('Akcja zakończona bez rozdziału. Odpowiedzi klientek są w pliku Excel.', 'success')
    return _detail_redirect(cid)


@gift_cards_bp.route('/admin/rozdzial-gratisow/<int:cid>/wznow', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_reopen(cid):
    campaign = _get_campaign(cid)
    try:
        reopen_manual(campaign)
    except GiftCardsError as exc:
        flash(str(exc), 'error')
        return _detail_redirect(cid)
    flash('Cofnięto zakończenie — akcja znów ma zamknięte zgłoszenia.', 'success')
    return _detail_redirect(cid)


@gift_cards_bp.route('/admin/rozdzial-gratisow/<int:cid>/cofnij', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_revert(cid):
    campaign = _get_campaign(cid)
    try:
        revert_approval(campaign)
    except GiftCardsError as exc:
        flash(str(exc), 'error')
        return _detail_redirect(cid)
    flash('Cofnięto zatwierdzenie.', 'success')
    return _detail_redirect(cid)
