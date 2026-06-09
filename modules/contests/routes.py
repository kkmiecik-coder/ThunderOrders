from flask import render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, distinct

from extensions import db
from utils.decorators import role_required
from modules.contests import contests_bp
from modules.contests.models import Contest, ContestSpin, ContestWinner
from modules.contests.forms import ContestForm
from modules.contests import utils as cu


def _display_name(user):
    return user.first_name or user.email


def _count_participants(contest):
    return db.session.query(func.count(distinct(ContestSpin.user_id))) \
        .filter(ContestSpin.contest_id == contest.id).scalar() or 0


@contests_bp.route('/admin/konkursy')
@login_required
@role_required('admin', 'mod')
def admin_list():
    contests = Contest.query.order_by(Contest.created_at.desc()).all()
    data = [{'c': c, 'pool': cu.get_pool(c),
             'participants': _count_participants(c)} for c in contests]
    return render_template('admin/contests/list.html', items=data)


def _apply_form(form, contest):
    # Uwaga: lista pól musi być zsynchronizowana z ContestForm (status i created_by_admin_id celowo pominięte)
    for f in ['name', 'description', 'image_path', 'prize_product_id', 'num_winners',
              'ticket_min', 'ticket_max', 'cooldown_minutes', 'eligibility_min_orders',
              'eligibility_min_total_value', 'eligibility_active_within_days', 'ends_at']:
        setattr(contest, f, getattr(form, f).data)


@contests_bp.route('/admin/konkursy/nowy', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def admin_new():
    form = ContestForm()
    if form.validate_on_submit():
        c = Contest(status='szkic', created_by_admin_id=current_user.id)
        _apply_form(form, c)
        db.session.add(c)
        db.session.commit()
        flash('Konkurs utworzony.', 'success')
        return redirect(url_for('contests.admin_list'))
    return render_template('admin/contests/form.html', form=form, contest=None)


@contests_bp.route('/admin/konkursy/<int:cid>/edytuj', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def admin_edit(cid):
    c = Contest.query.get_or_404(cid)
    form = ContestForm(obj=c)
    if form.validate_on_submit():
        _apply_form(form, c)
        db.session.commit()
        flash('Zapisano.', 'success')
        return redirect(url_for('contests.admin_list'))
    return render_template('admin/contests/form.html', form=form, contest=c)


@contests_bp.route('/admin/konkursy/<int:cid>/aktywuj', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_activate(cid):
    c = Contest.query.get_or_404(cid)
    # Inwariant "jeden aktywny" egzekwowany aplikacyjnie (brak constraintu DB); OK dla narzędzia jednoadminowego
    if cu.get_active_contest() is not None:
        flash('Inny konkurs jest już aktywny.', 'error')
        return redirect(url_for('contests.admin_list'))
    c.status = 'aktywny'
    db.session.commit()
    flash('Konkurs aktywny.', 'success')
    return redirect(url_for('contests.admin_list'))


@contests_bp.route('/admin/konkursy/<int:cid>/losowanie')
@login_required
@role_required('admin', 'mod')
def admin_draw_screen(cid):
    c = Contest.query.get_or_404(cid)
    return render_template('admin/contests/draw.html', contest=c, pool=cu.get_pool(c))


@contests_bp.route('/admin/konkursy/<int:cid>/losuj', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_draw(cid):
    c = Contest.query.get_or_404(cid)
    if c.status not in ('aktywny', 'rozlosowany'):
        return jsonify(success=False, error='Konkurs nie jest aktywny.'), 200
    # Blokuj losowanie dopóki trwa zaplanowane okno (ends_at w przyszłości).
    # Gdy ends_at jest None lub minął, admin może losować "na żywo".
    if c.status == 'aktywny' and c.ends_at is not None and cu.get_local_now() < c.ends_at:
        return jsonify(success=False,
                       error='Spiny wciąż otwarte — poczekaj na koniec konkursu (ends_at).'), 200

    winners = cu.draw_winners(c)
    pool = cu.get_pool(c)
    # pełne rozbicie puli z procentami — TYLKO dla admina (klient tego nie widzi)
    breakdown = []
    for user, tickets in cu.participants(c):
        breakdown.append({
            'user_id': user.id,
            'name': _display_name(user),
            'tickets': tickets,
            'pct': round(tickets / pool * 100, 2) if pool else 0,
        })
    breakdown.sort(key=lambda x: x['tickets'], reverse=True)
    return jsonify(success=True, pool=pool, breakdown=breakdown, winners=[{
        'user_id': w.user_id, 'place': w.place, 'tickets': w.tickets_at_draw,
        'pct': float(w.chance_pct or 0),
        'name': _display_name(w.user),
    } for w in winners])


@contests_bp.route('/admin/konkursy/<int:cid>/wyniki')
@login_required
@role_required('admin', 'mod')
def admin_results(cid):
    c = Contest.query.get_or_404(cid)
    winners = ContestWinner.query.filter_by(contest_id=cid).order_by(ContestWinner.place).all()
    return render_template('admin/contests/results.html', contest=c, winners=winners)
