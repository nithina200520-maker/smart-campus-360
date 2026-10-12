import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(BASE_DIR / ".env")

class Config:
    """Base application configuration for Smart Campus 360."""
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.getenv("SECRET_KEY", "smart-campus-360-default-dev-secret-key-gec-hassan")
    
    # Campus Information
    COLLEGE_NAME = os.getenv("COLLEGE_NAME", "Government Engineering College, Mosalehosahalli")
    COLLEGE_LOCATION = os.getenv("COLLEGE_LOCATION", "Hassan, Karnataka, India")
    APP_NAME = os.getenv("APP_NAME", "Smart Campus 360")
    
    # Upload Directories
    UPLOAD_FOLDER = BASE_DIR / os.getenv("UPLOAD_FOLDER", "app/static/uploads")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)) # 16 MB
    
    # Sub-upload directories
    UPLOAD_NAV_DIR = UPLOAD_FOLDER / "navigation"
    UPLOAD_LF_DIR = UPLOAD_FOLDER / "lost_found"
    UPLOAD_CANTEEN_DIR = UPLOAD_FOLDER / "canteen"
    UPLOAD_QR_DIR = UPLOAD_FOLDER / "qr_codes"
    
    # Database Settings
    USE_SQLITE = os.getenv("USE_SQLITE", "False").lower() in ("true", "1", "t")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "root")
    DB_NAME = os.getenv("DB_NAME", "smart_campus_360")

    # Construct Database URI
    if USE_SQLITE:
        # SQLITE_DB_PATH env allows tests to isolate on a throwaway file
        SQLITE_PATH = BASE_DIR / os.getenv("SQLITE_DB_PATH", "instance/smart_campus_360.db")
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{SQLITE_PATH.as_posix()}"
    else:
        # Default to MySQL with PyMySQL
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
        )
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 280,
        "pool_pre_ping": True,
    }

    # --- Phase 2 Security: Session Management Hardening ---
    PERMANENT_SESSION_LIFETIME = timedelta(
        minutes=int(os.getenv("SESSION_LIFETIME_MINUTES", 120))  # Default: 2 hours
    )
    SESSION_COOKIE_HTTPONLY = True                 # Block JavaScript access to session cookie
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")  # CSRF mitigation
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False").lower() in ("true", "1", "t")

    # Developer 1-click "Switch Role" testing tool: DISABLED outside development
    # (privilege-escalation surface if left exposed in production)
    ALLOW_QUICK_SWITCH = False

class DevelopmentConfig(Config):
    DEBUG = True
    ALLOW_QUICK_SWITCH = os.getenv("ENABLE_QUICK_SWITCH", "True").lower() in ("true", "1", "t")

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True

class TestingConfig(ProductionConfig):
    """Isolated configuration for the automated pytest suite."""
    TESTING = True
    WTF_CSRF_ENABLED = False

config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
