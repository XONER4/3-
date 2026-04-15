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
        InlineKeyboardButton(text="👨‍👩‍👧‍👦 Семья", callback_data="family")
    )
    builder.row(
        InlineKeyboardButton(text="🆘 ПОМОГИ СЕМЬЕ 🆘", callback_data="charity")
    )
    builder.row(
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

def casino_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎲 Кубик", callback_data="casino_dice"),
        InlineKeyboardButton(text="🎰 Слоты", callback_data="casino_slots")
    )
    builder.row(InlineKeyboardButton(text="📊 Рейтинг", callback_data="casino_rating"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

def dice_bet_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="100 ₽", callback_data="dice_100"),
        InlineKeyboardButton(text="500 ₽", callback_data="dice_500"),
        InlineKeyboardButton(text="1000 ₽", callback_data="dice_1000")
    )
    builder.row(
        InlineKeyboardButton(text="5000 ₽", callback_data="dice_5000"),
        InlineKeyboardButton(text="Своя сумма", callback_data="dice_custom")
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="casino_menu"))
    return builder.as_markup()

def dice_guess_keyboard():
    builder = InlineKeyboardBuilder()
    for i in range(1, 7):
        builder.button(text=str(i), callback_data=f"dice_guess_{i}")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="casino_dice"))
    return builder.as_markup()

def slots_bet_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="100 ₽", callback_data="slots_100"),
        InlineKeyboardButton(text="500 ₽", callback_data="slots_500"),
        InlineKeyboardButton(text="1000 ₽", callback_data="slots_1000")
    )
    builder.row(
        InlineKeyboardButton(text="5000 ₽", callback_data="slots_5000"),
        InlineKeyboardButton(text="Своя сумма", callback_data="slots_custom")
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="casino_menu"))
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

def back_keyboard(destination: str = "back_to_main"):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data=destination))
    return builder.as_markup()
    def back_to_admin_keyboard():
    return back_keyboard("admin")

def back_to_family_profile_keyboard(user_id: int):
    return back_keyboard(f"family_profile_{user_id}")

def admin_panel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="👤 Пользователи", callback_data="admin_users"))
    builder.row(InlineKeyboardButton(text="💸 Пополнить баланс", callback_data="admin_add_balance"))
    builder.row(InlineKeyboardButton(text="🎖 Установить звание", callback_data="admin_set_rank"))
    builder.row(InlineKeyboardButton(text="🏅 Выдать медаль", callback_data="admin_give_medal"))
    builder.row(InlineKeyboardButton(text="✏️ Сменить имя", callback_data="admin_rename"))
    builder.row(InlineKeyboardButton(text="🔐 Сменить пароль", callback_data="admin_change_password"))
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    builder.row(InlineKeyboardButton(text="🆕 Кастомная кнопка", callback_data="admin_custom_button"))
    builder.row(InlineKeyboardButton(text="📝 Изменить текст меню", callback_data="admin_change_main_text"))
    builder.row(InlineKeyboardButton(text="🏠 Войти в общее меню", callback_data="admin_enter_main"))
    return builder.as_markup()

def profile_sections_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏅 Звания", callback_data="profile_ranks"))
    builder.row(InlineKeyboardButton(text="🎁 Подарки/Покупки", callback_data="profile_gifts"))
    builder.row(InlineKeyboardButton(text="🏅 Медали", callback_data="profile_medals"))
    builder.row(InlineKeyboardButton(text="📸 Загрузить фото", callback_data="profile_upload_photo"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()
