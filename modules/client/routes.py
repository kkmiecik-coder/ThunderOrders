"""
Client Module - Routes
Endpointy panelu klienta
"""

from flask import render_template
from flask_login import login_required, current_user

from modules.client import client_bp


@client_bp.route('/dashboard')
@login_required
def dashboard():
    """
    Client Dashboard
    Główny panel klienta
    """
    return render_template(
        'client/dashboard.html',
        title='Panel Klienta',
        user=current_user
    )
