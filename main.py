import asyncio
import logging
import os
from datetime import datetime

import requests
import pytz
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

from db import init_db, load_user_settings, save_user_settings, get_all_users

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()

CURRENCY_URL = "https://www.cbr-xml-daily.ru/daily_json.js"

CURRENCY_TO_COUNTRY = {
    "USD": "US",
    "EUR": "EU",
    "RUB": "RU",
    "CNY": "CN",
    "GBP": "GB",
    "JPY": "JP",
    "TRY": "TR",
    "KZT": "KZ",
    "IDR": "ID",
    "VND": "VN",
    "THB": "TH",
    "AED": "AE",
    "KGS": "KG",
    "SGD": "SG"
}

popular_timezones = [
    "Europe/Moscow", "Europe/London", "Europe/Berlin", "Asia/Tokyo",
    "Asia/Shanghai", "Asia/Bangkok", "Asia/Almaty", "Asia/Kolkata",
    "Asia/Dubai", "America/New_York", "America/Los_Angeles",
    "America/Sao_Paulo", "Africa/Cairo", "Australia/Sydney"
]


def country_flag(country_code: str) -> str:
    return ''.join(chr(127397 + ord(c)) for c in country_code.upper())


def get_flag_by_currency(code: str) -> str:
    country = CURRENCY_TO_COUNTRY.get(code)
    return country_flag(country) if country else ""


async def fetch_currencies():
    response = requests.get(CURRENCY_URL)
    data = response.json()
    currencies = list(data["Valute"].keys())
    currencies.append("RUB")
    rates = {"RUB": 1.0}
    for code, details in data["Valute"].items():
        rates[code] = details["Value"] / details["Nominal"]
    return currencies, rates


async def format_currency_text(code: str, value: float, target_column: int, is_base=False) -> str:
    flag = get_flag_by_currency(code)
    if flag:
        code_with_flag = f"{flag} {code}"
    else:
        code_with_flag = code

    value_part = f"{value:,.2f}".replace(",", " ")  # Форматируем число красиво с пробелами: 1 000 000.00

    spaces_needed = target_column - len(code_with_flag)
    spaces_needed = max(spaces_needed, 1)  # хотя бы один пробел

    if is_base:
        left_spaces = spaces_needed // 2
        right_spaces = spaces_needed - left_spaces
        spaces = " " * left_spaces + "⭐" + " " * right_spaces
    else:
        spaces = " " * spaces_needed

    return f"{code_with_flag}{spaces}{value_part}"


def build_reply_keyboard():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [
                types.KeyboardButton(text="+1"),
                types.KeyboardButton(text="+10"),
                types.KeyboardButton(text="+100"),
                types.KeyboardButton(text="+1000"),
                types.KeyboardButton(text="+1000000"),
            ],
            [
                types.KeyboardButton(text="×2"),
                types.KeyboardButton(text="×10"),
                types.KeyboardButton(text="÷2"),
                types.KeyboardButton(text="÷10"),
                types.KeyboardButton(text="🔄")
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )


async def build_rates_keyboard(selected_currencies, base_currency, rates, amount):
    builder = InlineKeyboardBuilder()

    # Сначала собираем все value_part, чтобы понять максимальную длину
    values = {}
    for currency in selected_currencies:
        if currency == base_currency:
            values[currency] = amount
        else:
            values[currency] = (rates[base_currency] / rates[currency]) * amount

    # Найти максимальную длину числа для правильного выравнивания
    max_value_length = max(len(f"{v:,.2f}".replace(",", " ")) for v in values.values())
    target_column = 40 - max_value_length  # оставляем место для самого длинного числа

    # Теперь создаём кнопки
    for currency in selected_currencies:
        value = values[currency]
        text = await format_currency_text(
            code=currency,
            value=value,
            target_column=target_column,
            is_base=(currency == base_currency)
        )
        builder.button(text=text, callback_data=f"base_{currency}")

    builder.button(text="🔙 Изменить выбор валют", callback_data="back_to_selection")
    builder.adjust(1)
    return builder.as_markup()


async def build_currency_keyboard(all_currencies, selected_currencies):
    builder = InlineKeyboardBuilder()
    for idx, currency in enumerate(all_currencies):
        if currency in selected_currencies:
            text = f"✅ {currency}"
        else:
            text = f"❌ {currency}"
        builder.button(text=text, callback_data=f"select_{currency}")
        if (idx + 1) % 4 == 0:
            builder.adjust(4)

    builder.button(text="➡️ Показать курсы", callback_data="show_rates")
    builder.adjust(4)
    return builder.as_markup()


