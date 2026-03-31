import io
import re
import unicodedata
from datetime import datetime, timedelta

from flask import (
    render_template, request, redirect, url_for, flash,
    jsonify, send_file, abort,
)
from flask_login import login_required, current_user

from . import tracking_bp
from .models import QRCampaign, QRVisit, get_local_now
from .qr_generator import generate_qr_png, generate_qr_svg
from .export import export_visits_xlsx
from extensions import db
from utils.decorators import role_required


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

POLISH_CHARS = {
    'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
    'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
    'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N',
    'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z',
}


def slugify(text):
    """Generuje slug z tekstu (obsługuje polskie znaki)."""
    for pl_char, ascii_char in POLISH_CHARS.items():
        text = text.replace(pl_char, ascii_char)
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = text.strip('-')
    return text or 'kampania'


def _ensure_unique_slug(slug, exclude_id=None):
    """Sprawdza unikalność sluga i dodaje suffix jeśli trzeba."""
    original = slug
    counter = 1
    while True:
        query = QRCampaign.query.filter_by(slug=slug)
        if exclude_id:
            query = query.filter(QRCampaign.id != exclude_id)
        if not query.first():
            return slug
        slug = f'{original}-{counter}'
        counter += 1


# ---------------------------------------------------------------------------
# Route 1: Lista kampanii
# ---------------------------------------------------------------------------

@tracking_bp.route('/admin/qr-tracking')
@login_required
@role_required('admin', 'mod')
def qr_campaigns_list():
    """Lista wszystkich kampanii QR (bez usuniętych)."""
    campaigns = (
        QRCampaign.query
        .filter_by(is_deleted=False)
        .order_by(QRCampaign.created_at.desc())
        .all()
    )
    return render_template(
        'admin/tracking/campaigns_list.html',
        campaigns=campaigns,
    )


# ---------------------------------------------------------------------------
# Route 2: Nowa kampania
# ---------------------------------------------------------------------------

