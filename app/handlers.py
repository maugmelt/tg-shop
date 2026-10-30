from __future__ import annotations

import json
import logging

from app.catalog import (
    clear_draft,
    create_product,
    delete_product,
    format_product_list,
    get_draft,
    parse_price,
    parse_sizes,
    save_draft,
    set_active,
)
from app.config import Settings, admin_webapp_url, client_webapp_url
from app.telegram import download_file, send_message

logger = logging.getLogger("tgshop")

ADMIN_COMMANDS = {"/add", "/list", "/hide", "/show", "/del", "/cancel", "/skip"}
ADMIN_HELP = (
    "Редактор витрины.\n\n"
    "/add — новая вещь\n"
    "/list — все позиции\n"
    "/hide 12 — скрыть\n"
    "/show 12 — показать\n"
    "/del 12 — удалить\n"
    "/cancel — сбросить черновик\n\n"
    "Кнопка ниже открывает форму. Клиентам отдайте другого бота."
)


def command_name(text: str) -> str | None:
    if not text.startswith("/"):
        return None
    return text.split()[0].split("@", 1)[0].lower()


def second_int(text: str) -> int | None:
    parts = text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return None
    return int(parts[1])


def webapp_keyboard(text: str, url: str) -> dict | None:
    if not url.startswith("https://"):
        return None
    return {"inline_keyboard": [[{"text": text, "web_app": {"url": url}}]]}


def admin_markup(settings: Settings) -> dict | None:
    rows = []
    edit_url = admin_webapp_url(settings)
    catalog_url = client_webapp_url(settings)
    if edit_url.startswith("https://"):
        rows.append([{"text": "Редактировать витрину", "web_app": {"url": edit_url}}])
    if catalog_url.startswith("https://"):
        rows.append([{"text": "Открыть каталог", "web_app": {"url": catalog_url}}])
    if not rows:
        return None
    return {"inline_keyboard": rows}


def editor_token(settings: Settings) -> str:
    return settings.admin_bot_token or settings.bot_token


def _say(token: str, chat_id: str, text: str, markup: dict | None = None) -> None:
    send_message(token, chat_id, text, markup)


