from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


def validate_init_data(init_data: str, bot_token: str, max_age: int = 7 * 24 * 3600) -> dict | None:
    if not init_data or not bot_token:
        return None
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received = parsed.pop("hash", "")
    if not received:
        return None
    data_check = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received):
        return None
    try:
        auth_date = int(parsed.get("auth_date") or "0")
        user = json.loads(parsed.get("user") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    now = int(time.time())
    if auth_date <= 0 or auth_date > now + 30 or now - auth_date > max_age:
        return None
    if not isinstance(user, dict) or "id" not in user:
        return None
    return user
