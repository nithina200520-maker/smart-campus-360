import logging
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = SQLAlchemy()

def init_db_connection(app):
    """
    Initializes SQLAlchemy with the Flask application.
    Tests MySQL connection prior to binding and seamlessly falls back
    to local SQLite if MySQL credentials are not yet configured or database is missing.
    """
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    
    if 'sqlite' not in db_uri:
        try:
            # Test engine connection with 3-second timeout
            test_engine = create_engine(db_uri, pool_pre_ping=True, connect_args={"connect_timeout": 3})
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            test_engine.dispose()
            logger.info("Connected to MySQL database successfully.")
        except Exception as e:
            sqlite_path = app.config['BASE_DIR'] / "instance" / "smart_campus_360.db"
            logger.warning(
                f"\n{'='*70}\n"
                f"[DATABASE NOTICE] MySQL connection attempt returned: {e}\n"
                f"[DATABASE NOTICE] Falling back to local SQLite at: {sqlite_path}\n"
                f"[DATABASE NOTICE] To use MySQL, set DB_PASSWORD in .env and run init_db.py\n"
                f"{'='*70}\n"
            )
            app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{sqlite_path.as_posix()}"

    db.init_app(app)