def handle_admin_message(message: dict, settings: Settings) -> None:
    chat_id = str(message["chat"]["id"])
    user_id = int(message["from"]["id"])
    token = editor_token(settings)
    text = (message.get("text") or "").strip()
    cmd = command_name(text)
    photos = message.get("photo") or []
    file_id = photos[-1]["file_id"] if photos else None

    if not token:
        logger.warning("admin token is empty")
        return
    if user_id not in settings.admin_ids:
        _say(token, chat_id, "Редактировать витрину может только id из TG_ADMIN_IDS.")
        return

    if cmd in ("/start", "/help"):
        clear_draft(chat_id)
        _say(token, chat_id, ADMIN_HELP, admin_markup(settings))
        return
    if cmd == "/cancel":
        clear_draft(chat_id)
        _say(token, chat_id, "Черновик сброшен.")
        return
    if cmd == "/list":
        _say(token, chat_id, format_product_list())
        return
    if cmd in ("/del", "/hide", "/show"):
        product_id = second_int(text)
        if product_id is None:
            _say(token, chat_id, "Укажите номер. Пример: /hide 3")
            return
        if cmd == "/del":
            ok = delete_product(product_id)
            _say(token, chat_id, "Удалено." if ok else "Нет такой позиции.")
        elif cmd == "/hide":
            ok = set_active(product_id, False)
            _say(token, chat_id, "Скрыто с витрины." if ok else "Нет такой позиции.")
        else:
            ok = set_active(product_id, True)
            _say(token, chat_id, "Снова на витрине." if ok else "Нет такой позиции.")
        return
    if cmd == "/add":
        save_draft(chat_id, step="title", title="", price=None, category="", sizes="[]")
        _say(token, chat_id, "Название вещи?")
        return

    draft = get_draft(chat_id)
    if draft is None:
        _say(token, chat_id, "Команды: /add, /list, /hide, /show, /del. Или откройте форму кнопкой.", admin_markup(settings))
        return

    step = draft["step"]
    if step == "title":
        if not text or text.startswith("/") or len(text) > 120:
            _say(token, chat_id, "Пришлите название текстом, до 120 символов.")
            return
        save_draft(chat_id, step="price", title=" ".join(text.split()))
        _say(token, chat_id, "Цена в рублях? Например: 5600")
        return
    if step == "price":
        price = parse_price(text)
        if price is None:
            _say(token, chat_id, "Не вижу цену. Пришлите число, например 5600.")
            return
        save_draft(chat_id, step="category", price=price)
        _say(token, chat_id, "Категория? Например: Куртки")
        return
    if step == "category":
        category = " ".join(text.split())
        if not category or category.startswith("/") or len(category) > 40:
            _say(token, chat_id, "Пришлите короткую категорию, например Куртки.")
            return
        save_draft(chat_id, step="sizes", category=category)
        _say(token, chat_id, "Размеры через пробел: S M L или 42 43. Если размера нет — пришлите -")
        return
    if step == "sizes":
        if text.strip() == "-":
            sizes: list[str] = []
        else:
            sizes = parse_sizes(text)
            if text.strip() and not sizes:
                _say(token, chat_id, "Не разобрал размеры. Пример: S M L или 41 42. Либо -")
                return
        save_draft(chat_id, step="photo", sizes=json.dumps(sizes, ensure_ascii=False))
        _say(token, chat_id, "Пришлите фото вещи или /skip")
        return
    if step == "photo":
        blob: bytes | None = None
        mime: str | None = None
        if cmd == "/skip":
            pass
        elif file_id:
            try:
                blob = download_file(token, file_id)
            except Exception:
                logger.exception("photo download failed")
                _say(token, chat_id, "Не смог забрать фото из Telegram. Пришлите ещё раз или /skip")
                return
            if len(blob) > 5_000_000:
                _say(token, chat_id, "Фото больше 5 МБ. Пришлите поменьше или /skip")
                return
            mime = "image/jpeg"
        else:
            _say(token, chat_id, "Жду фото или /skip")
            return
        fresh = get_draft(chat_id) or draft
        product_id = create_product(
            title=fresh["title"],
            price=int(fresh["price"]),
            category=fresh["category"],
            sizes=json.loads(fresh["sizes"] or "[]"),
            photo=blob,
            photo_mime=mime,
            active=True,
        )
        clear_draft(chat_id)
        _say(token, chat_id, f"Добавлено, номер {product_id}. На витрине уже видно.")


def handle_client_message(message: dict, settings: Settings) -> None:
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()
    cmd = command_name(text)
    if not settings.bot_token:
        logger.warning("client token is empty")
        return
    markup = webapp_keyboard("Открыть каталог", client_webapp_url(settings))
    if cmd in ("/start", "/help", "/catalog"):
        note = ""
        if not settings.webapp_url:
            note = "\n\nСсылка витрины появится после TG_WEBAPP_URL."
        send_message(
            settings.bot_token,
            chat_id,
            "Каталог одежды. Откройте витрину, соберите корзину и пришлите скриншот сюда для оформления." + note,
            markup,
        )
        return
    send_message(
        settings.bot_token,
        chat_id,
        "Откройте витрину кнопкой ниже. Когда корзина готова, пришлите её скриншот в этот чат.",
        markup,
    )


def dispatch_client(update: dict, settings: Settings) -> None:
    message = update.get("message") or {}
    if not message.get("chat") or not message.get("from"):
        return
    user_id = int(message["from"]["id"])
    text = (message.get("text") or "").strip()
    cmd = command_name(text)
    same_bot = not settings.admin_bot_token or settings.admin_bot_token == settings.bot_token
    draft = get_draft(str(message["chat"]["id"]))
    if same_bot and user_id in settings.admin_ids and (cmd in ADMIN_COMMANDS or draft):
        handle_admin_message(message, settings)
        return
    handle_client_message(message, settings)


def dispatch_admin(update: dict, settings: Settings) -> None:
    message = update.get("message") or {}
    if not message.get("chat") or not message.get("from"):
        return
    handle_admin_message(message, settings)
