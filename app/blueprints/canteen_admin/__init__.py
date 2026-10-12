from flask import Blueprint

canteen_admin_bp = Blueprint('canteen_admin', __name__, url_prefix='/canteen-admin')

from . import routes
