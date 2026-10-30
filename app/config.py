from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DEFAULT_CHECKOUT = (
    "Проверьте позиции, сделайте скриншот и переходите в Telegram для оформления."
)
DEFAULT_TERMS = (
    "Вещи на витрине продаются в том виде, как на фото, часто в одном экземпляре. "
    "Размер и наличие подтверждайте в переписке. "
    "Чтобы оформить заказ, соберите корзину, сделайте скриншот и отправьте его в Telegram."
)

CLOTHES_SIZES = ["XS", "S", "M", "L", "XL", "XXL"]
SHOE_SIZES = [str(size) for size in range(36, 46)]


def _clean(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_bot_token: str
    webhook_secret: str
    admin_webhook_secret: str
    webapp_url: str
    webhook_base_url: str
    shop_name: str
    admin_ids: frozenset[int]
    database_url: str
    checkout_hint: str
    order_url: str
    terms_text: str
    currency: str
    seed_demo: bool
    dev_open: bool


def _database_url() -> str:
    raw = _clean("TG_DATABASE_URL")
    if raw.startswith("postgres://"):
        return "postgresql+psycopg://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw[len("postgresql://") :]
    if raw:
        return raw
    path = Path(_clean("TG_DATABASE_PATH") or str(ROOT / "data" / "shop.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return "sqlite:///" + path.resolve().as_posix()


def _admin_ids() -> frozenset[int]:
    found: set[int] = set()
    for part in _clean("TG_ADMIN_IDS").replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            found.add(int(part))
    return frozenset(found)


def load_settings() -> Settings:
    return Settings(
        bot_token=_clean("TG_BOT_TOKEN"),
        admin_bot_token=_clean("TG_ADMIN_BOT_TOKEN"),
        webhook_secret=_clean("TG_WEBHOOK_SECRET"),
        admin_webhook_secret=_clean("TG_ADMIN_WEBHOOK_SECRET"),
        webapp_url=_clean("TG_WEBAPP_URL").rstrip("/"),
        webhook_base_url=_clean("TG_WEBHOOK_BASE_URL").rstrip("/"),
        shop_name=_clean("TG_SHOP_NAME", "Витрина") or "Витрина",
        admin_ids=_admin_ids(),
        database_url=_database_url(),
        checkout_hint=_clean("TG_CHECKOUT_HINT", DEFAULT_CHECKOUT) or DEFAULT_CHECKOUT,
        order_url=_clean("TG_ORDER_URL"),
        terms_text=_clean("TG_TERMS_TEXT", DEFAULT_TERMS) or DEFAULT_TERMS,
        currency=_clean("TG_CURRENCY", "₽") or "₽",
        seed_demo=_clean("TG_SEED_DEMO", "0") == "1",
        dev_open=_clean("TG_DEV_OPEN", "0") == "1",
    )


_cached: Settings | None = None


def get_settings() -> Settings:
    global _cached
    if _cached is None:
        _cached = load_settings()
    return _cached


def reset_settings() -> None:
    global _cached
    _cached = None


def public_base(settings: Settings) -> str:
    if settings.webhook_base_url:
        return settings.webhook_base_url
    if not settings.webapp_url:
        return ""
    parsed = urlparse(settings.webapp_url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def client_webapp_url(settings: Settings) -> str:
    return settings.webapp_url


def admin_webapp_url(settings: Settings) -> str:
    if not settings.webapp_url:
        return ""
    if settings.webapp_url.endswith("/admin"):
        return settings.webapp_url
    return settings.webapp_url + "/admin"


def dev_bypass_allowed() -> bool:
    settings = get_settings()
    if not settings.dev_open:
        return False
    if settings.webapp_url or settings.webhook_base_url:
        return False
    return True
