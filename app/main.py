from __future__ import annotations

import hmac
import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.catalog import (
    categories,
    count_products,
    create_product,
    delete_product,
    get_photo,
    list_products,
    save_photo,
    update_product,
)
from app.config import (
    CLOTHES_SIZES,
    ROOT,
    SHOE_SIZES,
    dev_bypass_allowed,
    get_settings,
    public_base,
)
from app.db import init_db
from app.handlers import dispatch_admin, dispatch_client
from app.telegram import secret_ok, set_menu_button, set_webhook
from app.webapp_auth import validate_init_data

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("tgshop")

STATIC = ROOT / "static"
INDEX = STATIC / "index.html"
CSP = (
    "default-src 'self'; "
    "script-src 'self' https://telegram.org; "
    "style-src 'self'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "frame-ancestors https://web.telegram.org https://*.telegram.org"
)


class ProductIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    price: int = Field(ge=0, le=10_000_000)
    category: str = Field(min_length=1, max_length=60)
    sizes: list[str] = []
    active: bool = True


class ProductPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    price: int | None = Field(default=None, ge=0, le=10_000_000)
    category: str | None = Field(default=None, min_length=1, max_length=60)
    sizes: list[str] | None = None
    active: bool | None = None


def _squash(value: str) -> str:
    return " ".join(value.split())


def sniff_image(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def safe_eq(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return hmac.compare_digest(left.encode(), right.encode())


def require_admin(request: Request) -> dict:
    settings = get_settings()
    host = request.client.host if request.client else ""
    if dev_bypass_allowed() and host in {"127.0.0.1", "::1"}:
        return {"id": 0}
    token = settings.admin_bot_token or settings.bot_token
    user = validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), token)
    if not user or int(user.get("id", 0)) not in settings.admin_ids:
        raise HTTPException(status_code=401, detail="Откройте редактор из бота-заказчика")
    return user


def register_webhooks() -> dict:
    settings = get_settings()
    base = public_base(settings)
    result = {"client": False, "admin": False}
    if not base.startswith("https://"):
        logger.info("webhook setup skipped: public https url is empty")
        return result
    if settings.bot_token and secret_ok(settings.webhook_secret):
        set_webhook(settings.bot_token, f"{base}/tg/webhook/client", settings.webhook_secret)
        if settings.webapp_url.startswith("https://"):
            set_menu_button(settings.bot_token, "Витрина", settings.webapp_url)
        result["client"] = True
    else:
        logger.warning("client webhook skipped: TG_BOT_TOKEN or TG_WEBHOOK_SECRET")
    admin_token = settings.admin_bot_token
    if admin_token and admin_token == settings.bot_token:
        logger.warning("TG_ADMIN_BOT_TOKEN совпадает с TG_BOT_TOKEN, второй вебхук не ставлю")
        return result
    if admin_token and secret_ok(settings.admin_webhook_secret):
        set_webhook(admin_token, f"{base}/tg/webhook/admin", settings.admin_webhook_secret)
        edit_url = settings.webapp_url + "/admin" if settings.webapp_url.startswith("https://") else ""
        if edit_url:
            set_menu_button(admin_token, "Правка", edit_url)
        result["admin"] = True
    elif admin_token:
        logger.warning("admin webhook skipped: TG_ADMIN_WEBHOOK_SECRET")
    return result


def register_with_retry() -> None:
    if not public_base(get_settings()).startswith("https://"):
        return
    time.sleep(3)
    for attempt in range(1, 6):
        try:
            logger.info("telegram webhooks %s", register_webhooks())
            return
        except Exception:
            logger.exception("webhook setup attempt %s", attempt)
            time.sleep(4)


def check_secret(header_value: str, expected: str) -> None:
    if not expected:
        raise HTTPException(status_code=503, detail="webhook secret is not set")
    if not safe_eq(header_value or "", expected):
        raise HTTPException(status_code=401, detail="bad secret")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    settings = get_settings()
    logger.info(
        "shop=%s client_bot=%s admin_bot=%s",
        settings.shop_name,
        bool(settings.bot_token),
        bool(settings.admin_bot_token),
    )
    threading.Thread(target=register_with_retry, daemon=True).start()
    yield


