from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏦 СБЕРБАНК 🏦", callback_data="bank_menu")
    )
    builder.row(
        InlineKeyboardButton(text="🎰 КАЗИНО", callback_data="casino_menu"),
        InlineKeyboardButton(text="🧠 ТЕСТ IQ", callback_data="iq_test")
    )
    builder.row(
        InlineKeyboardButton(text="🛍️ МАГАЗИН", callback_data="shop_menu"),
        InlineKeyboardButton(text="🫆 ПРОФИЛЬ", callback_data="profile")
    )
    builder.row(
        InlineKeyboardButton(text="📰 НОВОСТИ", url="https://t.me/novostibots13")
    )
    builder.row(
        InlineKeyboardButton(text="🎁 ЕЖЕЧАСНЫЙ БОНУС", callback_data="hourly_bonus")
    )
    builder.row(
        InlineKeyboardButton(text="👨‍👩‍👧‍👦 СЕМЬЯ", callback_data="family")
    )
    builder.row(
        InlineKeyboardButton(text="🚧 РАБОТА", callback_data="work_menu")
    )
    builder.row(
        InlineKeyboardButton(text="📚 ОБУЧЕНИЕ", callback_data="learning_menu")
    )
    return builder.as_markup()

def password_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="ВВЕСТИ ПАРОЛЬ")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return kb

def bank_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 ПЕРЕВОД", callback_data="transfer"))
    builder.row(InlineKeyboardButton(text="💰 ВКЛАД", callback_data="deposit_menu"))
    builder.row(InlineKeyboardButton(text="💵 КРЕДИТ", callback_data="credit_menu"))
    builder.row(InlineKeyboardButton(text="💕 БЛАГОТВОРИТЕЛЬНЫЙ ФОНД", callback_data="charity"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_to_main"))
    return builder.as_markup()

def casino_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎲 КУБИК", callback_data="casino_dice"),
        InlineKeyboardButton(text="🎰 СЛОТЫ", callback_data="casino_slots")
    )
    builder.row(InlineKeyboardButton(text="📊 РЕЙТИНГ", callback_data="casino_rating"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_to_main"))
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
        InlineKeyboardButton(text="СВОЯ СУММА", callback_data="dice_custom")
    )
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="casino_menu"))
    return builder.as_markup()

def dice_guess_keyboard():
    builder = InlineKeyboardBuilder()
    for i in range(1, 7):
        builder.button(text=str(i), callback_data=f"dice_guess_{i}")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="casino_dice"))
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
        InlineKeyboardButton(text="СВОЯ СУММА", callback_data="slots_custom")
    )
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="casino_menu"))
    return builder.as_markup()

def credit_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="ВЗЯТЬ КРЕДИТ", callback_data="take_credit"))
    builder.row(InlineKeyboardButton(text="ПОГАСИТЬ КРЕДИТ", callback_data="repay_credit"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="bank_menu"))
    return builder.as_markup()

def credit_term_keyboard():
    builder = InlineKeyboardBuilder()
    for hours in [5, 10, 15, 20, 25]:
        builder.button(text=f"{hours} ЧАСОВ", callback_data=f"credit_term_{hours}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="credit_menu"))
    return builder.as_markup()

def deposit_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="ОТКРЫТЬ ВКЛАД", callback_data="open_deposit"))
    builder.row(InlineKeyboardButton(text="ЗАКРЫТЬ ВКЛАД", callback_data="close_deposit"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="bank_menu"))
    return builder.as_markup()

def shop_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🧪 ПРОБИВ БОТЫ 🧪", callback_data="shop_item_1"))
    builder.row(InlineKeyboardButton(text="💝 TELEGRAM PREMIUM 💝", callback_data="shop_item_2"))
    builder.row(InlineKeyboardButton(text="🔹 VPN СЕРВИС 🔹", callback_data="shop_item_3"))
    builder.row(InlineKeyboardButton(text="💜 СЕМЬЯ PREMIUM 💜", callback_data="shop_item_4"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_to_main"))
    return builder.as_markup()

def shop_item_keyboard(item_id: int, can_gift: bool = True):
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 КУПИТЬ", callback_data=f"buy_item_{item_id}")
    if can_gift:
        builder.button(text="🎁 ПОДАРИТЬ", callback_data=f"gift_item_{item_id}")
    builder.button(text="🔙 НАЗАД", callback_data="shop_menu")
    builder.adjust(1)
    return builder.as_markup()

def back_keyboard(destination: str = "back_to_main"):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data=destination))
    return builder.as_markup()

