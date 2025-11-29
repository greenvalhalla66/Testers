import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import sqlite3
from datetime import datetime, timedelta

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ID администратора (замените на свой ID Telegram)
ADMIN_ID = 8473087607  # замените на реальный ID

# Токен бота Telegram (замените на реальный токен)
TOKEN = "8461887435:AAEFLMXQzzVStz7jVmjLL0eCSaf2rxN0g9g"  # замените на токен вашего бота

# Подключение к базе данных
def init_db():
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0,
            last_deposit_time TEXT,
            pending_deposit REAL DEFAULT 0,
            pending_withdraw REAL DEFAULT 0
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    # Установка процента по умолчанию
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('percent', '25')"
    )
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def create_user(user_id):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def update_user_balance(user_id, balance):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET balance = ? WHERE user_id = ?", (balance, user_id)
    )
    conn.commit()
    conn.close()

def set_pending_deposit(user_id, amount):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET pending_deposit = ? WHERE user_id = ?", (amount, user_id)
    )
    conn.commit()
    conn.close()

def set_pending_withdraw(user_id, amount):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET pending_withdraw = ? WHERE user_id = ?", (amount, user_id)
    )
    conn.commit()
    conn.close()

def clear_pending_deposit(user_id):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET pending_deposit = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def clear_pending_withdraw(user_id):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET pending_withdraw = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def set_last_deposit_time(user_id, timestamp):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET last_deposit_time = ? WHERE user_id = ?",
        (timestamp, user_id),
    )
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def set_setting(key, value):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()
    conn.close()

# Команды бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not get_user(user_id):
        create_user(user_id)
    await update.message.reply_text(
        "Добро пожаловать в Удвоитель валюты!\n\n"
        "Используйте команды:\n"
        "/balance — проверить баланс\n"
        "/deposit — пополнить счёт\n"
        "/withdraw — вывести средства\n"
        "/admin — панель администратора"
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if user:
        balance = user[1]
        await update.message.reply_text(f"Ваш баланс: ${balance:.2f}")
    else:
        await update.message.reply_text("Ошибка: пользователь не найден.")

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("Ошибка: пользователь не найден.")
        return

    if user[3]:  # last_deposit_time
        last_time = datetime.fromisoformat(user[3])
        if datetime.now() - last_time < timedelta(hours=48):
            await update.message.reply_text(
                "Вы можете делать пополнение только раз в 48 часов."
            )
            return

    await update.message.reply_text(
        "Введите сумму для пополнения (в долларах):"
    )
    context.user_data["action"] = "deposit"

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("Ошибка: пользователь не найден.")
        return

    balance = user[1]
    if balance <= 0:
        await update.message.reply_text("На счету недостаточно средств для вывода.")
        return

    await update.message.reply_text(
        f"Введите сумму для вывода (доступно: ${balance:.2f}):"
    )
    context.user_data["action"] = "withdraw"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if "action" not in context.user_data:
        return

    action = context.user_data["action"]

    try:
        amount = float(text)
        if amount <= 0:
            await update.message.reply_text("Сумма должна быть больше нуля.")
            return
    except ValueError:
        await update.message.reply_text("Введите корректную сумму.")
        return

    if action == "deposit":
        set_pending_deposit(user_id, amount)
        await update.message.reply_text(
            f"Заявка на пополнение на сумму ${amount:.2f} отправлена на подтверждение."
        )
        # Отправляем уведомление администратору
        percent = float(get_setting("percent"))
        bonus = amount * (percent / 100)
        total = amount + bonus
        await context.bot.send_message(
            ADMIN_ID,
            f"❗ Новая заявка на