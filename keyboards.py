from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏦✅СберБанк✅🏦", callback_data="bank_menu")
    )
    builder.row(
        InlineKeyboardButton(text="🎰 Казино", callback_data="casino_menu"),
        InlineKeyboardButton(text="🧠 Тест IQ", callback_data="iq_test")
    )
    builder.row(
        InlineKeyboardButton(text="🛍️ Магазин", callback_data="shop_menu"),
        InlineKeyboardButton(text="📊 Личное дело", callback_data="profile")
    )
    builder.row(
        InlineKeyboardButton(text="🛍️ Купленные товары", callback_data="purchased_goods")
    )
    builder.row(
        InlineKeyboardButton(text="📰 Новости", url="https://t.me/your_news_channel")  # замени на ссылку канала
    )
    builder.row(
        InlineKeyboardButton(text="🎖️ Медали", callback_data="medals_info"),
        InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="daily_bonus")
    )
    builder.row(
        InlineKeyboardButton(text="👨‍👩‍👧‍👦 Семья", callback_data="family")
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

def bank_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 Перевод", callback_data="transfer"))
    builder.row(InlineKeyboardButton(text="💰 Вклад", callback_data="deposit_menu"))
    builder.row(InlineKeyboardButton(text="💵 Кредит", callback_data="credit_menu"))
    builder.row(InlineKeyboardButton(text="💕 Благотворительный фонд", callback_data="charity"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

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
    builder.row(InlineKeyboardButton(text="Погасить кредит", callback_data="repay_credit"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="bank_menu"))
    return builder.as_markup()

def credit_term_keyboard():
    builder = InlineKeyboardBuilder()
    for hours in [5, 10, 15, 20, 25]:
        builder.button(text=f"{hours} часов", callback_data=f"credit_term_{hours}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="credit_menu"))
    return builder.as_markup()

def deposit_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Открыть вклад", callback_data="open_deposit"))
    builder.row(InlineKeyboardButton(text="Закрыть вклад", callback_data="close_deposit"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="bank_menu"))
    return builder.as_markup()

# --- НОВЫЙ МАГАЗИН (5 товаров) ---
def shop_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🧪 ПРОБИВ БОТЫ 🧪", callback_data="shop_item_1"))
    builder.row(InlineKeyboardButton(text="💝 TELEGRAM PREMIUM 💝", callback_data="shop_item_2"))
    builder.row(InlineKeyboardButton(text="🔹 VPN СЕРВИС 🔹", callback_data="shop_item_3"))
    builder.row(InlineKeyboardButton(text="🎈🔮 ВОЗДУШНЫЕ ШАРЫ 🔮🎈", callback_data="shop_item_4"))
    builder.row(InlineKeyboardButton(text="💜 СЕМЬЯ PREMIUM 💜", callback_data="shop_item_5"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

def shop_item_keyboard(item_id: int, can_gift: bool = False):
    """Клавиатура для конкретного товара: Купить, Подарить (если can_gift), Назад."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Купить", callback_data=f"buy_item_{item_id}")
    if can_gift:
        builder.button(text="🎁 Подарить", callback_data=f"gift_item_{item_id}")
    builder.button(text="🔙 Назад", callback_data="shop_menu")
    builder.adjust(1)
    return builder.as_markup()

def back_keyboard(destination: str = "back_to_main"):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data=destination))
    return builder.as_markup()

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
    builder.row(InlineKeyboardButton(text="🔗 Реферальная ссылка", callback_data="profile_referral"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()
