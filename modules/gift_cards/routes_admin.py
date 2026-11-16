import os
import secrets

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from modules.auth.models import User
from modules.gift_cards import gift_cards_bp
from modules.gift_cards.emails import send_invites, send_results
from modules.gift_cards.models import (
    STATUS_APPROVED, STATUS_CLOSED, STATUS_DRAFT, STATUS_OPEN, STATUS_DISTRIBUTED,
    GiftAssignment, GiftCampaign, GiftCampaignPage, GiftCardType, GiftParticipant,
)
from modules.gift_cards.service import (
    GiftCardsError, can_revert, compute_entitlements, distribution_problems, queue_order, queue_position,
    approve, revert_approval, run_distribution, swap_assignment, type_usage,
)
from modules.offers.models import OfferPage, OfferSetBonus
from modules.products.models import Product
from utils.decorators import role_required
from utils.timeutil import format_pl_input, parse_pl_input

STATUS_LABELS = {
    STATUS_DRAFT: 'Szkic',
    STATUS_OPEN: 'Otwarta',
    STATUS_CLOSED: 'Zamknięta',
    STATUS_DISTRIBUTED: 'Rozdzielona',
    STATUS_APPROVED: 'Zatwierdzona',
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
    return (Product.query
            .filter(Product.id.in_(db.session.query(OfferSetBonus.bonus_product_id)
                                   .filter(OfferSetBonus.bonus_product_id.isnot(None))))
            .order_by(Product.name).all())


def _read_form(campaign=None):
    """Odczyt pól formularza do słownika; błędy trafiają do listy errors.

    `type_existing_image` przyjmujemy tylko, gdy to grafika obecnego rodzaju tej akcji —
    inna wartość z formularza jest ignorowana (nie wolno wskazać dowolnego pliku).
    """
    errors = []
    name = (request.form.get('name') or '').strip()
    if not name:
        errors.append('Podaj nazwę akcji.')

    race_at = None
    raw_race = (request.form.get('race_at') or '').strip()
    if raw_race:
        try:
            race_at = parse_pl_input(raw_race)
        except ValueError:
            errors.append('Niepoprawna data i godzina wyścigu.')

    page_ids = []
    for raw in request.form.getlist('offer_page_ids'):
        if raw.isdigit() and int(raw) not in page_ids and db.session.get(OfferPage, int(raw)):
            page_ids.append(int(raw))

    bonus_id = request.form.get('bonus_product_id', type=int)
    if bonus_id is not None and db.session.get(Product, bonus_id) is None:
        bonus_id = None

    names = [n.strip() for n in request.form.getlist('type_name')]
    allowed_images = {t.image_path for t in campaign.card_types if t.image_path} if campaign else set()
    existing = [v if v in allowed_images else '' for v in request.form.getlist('type_existing_image')]
    files = request.files.getlist('type_image')
    rows = []
    for i, type_name in enumerate(names):
        if not type_name:
            continue
        rows.append({
            'name': type_name,
            'existing_image': existing[i] if i < len(existing) else '',
            'file': files[i] if i < len(files) else None,
        })
    return {'name': name, 'race_at': race_at, 'raw_race': raw_race, 'page_ids': page_ids,
            'bonus_id': bonus_id, 'rows': rows, 'errors': errors}


def _render_form(campaign, data=None):
    pages = OfferPage.query.order_by(OfferPage.created_at.desc()).all()
    if data is None:
        data = {
            'name': campaign.name if campaign else '',
            'raw_race': format_pl_input(campaign.race_at) if campaign and campaign.race_at else '',
            'page_ids': campaign.offer_page_ids if campaign else [],
            'bonus_id': campaign.bonus_product_id if campaign else None,
            'rows': [{'name': t.name, 'existing_image': t.image_path or ''}
                     for t in campaign.card_types] if campaign else [],
        }
    return render_template('admin/gift_cards/form.html', campaign=campaign, data=data, pages=pages,
                           products=_bonus_products(),
                           locked=bool(campaign and campaign.status != STATUS_DRAFT))


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
        if data['bonus_id'] is None:
            data['errors'].append('Wybierz produkt-gratis.')
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
        campaign.bonus_product_id = data['bonus_id']
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
        new_types = []
        for order, row in enumerate(data['rows']):
            image = _save_type_image(row['file']) or row['existing_image'] or None
            new_types.append(GiftCardType(name=row['name'], image_path=image, sort_order=order))
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
    rows = []
    for index, uid in enumerate(uids, start=1):
        participant = participants.get(uid)
        cards = assignments.get(uid, [])
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
        })

    entitled_total = sum(e.total for e in entitlements.values())
    quantities = [t.quantity for t in campaign.card_types]
    available = sum(q for q in quantities if isinstance(q, int)) if all(isinstance(q, int) for q in quantities) and quantities else None
    duplicates = sum(1 for lst in assignments.values() for a in lst if a.is_duplicate)
    revert_ok = can_revert(campaign) if campaign.status == STATUS_APPROVED else True
    usage = ([{'type': t, 'assigned': assigned, 'quantity': quantity, 'over': max(assigned - quantity, 0)}
              for t, assigned, quantity in type_usage(campaign)] if has_assignments else [])
    return render_template(
        'admin/gift_cards/detail.html', campaign=campaign, rows=rows, has_assignments=has_assignments,
        entitled_total=entitled_total, available=available, duplicates=duplicates,
        revert_ok=revert_ok, status_label=STATUS_LABELS.get(campaign.status, campaign.status),
        quantities_editable=campaign.status in (STATUS_CLOSED, STATUS_DISTRIBUTED),
        problems=distribution_problems(campaign), usage=usage,
    )


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
    if not campaign.card_types or not campaign.pages or campaign.bonus_product_id is None:
        flash('Uzupełnij strony ofert, produkt-gratis i rodzaje kart przed publikacją.', 'error')
        return _detail_redirect(cid)
    if campaign.race_at is None:
        flash('Ustaw datę i godzinę wyścigu przed publikacją.', 'error')
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
    values = {}
    for card_type in campaign.card_types:
        raw = (request.form.get(f'quantity_{card_type.id}') or '').strip()
        if not raw.isdigit():
            flash(f'Podaj ilość (liczbę całkowitą, od 0) dla: {card_type.name}.', 'error')
            return _detail_redirect(cid)
        values[card_type.id] = int(raw)
    for card_type in campaign.card_types:
        card_type.quantity = values[card_type.id]
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
    try:
        approve(campaign)
    except GiftCardsError as exc:
        flash(str(exc), 'error')
        return _detail_redirect(cid)
    sent = send_results(campaign)
    flash(f'Zatwierdzono. Wysłano {sent} maili z wynikiem.', 'success')
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