def admin_panel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="👤 ПОЛЬЗОВАТЕЛИ", callback_data="admin_users"))
    builder.row(InlineKeyboardButton(text="💸 ПОПОЛНИТЬ БАЛАНС", callback_data="admin_add_balance"))
    builder.row(InlineKeyboardButton(text="💸 СПИСАТЬ БАЛАНС", callback_data="admin_sub_balance"))
    builder.row(InlineKeyboardButton(text="🎖 УСТАНОВИТЬ ЗВАНИЕ", callback_data="admin_set_rank"))
    builder.row(InlineKeyboardButton(text="🏅 ВЫДАТЬ МЕДАЛЬ", callback_data="admin_give_medal"))
    builder.row(InlineKeyboardButton(text="✏️ СМЕНИТЬ ИМЯ", callback_data="admin_rename"))
    builder.row(InlineKeyboardButton(text="🔐 СМЕНИТЬ ПАРОЛЬ", callback_data="admin_change_password"))
    builder.row(InlineKeyboardButton(text="📢 РАССЫЛКА", callback_data="admin_broadcast"))
    builder.row(InlineKeyboardButton(text="📝 ИЗМЕНИТЬ ТЕКСТ МЕНЮ", callback_data="admin_change_main_text"))
    builder.row(InlineKeyboardButton(text="🚫 ЗАБЛОКИРОВАТЬ ПОЛЬЗОВАТЕЛЯ", callback_data="admin_ban_user"))
    builder.row(InlineKeyboardButton(text="✅ РАЗБЛОКИРОВАТЬ ПОЛЬЗОВАТЕЛЯ", callback_data="admin_unban_user"))
    builder.row(InlineKeyboardButton(text="🏠 ВОЙТИ В ОБЩЕЕ МЕНЮ", callback_data="admin_enter_main"))
    return builder.as_markup()

def profile_sections_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏅 ЗВАНИЯ", callback_data="profile_ranks"))
    builder.row(InlineKeyboardButton(text="🎁 ПОДАРКИ/ПОКУПКИ", callback_data="profile_gifts"))
    builder.row(InlineKeyboardButton(text="🏅 МЕДАЛИ", callback_data="profile_medals"))
    builder.row(InlineKeyboardButton(text="🔗 РЕФЕРАЛЬНАЯ ССЫЛКА", callback_data="profile_referral"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_to_main"))
    return builder.as_markup()

def work_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🧠 УМСТВЕННЫЙ ТРУД", callback_data="work_mental"))
    builder.row(InlineKeyboardButton(text="🔨 ФИЗИЧЕСКИЙ ТРУД", callback_data="work_physical"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_to_main"))
    return builder.as_markup()

def physical_work_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🧱 ПОЛОЖИТЬ КИРПИЧ (+57₽)", callback_data="physical_work_brick"))
    builder.row(InlineKeyboardButton(text="📊 РЕЙТИНГ СТРОИТЕЛЕЙ", callback_data="physical_rating"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="work_menu"))
    return builder.as_markup()

def mental_work_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📝 СЛЕДУЮЩАЯ ЗАДАЧА", callback_data="mental_next_task"))
    builder.row(InlineKeyboardButton(text="📊 РЕЙТИНГ УМНИКОВ", callback_data="mental_rating"))
    builder.row(InlineKeyboardButton(text="🔙 ЗАВЕРШИТЬ РАБОТУ", callback_data="work_menu"))
    return builder.as_markup()

def learning_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎖 ЗВАНИЯ", callback_data="learn_ranks"))
    builder.row(InlineKeyboardButton(text="🏅 МЕДАЛИ", callback_data="learn_medals"))
    builder.row(InlineKeyboardButton(text="📖 ОСТАЛЬНОЕ", callback_data="learn_other"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_to_main"))
    return builder.as_markup()

def learning_other_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💼 РАБОТА", callback_data="learn_work"))
    builder.row(InlineKeyboardButton(text="🏦 БАНК", callback_data="learn_bank"))
    builder.row(InlineKeyboardButton(text="🛍️ МАГАЗИН", callback_data="learn_shop"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="learning_menu"))
    return builder.as_markup()
