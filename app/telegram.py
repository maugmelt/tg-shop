from __future__ import annotations

import re

import httpx

_API = "https://api.telegram.org"
_SECRET_OK = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


def secret_ok(secret: str) -> bool:
    return bool(_SECRET_OK.fullmatch(secret or ""))


def api(token: str, method: str, payload: dict | None = None) -> dict:
    response = httpx.post(f"{_API}/bot{token}/{method}", json=payload or {}, timeout=30)
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("Telegram вернул не JSON") from exc
    if not data.get("ok"):
        raise RuntimeError(data.get("description") or "ошибка Telegram")
    return data["result"]


def send_message(token: str, chat_id: int | str, text: str, reply_markup: dict | None = None) -> dict:
    payload: dict = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return api(token, "sendMessage", payload)


def set_webhook(token: str, url: str, secret: str) -> dict:
    return api(
        token,
        "setWebhook",
        {
            "url": url,
            "secret_token": secret,
            "allowed_updates": ["message"],
            "drop_pending_updates": False,
        },
    )


def set_menu_button(token: str, text: str, url: str) -> dict:
    return api(
        token,
        "setChatMenuButton",
        {"menu_button": {"type": "web_app", "text": text, "web_app": {"url": url}}},
    )


def download_file(token: str, file_id: str) -> bytes:
    meta = api(token, "getFile", {"file_id": file_id})
    path = meta["file_path"]
    response = httpx.get(f"{_API}/file/bot{token}/{path}", timeout=30)
    response.raise_for_status()
    return response.content
