"""
Feedback Routes
Endpointy dla systemu ankiet
"""

from flask import render_template, redirect, url_for, request, jsonify, flash, abort
from flask_login import login_required, current_user
from functools import wraps

from . import feedback_bp
from .models import FeedbackSurvey, FeedbackQuestion, FeedbackResponse, FeedbackAnswer, get_local_now
from extensions import db


# ============================================
# Decorators
# ============================================

def admin_required(f):
    """Dekorator wymagający roli admin lub mod"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.role not in ['admin', 'mod']:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


# ============================================
# Admin Routes
# ============================================

@feedback_bp.route('/admin/feedback')
@login_required
@admin_required
def admin_list():
    """Lista wszystkich ankiet"""
    surveys = FeedbackSurvey.query.order_by(FeedbackSurvey.created_at.desc()).all()
    return render_template('admin/feedback/list.html', surveys=surveys)


@feedback_bp.route('/admin/feedback/create', methods=['POST'])
@login_required
@admin_required
def admin_create():
    """Utwórz nową ankietę"""
    name = request.form.get('name', 'Nowa ankieta')

    survey = FeedbackSurvey(
        name=name,
        token=FeedbackSurvey.generate_token(),
        created_by=current_user.id,
        status='draft'
    )
    db.session.add(survey)
    db.session.commit()

    flash('Ankieta została utworzona.', 'success')
    return redirect(url_for('feedback.admin_edit', survey_id=survey.id))


@feedback_bp.route('/admin/feedback/<int:survey_id>/edit')
@login_required
@admin_required
def admin_edit(survey_id):
    """Edytor ankiety (builder)"""
    survey = FeedbackSurvey.query.get_or_404(survey_id)
    questions = survey.get_questions_ordered()

    return render_template(
        'admin/feedback/edit.html',
        survey=survey,
        questions=questions
    )


@feedback_bp.route('/admin/feedback/<int:survey_id>/save', methods=['POST'])
@login_required
@admin_required
def admin_save(survey_id):
    """Zapisz ankietę (AJAX)"""
    survey = FeedbackSurvey.query.get_or_404(survey_id)

    try:
        data = request.get_json()

        # Aktualizuj podstawowe dane ankiety
        survey.name = data.get('name', survey.name)
        survey.description = data.get('description')

        closes_at = data.get('closes_at')
        if closes_at:
            from datetime import datetime
            survey.closes_at = datetime.fromisoformat(closes_at.replace('Z', '+00:00').replace('+00:00', ''))
        else:
            survey.closes_at = None

        survey.is_anonymous = data.get('is_anonymous', False)
        survey.allow_multiple_responses = data.get('allow_multiple_responses', False)

        # Aktualizuj pytania
        questions_data = data.get('questions', [])
        _update_questions(survey, questions_data)

        survey.updated_at = get_local_now()
        db.session.commit()

        return jsonify({
            'success': True,
            'updated_at': survey.updated_at.strftime('%H:%M:%S')
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


def _update_questions(survey, questions_data):
    """Aktualizuje pytania ankiety"""
    existing_ids = set()

    for idx, q_data in enumerate(questions_data):
        q_id = q_data.get('id')

        if q_id:
            # Aktualizuj istniejące pytanie
            question = FeedbackQuestion.query.get(q_id)
            if question and question.survey_id == survey.id:
                question.question_type = q_data.get('type', question.question_type)
                question.content = q_data.get('content')
                question.options = q_data.get('options')
                question.is_required = q_data.get('is_required', False)
                question.sort_order = idx
                existing_ids.add(q_id)
        else:
            # Utwórz nowe pytanie
            question = FeedbackQuestion(
                survey_id=survey.id,
                question_type=q_data.get('type', 'text'),
                content=q_data.get('content'),
                options=q_data.get('options'),
                is_required=q_data.get('is_required', False),
                sort_order=idx
            )
            db.session.add(question)
            db.session.flush()
            existing_ids.add(question.id)

    # Usuń pytania które nie są w danych
    for question in survey.questions.all():
        if question.id not in existing_ids:
            db.session.delete(question)


@feedback_bp.route('/admin/feedback/<int:survey_id>/status', methods=['POST'])
@login_required
@admin_required
def admin_status(survey_id):
    """Zmień status ankiety (AJAX)"""
    survey = FeedbackSurvey.query.get_or_404(survey_id)

    try:
        data = request.get_json()
        action = data.get('action')

        if action == 'activate':
            survey.activate()
        elif action == 'close':
            survey.close()
        elif action == 'reopen':
            survey.reopen()
        elif action == 'draft':
            survey.status = 'draft'
        else:
            return jsonify({'success': False, 'error': 'Nieznana akcja'}), 400

        db.session.commit()

        return jsonify({
            'success': True,
            'status': survey.status
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


@feedback_bp.route('/admin/feedback/<int:survey_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete(survey_id):
    """Usuń ankietę"""
    survey = FeedbackSurvey.query.get_or_404(survey_id)

    db.session.delete(survey)
    db.session.commit()

    flash('Ankieta została usunięta.', 'success')
    return redirect(url_for('feedback.admin_list'))


@feedback_bp.route('/admin/feedback/<int:survey_id>/responses')
@login_required
@admin_required
def admin_responses(survey_id):
    """Przegląd odpowiedzi na ankietę"""
    survey = FeedbackSurvey.query.get_or_404(survey_id)
    responses = survey.responses.order_by(FeedbackResponse.submitted_at.desc()).all()
    questions = survey.get_questions_ordered()

    return render_template(
        'admin/feedback/responses.html',
        survey=survey,
        responses=responses,
        questions=questions
    )


@feedback_bp.route('/admin/feedback/<int:survey_id>/export')
@login_required
@admin_required
def admin_export(survey_id):
    """Eksportuj odpowiedzi do CSV"""
    import csv
    from io import StringIO
    from flask import Response

    survey = FeedbackSurvey.query.get_or_404(survey_id)
    responses = survey.responses.order_by(FeedbackResponse.submitted_at.desc()).all()
    questions = survey.get_answerable_questions()

    # Przygotuj CSV
    output = StringIO()
    writer = csv.writer(output)

    # Nagłówek
    header = ['Data', 'Użytkownik']
    for q in questions:
        header.append(q.content[:50] if q.content else f'Pytanie {q.id}')
    writer.writerow(header)

    # Dane
    for response in responses:
        row = [
            response.submitted_at.strftime('%Y-%m-%d %H:%M'),
            response.respondent_name if not survey.is_anonymous else 'Anonimowy'
        ]

        # Odpowiedzi na pytania
        answers_map = {a.question_id: a for a in response.answers.all()}
        for q in questions:
            answer = answers_map.get(q.id)
            if answer:
                row.append(answer.display_value)
            else:
                row.append('')

        writer.writerow(row)

    # Zwróć jako plik CSV
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=ankieta_{survey.id}_odpowiedzi.csv'
        }
    )


# ============================================
# Public Routes
# ============================================

@feedback_bp.route('/feedback/<token>')
@login_required
def survey_page(token):
    """Strona wypełniania ankiety"""
    survey = FeedbackSurvey.get_by_token(token)

    if not survey:
        abort(404)

    # Sprawdź czy ankieta jest aktywna
    survey.check_and_update_status()

    if survey.status == 'draft':
        flash('Ta ankieta nie jest jeszcze dostępna.', 'warning')
        return redirect(url_for('client.dashboard'))

    if survey.status == 'closed':
        flash('Ta ankieta została zamknięta.', 'info')
        return redirect(url_for('client.dashboard'))

    # Sprawdź czy użytkownik już odpowiedział (jeśli nie pozwalamy na wiele odpowiedzi)
    if not survey.allow_multiple_responses:
        existing_response = FeedbackResponse.query.filter_by(
            survey_id=survey.id,
            user_id=current_user.id
        ).first()

        if existing_response:
            flash('Już wypełniłeś tę ankietę.', 'info')
            return redirect(url_for('feedback.thank_you', token=token))

    questions = survey.get_questions_ordered()

    return render_template(
        'feedback/survey.html',
        survey=survey,
        questions=questions
    )


@feedback_bp.route('/feedback/<token>/submit', methods=['POST'])
@login_required
def survey_submit(token):
    """Wyślij odpowiedzi na ankietę"""
    survey = FeedbackSurvey.get_by_token(token)

    if not survey:
        abort(404)

    if not survey.can_respond:
        return jsonify({'success': False, 'error': 'Ankieta nie jest dostępna'}), 400

    # Sprawdź czy użytkownik już odpowiedział
    if not survey.allow_multiple_responses:
        existing_response = FeedbackResponse.query.filter_by(
            survey_id=survey.id,
            user_id=current_user.id
        ).first()

        if existing_response:
            return jsonify({'success': False, 'error': 'Już wypełniłeś tę ankietę'}), 400

    try:
        data = request.get_json()
        answers_data = data.get('answers', {})

        # Utwórz response
        response = FeedbackResponse(
            survey_id=survey.id,
            user_id=current_user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string[:500] if request.user_agent.string else None
        )
        db.session.add(response)
        db.session.flush()

        # Zapisz odpowiedzi
        for question_id, answer_data in answers_data.items():
            question = FeedbackQuestion.query.get(int(question_id))
            if not question or question.survey_id != survey.id:
                continue

            answer = FeedbackAnswer(
                response_id=response.id,
                question_id=question.id,
                answer_value=answer_data.get('value'),
                answer_text=answer_data.get('text'),
                answer_options=answer_data.get('options')
            )
            db.session.add(answer)

        db.session.commit()

        return jsonify({
            'success': True,
            'redirect_url': url_for('feedback.thank_you', token=token)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


@feedback_bp.route('/feedback/<token>/thank-you')
@login_required
def thank_you(token):
    """Strona podziękowania po wypełnieniu ankiety"""
    survey = FeedbackSurvey.get_by_token(token)

    if not survey:
        abort(404)

    return render_template('feedback/thank_you.html', survey=survey)
