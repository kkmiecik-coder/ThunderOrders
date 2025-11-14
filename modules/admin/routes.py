"""
Admin Routes
Routing dla panelu administratora
"""

from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from modules.admin import admin_bp
from utils.decorators import role_required


@admin_bp.route('/dashboard')
@login_required
@role_required('admin', 'mod')
def dashboard():
    """
    Admin Dashboard
    Widok główny panelu administratora z podstawowymi metrykami
    """
    # TODO: W przyszłości dodamy prawdziwe statystyki z bazy danych
    # Na razie pusty dashboard (placeholder)

    return render_template('admin/dashboard.html', title='Panel Administratora')
