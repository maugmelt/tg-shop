# tg-shop

Личный каталог одежды: бот-витрина с мини-приложением и бот-редактор. Это отдельный сервис, его не нужно подключать к рабочему проекту.

Клиент открывает каталог, фильтрует размер, собирает избранное и корзину, затем присылает скриншот в Telegram. Заказчик правит позиции вторым ботом или формой `/admin`.

## Переменные

Все настройки называются с префикса `TG_`. Список лежит в `.env.example`. Секреты в git не коммитить.

`TG_DEV_OPEN=1` открывает редактор только на своей машине и только пока пустые `TG_WEBAPP_URL` и `TG_WEBHOOK_BASE_URL`. На Render его оставляют `0`.

Без `TG_DATABASE_URL` каталог пишется в SQLite. На бесплатном Render диск временный: после сна или деплоя товары пропадут. Для постоянной витрины нужна своя Postgres, строка подключения — в `TG_DATABASE_URL`.

## Локально

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

## Render

Новый Web Service, не существующий рабочий. Если репозиторий — только эта папка, Root Directory пустой. Если репозиторий весь рабочий каталог, Root Directory = `tg-shop`.

Blueprint: `render.yaml`. После первого адреса сервиса:

- `TG_WEBAPP_URL` = `https://<сервис>.onrender.com`
- `TG_BOT_TOKEN` и `TG_ADMIN_BOT_TOKEN` — два разных бота из BotFather
- `TG_WEBHOOK_SECRET` и `TG_ADMIN_WEBHOOK_SECRET` — случайные строки из латиницы, цифр, `_` и `-`
- `TG_ADMIN_IDS` — числовой Telegram id заказчика

Сервис сам вызовет setWebhook, когда эти значения уже заданы. Порт слушает переменную `PORT`, её добавляет сам Render, в список `TG_` она не входит.
