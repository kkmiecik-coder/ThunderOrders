from flask_login import login_required

from . import gift_cards_bp  # noqa: F401


@gift_cards_bp.route('/gratisy/<int:cid>')
@login_required
def client_campaign(cid):
    # Placeholder — treść strony klienta dochodzi w Task 7.
    return 'Wkrótce'
