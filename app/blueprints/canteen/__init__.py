from flask import Blueprint

canteen_bp = Blueprint('canteen', __name__, url_prefix='/canteen')

from . import routes
