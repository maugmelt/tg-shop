import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "pytest-shop.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
if DB_PATH.exists():
    DB_PATH.unlink()

os.environ["TG_DATABASE_URL"] = ""
os.environ["TG_DATABASE_PATH"] = str(DB_PATH)
os.environ["TG_SEED_DEMO"] = "0"
os.environ["TG_DEV_OPEN"] = "0"
os.environ["TG_WEBAPP_URL"] = ""
os.environ["TG_WEBHOOK_BASE_URL"] = ""
os.environ["TG_BOT_TOKEN"] = "111:CLIENT"
os.environ["TG_ADMIN_BOT_TOKEN"] = "222:ADMIN"
os.environ["TG_WEBHOOK_SECRET"] = "client-secret"
os.environ["TG_ADMIN_WEBHOOK_SECRET"] = "admin-secret"
os.environ["TG_ADMIN_IDS"] = "42"
os.environ["TG_SHOP_NAME"] = "Витрина"
os.environ["TG_ORDER_URL"] = ""

from app.config import reset_settings  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_settings():
    reset_settings()
    yield
    reset_settings()
