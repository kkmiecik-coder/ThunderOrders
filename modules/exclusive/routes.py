"""
Exclusive Module - Public Routes
Publiczne endpointy dla stron ekskluzywnych zamówień
"""

from flask import render_template, abort, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from . import exclusive_bp
from .models import ExclusivePage


@exclusive_bp.route('/countdown')
def countdown_page():
    """
    Dedykowana strona countdown - uniwersalny timer odliczający do startu

    Parametry URL:
    - page: token strony exclusive

    Po zakończeniu odliczania JS przekierowuje na właściwą stronę zamówienia.
    """
    token = request.args.get('page')

    if not token:
        abort(404)

    page = ExclusivePage.get_by_token(token)

    if not page:
        abort(404)

    # Sprawdź czy strona ma datę startu
    if not page.starts_at:
        # Brak daty startu - przekieruj na główną stronę
        return redirect(url_for('exclusive.order_page', token=token))

    # Automatyczna aktualizacja statusu
    page.check_and_update_status()

    # Jeśli strona już aktywna lub zakończona - przekieruj
    if page.is_active or page.is_ended or page.is_paused:
        return redirect(url_for('exclusive.order_page', token=token))

    return render_template('exclusive/countdown.html', page=page)


@exclusive_bp.route('/<token>')
def order_page(token):
    """
    Główna strona ekskluzywna - wyświetla odpowiedni widok w zależności od statusu

    Statusy:
    - draft: "Strona w przygotowaniu"
    - scheduled: Przekierowanie na /countdown?page=token
    - active: Formularz zamówień
    - paused: "Sprzedaż wstrzymana"
    - ended: "Sprzedaż zakończona"
    """
    page = ExclusivePage.get_by_token(token)

    if not page:
        abort(404)

    # Automatyczna aktualizacja statusu na podstawie dat
    page.check_and_update_status()

    # Routing na podstawie statusu
    if page.is_draft:
        return render_template('exclusive/draft.html', page=page)

    if page.is_scheduled:
        # Przekieruj na dedykowaną stronę countdown
        return redirect(url_for('exclusive.countdown_page', page=token))

    if page.is_active:
        sections = page.get_sections_ordered()
        return render_template('exclusive/order_page.html', page=page, sections=sections)

    if page.is_paused:
        return render_template('exclusive/paused.html', page=page)

    if page.is_ended:
        return render_template('exclusive/ended.html', page=page)

    # Fallback
    abort(404)


@exclusive_bp.route('/<token>/thank-you')
def thank_you(token):
    """Strona podziękowania po złożeniu zamówienia"""
    page = ExclusivePage.get_by_token(token)

    if not page:
        abort(404)

    return render_template('exclusive/thank_you.html', page=page)


@exclusive_bp.route('/<token>/preview')
@login_required
def preview_page(token):
    """
    Podgląd strony ekskluzywnej dla admina/moda
    Pokazuje stronę tak jakby była aktywna, niezależnie od statusu
    """
    # Sprawdź czy użytkownik ma uprawnienia (admin lub mod)
    if current_user.role not in ['admin', 'mod']:
        abort(403)

    page = ExclusivePage.get_by_token(token)

    if not page:
        abort(404)

    sections = page.get_sections_ordered()
    return render_template('exclusive/order_page.html', page=page, sections=sections, preview_mode=True)


@exclusive_bp.route('/<token>/status')
def check_status(token):
    """
    API endpoint do sprawdzania statusu strony (używany przez countdown)
    Zwraca aktualny status strony - pozwala wykryć ręczną aktywację przez admina
    """
    page = ExclusivePage.get_by_token(token)

    if not page:
        return jsonify({'error': 'Page not found'}), 404

    # Automatyczna aktualizacja statusu na podstawie dat
    page.check_and_update_status()

    return jsonify({
        'status': page.status,
        'is_active': page.is_active
    })
