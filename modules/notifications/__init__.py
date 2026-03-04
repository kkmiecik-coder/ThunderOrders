from flask import Blueprint

notifications_bp = Blueprint(
    'notifications',
    __name__,
    template_folder='../../templates/notifications',
    static_folder='../../static'
)

from . import routes  # noqa