@tracking_bp.route('/admin/qr-tracking/new', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def qr_campaign_new():
    """Formularz tworzenia nowej kampanii QR."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        target_url = request.form.get('target_url', '').strip()
        slug_input = request.form.get('slug', '').strip()

        if not name:
            flash('Nazwa kampanii jest wymagana.', 'error')
            return render_template('admin/tracking/campaign_form.html', campaign=None)

        if not target_url:
            target_url = 'https://thunderorders.cloud'

        slug = slugify(slug_input) if slug_input else slugify(name)
        slug = _ensure_unique_slug(slug)

        campaign = QRCampaign(
            name=name,
            slug=slug,
            target_url=target_url,
            is_active=True,
            created_by=current_user.id,
        )
        db.session.add(campaign)
        db.session.commit()

        flash(f'Kampania "{name}" została utworzona.', 'success')
        return redirect(url_for('tracking.qr_campaign_detail', campaign_id=campaign.id))

    return render_template('admin/tracking/campaign_form.html', campaign=None)


# ---------------------------------------------------------------------------
# Route 3: Edycja kampanii
# ---------------------------------------------------------------------------

@tracking_bp.route('/admin/qr-tracking/<int:campaign_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def qr_campaign_edit(campaign_id):
    """Formularz edycji kampanii QR."""
    campaign = QRCampaign.query.filter_by(id=campaign_id, is_deleted=False).first_or_404()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        target_url = request.form.get('target_url', '').strip()
        slug_input = request.form.get('slug', '').strip()

        if not name:
            flash('Nazwa kampanii jest wymagana.', 'error')
            return render_template('admin/tracking/campaign_form.html', campaign=campaign)

        if not target_url:
            target_url = 'https://thunderorders.cloud'

        new_slug = slugify(slug_input) if slug_input else slugify(name)
        new_slug = _ensure_unique_slug(new_slug, exclude_id=campaign.id)

        campaign.name = name
        campaign.slug = new_slug
        campaign.target_url = target_url
        db.session.commit()

        flash(f'Kampania "{name}" została zaktualizowana.', 'success')
        return redirect(url_for('tracking.qr_campaign_detail', campaign_id=campaign.id))

    return render_template('admin/tracking/campaign_form.html', campaign=campaign)


# ---------------------------------------------------------------------------
# Route 4: Soft delete
# ---------------------------------------------------------------------------

@tracking_bp.route('/admin/qr-tracking/<int:campaign_id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def qr_campaign_delete(campaign_id):
    """Soft-delete kampanii (is_deleted=True)."""
    campaign = QRCampaign.query.filter_by(id=campaign_id, is_deleted=False).first_or_404()
    campaign.is_deleted = True
    campaign.is_active = False
    db.session.commit()

    flash(f'Kampania "{campaign.name}" została usunięta.', 'success')
    return redirect(url_for('tracking.qr_campaigns_list'))


# ---------------------------------------------------------------------------
# Route 5: Reset wizyt kampanii (AJAX)
# ---------------------------------------------------------------------------

@tracking_bp.route('/admin/qr-tracking/<int:campaign_id>/reset-visits', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def qr_campaign_reset_visits(campaign_id):
    """Usuń wszystkie wizyty kampanii."""
    campaign = QRCampaign.query.filter_by(id=campaign_id, is_deleted=False).first()
    if not campaign:
        return jsonify({'success': False, 'error': 'Kampania nie znaleziona'}), 404

    count = QRVisit.query.filter_by(campaign_id=campaign.id).delete()
    db.session.commit()

    return jsonify({
        'success': True,
        'deleted': count,
        'message': f'Usunięto {count} wizyt z kampanii "{campaign.name}".',
    })


# ---------------------------------------------------------------------------
# Route 6: Toggle is_active (AJAX)
# ---------------------------------------------------------------------------

@tracking_bp.route('/admin/qr-tracking/<int:campaign_id>/toggle', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def qr_campaign_toggle(campaign_id):
    """Przełącz aktywność kampanii (AJAX)."""
    campaign = QRCampaign.query.filter_by(id=campaign_id, is_deleted=False).first()
    if not campaign:
        return jsonify({'success': False, 'error': 'Kampania nie znaleziona'}), 404

    campaign.is_active = not campaign.is_active
    db.session.commit()

    return jsonify({
        'success': True,
        'is_active': campaign.is_active,
        'message': f'Kampania {"aktywowana" if campaign.is_active else "dezaktywowana"}.',
    })


# ---------------------------------------------------------------------------
# Route 6: Szczegóły / statystyki
# ---------------------------------------------------------------------------

@tracking_bp.route('/admin/qr-tracking/<int:campaign_id>')
@login_required
@role_required('admin', 'mod')
def qr_campaign_detail(campaign_id):
    """Strona szczegółów kampanii ze statystykami."""
    campaign = QRCampaign.query.filter_by(id=campaign_id, is_deleted=False).first_or_404()

    return render_template(
        'admin/tracking/campaign_detail.html',
        campaign=campaign,
    )


# ---------------------------------------------------------------------------
# Route 7: Podgląd QR kodu
# ---------------------------------------------------------------------------

@tracking_bp.route('/admin/qr-tracking/<int:campaign_id>/qr-code')
@login_required
@role_required('admin', 'mod')
def qr_campaign_qr_code(campaign_id):
    """Podgląd QR kodu kampanii."""
    campaign = QRCampaign.query.filter_by(id=campaign_id, is_deleted=False).first_or_404()
    qr_url = f'https://thunderorders.cloud/qr/{campaign.slug}'
    svg_preview = generate_qr_svg(qr_url)

    return render_template(
        'admin/tracking/qr_preview.html',
        campaign=campaign,
        qr_url=qr_url,
        svg_preview=svg_preview,
    )


# ---------------------------------------------------------------------------
# Route 8: Pobierz QR kod (SVG / PNG)
# ---------------------------------------------------------------------------

@tracking_bp.route('/admin/qr-tracking/<int:campaign_id>/download/<format>')
@login_required
@role_required('admin', 'mod')
def qr_campaign_download(campaign_id, format):
    """Pobierz QR kod w formacie SVG lub PNG."""
    campaign = QRCampaign.query.filter_by(id=campaign_id, is_deleted=False).first_or_404()
    qr_url = f'https://thunderorders.cloud/qr/{campaign.slug}'

    if format == 'svg':
        svg_content = generate_qr_svg(qr_url)
        buffer = io.BytesIO(svg_content.encode('utf-8'))
        return send_file(
            buffer,
            mimetype='image/svg+xml',
            as_attachment=True,
            download_name=f'qr-{campaign.slug}.svg',
        )
    elif format == 'png':
        png_data = generate_qr_png(qr_url, size=1024)
        buffer = io.BytesIO(png_data)
        return send_file(
            buffer,
            mimetype='image/png',
            as_attachment=True,
            download_name=f'qr-{campaign.slug}.png',
        )
    else:
        abort(400)


# ---------------------------------------------------------------------------
# Route 9: API - statystyki dla wykresów
# ---------------------------------------------------------------------------

@tracking_bp.route('/admin/qr-tracking/<int:campaign_id>/api/stats')
@login_required
@role_required('admin', 'mod')
def qr_campaign_api_stats(campaign_id):
    """JSON ze statystykami kampanii do wykresów."""
    campaign = QRCampaign.query.filter_by(id=campaign_id, is_deleted=False).first()
    if not campaign:
        return jsonify({'success': False, 'error': 'Kampania nie znaleziona'}), 404

    # Parametry filtrowania
    date_from_str = request.args.get('date_from')
    date_to_str = request.args.get('date_to')
    granularity = request.args.get('granularity', 'daily')

    # Calculate query padding for -1/+1 range on daily/weekly/monthly
    query_pad_before = timedelta(0)
    query_pad_after = timedelta(0)
    if granularity == 'daily':
        query_pad_before = timedelta(days=1)
        query_pad_after = timedelta(days=1)
    elif granularity == 'weekly':
        query_pad_before = timedelta(weeks=1, days=6)  # +6 for weekday alignment
        query_pad_after = timedelta(weeks=1, days=6)
    elif granularity == 'monthly':
        query_pad_before = timedelta(days=31)
        query_pad_after = timedelta(days=31)

    # Bazowe zapytanie - extended range to include padding data
    query = QRVisit.query.filter_by(campaign_id=campaign.id)

    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d')
            query = query.filter(QRVisit.visited_at >= date_from - query_pad_before)
        except ValueError:
            pass

    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(QRVisit.visited_at < date_to + query_pad_after)
        except ValueError:
            pass

    visits = query.order_by(QRVisit.visited_at.asc()).all()

    # --- Timeline ---
    timeline = {}
    for v in visits:
        if not v.visited_at:
            continue
        if granularity == 'minutely':
            key = v.visited_at.strftime('%Y-%m-%d %H:%M')
        elif granularity == 'hourly':
            key = v.visited_at.strftime('%Y-%m-%d %H:00')
        elif granularity == 'monthly':
            key = v.visited_at.strftime('%Y-%m')
        elif granularity == 'weekly':
            monday = v.visited_at - timedelta(days=v.visited_at.weekday())
            key = monday.strftime('%Y-%m-%d')
        else:  # daily
            key = v.visited_at.strftime('%Y-%m-%d')

        if key not in timeline:
            timeline[key] = {'total': 0, 'unique': 0}
        timeline[key]['total'] += 1
        if v.is_unique:
            timeline[key]['unique'] += 1

    # Fill missing slots so chart shows full continuous range
    if date_from_str and date_to_str:
        try:
            fill_start = datetime.strptime(date_from_str, '%Y-%m-%d')
            fill_end = datetime.strptime(date_to_str, '%Y-%m-%d')

            if granularity == 'minutely':
                # Only fill between first and last visit
                if timeline:
                    sorted_keys = sorted(timeline.keys())
                    fill_start = datetime.strptime(sorted_keys[0], '%Y-%m-%d %H:%M')
                    fill_end = datetime.strptime(sorted_keys[-1], '%Y-%m-%d %H:%M')
                step = timedelta(minutes=1)
                fmt = '%Y-%m-%d %H:%M'
            elif granularity == 'hourly':
                fill_end = fill_end + timedelta(days=1)
                step = timedelta(hours=1)
                fmt = '%Y-%m-%d %H:00'
            elif granularity == 'daily':
                fill_start = fill_start - timedelta(days=1)
                fill_end = fill_end + timedelta(days=1)
                step = timedelta(days=1)
                fmt = '%Y-%m-%d'
            elif granularity == 'weekly':
                # -1/+1 week, aligned to Monday
                fill_start = fill_start - timedelta(days=fill_start.weekday()) - timedelta(weeks=1)
                fill_end_monday = fill_end - timedelta(days=fill_end.weekday())
                fill_end = fill_end_monday + timedelta(weeks=1)
                step = timedelta(weeks=1)
                fmt = '%Y-%m-%d'
            elif granularity == 'monthly':
                # -1 month
                if fill_start.month == 1:
                    fill_start = fill_start.replace(year=fill_start.year - 1, month=12, day=1)
                else:
                    fill_start = fill_start.replace(month=fill_start.month - 1, day=1)
                # +1 month
                if fill_end.month == 12:
                    fill_end = fill_end.replace(year=fill_end.year + 1, month=1, day=1)
                else:
                    fill_end = fill_end.replace(month=fill_end.month + 1, day=1)
                # Generate month keys manually
                cursor = fill_start
                while cursor <= fill_end:
                    key = cursor.strftime('%Y-%m')
                    if key not in timeline:
                        timeline[key] = {'total': 0, 'unique': 0}
                    # Advance to next month
                    if cursor.month == 12:
                        cursor = cursor.replace(year=cursor.year + 1, month=1)
                    else:
                        cursor = cursor.replace(month=cursor.month + 1)
                step = None  # Already handled
                fmt = None
            else:
                step = None
                fmt = None

            if step and fmt:
                cursor = fill_start
                while cursor <= fill_end:
                    key = cursor.strftime(fmt)
                    if key not in timeline:
                        timeline[key] = {'total': 0, 'unique': 0}
                    cursor += step
        except ValueError:
            pass

    timeline_data = [
        {'date': k, 'total': v['total'], 'unique': v['unique']}
        for k, v in sorted(timeline.items())
    ]

    # --- Devices ---
    devices = {}
    for v in visits:
        dt = v.device_type or 'Nieznane'
        devices[dt] = devices.get(dt, 0) + 1

    devices_data = [
        {'name': k, 'count': v}
        for k, v in sorted(devices.items(), key=lambda x: x[1], reverse=True)
    ]

    # --- Browsers ---
    browsers = {}
    for v in visits:
        br = v.browser or 'Nieznana'
        browsers[br] = browsers.get(br, 0) + 1

    browsers_data = [
        {'name': k, 'count': v}
        for k, v in sorted(browsers.items(), key=lambda x: x[1], reverse=True)
    ]

    # --- Operating Systems ---
    os_stats = {}
    for v in visits:
        os_name = v.os or 'Nieznany'
        os_stats[os_name] = os_stats.get(os_name, 0) + 1

    os_data = [
        {'name': k, 'count': v}
        for k, v in sorted(os_stats.items(), key=lambda x: x[1], reverse=True)
    ]

    # --- Countries ---
    countries = {}
    for v in visits:
        co = v.country or 'Nieznany'
        countries[co] = countries.get(co, 0) + 1

    countries_data = [
        {'name': k, 'count': v}
        for k, v in sorted(countries.items(), key=lambda x: x[1], reverse=True)
    ]

    return jsonify({
        'success': True,
        'total_visits': len(visits),
        'unique_visits': sum(1 for v in visits if v.is_unique),
        'timeline': timeline_data,
        'devices': devices_data,
        'browsers': browsers_data,
        'os': os_data,
        'countries': countries_data,
    })


# ---------------------------------------------------------------------------
# Route 10: API - lista wizyt (paginacja)
# ---------------------------------------------------------------------------

@tracking_bp.route('/admin/qr-tracking/<int:campaign_id>/api/visits')
@login_required
@role_required('admin', 'mod')
def qr_campaign_api_visits(campaign_id):
    """JSON z listą wizyt (paginacja, 50 na stronę)."""
    campaign = QRCampaign.query.filter_by(id=campaign_id, is_deleted=False).first()
    if not campaign:
        return jsonify({'success': False, 'error': 'Kampania nie znaleziona'}), 404

    page = request.args.get('page', 1, type=int)
    per_page = 50

    pagination = (
        QRVisit.query
        .filter_by(campaign_id=campaign.id)
        .order_by(QRVisit.visited_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    visits_data = []
    for v in pagination.items:
        visits_data.append({
            'id': v.id,
            'visited_at': v.visited_at.strftime('%Y-%m-%d %H:%M:%S') if v.visited_at else None,
            'device_type': v.device_type,
            'browser': v.browser,
            'os': v.os,
            'country': v.country,
            'city': v.city,
            'ip_address': v.ip_address,
            'is_unique': v.is_unique,
            'referer': v.referer,
        })

    return jsonify({
        'success': True,
        'visits': visits_data,
        'page': page,
        'per_page': per_page,
        'total': pagination.total,
        'pages': pagination.pages,
        'has_next': pagination.has_next,
        'has_prev': pagination.has_prev,
    })


# ---------------------------------------------------------------------------
# Route 11: Eksport XLSX
# ---------------------------------------------------------------------------

@tracking_bp.route('/admin/qr-tracking/<int:campaign_id>/export')
@login_required
@role_required('admin', 'mod')
def qr_campaign_export(campaign_id):
    """Eksportuj wizyty kampanii do pliku XLSX."""
    campaign = QRCampaign.query.filter_by(id=campaign_id, is_deleted=False).first_or_404()
    visits = (
        QRVisit.query
        .filter_by(campaign_id=campaign.id)
        .order_by(QRVisit.visited_at.desc())
        .all()
    )

    xlsx_data = export_visits_xlsx(campaign, visits)
    buffer = io.BytesIO(xlsx_data)

    return send_file(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'qr-wizyty-{campaign.slug}.xlsx',
    )
