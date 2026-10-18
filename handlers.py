# handlers.py
# Бот «Grand Bistro»: приветствие, приём заказов из Mini App, управление заказами администратором.

import json
import logging

from aiogram import F, Router, html, types
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from config import ADMIN_ID, WEB_APP_URL
from database import save_order, update_order_status

logger = logging.getLogger(__name__)

router = Router()


# ============================================================
# callback_data в формате order:accept:[ID]:[USER_ID]
# ============================================================
class OrderCB(CallbackData, prefix="order"):
    action: str      # accept / decline
    order_id: int
    user_id: int


# ============================================================
# Вспомогательные функции
# ============================================================
def fmt_num(value: float) -> str:
    """1200.0 -> '1200', 99.5 -> '99.50'."""
    value = float(value)
    return f"{value:.0f}" if value.is_integer() else f"{value:.2f}"


def build_receipt_body(items: list[dict], total_price: float, order_type: str, target: str) -> str:
    """Общая часть чека: тип заказа, состав, итог. Весь пользовательский ввод экранируется."""
    if order_type == "delivery":
        type_line = f"🚚 Доставка по адресу: {html.quote(target)}"
    else:
        type_line = f"🍽️ В ресторане, столик №{html.quote(target)}"

    lines = []
    for item in items:
        name = html.quote(str(item.get("name", "Блюдо")))
        qty = int(item.get("qty", 1))
        price = float(item.get("price", 0))
        # Цена в строке — стоимость позиции (количество × цена за штуку)
        lines.append(f"• {name} x {qty} — {fmt_num(qty * price)} руб.")

    return (
        f"{type_line}\n\n"
        f"<b>Состав заказа:</b>\n"
        f"{chr(10).join(lines)}\n\n"
        f"💰 <b>Итого к оплате: {fmt_num(total_price)} руб.</b>\n"
        f"Ожидайте подтверждения администратора."
    )


def admin_keyboard(order_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Принять заказ ✅",
            callback_data=OrderCB(action="accept", order_id=order_id, user_id=user_id).pack(),
        ),
        InlineKeyboardButton(
            text="Отклонить заказ ❌",
            callback_data=OrderCB(action="decline", order_id=order_id, user_id=user_id).pack(),
        ),
    ]])


# ============================================================
# /start
# ============================================================
@router.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    # Именно Reply-клавиатура: только с неё работает tg.sendData из Mini App
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="Открыть меню 🍽️", web_app=WebAppInfo(url=WEB_APP_URL))
        ]],
        resize_keyboard=True,
    )
    await message.answer(
        "Приветствуем вас в Grand Bistro! 🍷 Здесь вы можете заказать изысканные блюда "
        "с доставкой или оформить заказ прямо к вашему столику в ресторане.",
        reply_markup=keyboard,
    )


# ============================================================
# Данные из Mini App
# ============================================================
@router.message(F.content_type == types.ContentType.WEB_APP_DATA)
async def handle_web_app_data(message: types.Message) -> None:
    # 1. Разбор и проверка данных
    try:
        data = json.loads(message.web_app_data.data)
        items = data["items"]
        total_price = float(data["total_price"])
        name = str(data["name"]).strip()
        phone = str(data["phone"]).strip()
        order_type = str(data["order_type"])      # "delivery" или "table"
        target = str(data["target"]).strip()      # адрес или номер столика

        if not items or not isinstance(items, list):
            raise ValueError("Пустой заказ")
        if order_type not in ("delivery", "table"):
            raise ValueError(f"Неизвестный тип заказа: {order_type}")
        if not target:
            raise ValueError("Пустой адрес/столик")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.warning("Некорректные данные из Mini App: %s", e)
        await message.answer("😔 Не удалось обработать заказ. Пожалуйста, оформите его ещё раз.")
        return

    user_id = message.from_user.id

    # В БД тип заказа хранится как delivery / dine_in
    db_type = "delivery" if order_type == "delivery" else "dine_in"

    # 2. Сохранение в SQLite
    try:
        order_id = await save_order(
            user_id=user_id,
            items=items,
            total_price=total_price,
            client_name=name,
            client_phone=phone,
            type_order=db_type,
            table_or_address=target,
        )
    except Exception:
        logger.exception("Не удалось сохранить заказ")
        await message.answer("😔 Произошла ошибка при сохранении заказа. Попробуйте ещё раз чуть позже.")
        return

    body = build_receipt_body(items, total_price, order_type, target)

    # 3. Чек клиенту
    await message.answer(
        f"🧾 <b>Ваш заказ №{order_id} успешно оформлен!</b>\n\n{body}",
        parse_mode=ParseMode.HTML,
    )

    # 4. Карточка администратору
    admin_extra = f"👤 Клиент: {html.quote(name)}\n📞 Телефон: {html.quote(phone)}\n\n"
    try:
        await message.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🚨 <b>НОВЫЙ ЗАКАЗ №{order_id}!</b>\n\n{admin_extra}{body}",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(order_id, user_id),
        )
    except TelegramAPIError as e:
        # Заказ уже сохранён, поэтому только логируем
        logger.error("Не удалось отправить заказ №%s администратору: %s", order_id, e)


# ============================================================
# Callback-кнопки администратора
# ============================================================
@router.callback_query(OrderCB.filter(F.action == "accept"))
async def accept_order(callback: types.CallbackQuery, callback_data: OrderCB) -> None:
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    order_id = callback_data.order_id

    if not await update_order_status(order_id, "preparing"):
        await callback.answer("Заказ не найден в базе", show_alert=True)
        return

    # Уведомляем клиента
    warning = ""
    try:
        await callback.bot.send_message(
            chat_id=callback_data.user_id,
            text=f"👨‍🍳 Ваш заказ №{order_id} передан на кухню! "
                 f"Шеф-повар уже начал готовить ваши блюда.",
        )
    except TelegramAPIError:
        warning = "\n⚠️ Не удалось уведомить клиента."

    # Обновляем карточку админа и убираем кнопки
    await callback.message.edit_text(
        f"{callback.message.html_text}\n\n✅ <b>Заказ №{order_id} принят и готовится.</b>{warning}",
        parse_mode=ParseMode.HTML,
        reply_markup=None,
    )
    await callback.answer("Заказ принят")


@router.callback_query(OrderCB.filter(F.action == "decline"))
async def decline_order(callback: types.CallbackQuery, callback_data: OrderCB) -> None:
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    order_id = callback_data.order_id

    if not await update_order_status(order_id, "cancelled"):
        await callback.answer("Заказ не найден в базе", show_alert=True)
        return

    warning = ""
    try:
        await callback.bot.send_message(
            chat_id=callback_data.user_id,
            text=f"❌ К сожалению, ресторан отменил ваш заказ №{order_id}. "
                 f"Пожалуйста, свяжитесь с поддержкой или попробуйте оформить заказ заново.",
        )
    except TelegramAPIError:
        warning = "\n⚠️ Не удалось уведомить клиента."

    # Сообщение админа заменяется целиком, кнопки убираются
    await callback.message.edit_text(
        f"❌ Заказ №{order_id} отклонен.{warning}",
        reply_markup=None,
    )
    await callback.answer("Заказ отклонён")