import asyncio
import logging
import sqlite3

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton
)

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = ""
DB_FILE = "bot.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

bot_username = "unknown_bot"


# --- БАЗА ДАННЫХ ---
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id      INTEGER PRIMARY KEY,
            username     TEXT,
            phone        TEXT,
            stars        REAL DEFAULT 0,
            referrals    INTEGER DEFAULT 0,
            referrer_id  INTEGER,
            is_confirmed INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row


def create_user(user_id, username, referrer_id=None):
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, username, referrer_id) VALUES (?, ?, ?)",
        (user_id, username, referrer_id)
    )
    conn.commit()
    conn.close()


def update_phone(user_id, phone):
    conn = get_db()
    conn.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
    conn.commit()
    conn.close()


def add_stars(user_id, amount):
    conn = get_db()
    conn.execute("UPDATE users SET stars = stars + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()


def add_referral(referrer_id):
    conn = get_db()
    conn.execute(
        "UPDATE users SET referrals = referrals + 1 WHERE user_id = ?",
        (referrer_id,)
    )
    conn.commit()
    conn.close()


def set_confirmed(user_id):
    conn = get_db()
    conn.execute("UPDATE users SET is_confirmed = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# --- КЛАВИАТУРЫ ---
def get_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💰 Получить звезды")],
            [KeyboardButton(text="👥 Рефералы")],
            [KeyboardButton(text="💸 Вывести")],
            [KeyboardButton(text="✅ Подтвердить аккаунт")],
        ],
        resize_keyboard=True
    )


def get_contact_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить контакт", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


# --- /start ---
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    user_id = user.id

    referrer_id = None
    if message.text and len(message.text.split()) > 1:
        arg = message.text.split()[1]
        if arg.startswith("ref_"):
            try:
                rid = int(arg.replace("ref_", ""))
                if rid != user_id and get_user(rid):
                    referrer_id = rid
            except ValueError:
                pass

    if not get_user(user_id):
        create_user(user_id, user.username, referrer_id=referrer_id)

        if referrer_id:
            add_stars(referrer_id, 10)
            add_referral(referrer_id)
            try:
                await bot.send_message(
                    chat_id=referrer_id,
                    text="🎉 Твой реферал зарегистрировался! +10 звёзд."
                )
            except Exception as e:
                logger.error(f"Не смог уведомить реферера: {e}")

        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        await message.answer(
            f"👋 Добро пожаловать!\n\n"
            f"🔗 Твоя реферальная ссылка:\n{ref_link}\n\n"
            f"Пригласи друга — получишь 10 звёзд.",
            reply_markup=get_main_kb()
        )
    else:
        await message.answer("👋 С возвращением!", reply_markup=get_main_kb())


# --- Кнопки меню ---
@dp.message(F.text == "💰 Получить звезды")
async def cmd_get_stars(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return
    add_stars(message.from_user.id, 0.1)
    fresh = get_user(message.from_user.id)
    await message.answer(f"✅ +0.1 звезды. Баланс: {fresh['stars']:.2f}")


@dp.message(F.text == "👥 Рефералы")
async def cmd_referrals(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return
    ref_link = f"https://t.me/{bot_username}?start=ref_{message.from_user.id}"
    await message.answer(
        f"👥 Твоя ссылка:\n{ref_link}\n\n"
        f"Приглашено: {user['referrals']}\n"
        f"За друга: 10 звёзд"
    )


@dp.message(F.text == "💸 Вывести")
async def cmd_withdraw(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return

    if user["is_confirmed"] == 0:
        await message.answer("❌ Сначала подтверди аккаунт!")
        return

    if user["stars"] >= 150:
        add_stars(message.from_user.id, -150)
        await message.answer("✅ Заявка на вывод 150 звёзд принята.")
    else:
        await message.answer(
            f"❌ Минимум 150 звёзд. У тебя: {user['stars']:.2f}"
        )


@dp.message(F.text == "✅ Подтвердить аккаунт")
async def cmd_confirm(message: Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Сначала /start")
        return

    if user["is_confirmed"]:
        await message.answer("✅ Аккаунт уже подтверждён.")
        return

    await message.answer(
        "📱 Отправь свой номер телефона, нажав кнопку ниже:",
        reply_markup=get_contact_kb()
    )


# --- Обработка контакта ---
@dp.message(F.contact)
async def handle_contact(message: Message):
    user_id = message.from_user.id
    contact = message.contact

    if not get_user(user_id):
        await message.answer("Сначала /start")
        return

    update_phone(user_id, contact.phone_number)
    set_confirmed(user_id)

    await message.answer(
        "✅ Аккаунт подтверждён! Номер сохранён.",
        reply_markup=get_main_kb()
    )


# --- Запуск ---
async def main():
    global bot_username
    init_db()
    try:
        me = await bot.get_me()
        bot_username = me.username
    except Exception as e:
        logger.error(f"Не удалось получить username бота: {e}")

    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
