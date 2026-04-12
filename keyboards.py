from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- Главное меню (после авторизации) ---
def main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
        InlineKeyboardButton(text="🎰 Казино", callback_data="casino_menu")
    )
    builder.row(
        InlineKeyboardButton(text="🧠 Тест IQ", callback_data="iq_test"),
        InlineKeyboardButton(text="📋 Кредит", callback_data="credit_menu")
    )
    builder.row(
        InlineKeyboardButton(text="🏦 Вклад", callback_data="deposit_menu"),
        InlineKeyboardButton(text="🎁 Магазин", callback_data="shop_menu")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Личное дело", callback_data="profile"),
        InlineKeyboardButton(text="📰 Новости", callback_data="news")
    )
    builder.row(
        InlineKeyboardButton(text="🎖️ Медали", callback_data="medals_info"),
        InlineKeyboardButton(text="🔄 Перевод", callback_data="transfer")
    )
    builder.row(
        InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="daily_bonus"),
        InlineKeyboardButton(text="❓ Помощь", callback_data="help")
    )
    return builder.as_markup()

# --- Клавиатура для ввода пароля ---
def password_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Ввести пароль")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return kb

# --- Клавиатура для игры в казино ---
def casino_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1", callback_data="guess_1"),
        InlineKeyboardButton(text="2", callback_data="guess_2"),
        InlineKeyboardButton(text="3", callback_data="guess_3")
    )
    builder.row(
        InlineKeyboardButton(text="4", callback_data="guess_4"),
        InlineKeyboardButton(text="5", callback_data="guess_5"),
        InlineKeyboardButton(text="6", callback_data="guess_6")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")
    )
    return builder.as_markup()

# --- Клавиатура для теста IQ (пример для ответов) ---
def iq_answer_keyboard(question_num: int, options: list):
    builder = InlineKeyboardBuilder()
    for idx, option in enumerate(options):
        builder.row(InlineKeyboardButton(text=option, callback_data=f"iq_answer_{question_num}_{idx}"))
    return builder.as_markup()

# --- Клавиатура для кредита ---
def credit_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Взять кредит", callback_data="take_credit"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

# --- Клавиатура для вклада ---
def deposit_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Открыть вклад", callback_data="open_deposit"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

# --- Клавиатура для магазина (упрощенно) ---
def shop_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Автомобили", callback_data="shop_cars"))
    builder.row(InlineKeyboardButton(text="Цветы", callback_data="shop_flowers"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

# --- Клавиатура для админ-панели ---
def admin_panel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="👤 Пользователи", callback_data="admin_users"))
    builder.row(InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings"))
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    return builder.as_markup()

# --- Клавиатура для подтверждения действий ---
def confirm_keyboard(action: str):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}"),
        InlineKeyboardButton(text="❌ Нет", callback_data="cancel")
    )
    return builder.as_markup()

# --- Клавиатура с кнопкой "Назад" ---
def back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()
