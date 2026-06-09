import json
import os
import random
import secrets

from flask import render_template, redirect, url_for, flash, request, abort, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, distinct

from extensions import db
from utils.decorators import role_required
from modules.contests import contests_bp
from modules.contests.models import Contest, ContestPrize, ContestPrizeItem, ContestSpin, ContestWinner
from modules.contests.forms import ContestForm
from modules.contests import utils as cu


def _display_name(user):
    return user.full_name  # imię + nazwisko, fallback na email


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
    for f in ['name', 'description', 'image_path', 'num_winners',
              'ticket_min', 'ticket_max', 'cooldown_minutes', 'eligibility_min_orders',
              'eligibility_min_total_value', 'eligibility_active_within_days', 'ends_at']:
        setattr(contest, f, getattr(form, f).data)


def _apply_prizes(contest):
    """Przebuduj zestaw nagród z pola prizes_json (JSON)."""
    from modules.products.models import Product
    raw = request.form.get('prizes_json', '').strip()
    contest.prizes.clear()  # cascade delete-orphan usuwa stare wiersze
    if not raw:
        return
    try:
        entries = json.loads(raw)
    except (ValueError, TypeError):
        return
    for e in entries or []:
        try:
            qty = int(e.get('quantity', 1))
        except (ValueError, TypeError):
            qty = 1
        if qty < 1:
            qty = 1
        name = (e.get('name') or None)
        items_raw = e.get('items') or []
        valid_items = []
        for it in items_raw:
            try:
                pid = int(it.get('product_id'))
                iqty = int(it.get('quantity', 1))
            except (ValueError, TypeError):
                continue
            if iqty < 1:
                iqty = 1
            if db.session.get(Product, pid):
                valid_items.append(ContestPrizeItem(product_id=pid, quantity=iqty))
        if not valid_items:
            continue   # pomiń wpisy bez prawidłowych produktów
        prize = ContestPrize(name=(name if name else None), quantity=qty)
        prize.items = valid_items
        contest.prizes.append(prize)


def _delete_contest_image_files(relative_path, static_dir):
    """Usuń stary plik grafiki z dysku (defensywnie — błędy ignorowane)."""
    if not relative_path:
        return
    # Sanity guard: usuwaj tylko pliki z uploads/contests/
    norm = relative_path.replace('\\', '/')
    if not norm.startswith('uploads/contests/'):
        return
    comp_abs = os.path.join(static_dir, norm)
    orig_abs = comp_abs.replace(
        os.path.join('uploads', 'contests', 'compressed'),
        os.path.join('uploads', 'contests', 'original'),
    )
    for path in (comp_abs, orig_abs):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as exc:
            current_app.logger.warning('[_delete_contest_image_files] nie usunięto %s: %s', path, exc)


def _handle_contest_image(contest):
    """Zapisz przesłany plik grafiki i ustaw contest.image_path. Bez pliku — brak zmian."""
    from utils.image_processor import allowed_file, compress_image
    from PIL import Image, ImageOps
    import shutil

    file = request.files.get('image_file')
    if not file or not file.filename:
        return
    if not allowed_file(file.filename):
        return
    ext = file.filename.rsplit('.', 1)[1].lower()
    fname = secrets.token_urlsafe(16) + '.' + ext
    static_dir = os.path.join(current_app.root_path, 'static')
    orig_dir = os.path.join(static_dir, 'uploads', 'contests', 'original')
    comp_dir = os.path.join(static_dir, 'uploads', 'contests', 'compressed')
    os.makedirs(orig_dir, exist_ok=True)
    os.makedirs(comp_dir, exist_ok=True)
    orig_path = os.path.join(orig_dir, fname)
    comp_path = os.path.join(comp_dir, fname)
    try:
        file.save(orig_path)
        img = Image.open(orig_path)
        img = ImageOps.exif_transpose(img)
        img.save(orig_path)
        shutil.copy2(orig_path, comp_path)
        compress_image(comp_path)
        old_path = contest.image_path
        contest.image_path = os.path.join('uploads', 'contests', 'compressed', fname)
        _delete_contest_image_files(old_path, static_dir)
    except Exception as exc:
        current_app.logger.warning('[_handle_contest_image] błąd uploadu: %s', exc)
        for path in (orig_path, comp_path):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        flash('Nie udało się zapisać grafiki — spróbuj ponownie lub wybierz inny plik.', 'error')


@contests_bp.route('/admin/konkursy/nowy', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def admin_new():
    form = ContestForm()
    if form.validate_on_submit():
        c = Contest(status='szkic', created_by_admin_id=current_user.id)
        _apply_form(form, c)
        db.session.add(c)
        db.session.flush()  # generuje c.id potrzebne dla ContestPrize FK
        _apply_prizes(c)
        _handle_contest_image(c)
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
        _apply_prizes(c)
        _handle_contest_image(c)
        db.session.commit()
        flash('Zapisano.', 'success')
        return redirect(url_for('contests.admin_list'))
    return render_template('admin/contests/form.html', form=form, contest=c)


@contests_bp.route('/admin/konkursy/<int:cid>/usun', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_delete(cid):
    c = Contest.query.get_or_404(cid)
    if c.status != 'szkic':
        flash('Można usuwać tylko konkursy w statusie szkic.', 'error')
        return redirect(url_for('contests.admin_list'))
    db.session.delete(c)   # ContestPrize/items cascade via ORM; draft has no spins/winners
    db.session.commit()
    flash('Konkurs usunięty.', 'success')
    return redirect(url_for('contests.admin_list'))


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


# ---------------------------------------------------------------------------
# Trasy klienckie
# ---------------------------------------------------------------------------

@contests_bp.route('/konkurs')
@login_required
def client_contest():
    c = cu.get_active_contest()
    ctx = cu.widget_context(c, current_user) if c else None
    return render_template('client/contest.html', contest=c, ctx=ctx)


@contests_bp.route('/konkurs/spin', methods=['POST'])
@login_required
def client_spin():
    c = cu.get_active_contest()
    if c is None:
        return jsonify(success=False, error='Brak aktywnego konkursu.'), 200
    if not cu.spins_open(c):
        return jsonify(success=False, error='Konkurs nie przyjmuje losów.'), 200
    if not cu.is_eligible(c, current_user):
        return jsonify(success=False, error='Nie spełniasz warunków udziału.'), 200
    if not cu.can_spin(c, current_user):
        nxt = cu.get_next_spin_at(c, current_user)
        return jsonify(success=False, error='Następny los dostępny później.',
                       next_spin_at=nxt.isoformat() if nxt else None), 200

    # TODO: przy większym ruchu rozważyć blokadę DB na podwójny spin w oknie cooldownu (TOCTOU)
    tickets = cu.draw_ticket_count(c)  # rozkład skośny ku ticket_min (wyższe rzadsze)
    db.session.add(ContestSpin(contest_id=c.id, user_id=current_user.id, tickets_won=tickets))
    db.session.commit()
    nxt = cu.get_next_spin_at(c, current_user)
    return jsonify(success=True, tickets_won=tickets,
                   my_total=cu.get_user_tickets(c, current_user),
                   next_spin_at=nxt.isoformat() if nxt else None)
