import json

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from extensions import db
from modules.gift_cards.emails import pl_cards
from modules.gift_cards.models import (
    GiftAssignment, GiftCampaign, GiftParticipant, GiftRaceEntry,
    STATUS_APPROVED, STATUS_DRAFT, STATUS_OPEN,
)
from modules.gift_cards.service import _valid_ranking, compute_entitlements, pool_breakdown, queue_position
from utils.timeutil import iso_utc, to_pl, utcnow

from . import gift_cards_bp  # noqa: F401

NOTES_MAX = 1000


def _entitled_total(campaign):
    """Ile kart przysługuje zalogowanemu klientowi (0 = akcja go nie dotyczy)."""
    if campaign.status == STATUS_DRAFT:
        return 0
    ent = compute_entitlements(campaign).get(current_user.id)
    return ent.total if ent else 0


def _ranking_error(message, campaign):
    flash(message, 'error')
    return client_campaign(campaign.id), 400


@gift_cards_bp.route('/gratisy/<int:cid>')
@login_required
def client_campaign(cid):
    campaign = db.get_or_404(GiftCampaign, cid)
    total = _entitled_total(campaign)
    if total == 0:
        return render_template('client/gift_cards/campaign.html', campaign=None, page_title='Gratisowe karty')

    types = list(campaign.card_types)
    participant = GiftParticipant.query.filter_by(campaign_id=cid, user_id=current_user.id).first()
    ranking = list(_valid_ranking(participant, [t.id for t in types]))
    position = {tid: i + 1 for i, tid in enumerate(ranking)}

    assignments, shortage = [], 0
    if campaign.status == STATUS_APPROVED:
        assignments = (GiftAssignment.query.filter_by(campaign_id=cid, user_id=current_user.id)
                       .order_by(GiftAssignment.round_no, GiftAssignment.id).all())
        shortage = max(0, total - len(assignments))
    several_pools = len(campaign.pools) > 1
    groups = [(pool, [a for a in assignments if a.pool_id == pool.id]) for pool in campaign.pools]
    breakdown = [(pool, pl_cards(n)) for pool, n in
                 pool_breakdown(campaign, compute_entitlements(campaign).get(current_user.id))]

    return render_template(
        'client/gift_cards/campaign.html',
        campaign=campaign, total=total, total_text=pl_cards(total), types=types,
        place_of=position, has_ranking=bool(ranking),
        is_open=campaign.status == STATUS_OPEN,
        race_at_iso=iso_utc(campaign.race_at),
        server_now_iso=iso_utc(utcnow()),
        race_at_text=to_pl(campaign.race_at).strftime('%d.%m.%Y, godz. %H:%M') if campaign.race_at else None,
        queue_pos=queue_position(campaign, current_user.id),
        assignments=assignments, shortage=shortage,
        several_pools=several_pools, breakdown=breakdown,
        assignment_groups=[g for g in groups if g[1]],
        notes=(participant.notes or '') if participant else '', notes_max=NOTES_MAX,
        shortage_text=pl_cards(shortage) if shortage else None,
        page_title='Gratisowe karty',
    )


def _participant(cid):
    """Wiersz uczestnika zalogowanego klienta; przy równoczesnym pierwszym zapisie bierze istniejący."""
    participant = GiftParticipant.query.filter_by(campaign_id=cid, user_id=current_user.id).first()
    if participant is not None:
        return participant
    db.session.add(GiftParticipant(campaign_id=cid, user_id=current_user.id))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return GiftParticipant.query.filter_by(campaign_id=cid, user_id=current_user.id).one()


def _store_ranking(cid, ranking_json):
    participant = _participant(cid)
    participant.ranking_json = ranking_json
    participant.ranking_updated_at = utcnow()
    db.session.commit()


@gift_cards_bp.route('/gratisy/<int:cid>/ranking', methods=['POST'])
@login_required
def client_save_ranking(cid):
    campaign = db.get_or_404(GiftCampaign, cid)
    if _entitled_total(campaign) == 0:
        return 'Ta akcja Cię nie dotyczy', 403
    if campaign.status != STATUS_OPEN:
        return _ranking_error('Ranking można zmieniać tylko, gdy akcja jest otwarta.', campaign)

    type_ids = [t.id for t in campaign.card_types]
    keys = {k for k in request.form if k.startswith('rank_')}
    if keys != {f'rank_{tid}' for tid in type_ids}:
        return _ranking_error('Ułóż miejsca dla wszystkich rodzajów kart.', campaign)
    try:
        places = {tid: int(request.form[f'rank_{tid}']) for tid in type_ids}
    except (TypeError, ValueError):
        return _ranking_error('Nieprawidłowe miejsce w rankingu.', campaign)
    if sorted(places.values()) != list(range(1, len(type_ids) + 1)):
        return _ranking_error('Każde miejsce może być wybrane tylko raz.', campaign)

    ranking = sorted(type_ids, key=lambda tid: places[tid])
    _store_ranking(cid, json.dumps(ranking))
    flash('Ranking zapisany.', 'success')
    return redirect(url_for('gift_cards.client_campaign', cid=cid))


@gift_cards_bp.route('/gratisy/<int:cid>/zglaszam-sie', methods=['POST'])
@login_required
def client_race(cid):
    campaign = db.get_or_404(GiftCampaign, cid)
    if _entitled_total(campaign) == 0:
        return jsonify(success=False, error='Ta akcja Cię nie dotyczy.'), 403
    if campaign.status != STATUS_OPEN:
        return jsonify(success=False, error='Zgłoszenia są teraz zamknięte.'), 400
    if campaign.race_at is None or utcnow() < campaign.race_at:
        return jsonify(success=False, error='Zgłoszenia ruszą dopiero o wyznaczonej godzinie.'), 400

    if GiftRaceEntry.query.filter_by(campaign_id=cid, user_id=current_user.id).first() is None:
        db.session.add(GiftRaceEntry(campaign_id=cid, user_id=current_user.id))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    return jsonify(success=True, position=queue_position(campaign, current_user.id))


@gift_cards_bp.route('/gratisy/<int:cid>/uwagi', methods=['POST'])
@login_required
def client_save_notes(cid):
    campaign = db.get_or_404(GiftCampaign, cid)
    if _entitled_total(campaign) == 0:
        return 'Ta akcja Cię nie dotyczy', 403
    if campaign.status != STATUS_OPEN:
        return _ranking_error('Uwagi można zmieniać tylko, gdy akcja jest otwarta.', campaign)
    notes = (request.form.get('notes') or '').strip()
    if len(notes) > NOTES_MAX:
        return _ranking_error(f'Uwagi mogą mieć najwyżej {NOTES_MAX} znaków.', campaign)
    participant = _participant(cid)
    participant.notes = notes or None
    db.session.commit()
    flash('Uwagi zapisane.' if notes else 'Uwagi usunięte.', 'success')
    return redirect(url_for('gift_cards.client_campaign', cid=cid))
