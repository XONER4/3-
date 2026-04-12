from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

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

def password_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Ввести пароль")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return kb

def casino_bet_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="100 ₽", callback_data="bet_100"),
        InlineKeyboardButton(text="500 ₽", callback_data="bet_500"),
        InlineKeyboardButton(text="1000 ₽", callback_data="bet_1000")
    )
    builder.row(
        InlineKeyboardButton(text="5000 ₽", callback_data="bet_5000"),
        InlineKeyboardButton(text="Своя сумма", callback_data="bet_custom")
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

def casino_guess_keyboard():
    builder = InlineKeyboardBuilder()
    for i in range(1, 7):
        builder.button(text=str(i), callback_data=f"guess_{i}")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_casino"))
    return builder.as_markup()

def credit_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Взять кредит", callback_data="take_credit"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

def deposit_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Открыть вклад", callback_data="open_deposit"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

def shop_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🚗 Автомобили", callback_data="shop_cars"))
    builder.row(InlineKeyboardButton(text="🌸 Цветы", callback_data="shop_flowers"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

def back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

def confirm_keyboard(action: str):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}"),
        InlineKeyboardButton(text="❌ Нет", callback_data="cancel")
    )
    return builder.as_markup()

def admin_panel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="👤 Пользователи", callback_data="admin_users"))
    builder.row(InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings"))
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    return builder.as_markup()
