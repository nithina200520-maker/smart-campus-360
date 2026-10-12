from flask import Blueprint

navigation_bp = Blueprint('navigation', __name__, url_prefix='/navigation')

from . import routes
