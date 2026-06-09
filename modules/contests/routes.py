from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from sqlalchemy import func, distinct

from extensions import db
from utils.decorators import role_required
from modules.contests import contests_bp
from modules.contests.models import Contest, ContestSpin, ContestWinner
from modules.contests.forms import ContestForm
from modules.contests import utils as cu


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
