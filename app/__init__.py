from pathlib import Path
from flask import Flask, render_template
from app.config import config_by_name, Config
from app.database import db, init_db_connection
from app.utils.auth_helpers import get_current_user

def create_app(config_name="default"):
    """
    Application factory constructing the integrated Smart Campus 360 platform.
    """
    app = Flask(__name__)
    cfg = config_by_name.get(config_name, Config)
    app.config.from_object(cfg)
    app.config['BASE_DIR'] = Config.BASE_DIR

    # Ensure upload directories exist
    upload_dirs = [
        app.config['UPLOAD_FOLDER'],
        app.config['UPLOAD_NAV_DIR'],
        app.config['UPLOAD_LF_DIR'],
        app.config['UPLOAD_CANTEEN_DIR'],
        app.config['UPLOAD_QR_DIR'],
        Config.BASE_DIR / "instance"
    ]
    for d in upload_dirs:
        Path(d).mkdir(parents=True, exist_ok=True)

    # Initialize Database
    init_db_connection(app)

    # Register Context Processors for global template access
    @app.context_processor
    def inject_global_template_vars():
        return {
            "current_user": get_current_user(),
            "COLLEGE_NAME": app.config.get("COLLEGE_NAME"),
            "COLLEGE_LOCATION": app.config.get("COLLEGE_LOCATION"),
            "APP_NAME": app.config.get("APP_NAME"),
            "ALLOW_QUICK_SWITCH": app.config.get("ALLOW_QUICK_SWITCH", False)
        }

    # Register Blueprints
    from app.blueprints.auth import auth_bp
    from app.blueprints.main import main_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.canteen_admin import canteen_admin_bp
    from app.blueprints.navigation import navigation_bp
    from app.blueprints.lost_found import lost_found_bp
    from app.blueprints.canteen import canteen_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(canteen_admin_bp)
    app.register_blueprint(navigation_bp)
    app.register_blueprint(lost_found_bp)
    app.register_blueprint(canteen_bp)

    # Register Error Handlers
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html', user=get_current_user()), 403

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html', user=get_current_user()), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html', user=get_current_user()), 500

    return app