app = FastAPI(title="tg-shop", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/media/"):
        response.headers["Cache-Control"] = "public, max-age=86400"
    elif path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/api/health")
def health():
    settings = get_settings()
    count_products()
    return {
        "ok": True,
        "shop": settings.shop_name,
        "client_bot": bool(settings.bot_token),
        "admin_bot": bool(settings.admin_bot_token),
    }


@app.get("/api/meta")
def meta():
    settings = get_settings()
    return {
        "shop_name": settings.shop_name,
        "checkout_hint": settings.checkout_hint,
        "terms": settings.terms_text,
        "order_url": settings.order_url,
        "currency": settings.currency,
        "categories": categories(active_only=True),
        "clothes_sizes": CLOTHES_SIZES,
        "shoe_sizes": SHOE_SIZES,
    }


@app.get("/api/products")
def public_products():
    return list_products(active_only=True)


@app.get("/api/media/{product_id}")
def media(product_id: int):
    found = get_photo(product_id)
    if not found:
        raise HTTPException(status_code=404, detail="no photo")
    blob, mime = found
    return Response(content=blob, media_type=mime)


@app.get("/api/admin/products")
def admin_products(request: Request):
    require_admin(request)
    return list_products(active_only=False)


@app.post("/api/admin/products", status_code=201)
def admin_create(body: ProductIn, request: Request):
    require_admin(request)
    title = _squash(body.title)
    category = _squash(body.category)
    if not title or not category:
        raise HTTPException(status_code=400, detail="Проверьте название и категорию")
    product_id = create_product(
        title=title,
        price=body.price,
        category=category,
        sizes=body.sizes,
        active=body.active,
    )
    return {"id": product_id}


@app.patch("/api/admin/products/{product_id}")
def admin_patch(product_id: int, body: ProductPatch, request: Request):
    require_admin(request)
    fields = body.model_dump(exclude_unset=True)
    if "title" in fields:
        fields["title"] = _squash(fields["title"])
        if not fields["title"]:
            raise HTTPException(status_code=400, detail="Проверьте название")
    if "category" in fields:
        fields["category"] = _squash(fields["category"])
        if not fields["category"]:
            raise HTTPException(status_code=400, detail="Проверьте категорию")
    if not update_product(product_id, fields):
        raise HTTPException(status_code=404, detail="Нет такой позиции")
    return {"ok": True}


@app.post("/api/admin/products/{product_id}/photo")
async def admin_photo(product_id: int, request: Request, file: UploadFile = File(...)):
    require_admin(request)
    data = await file.read(5_000_001)
    if len(data) > 5_000_000:
        raise HTTPException(status_code=413, detail="Фото больше 5 МБ")
    mime = sniff_image(data)
    if not mime:
        raise HTTPException(status_code=400, detail="Нужен jpeg, png или webp")
    if not save_photo(product_id, data, mime):
        raise HTTPException(status_code=404, detail="Нет такой позиции")
    return {"ok": True}


@app.delete("/api/admin/products/{product_id}")
def admin_delete(product_id: int, request: Request):
    require_admin(request)
    if not delete_product(product_id):
        raise HTTPException(status_code=404, detail="Нет такой позиции")
    return {"ok": True}


@app.post("/tg/webhook/client")
async def client_webhook(request: Request):
    check_secret(request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), get_settings().webhook_secret)
    update = await _json_body(request)
    dispatch_client(update, get_settings())
    return {"ok": True}


@app.post("/tg/webhook/admin")
async def admin_webhook(request: Request):
    check_secret(
        request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""),
        get_settings().admin_webhook_secret,
    )
    update = await _json_body(request)
    dispatch_admin(update, get_settings())
    return {"ok": True}


async def _json_body(request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="bad json") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="bad json")
    return payload


@app.get("/")
def index():
    return FileResponse(INDEX, headers={"Cache-Control": "no-cache"})


@app.get("/admin")
def admin_page():
    return FileResponse(INDEX, headers={"Cache-Control": "no-cache"})


@app.get("/admin/")
def admin_slash():
    return RedirectResponse("/admin")


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.mount("/static", StaticFiles(directory=STATIC), name="static")
