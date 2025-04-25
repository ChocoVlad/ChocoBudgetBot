import os
import logging
import random
import requests
from datetime import datetime

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


user_settings = {}


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


def build_rates_text_and_keyboard(rates, settings):
    base = settings["base"]
    selected = settings["selected"]
    amount = settings.get("amount", 1.0)
    base_rate = rates[base]["Value"] / rates[base]["Nominal"]

    builder = InlineKeyboardBuilder()

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
    text = f"<i>{timestamp}</i>"
    return text, builder.as_markup()


async def process_amount(user_id: int, chat_id: int, amount: float):
    settings = user_settings.get(user_id)
    if not settings or "msg_id" not in settings:
        return

    settings["amount"] = round(amount, 4)
    msg_id = settings["msg_id"]

    rates = fetch_rates()
    text, keyboard = build_rates_text_and_keyboard(rates, settings)

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=keyboard
        )
        await save_user_settings(user_id, settings)
    except Exception as e:
        logging.error(f"Ошибка обновления сообщения: {e}")


@dp.message(CommandStart())
async def handle_start(message: types.Message):
    user_id = message.from_user.id
    rates = fetch_rates()
    if not rates:
        return

    settings = user_settings.get(user_id)
    if not settings:
        settings = await load_user_settings(user_id)
        user_settings[user_id] = settings

    if not settings["selected"]:
        await message.answer("Вы ещё не выбрали валюты. Перейдите в /settings.")
        return

    if not settings["base"]:
        settings["base"] = settings["selected"][0]

    text, keyboard = build_rates_text_and_keyboard(rates, settings)
    msg = await message.answer(text, reply_markup=keyboard)
    settings["msg_id"] = msg.message_id
    await save_user_settings(user_id, settings)


@dp.message(Command("settings"))
async def handle_settings(message: types.Message):
    user_id = message.from_user.id
    rates = fetch_rates()
    settings = user_settings.get(user_id)
    if not settings:
        settings = await load_user_settings(user_id)
        user_settings[user_id] = settings

    builder = InlineKeyboardBuilder()
    for code in sorted(rates.keys()):
        mark = "✅" if code in settings["selected"] else "❌"
        builder.button(text=f"{mark} {code}", callback_data=f"toggle_{code}")
    builder.adjust(3)
    builder.button(text="⬅️ Назад", callback_data="back_to_main")

    msg_id = settings.get("msg_id")
    if msg_id:
        try:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg_id,
                text="Выберите валюты:",
                reply_markup=builder.as_markup()
            )
        except Exception as e:
            logging.warning(f"Ошибка при открытии настроек: {e}")

    try:
        await message.delete()
    except Exception as e:
        logging.warning(f"Ошибка при удалении команды /settings: {e}")



@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_currency(callback: types.CallbackQuery):
    code = callback.data.split("_")[1]
    user_id = callback.from_user.id
    settings = user_settings.get(user_id)
    if not settings:
        settings = await load_user_settings(user_id)
        user_settings[user_id] = settings

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

    await callback.answer()

    rates = fetch_rates()
    builder = InlineKeyboardBuilder()
    for curr in sorted(rates.keys()):
        mark = "✅" if curr in selected else "❌"
        builder.button(text=f"{mark} {curr}", callback_data=f"toggle_{curr}")
    builder.adjust(3)
    builder.button(text="⬅️ Назад", callback_data="back_to_main")
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await save_user_settings(user_id, settings)


@dp.callback_query(F.data.startswith("set_base_"))
async def set_base_currency(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    settings = user_settings.get(user_id)
    if not settings:
        settings = await load_user_settings(user_id)
        user_settings[user_id] = settings

    new_base = callback.data.split("_")[2]
    settings["base"] = new_base
    await state.set_state(CurrencyStates.waiting_for_amount)

    rates = fetch_rates()
    text, keyboard = build_rates_text_and_keyboard(rates, settings)
    msg_id = settings.get("msg_id")
    if msg_id:
        try:
            await bot.edit_message_text(
                chat_id=callback.message.chat.id,
                message_id=msg_id,
                text=text,
                reply_markup=keyboard
            )
            settings["msg_id"] = msg_id
            await save_user_settings(user_id, settings)
        except Exception as e:
            logging.warning(f"Ошибка при обновлении базовой валюты: {e}")

    await callback.answer()


@dp.message(F.text.regexp(r"^\d+([.,]\d+)?$"))
async def handle_amount_input(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        await process_amount(message.from_user.id, message.chat.id, amount)
        await save_user_settings(message.from_user.id, user_settings[message.from_user.id])
        await state.clear()
        await message.delete()
    except Exception as e:
        logging.warning(f"Ошибка обработки ввода суммы: {e}")


@dp.message(Command("refresh"))
async def handle_refresh(message: types.Message):
    user_id = message.from_user.id
    settings = user_settings.get(user_id)
    if not settings:
        settings = await load_user_settings(user_id)
        user_settings[user_id] = settings

    rates = fetch_rates()
    text, keyboard = build_rates_text_and_keyboard(rates, settings)

    msg_id = settings.get("msg_id")
    if msg_id:
        try:
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg_id,
                text=text,
                reply_markup=keyboard
            )
        except Exception as e:
            logging.warning(f"Ошибка при обновлении курсов: {e}")
    try:
        await message.delete()
    except Exception as e:
        logging.warning(f"Ошибка при удалении команды /refresh: {e}")


@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    settings = user_settings.get(user_id)
    if not settings:
        settings = await load_user_settings(user_id)
        user_settings[user_id] = settings

    if not settings or not settings.get("selected"):
        await callback.message.edit_text("Вы ещё не выбрали валюты.")
        return

    rates = fetch_rates()
    text, keyboard = build_rates_text_and_keyboard(rates, settings)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
        settings["msg_id"] = callback.message.message_id
        await save_user_settings(user_id, settings)
    except Exception as e:
        logging.warning(f"Не удалось обновить сообщение: {e}")


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
