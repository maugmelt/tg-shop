from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from sqlalchemy import delete, func, insert, select

from app.config import CLOTHES_SIZES, get_settings
from app.db import drafts, get_engine, products

_CLOTHES = set(CLOTHES_SIZES)
_SHOES = {str(size) for size in range(36, 46)}
_CYR = str.maketrans({"Х": "X", "М": "M", "Л": "L"})


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def format_price(value: int, currency: str) -> str:
    grouped = f"{int(value):,}".replace(",", " ")
    return f"{grouped} {currency or '₽'}"


def parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text or "")
    if not digits:
        return None
    value = int(digits)
    if value > 10_000_000:
        return None
    return value


def normalize_sizes(items: list[str]) -> list[str]:
    found: list[str] = []
    for raw in items:
        token = str(raw).strip().upper().translate(_CYR)
        if token in _CLOTHES or token in _SHOES:
            if token not in found:
                found.append(token)
    return found


def parse_sizes(text: str) -> list[str]:
    parts = [part for part in re.split(r"[,;/]+|\s+", (text or "").strip()) if part and part != "-"]
    return normalize_sizes(parts)


def _to_dict(row: dict, currency: str) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "price": row["price"],
        "price_label": format_price(row["price"], currency),
        "category": row["category"],
        "sizes": json.loads(row["sizes"] or "[]"),
        "active": bool(row["active"]),
        "sort_order": row["sort_order"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "has_photo": bool(row["has_photo"]),
    }


def list_products(active_only: bool) -> list[dict]:
    currency = get_settings().currency
    stmt = select(
        products.c.id,
        products.c.title,
        products.c.price,
        products.c.category,
        products.c.sizes,
        products.c.active,
        products.c.sort_order,
        products.c.created_at,
        products.c.updated_at,
        products.c.photo.is_not(None).label("has_photo"),
    ).order_by(products.c.sort_order.asc(), products.c.id.asc())
    if active_only:
        stmt = stmt.where(products.c.active == 1)
    with get_engine().connect() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [_to_dict(dict(row), currency) for row in rows]


def categories(active_only: bool = True) -> list[str]:
    order_col = func.min(products.c.sort_order)
    stmt = select(products.c.category, order_col).group_by(products.c.category).order_by(order_col)
    if active_only:
        stmt = stmt.where(products.c.active == 1)
    with get_engine().connect() as conn:
        return [row[0] for row in conn.execute(stmt)]


def count_products() -> int:
    with get_engine().connect() as conn:
        return int(conn.execute(select(func.count()).select_from(products)).scalar_one())


def _next_sort() -> int:
    with get_engine().connect() as conn:
        current = conn.execute(select(func.max(products.c.sort_order))).scalar()
    return 0 if current is None else int(current) + 1


def create_product(
    *,
    title: str,
    price: int,
    category: str,
    sizes: list[str],
    photo: bytes | None = None,
    photo_mime: str | None = None,
    active: bool = True,
    sort_order: int | None = None,
) -> int:
    stamp = now()
    with get_engine().begin() as conn:
        result = conn.execute(
            insert(products).values(
                title=title,
                price=price,
                category=category,
                sizes=json.dumps(normalize_sizes(sizes), ensure_ascii=False),
                photo=photo,
                photo_mime=photo_mime,
                active=1 if active else 0,
                sort_order=_next_sort() if sort_order is None else sort_order,
                created_at=stamp,
                updated_at=stamp,
            )
        )
        return int(result.inserted_primary_key[0])


def update_product(product_id: int, fields: dict) -> bool:
    payload: dict = {}
    for key, value in fields.items():
        if key == "sizes":
            payload["sizes"] = json.dumps(normalize_sizes(value), ensure_ascii=False)
        elif key == "active":
            payload["active"] = 1 if value else 0
        elif key in {"title", "price", "category"}:
            payload[key] = value
    if not payload:
        return False
    payload["updated_at"] = now()
    with get_engine().begin() as conn:
        result = conn.execute(products.update().where(products.c.id == product_id).values(**payload))
        return result.rowcount > 0


