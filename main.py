import os
import logging
import random
import requests
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from db import init_db, load_user_settings, save_user_settings

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

session = AiohttpSession()
bot = Bot(
    token=BOT_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())


class CurrencyStates(StatesGroup):
    waiting_for_amount = State()


def fetch_rates():
    try:
        response = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=5)
        data = response.json()
        valutes = data["Valute"]
        valutes["RUB"] = {"Value": 1.0, "Nominal": 1, "Name": "Российский рубль"}
        return valutes
    except Exception as e:
        logging.error(f"Ошибка при получении курсов: {e}")
        return {}


def build_no_currency_selected_message():
    builder = InlineKeyboardBuilder()
    builder.button(text="Перейти к настройкам", callback_data="back_to_settings")
    return "Вы ещё не выбрали валюты.", builder.as_markup()


async def update_or_resend_message(user_id: int, chat_id: int, text: str, reply_markup):
    settings = await load_user_settings(user_id)
    msg_id = settings.get("msg_id")
    sent_at = settings.get("message_sent_at")
    expired = False

    if msg_id and sent_at:
        sent_time = sent_at if isinstance(sent_at, datetime) else datetime.fromisoformat(sent_at)
        if datetime.utcnow() - sent_time >= timedelta(hours=47):
            expired = True
    else:
        expired = True

    # Сохраним старый msg_id перед редактированием
    old_msg_id = msg_id

    if not expired:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                reply_markup=reply_markup
            )
            return settings
        except Exception as e:
            logging.warning(f"Не удалось отредактировать сообщение {msg_id}: {e}")
            # Обнуляем msg_id и дату
            settings["msg_id"] = None
            settings["message_sent_at"] = None
            await save_user_settings(user_id, settings)

    # Удаляем старое сообщение, даже если редактирование не удалось
    if old_msg_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
        except Exception:
            pass

    # Отправляем новое сообщение
    msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    settings["msg_id"] = msg.message_id
    settings["message_sent_at"] = datetime.utcnow()
    await save_user_settings(user_id, settings)

    # Загрузка обновлённого settings
    return await load_user_settings(user_id)



def build_rates_text_and_keyboard(rates, settings):
    base = settings["base"]
    selected = settings["selected"]
    amount = settings.get("amount", 1.0)

    builder = InlineKeyboardBuilder()

    # Если не выбрано валют — сообщаем об этом
    if not selected or not base or base not in rates:
        builder.button(text="Перейти к настройкам", callback_data="back_to_settings")
        return build_no_currency_selected_message()

    base_rate = rates[base]["Value"] / rates[base]["Nominal"]

    for code in selected:
        target_rate = rates[code]["Value"] / rates[code]["Nominal"]
        if code == base:
            label = f"{code}: {amount:.2f} ⭐"
        else:
            relative = (base_rate / target_rate) * amount
            label = f"{code}: {relative:.2f}"
        builder.button(text=label, callback_data=f"set_base_{code}")
    builder.adjust(1)

    timestamp = datetime.now().strftime("Обновлено: %d-%m %H:%M:%S")
    return f"<i>{timestamp}</i>", builder.as_markup()


async def ensure_user_and_message(message: types.Message) -> dict:
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except Exception:
        pass

    settings = await load_user_settings(user_id)
    if not settings:
        settings = await load_user_settings(user_id)
        await save_user_settings(user_id, settings)

    # Если валюты не выбраны — отправляем отдельное сообщение
    if not settings.get("selected"):
        text, markup = build_no_currency_selected_message()
        msg = await bot.send_message(chat_id, text=text, reply_markup=markup)
        settings["msg_id"] = msg.message_id
        settings["message_sent_at"] = datetime.utcnow()
        await save_user_settings(user_id, settings)
        return settings

    if not settings.get("base") and settings["selected"]:
        settings["base"] = settings["selected"][0]

    rates = fetch_rates()
    text, keyboard = build_rates_text_and_keyboard(rates, settings)

    settings = await update_or_resend_message(user_id, chat_id, text, keyboard)
    return settings


async def process_amount(user_id: int, chat_id: int, amount: float):
    settings = await load_user_settings(user_id)
    if not settings or "msg_id" not in settings:
        return

    settings["amount"] = round(amount, 4)
    await save_user_settings(user_id, settings)

    rates = fetch_rates()
    text, keyboard = build_rates_text_and_keyboard(rates, settings)

    settings = await update_or_resend_message(user_id, chat_id, text, keyboard)

    await save_user_settings(user_id, settings)



