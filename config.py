import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
    DATABASE = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "finance.db"))
    PER_PAGE = int(os.environ.get("PER_PAGE", 15))
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB upload cap
    CURRENCY = os.environ.get("CURRENCY", "₹")
