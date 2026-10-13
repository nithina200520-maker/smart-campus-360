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

    # --- Phase 5: Lost & Found AI matcher thresholds (tunable, measurable) ---
    # Minimum composite score for the engine to surface a suggested match at all
    LF_MATCH_MIN_COMPOSITE = float(os.getenv("LF_MATCH_MIN_COMPOSITE", 0.35))
    # Composite at/above which a suggestion is labelled a HIGH-confidence match
    LF_STRONG_MATCH_SCORE = float(os.getenv("LF_STRONG_MATCH_SCORE", 0.70))
    # Mid band boundary between 'medium' and 'possible' confidence
    LF_MEDIUM_MATCH_SCORE = float(os.getenv("LF_MEDIUM_MATCH_SCORE", 0.50))
    # Combined duplicate-report score at/above which a second report is flagged
    LF_DUPLICATE_SCORE = float(os.getenv("LF_DUPLICATE_SCORE", 0.65))
    # Number of ranked suggestions stored per new report
    LF_MATCH_LIMIT = int(os.getenv("LF_MATCH_LIMIT", 10))

    # --- Phase 6: Smart Canteen Booking (teacher-first allocation) ---
    # Master switch for teacher-first slot reservation. When False every order
    # competes for slot capacity on a first-come basis (queue sorting still
    # favours verified teachers at the kitchen counter).
    CANTEEN_TEACHER_PRIORITY_ENABLED = os.getenv("CANTEEN_TEACHER_PRIORITY_ENABLED", "True").lower() in ("true", "1", "t")
    # Fraction of each slot's capacity reserved for verified teachers until the
    # slot opens (reservations are released at slot start so student orders
    # are never indefinitely delayed).
    CANTEEN_TEACHER_RESERVE_RATIO = float(os.getenv("CANTEEN_TEACHER_RESERVE_RATIO", 0.25))
    # Auto-confirm orders when allocation succeeds (False keeps them 'pending'
    # for manual canteen admin confirmation).
    CANTEEN_AUTO_CONFIRM = os.getenv("CANTEEN_AUTO_CONFIRM", "True").lower() in ("true", "1", "t")
    # Minimum lead time (minutes) before a slot start a student/teacher may book it
    CANTEEN_MIN_LEAD_MINS = int(os.getenv("CANTEEN_MIN_LEAD_MINS", 15))
    # Average kitchen minutes added per order queued ahead in the same slot
    CANTEEN_PREP_MIN_PER_ORDER = int(os.getenv("CANTEEN_PREP_MIN_PER_ORDER", 4))

    # --- Phase 7: Payment & Refund Processing ---
    # 'sandbox' = built-in deterministic gateway (default; no credentials needed,
    # used by development + the automated test suite). 'stripe' = official Stripe
    # SDK, TEST-MODE ONLY: startup refuses any secret key that is not sk_test_*.
    PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "sandbox")
    PAYMENT_CURRENCY = os.getenv("PAYMENT_CURRENCY", "inr")
    # Credentials come from the environment ONLY and are never rendered in pages.
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    # Shared secret used to sign/verify webhook payloads (sandbox HMAC and the
    # Stripe signing secret both live here).
    PAYMENT_WEBHOOK_SECRET = os.getenv("PAYMENT_WEBHOOK_SECRET", "sc360-sandbox-webhook-secret-change-me")
    PAYMENT_WEBHOOK_TOLERANCE_SECS = int(os.getenv("PAYMENT_WEBHOOK_TOLERANCE_SECS", 300))
    # Sandbox outcome switches (documented test hooks; ignored by the Stripe path):
    # 'succeeded' (default, instant capture) | 'failed' | 'processing' (async,
    # the order only confirms once a signed webhook reports success).
    PAYMENT_SANDBOX_PAYMENT_OUTCOME = os.getenv("PAYMENT_SANDBOX_PAYMENT_OUTCOME", "succeeded")
    # 'succeeded' (default) | 'failed' | 'processing' (delayed; finalised by a
    # later webhook or an admin re-sync).
    PAYMENT_SANDBOX_REFUND_OUTCOME = os.getenv("PAYMENT_SANDBOX_REFUND_OUTCOME", "succeeded")
    # Auto-refund a captured payment when the order later proves unfulfillable.
    PAYMENT_AUTO_REFUND_ON_UNFULFILLABLE = os.getenv("PAYMENT_AUTO_REFUND_ON_UNFULFILLABLE", "True").lower() in ("true", "1", "t")

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
