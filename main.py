import logging
import asyncio
import threading
from datetime import datetime
from typing import Dict, Set, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Настройки
TOKEN = "8461887435:AAEFLMXQzzVStz7jVmjLL0eCSaf2rxN0g9g"  # Замените на токен от @BotFather
ADMIN_ID = 8473087607  # Ваш Telegram ID (можно узнать через @userinfobot)

# База данных (в памяти для простоты)
users: Dict[int, float] = {}  # user_id → balance
blacklist: Set[int] = set()
pending_payments: Dict[int, str] = {}  # user_id → payment_id

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)



# 1. Ежесекундное начисление баланса
async def balance_incrementer(app: Application):
    while True:
        await asyncio.sleep(1)
        for user_id in users:
            if user_id not in blacklist:
                users[user_id] += 0.01  # +0.01 ₽ в секунду
        logger.info("Балансы обновлены для всех активных пользователей.")



# 2. Старт и приветствие
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in blacklist:
        await update.message.reply_text("❌ Вы в чёрном списке.")
        return

    if user_id not in users:
        users[user_id] = 0.0
        logger.info(f"Новый пользователь: {user_id}")

    await update.message.reply_text(
        f"👋 Привет! Твой баланс: **{users[user_id]:.2f} ₽**\n\n"
        "Используй /menu для управления."
    )



# 3. Главное меню
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💵 Пополнить баланс", callback_data="pay")],
        [InlineKeyboardButton("💰 Мой баланс", callback_data="balance")],
    ]
    # Добавляем админ-кнопку только для админа
    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)



# 4. Обработка кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Подтверждаем получение callback

    user_id = query.from_user.id

    if user_id in blacklist:
        await query.edit_message_text("❌ Вы в чёрном списке.")
        return

    data = query.data

    if data == "balance":
        await query.edit_message_text(f"💰 Твой баланс: **{users[user_id]:.2f} ₽**")

    elif data == "pay":
        # Генерируем QR-код для пополнения
        payment_id = f"PAY_{user_id}_{int(datetime.now().timestamp())}"
        pending_payments[user_id] = payment_id

        import qrcode
        from io import BytesIO

        img = qrcode.make(payment_id)
        bio = BytesIO()
        img.save(bio, "PNG")
        bio.seek(0)

        await query.message.reply_photo(
            photo=bio,
            caption=(
                f"🔳 Отсканируй QR-код для пополнения\n"
                f"ID платежа: `{payment_id}`\n"
                "После оплаты нажми /confirm"
            ),
        )

    elif data == "admin" and user_id == ADMIN_ID:
        await show_admin_panel(query, context)

    elif data == "back_to_menu":
        await menu(update, context)

    elif data == "admin_users":
        await admin_users(query, context)

    elif data == "admin_blacklist":
        await admin_blacklist(query, context)

    elif data == "admin_add_balance":
        await admin_add_balance(query, context)

    else:
        # Обработка неизвестных callback_data
        logger.warning(f"Неизвестный callback_data: {data} от пользователя {user_id}")
        await query.answer(text="Неизвестное действие.", show_alert=True)




# 5. Админ‑панель
async def show_admin_panel(query):
    count = len(users)
    banned = len(blacklist)
    total_balance = sum(users.values())

    keyboard = [
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton("🛑 Чёрный список", callback_data="admin_blacklist")],
        [InlineKeyboardButton("➕ Ручное пополнение", callback_data="admin_add_balance")],
        [InlineKeyboardButton("↩️ Назад", callback_data="back_to_menu")],
    ]
    text = (
    "⚙️ *Админ‑панель*\n\n"
    f"Всего пользователей: {count}\n"
    f"В чёрном списке: {banned}\n"
    f"Общий баланс: {total_balance:.2f} ₽"
)
try:
    # Проверяем, что клавиатура не пустая
    if not keyboard:
        keyboard = [[]]  # Пустая клавиатура

    # Избегаем отправки идентичного текста (может вызвать ошибку Telegram)
    if query.message.text != text:
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="MarkdownV2"  # Используем актуальный режим
        )
    else:
        # Если текст не изменился, обновляем только клавиатуру
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

except telegram.error.BadRequest as e:
    if "Message is not modified" in str(e):
        logger.debug("Сообщение не изменилось, пропуск редактирования")
    else:
        logger.error(f"Ошибка Telegram при редактировании сообщения: {e}")

except telegram.error.NotFound:
    logger.error("Сообщение не найдено (возможно, удалено)")

except Exception as e:
    logger.error(f"Неожиданная ошибка при редактировании сообщения: {e}")



# 6. Управление пользователями (админ)
async def admin_users(query):
    text = "👥 *Список пользователей*:\n\n"
    for uid, bal in users.items():
        status = "✅" if uid not in blacklist else "❌"
        text += f"{status} `{uid}` → {bal:.2f} ₽\n"

    keyboard = [[InlineKeyboardButton("↩️ Назад", callback_data="admin")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")



# 7. Чёрный список (админ)
async def admin_blacklist(query):
    if not blacklist:
        text = "🛑 Чёрный список пуст."
    else:
        text = "🛑 *Чёрный список*:\n\n"
        for uid in blacklist:
            text += f"`{uid}`\n"

    keyboard = [[InlineKeyboardButton("↩️ Назад", callback_data="admin")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")



# 8. Ручное пополнение (админ)
async def admin_add_balance(query, context: ContextTypes.DEFAULT_TYPE):
    await query.edit_message_text(
        "➕ *Ручное пополнение*\n\n"
        "Отправьте в чат:\n"
        "`ID_пользователя сумма`\n\n"
        "Пример:\n`123456789 100`",
        parse_mode="Markdown",
    )
    context.user_data["expecting_admin_payment"] = True



# 9. Подтверждение платежа пользователем
async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in pending_payments:
        await update.message.reply_text("❌ Нет активных платежей.")
        return

    # Здесь должна быть интеграция с платёжной системой
    # Для примера — просто добавляем 10 ₽
    users[user_id] += 10.0
    del pending_payments[user_id]
    await update.message.reply_text("✅ Платёж подтверждён! +10.00 ₽")



# 10. Обработка текстовых команд админа
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # Если админ ожидает ввода данных для ручного пополнения
    if context.user_data.get("expecting_admin_payment") and user_id == ADMIN_ID:
        try:
            # Разбираем ввод: ID пользователя и сумма
            parts = text.strip().split()
            if len(parts) != 2:
                await update.message.reply_text(
                    "❌ Неверный формат. Нужно: `ID_пользователя сумма`\n"
                    "Пример: `123456789 100`"
                )
                return

            uid_str, amount_str = parts
            uid = int(uid_str)
            amount = float(amount_str)

            if amount <= 0:
                await update.message.reply_text("❌ Сумма должна быть больше нуля.")
                return

            # Обновляем баланс пользователя
            if uid not in users:
                users[uid] = 0.0
            users[uid] += amount

            await update.message.reply_text(
                f"✅ Пользователь {uid} пополнил баланс на {amount:.2f} ₽\n"
                f"Новый баланс: {users[uid]:.2f} ₽"
            )

            # Сбрасываем флаг ожидания
            context.user_data["expecting_admin_payment"] = False

        except ValueError:
            await update.message.reply_text(
                "❌ Ошибка: убедитесь, что ID — целое число, а сумма — число с точкой (например, 100.50)."
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Произошла ошибка: {e}")
    else:
        # Если сообщение не относится к ожидаемой команде админа, можно проигнорировать или вывести подсказку
        await update.message.reply_text("Неизвестная команда. Используйте /menu для навигации.")
