# database.py
# Работа с базой заказов ресторана (SQLite через aiosqlite).

import json
import os
from typing import Any

import aiosqlite

from config import DB_PATH

# Допустимые значения (используются и в CHECK-ограничениях таблицы, и в проверках)
ORDER_TYPES = ("delivery", "dine_in")                       # доставка / в ресторане
ORDER_STATUSES = ("new", "preparing", "ready", "cancelled")


async def init_db() -> None:
    """
    Создаёт таблицу orders, если её ещё нет.
    Вызывать один раз при старте приложения.
    """
    # Если DB_PATH содержит папку (например /var/data/...), создаём её при необходимости
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL,       -- Telegram ID клиента
                items_json       TEXT    NOT NULL,       -- список блюд в JSON
                total_price      REAL    NOT NULL,       -- итоговая сумма
                client_name      TEXT    NOT NULL,       -- имя клиента
                client_phone     TEXT    NOT NULL,       -- телефон клиента
                type_order       TEXT    NOT NULL        -- delivery / dine_in
                    CHECK (type_order IN ('delivery', 'dine_in')),
                table_or_address TEXT    NOT NULL,       -- адрес доставки или номер столика
                status           TEXT    NOT NULL DEFAULT 'new'
                    CHECK (status IN ('new', 'preparing', 'ready', 'cancelled')),
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()


async def save_order(
    user_id: int,
    items: list[dict[str, Any]],
    total_price: float,
    client_name: str,
    client_phone: str,
    type_order: str,
    table_or_address: str,
) -> int:
    """
    Сохраняет новый заказ и возвращает его id.

    :param items: список блюд, например
                  [{"name": "Борщ", "qty": 2, "price": 250}]
    :param type_order: "delivery" (доставка) или "dine_in" (в ресторане)
    :param table_or_address: адрес доставки либо номер столика
    """
    if type_order not in ORDER_TYPES:
        raise ValueError(f"type_order должен быть одним из {ORDER_TYPES}, получено: {type_order!r}")

    # ensure_ascii=False, чтобы кириллица хранилась читаемо, а не как \uXXXX
    items_json = json.dumps(items, ensure_ascii=False)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO orders (
                user_id, items_json, total_price, client_name,
                client_phone, type_order, table_or_address
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                items_json,
                total_price,
                client_name,
                client_phone,
                type_order,
                table_or_address,
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def update_order_status(order_id: int, status: str) -> bool:
    """
    Обновляет статус заказа: new, preparing, ready или cancelled.
    Возвращает True, если заказ найден и обновлён.
    """
    if status not in ORDER_STATUSES:
        raise ValueError(f"status должен быть одним из {ORDER_STATUSES}, получено: {status!r}")

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, order_id),
        )
        await db.commit()
        return cursor.rowcount > 0