import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from app.catalog import normalize_sizes, parse_price
from app.config import dev_bypass_allowed, reset_settings
from app.main import app

ADMIN_TOKEN = "222:ADMIN"


def make_init(token: str, user_id: int) -> str:
    user = json.dumps({"id": user_id, "first_name": "A"}, separators=(",", ":"))
    pairs = {"auth_date": str(int(time.time())), "user": user}
    data_check = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    sign = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**pairs, "hash": sign})


def test_price_and_sizes():
    assert parse_price("5 600 ₽") == 5600
    assert parse_price("нет") is None
    assert normalize_sizes(["s", "42", "хл", "10"]) == ["S", "42", "XL"]


def test_dev_bypass_stays_off_on_public_url(monkeypatch):
    monkeypatch.setenv("TG_DEV_OPEN", "1")
    monkeypatch.setenv("TG_WEBAPP_URL", "https://shop.example")
    reset_settings()
    try:
        assert dev_bypass_allowed() is False
    finally:
        monkeypatch.setenv("TG_DEV_OPEN", "0")
        monkeypatch.setenv("TG_WEBAPP_URL", "")
        reset_settings()


def test_catalog_admin_and_pages():
    init = make_init(ADMIN_TOKEN, 42)
    stranger = make_init(ADMIN_TOKEN, 7)
    with TestClient(app) as client:
        assert client.get("/api/health").json()["ok"] is True
        assert "Витрина" in client.get("/").text
        assert client.get("/admin").status_code == 200
        assert client.get("/static/app.js").status_code == 200

        denied = client.post(
            "/api/admin/products",
            json={"title": "Секрет", "price": 100, "category": "Куртки", "sizes": ["M"]},
        )
        assert denied.status_code == 401

        denied_user = client.post(
            "/api/admin/products",
            headers={"X-Telegram-Init-Data": stranger},
            json={"title": "Секрет", "price": 100, "category": "Куртки", "sizes": ["M"]},
        )
        assert denied_user.status_code == 401

        created = client.post(
            "/api/admin/products",
            headers={"X-Telegram-Init-Data": init},
            json={"title": "Кожаная куртка", "price": 5600, "category": "Куртки", "sizes": ["s", "m"]},
        )
        assert created.status_code == 201
        product_id = created.json()["id"]

        photo = client.post(
            f"/api/admin/products/{product_id}/photo",
            headers={"X-Telegram-Init-Data": init},
            files={"file": ("a.jpg", b"\xff\xd8\xff\x00", "image/jpeg")},
        )
        assert photo.status_code == 200
        media = client.get(f"/api/media/{product_id}")
        assert media.status_code == 200
        assert media.content.startswith(b"\xff\xd8\xff")

        listed = client.get("/api/products").json()
        assert any(item["title"] == "Кожаная куртка" and item["sizes"] == ["S", "M"] for item in listed)

        hidden = client.patch(
            f"/api/admin/products/{product_id}",
            headers={"X-Telegram-Init-Data": init},
            json={"active": False},
        )
        assert hidden.status_code == 200
        assert all(item["id"] != product_id for item in client.get("/api/products").json())


def test_webhooks_and_admin_add(monkeypatch):
    sent = []

    def fake_send(_token, _chat_id, text, _markup=None):
        sent.append(text)

    monkeypatch.setattr("app.handlers.send_message", fake_send)
    headers = {"X-Telegram-Bot-Api-Secret-Token": "admin-secret"}

    def post(client, text):
        return client.post(
            "/tg/webhook/admin",
            json={"message": {"chat": {"id": 42}, "from": {"id": 42}, "text": text}},
            headers=headers,
        )

    with TestClient(app) as client:
        bad = client.post(
            "/tg/webhook/client",
            json={"message": {"chat": {"id": 7}, "from": {"id": 7}, "text": "/start"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "nope"},
        )
        assert bad.status_code == 401

        start = client.post(
            "/tg/webhook/client",
            json={"message": {"chat": {"id": 7}, "from": {"id": 7}, "text": "/start"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "client-secret"},
        )
        assert start.status_code == 200
        assert "Каталог одежды" in sent[-1]

        stranger = client.post(
            "/tg/webhook/admin",
            json={"message": {"chat": {"id": 9}, "from": {"id": 9}, "text": "/add"}},
            headers=headers,
        )
        assert stranger.status_code == 200
        assert "TG_ADMIN_IDS" in sent[-1]

        assert post(client, "/add").status_code == 200
        assert post(client, "Тестовая куртка").status_code == 200
        assert post(client, "5600").status_code == 200
        assert post(client, "Куртки").status_code == 200
        assert post(client, "S M").status_code == 200
        assert post(client, "/skip").status_code == 200
        listed = client.get("/api/products").json()
        assert any(item["title"] == "Тестовая куртка" and item["price"] == 5600 for item in listed)