async def delete_user_message(message: types.Message):
    try:
        await message.delete()
    except Exception:
        pass


async def send_welcome_message(chat_id: int):
    await bot.send_message(
        chat_id=chat_id,
        text="Добро пожаловать!",
        reply_markup=build_reply_keyboard()
    )


async def recreate_dynamic_message(user_id: int, text: str, reply_markup):
    settings = await load_user_settings(user_id)

    # Удаляем старое динамическое сообщение, если есть
    if settings.get("msg_id"):
        try:
            await bot.delete_message(chat_id=settings["chat_id"], message_id=settings["msg_id"])
        except Exception:
            pass

    sent = await bot.send_message(
        chat_id=settings["chat_id"],
        text=text,
        reply_markup=reply_markup
    )
    settings["msg_id"] = sent.message_id
    settings["message_sent_at"] = datetime.now()
    await save_user_settings(user_id, settings)


async def update_dynamic_message(user_id: int, text: str, reply_markup):
    settings = await load_user_settings(user_id)

    try:
        await bot.edit_message_text(
            chat_id=settings["chat_id"],
            message_id=settings["msg_id"],
            text=text,
            reply_markup=reply_markup
        )
    except Exception:
        pass


async def show_currency_selection(user_id: int):
    currencies, _ = await fetch_currencies()
    settings = await load_user_settings(user_id)
    keyboard = await build_currency_keyboard(currencies, settings.get("selected", []))
    await recreate_dynamic_message(user_id, "Выберите валюты для отслеживания:", keyboard)


async def show_rates(user_id: int):
    currencies, rates = await fetch_currencies()
    settings = await load_user_settings(user_id)

    selected = settings.get("selected", [])
    base_currency = settings.get("base")
    amount = settings.get("amount", 1.0)

    if not selected:
        return

    if not base_currency or base_currency not in selected:
        base_currency = selected[0]
        settings["base"] = base_currency
        await save_user_settings(user_id, settings)

    tz_name = settings.get("timezone", "UTC")
    tz = pytz.timezone(tz_name)
    now = datetime.now(pytz.utc).astimezone(tz)

    text = f"Курсы валют\nОбновлено: {now.strftime('%d.%m.%Y %H:%M:%S')}"
    keyboard = await build_rates_keyboard(selected, base_currency, rates, amount)
    await update_dynamic_message(user_id, text, keyboard)


@dp.message(CommandStart())
async def start(message: types.Message):
    await delete_user_message(message)
    user_id = message.from_user.id

    settings = await load_user_settings(user_id)

    settings.update({
        "chat_id": message.chat.id,
        "recent_amounts": [],
        "amount": 1.0,
        "msg_id": None,
        "message_sent_at": None,
    })

    await save_user_settings(user_id, settings)

    selected = settings.get("selected", [])

    if selected:
        # Если уже есть выбранные валюты, сразу показываем курсы
        await show_rates(user_id)
    else:
        # Всегда отправляем приветственное сообщение с Reply клавиатурой
        await send_welcome_message(message.chat.id)
        # Если валют ещё нет — показываем выбор валют
        await show_currency_selection(user_id)


@dp.message(Command("restart"))
async def restart(message: types.Message):
    await delete_user_message(message)
    user_id = message.from_user.id

    # Полная очистка данных пользователя
    settings = {
        "chat_id": message.chat.id,
        "recent_amounts": [],
        "selected": [],
        "base": None,
        "amount": 1.0,
        "msg_id": None,
        "message_sent_at": None,
    }
    await save_user_settings(user_id, settings)

    # Отправляем приветственное сообщение с ReplyKeyboard
    await send_welcome_message(message.chat.id)

    # Отправляем выбор валют
    await show_currency_selection(user_id)


@dp.message(Command("refresh"))
async def refresh(message: types.Message):
    await delete_user_message(message)

    user_id = message.from_user.id
    await show_rates(user_id)


@dp.message(Command("setting"))
async def settings_menu(message: types.Message):
    await delete_user_message(message)
    user_id = message.from_user.id

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🌐 Настроить часовой пояс", callback_data="set_timezone")
    keyboard.button(text="💱 Настроить валюты", callback_data="set_currencies")
    keyboard.adjust(1)

    settings = await load_user_settings(user_id)
    await update_dynamic_message(
        user_id,
        "Что вы хотите настроить?",
        keyboard.as_markup()
    )


