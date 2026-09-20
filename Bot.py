import logging
import sqlite3
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

TOKEN = "8941994828:AAEvdg97xKy6C-sUd_itWglfW2JXQdWJjx8"
BOT_LINK = "https://t.me/your_bot"
DB = "bot.db"


def db_init():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            phone       TEXT,
            stars       REAL DEFAULT 0,
            referrals   INTEGER DEFAULT 0,
            referrer_id INTEGER,
            confirmed   INTEGER DEFAULT 0
        )
    """)
    con.commit()
    con.close()


def db_get(user_id):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT user_id, username, phone, stars, referrals, "
                "referrer_id, confirmed FROM users WHERE user_id = ?",
                (user_id,))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "user_id": row[0], "username": row[1], "phone": row[2],
        "stars": row[3], "referrals": row[4],
        "referrer_id": row[5], "confirmed": row[6],
    }


def db_add(user_id, username, phone, referrer_id=None):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, username, phone, referrer_id) "
        "VALUES (?, ?, ?, ?)",
        (user_id, username, phone, referrer_id)
    )
    con.commit()
    con.close()


def db_add_stars(user_id, amount):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("UPDATE users SET stars = stars + ? WHERE user_id = ?",
                (amount, user_id))
    con.commit()
    con.close()


def db_set_confirmed(user_id):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("UPDATE users SET confirmed = 1 WHERE user_id = ?", (user_id,))
    con.commit()
    con.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if db_get(user.id):
        await update.message.reply_text("Вы уже зарегистрированы!")
        return

    referrer_id = None
    if context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0].replace("ref_", ""))
            if referrer_id == user.id or not db_get(referrer_id):
                referrer_id = None
        except ValueError:
            referrer_id = None

    context.user_data["referrer_id"] = referrer_id

    keyboard = [[KeyboardButton("Поделиться контактом", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=True
    )

    await update.message.reply_text(
        "Чтобы зарегистрироваться, поделитесь своим контактом:",
        reply_markup=reply_markup
    )


async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    user = update.effective_user

    if db_get(user.id):
        await update.message.reply_text(
            "Вы уже зарегистрированы!",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    referrer_id = context.user_data.pop("referrer_id", None)
    db_add(user.id, user.username, contact.phone_number, referrer_id)

    if referrer_id:
        db_add_stars(referrer_id, 10)
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text="У вас новый реферал! +10 звёзд"
            )
        except Exception as e:
            log.warning("Не смог уведомить реферера: %s", e)

    await update.message.reply_text(
        "Регистрация завершена! Теперь вы можете зарабатывать звёзды.",
        reply_markup=ReplyKeyboardRemove()
    )


async def get_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db_get(user.id):
        await update.message.reply_text("Сначала зарегистрируйтесь: /start")
        return

    keyboard = [[InlineKeyboardButton("Получить 0.1 звезды",
                                      callback_data="get_stars")]]
    await update.message.reply_text(
        "Нажмите кнопку чтобы получить звёзды:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "get_stars":
        db_add_stars(user_id, 0.1)
        data = db_get(user_id)
        await query.edit_message_text(
            text=f"Теперь у вас {data['stars']:.2f} звёзд"
        )


async def withdraw_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = db_get(user.id)
    if not data:
        await update.message.reply_text("Сначала зарегистрируйтесь: /start")
        return

    if data["stars"] < 150:
        await update.message.reply_text(
            f"Недостаточно звёзд для вывода. У вас {data['stars']:.2f}"
        )
        return

    await update.message.reply_text("Вывод успешно выполнен.")


async def confirm_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db_get(user.id):
        await update.message.reply_text("Сначала зарегистрируйтесь: /start")
        return

    keyboard = [[InlineKeyboardButton("Подтвердить", callback_data="confirm")]]
    await update.message.reply_text(
        "Нажмите кнопку, чтобы подтвердить аккаунт:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm":
        db_set_confirmed(query.from_user.id)
        await query.edit_message_text("Аккаунт подтверждён!")


async def referral_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db_get(user.id):
        await update.message.reply_text("Сначала зарегистрируйтесь: /start")
        return

    link = f"{BOT_LINK}?start=ref_{user.id}"
    await update.message.reply_text(
        f"Ваша реферальная ссылка:\n{link}\n\n"
        "За каждого друга вы получаете 10 звёзд."
    )


def main():
    db_init()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    app.add_handler(CommandHandler("get_stars", get_stars))
    app.add_handler(CommandHandler("withdraw", withdraw_stars))
    app.add_handler(CommandHandler("confirm", confirm_account))
    app.add_handler(CommandHandler("ref", referral_system))
    app.add_handler(CallbackQueryHandler(button_click, pattern="^get_stars$"))
    app.add_handler(CallbackQueryHandler(confirm_callback, pattern="^confirm$"))

    log.info("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