@dp.message(CommandStart())
async def handle_start(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Загружаем настройки пользователя
    settings = await load_user_settings(user_id)
    if not settings:
        settings = await load_user_settings(user_id)
        settings[user_id] = settings

    # Если валюты не выбраны — отправляем сообщение с предложением настроить
    if not settings or not settings.get("selected"):
        text, markup = build_no_currency_selected_message()
        msg = await message.answer(text, reply_markup=markup)
        settings["msg_id"] = msg.message_id
        settings["message_sent_at"] = datetime.utcnow()
        await save_user_settings(user_id, settings)
        return

    # Если нет базовой валюты — устанавливаем первую из выбранных
    if not settings.get("base"):
        settings["base"] = settings["selected"][0]

    # Строим и отправляем новое сообщение с курсами
    rates = fetch_rates()
    text, keyboard = build_rates_text_and_keyboard(rates, settings)
    msg = await message.answer(text, reply_markup=keyboard)

    settings["msg_id"] = msg.message_id
    await save_user_settings(user_id, settings)

    try:
        await message.delete()
    except Exception:
        pass


@dp.message(Command("settings"))
async def handle_settings(message: types.Message):
    settings = await ensure_user_and_message(message)
    rates = fetch_rates()

    builder = InlineKeyboardBuilder()
    for code in sorted(rates.keys()):
        mark = "✅" if code in settings["selected"] else "❌"
        builder.button(text=f"{mark} {code}", callback_data=f"toggle_{code}")
    builder.adjust(3)
    builder.button(text="⬅️ Назад", callback_data="back_to_main")

    settings = await update_or_resend_message(message.from_user.id, message.chat.id, "Выберите валюты:",
                                              builder.as_markup())
    await save_user_settings(message.from_user.id, settings)


@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_currency(callback: types.CallbackQuery):
    code = callback.data.split("_")[1]
    user_id = callback.from_user.id
    settings = await load_user_settings(user_id)

    selected = settings["selected"]
    base = settings["base"]

    if code in selected:
        selected.remove(code)
        if code == base:
            settings["base"] = random.choice(selected) if selected else None
    else:
        selected.append(code)
        if not base:
            settings["base"] = code

    await save_user_settings(user_id, settings)
    await callback.answer()

    rates = fetch_rates()
    builder = InlineKeyboardBuilder()
    for curr in sorted(rates.keys()):
        mark = "✅" if curr in selected else "❌"
        builder.button(text=f"{mark} {curr}", callback_data=f"toggle_{curr}")
    builder.adjust(3)
    builder.button(text="⬅️ Назад", callback_data="back_to_main")

    settings = await update_or_resend_message(user_id, callback.message.chat.id, "Выберите валюты:", builder.as_markup())
    await save_user_settings(user_id, settings)



@dp.callback_query(F.data.startswith("set_base_"))
async def set_base_currency(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    settings = await load_user_settings(user_id)

    new_base = callback.data.split("_")[2]
    settings["base"] = new_base
    await save_user_settings(user_id, settings)

    await state.set_state(CurrencyStates.waiting_for_amount)

    rates = fetch_rates()
    text, keyboard = build_rates_text_and_keyboard(rates, settings)

    settings = await update_or_resend_message(user_id, callback.message.chat.id, text, keyboard)

    await callback.answer()
    await save_user_settings(user_id, settings)



@dp.message(F.text.regexp(r"^\d+([.,]\d+)?$"))
async def handle_amount_input(message: types.Message, state: FSMContext):
    try:
        try:
            await message.delete()
        except Exception:
            pass

        amount = float(message.text.replace(",", "."))
        await process_amount(message.from_user.id, message.chat.id, amount)
        await state.clear()
    except Exception as e:
        logging.warning(f"Ошибка обработки ввода суммы: {e}")



@dp.message(Command("refresh"))
async def handle_refresh(message: types.Message):
    await ensure_user_and_message(message)


@dp.callback_query(F.data == "back_to_settings")
async def back_to_settings(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    settings = await load_user_settings(user_id)
    if settings and settings.get("msg_id"):
        try:
            await bot.delete_message(callback.message.chat.id, settings["msg_id"])
        except Exception:
            pass

    settings["msg_id"] = None
    settings["message_sent_at"] = None
    await save_user_settings(user_id, settings)

    # Теперь отправляем новое сообщение
    await handle_settings(callback.message)



@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    settings = await load_user_settings(user_id)
    if not settings:
        settings = await load_user_settings(user_id)
        await save_user_settings(user_id, settings)

    rates = fetch_rates()
    text, keyboard = build_rates_text_and_keyboard(rates, settings)

    settings = await update_or_resend_message(user_id, callback.message.chat.id, text, keyboard)


async def main():
    from aiogram.types import BotCommand, MenuButtonCommands

    await init_db()

    await bot.set_my_commands([
        BotCommand(command="refresh", description="Обновить курсы"),
        BotCommand(command="settings", description="Настроить валюты"),
    ])
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
