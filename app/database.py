import logging
import sqlite3
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """Phase 10: SQLite switches OFF foreign key enforcement per connection by
    default, which silently disables every ondelete=CASCADE constraint in the
    models. Enable it on any SQLite connection so referential integrity and
    cascades behave exactly as declared (no-op on MySQL)."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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