def set_active(product_id: int, active: bool) -> bool:
    return update_product(product_id, {"active": active})


def delete_product(product_id: int) -> bool:
    with get_engine().begin() as conn:
        result = conn.execute(delete(products).where(products.c.id == product_id))
        return result.rowcount > 0


def save_photo(product_id: int, blob: bytes, mime: str) -> bool:
    with get_engine().begin() as conn:
        result = conn.execute(
            products.update()
            .where(products.c.id == product_id)
            .values(photo=blob, photo_mime=mime, updated_at=now())
        )
        return result.rowcount > 0


def get_photo(product_id: int) -> tuple[bytes, str] | None:
    stmt = select(products.c.photo, products.c.photo_mime).where(products.c.id == product_id)
    with get_engine().connect() as conn:
        row = conn.execute(stmt).first()
    if not row or not row.photo:
        return None
    return bytes(row.photo), row.photo_mime or "image/jpeg"


def get_draft(chat_id: str) -> dict | None:
    stmt = select(drafts).where(drafts.c.chat_id == str(chat_id))
    with get_engine().connect() as conn:
        row = conn.execute(stmt).mappings().first()
    return dict(row) if row else None


def save_draft(chat_id: str, **fields) -> None:
    current = get_draft(chat_id) or {
        "chat_id": str(chat_id),
        "step": "title",
        "title": "",
        "price": None,
        "category": "",
        "sizes": "[]",
    }
    current["chat_id"] = str(chat_id)
    current.update(fields)
    with get_engine().begin() as conn:
        conn.execute(delete(drafts).where(drafts.c.chat_id == str(chat_id)))
        conn.execute(insert(drafts).values(**current))


def clear_draft(chat_id: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(delete(drafts).where(drafts.c.chat_id == str(chat_id)))


def jacket_svg(tone: str) -> bytes:
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="600" height="800" viewBox="0 0 300 400">
      <rect width="300" height="400" fill="#0c0c0c"/>
      <path d="M78 168 L112 96 H188 L222 168 L268 214 V340 H32 V214 Z" fill="{tone}"/>
      <path d="M112 96 L150 132 L188 96" fill="none" stroke="#0c0c0c" stroke-width="8"/>
    </svg>"""
    return svg.encode()


def seed_demo() -> None:
    if not get_settings().seed_demo or count_products() > 0:
        return
    samples = [
        ("Кожаная куртка с мехом", 5600, "Куртки", ["S", "M", "L"], "#1a1a1a"),
        ("Куртка с капюшоном", 9600, "Куртки", ["M", "L", "XL"], "#241c16"),
        ("Зимний бомбер", 8200, "Куртки", ["S", "M", "L", "XL"], "#141414"),
        ("Укороченный пуховик", 5600, "Куртки", ["XS", "S", "M"], "#2a2118"),
    ]
    for index, (title, price, category, sizes, tone) in enumerate(samples):
        create_product(
            title=title,
            price=price,
            category=category,
            sizes=sizes,
            photo=jacket_svg(tone),
            photo_mime="image/svg+xml",
            sort_order=index,
        )


def format_product_list() -> str:
    rows = list_products(active_only=False)
    if not rows:
        return "Витрина пустая. /add — добавить вещь."
    lines = []
    for row in rows[:40]:
        flag = "на витрине" if row["active"] else "скрыто"
        sizes = " ".join(row["sizes"]) or "без размера"
        lines.append(
            f"{row['id']}. {row['title']} — {row['price_label']} — {row['category']} — {sizes} — {flag}"
        )
    if len(rows) > 40:
        lines.append(f"…ещё {len(rows) - 40}")
    text = "\n".join(lines)
    return text[:4000]