@dp.message()
async def handle_user_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()

    settings = await load_user_settings(user_id)

    try:
        if text.startswith("+"):
            delta = float(text[1:])
            settings["amount"] += delta
        elif text.startswith("×") or text.startswith("*"):
            factor = float(text[1:])
            settings["amount"] *= factor
        elif text.startswith("/") or text.startswith("÷"):
            divisor = float(text[1:])
            settings["amount"] /= divisor
        elif text in ("🔄", "сброс", "сбросить"):
            settings["amount"] = 1.0
        else:
            amount = float(text.replace(",", "."))
            settings["amount"] = amount
    except Exception:
        await delete_user_message(message)
        return

    await save_user_settings(user_id, settings)
    await show_rates(user_id)

    await delete_user_message(message)


@dp.callback_query(F.data == "set_timezone")
async def show_timezone_selection(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    keyboard = InlineKeyboardBuilder()

    for tz_name in popular_timezones:
        try:
            tz = pytz.timezone(tz_name)
            offset = datetime.now(tz).utcoffset()
            if offset is None:
                continue
            total_minutes = int(offset.total_seconds() / 60)
            hours, minutes = divmod(abs(total_minutes), 60)
            sign = '+' if total_minutes >= 0 else '-'
            offset_str = f"UTC{sign}{hours}" if minutes == 0 else f"UTC{sign}{hours}:{minutes:02}"
            display_name = f"{tz_name} ({offset_str})"
            keyboard.button(text=display_name, callback_data=f"timezone_{tz_name}")
        except Exception:
            continue

    keyboard.adjust(1)

    await update_dynamic_message(
        user_id,
        "Выберите ваш часовой пояс:",
        keyboard.as_markup()
    )


@dp.callback_query(F.data.startswith("timezone_"))
async def set_user_timezone(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    timezone = callback.data.replace("timezone_", "")
    settings = await load_user_settings(user_id)

    settings["timezone"] = timezone
    await save_user_settings(user_id, settings)
    selected = settings.get("selected", [])

    if selected:
        await show_rates(user_id)
    else:
        await show_currency_selection(user_id)


@dp.callback_query(F.data == "set_currencies")
async def show_currency_config(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await show_currency_selection(user_id)


@dp.callback_query(F.data == "back_to_selection")
async def back_to_selection(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    settings = await load_user_settings(user_id)

    currencies, _ = await fetch_currencies()
    selected = settings.get("selected", [])
    keyboard = await build_currency_keyboard(currencies, selected)

    try:
        await bot.edit_message_text(
            chat_id=settings["chat_id"],
            message_id=settings["msg_id"],
            text="Выберите валюты для отслеживания:",
            reply_markup=keyboard
        )
    except Exception:
        pass


@dp.callback_query(F.data == "show_rates")
async def on_show_rates(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await show_rates(user_id)


@dp.callback_query(F.data.startswith("select_"))
async def select_currency(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    currency = callback.data.replace("select_", "")

    settings = await load_user_settings(user_id)
    selected = settings.get("selected", [])

    if currency in selected:
        selected.remove(currency)
    else:
        selected.append(currency)
        if len(selected) == 1:
            settings["base"] = currency

    settings["selected"] = selected
    await save_user_settings(user_id, settings)

    # Обновляем текущее сообщение, не удаляя его
    currencies, _ = await fetch_currencies()
    keyboard = await build_currency_keyboard(currencies, selected)

    try:
        await bot.edit_message_text(
            chat_id=settings["chat_id"],
            message_id=settings["msg_id"],
            text="Выберите валюты для отслеживания:",
            reply_markup=keyboard
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("base_"))
async def change_base_currency(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    currency = callback.data.replace("base_", "")
    settings = await load_user_settings(user_id)
    settings["base"] = currency
    await save_user_settings(user_id, settings)
    await show_rates(user_id)


async def set_commands(bot: Bot):
    commands = [
        types.BotCommand(command="restart", description="Перезапустить бота"),
        types.BotCommand(command="refresh", description="Обновить курсы валют"),
        types.BotCommand(command="setting", description="Настройки"),
    ]
    await bot.set_my_commands(commands)


async def periodic_update_all_users():
    while True:
        await asyncio.sleep(7200)

        users = await get_all_users()
        now = datetime.now()

        for user in users:
            user_id = user["user_id"]
            settings = await load_user_settings(user_id)

            last_update = settings.get("message_sent_at")
            if not last_update:
                continue

            if isinstance(last_update, str):
                last_update = datetime.fromisoformat(last_update)

            if (now - last_update).total_seconds() > 7200:
                await show_rates(user_id)


async def main():
    await init_db()
    await set_commands(bot)
    asyncio.create_task(periodic_update_all_users())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
