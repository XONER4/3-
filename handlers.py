import json
import random
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import Command, StateFilter, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    BOT_PASSWORD, START_BALANCE, DAILY_BONUS_BASE,
    ADMIN_ID, TIMEZONE_OFFSET, MAIN_MENU_TEXT,
    NEWS_CHANNEL_ID, NEWS_CHANNEL_USERNAME, BOT_USERNAME
)
from models import User, Transaction, CasinoGame, IQResult
from keyboards import *
from utils import (
    check_rank_upgrade, add_medal, calculate_deposit_payout,
    calculate_credit_debt, get_rank_conditions, get_medals_info,
    RANK_BONUS_MULTIPLIER, notify_user, RANK_REWARDS, generate_referral_link,
    get_random_mental_task, check_mental_answer, get_work_rating,
    send_news_to_channel, add_transaction
)
from work_tracker import update_work_activity

router = Router()

# ---------- FSM Состояния ----------
class AuthState(StatesGroup):
    waiting_for_password = State()
    waiting_for_fullname = State()
    waiting_for_channel_sub = State()

class CasinoState(StatesGroup):
    waiting_for_bet = State()
    waiting_for_dice_bet = State()
    waiting_for_slots_bet = State()
    waiting_for_dice_guess = State()

class IQState(StatesGroup):
    answering = State()

class CreditState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_term = State()

class DepositState(StatesGroup):
    waiting_for_amount = State()

class TransferState(StatesGroup):
    waiting_for_recipient_name = State()
    waiting_for_amount = State()

class ShopState(StatesGroup):
    choosing_item = State()
    choosing_recipient_name = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

class AdminState(StatesGroup):
    waiting_for_user_id_balance = State()
    waiting_for_amount_balance = State()
    waiting_for_user_id_sub_balance = State()
    waiting_for_amount_sub_balance = State()
    waiting_for_user_id_rank = State()
    waiting_for_rank = State()
    waiting_for_user_id_rename = State()
    waiting_for_new_name = State()
    waiting_for_new_password = State()
    waiting_for_custom_button_text = State()
    waiting_for_custom_button_callback = State()
    waiting_for_medal_user_name = State()
    waiting_for_medal_name = State()
    waiting_for_main_menu_text = State()
    waiting_for_ban_user_name = State()
    waiting_for_unban_user_name = State()

class CharityState(StatesGroup):
    waiting_for_amount = State()

class MentalWorkState(StatesGroup):
    answering = State()

# ---------- Глобальный словарь для кастомных кнопок (не используется после удаления) ----------
custom_buttons = {}

# ---------- Вспомогательные функции ----------
async def get_user(user_id: int, session: AsyncSession) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == user_id))
    return result.scalar_one_or_none()

async def get_user_by_name(full_name: str, session: AsyncSession) -> User | None:
    result = await session.execute(select(User).where(User.full_name == full_name))
    return result.scalar_one_or_none()

async def update_balance(user: User, amount: float, session: AsyncSession, type_: str, description: str = None, bot=None):
    user.balance += amount
    if amount > 0:
        user.total_earned += amount
    await add_transaction(session, user.id, amount, type_, description)
    await session.commit()
    rank_change = await check_rank_upgrade(user, session)
    if rank_change:
        old, new = rank_change
        reward = RANK_REWARDS.get(new, 0)
        if reward > 0:
            user.balance += reward
            user.total_earned += reward
            await add_transaction(session, user.id, reward, "rank_reward", f"Награда за звание {new}")
            await session.commit()
        if bot:
            try:
                msg = f"🎉 Поздравляем! Ваше звание повышено с {old} до {new}!\n"
                msg += f"Теперь ваш ежечасный бонус составляет {DAILY_BONUS_BASE * RANK_BONUS_MULTIPLIER[new]:,} ₽!\n"
                if reward > 0:
                    msg += f"💰 Вы получили награду {reward:,.0f} ₽!"
                await bot.send_message(user.telegram_id, msg)
                await send_news_to_channel(bot, f"🎉 {user.full_name} повышен до звания {new} и получил {reward:,.0f} ₽")
            except:
                pass

def format_balance(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", ".")

def get_current_date() -> str:
    return datetime.now().strftime("%d.%m.%Y")

# ---------- IQ вопросы ----------
IQ_QUESTIONS = [
    {"q": "Сколько будет 2+2?", "o": ["3", "4", "5", "6"], "a": 1},
    {"q": "Какая планета ближе всего к Солнцу?", "o": ["Венера", "Земля", "Меркурий", "Марс"], "a": 2},
    {"q": "Сколько дней в високосном году?", "o": ["365", "366", "364", "367"], "a": 1},
    {"q": "Кто написал 'Войну и мир'?", "o": ["Достоевский", "Толстой", "Пушкин", "Гоголь"], "a": 1},
    {"q": "Какой газ преобладает в атмосфере Земли?", "o": ["Кислород", "Углекислый", "Азот", "Водород"], "a": 2},
    {"q": "Сколько континентов на Земле?", "o": ["5", "6", "7", "8"], "a": 2},
    {"q": "Какая самая длинная река в мире?", "o": ["Нил", "Амазонка", "Янцзы", "Миссисипи"], "a": 1},
    {"q": "В каком году началась Вторая мировая война?", "o": ["1939", "1941", "1914", "1945"], "a": 0},
    {"q": "Кто изобрёл телефон?", "o": ["Эдисон", "Белл", "Тесла", "Маркони"], "a": 1},
    {"q": "Сколько костей в теле взрослого человека?", "o": ["206", "205", "208", "210"], "a": 0},
    {"q": "Какая столица Франции?", "o": ["Лондон", "Берлин", "Мадрид", "Париж"], "a": 3},
    {"q": "Сколько цветов в радуге?", "o": ["5", "6", "7", "8"], "a": 2},
    {"q": "Какой элемент имеет символ 'O'?", "o": ["Золото", "Кислород", "Серебро", "Олово"], "a": 1},
    {"q": "Кто написал 'Преступление и наказание'?", "o": ["Толстой", "Достоевский", "Чехов", "Горький"], "a": 1},
    {"q": "Сколько сторон у куба?", "o": ["4", "5", "6", "8"], "a": 2},
]

# Товары для магазина (4 товара)
SHOP_ITEMS = [
    {
        "id": 1,
        "name": "🧪 Пробив боты 🧪",
        "price": 50000,
        "description": "🤖 После покупки товара вы получите ссылки на 2 бота в Телеграмме, которые ищут информацию о пользователе.\n✅ 1. Бот ищет информацию по всем сервисам, включая утечку данных.\n✅ 2. Бот ищет информацию только в Телеграмме.",
        "message": "✅ 1 Бот: @Obnalehevaem_Pyhkenskyq_bot (ищет информацию во всех источниках)\n✅ 2 Бот: @SKxoner_bot (ищет информацию только в Телеграмме)"
    },
    {
        "id": 2,
        "name": "💝 Telegram premium 💝",
        "price": 25000,
        "description": "🛍️ После покупки вы получаете Телеграмм бота, где можно оплатить 💝Telegram premium💝 банковской картой «🧤Мир🧤».",
        "message": "💝 @PremiumBot 💝 - Бот для покупки Premium функций Телеграмма.\n✅ Оплата доступна картами «🧤Мир🧤»."
    },
    {
        "id": 3,
        "name": "🔹 Vpn сервис 🔹",
        "price": 85000,
        "description": "🛍️ После покупки вы получаете Телеграмм бот для установки Vpn сервиса Android/iPhone. 2 дня бесплатного пробного периода, далее 299₽ в месяц.",
        "message": "🔹 @ultimavpnbot 🔹 - Бот для установки Vpn сервиса на ваш смартфон 💚"
    },
    {
        "id": 4,
        "name": "💜 Семья premium 💜",
        "price": 120000,
        "description": "💜 После покупки товара вы получаете «💟Premium💟» функции в боте:\n✅ Все кнопки перекрасятся в фиолетовый текст\n✅ В личном деле добавится надпись 💜Vip💜\n✅ Повышение в звании без ограничений\n✅ Медаль «💜Premium клиент💜»",
        "message": "💜 Поздравляем! Вы получили статус Vip! 💜\nТеперь у вас фиолетовые кнопки, звание повышено, медаль получена.",
        "is_vip": True
    }
]

ALL_MEDALS = [
    "✅15 из 15 iq✅", "💚Хорошист iq💚", "❌Все плохо iq❌",
    "😍💰Денежная щедрость💰😍", "🎁💝Подарочная щедрость💝🎁",
    "🎗️🎗️Помощь бедным🎗️🎗️", "🎰Лудоман🎰", "🔴Должник🔴", "❌Любитель кредитов❌",
    "❇️Бонус❇️", "🤑🤑Вкладчик🤑🤑", "💜Premium клиент💜", "🤝 Реферер 🤝", "🏅Медальщик🏅"
]

# ---------- /start ----------
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession, command: CommandObject = None):
    user_id = message.from_user.id
    user = await get_user(user_id, session)
    referrer_id = None
    args = command.args
    if args and args.isdigit():
        referrer_id = int(args)
    
    if not user:
        user = User(
            telegram_id=user_id,
            full_name="Не указано",
            balance=START_BALANCE,
            is_authorized=False,
            rank="Рядовой",
            medals="[]",
            max_balance_achieved=START_BALANCE,
            has_taken_credit=False,
            has_made_deposit=False,
            gifts_sent=0,
            purchases="[]",
            total_earned=0.0,
            total_donated=0.0,
            casino_bets_count=0,
            loans_taken=0,
            deposits_made=0,
            hourly_bonus_count=0,
            referrer_id=referrer_id,
            invited_count=0,
            is_vip=False,
            channel_subscribed=False,
            rank_manual=False,
            is_banned=False
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        if referrer_id and not user.referrer_id:
            user.referrer_id = referrer_id
            await session.commit()
        if user.is_banned:
            await message.answer("⛔ Вы заблокированы в боте.")
            return
    
    if not user.is_authorized:
        await message.answer(
            "🔐 Добро пожаловать! Для входа в бота введите пароль.",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(AuthState.waiting_for_password)
    else:
        if not user.channel_subscribed:
            await check_channel_subscription(message, user, state)
            return
        await message.answer(
            f"👋 С возвращением, {user.full_name}! Вы в главном меню.\n"
            f"📅 Сегодня {get_current_date()}",
            reply_markup=main_menu()
        )

async def check_channel_subscription(message: Message, user: User, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Подписаться на канал", url=f"https://t.me/{NEWS_CHANNEL_USERNAME}")
    builder.button(text="✅ Я подписался", callback_data="check_sub")
    await message.answer(
        "📰 Для продолжения необходимо подписаться на наш канал новостей!\n"
        "После подписки нажмите кнопку «Я подписался».",
        reply_markup=builder.as_markup()
    )
    await state.set_state(AuthState.waiting_for_channel_sub)
    await state.update_data(user_id=user.telegram_id)

@router.callback_query(StateFilter(AuthState.waiting_for_channel_sub), F.data == "check_sub")
async def check_subscription(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    user = await get_user(user_id, session)
    try:
        chat_member = await callback.bot.get_chat_member(chat_id=NEWS_CHANNEL_ID, user_id=user_id)
        if chat_member.status in ["member", "administrator", "creator"]:
            user.channel_subscribed = True
            await session.commit()
            await state.clear()
            if user.referrer_id and not user.referrer_id == user_id:
                referrer = await get_user(user.referrer_id, session)
                if referrer:
                    referrer.balance += 25000
                    referrer.total_earned += 25000
                    referrer.invited_count += 1
                    await add_transaction(session, referrer.id, 25000, "referral_bonus", f"Бонус за приглашение {user.full_name}")
                    await add_medal(referrer, "🤝 Реферер 🤝", session, give_bonus=True)
                    await notify_user(callback.bot, referrer.telegram_id, "🎉 Вы получили бонус 25 000 ₽ за приглашение друга!")
                    await send_news_to_channel(callback.bot, f"🤝 {referrer.full_name} пригласил друга и получил 25 000 ₽")
                await session.commit()
            await callback.message.edit_text("✅ Подписка подтверждена! Добро пожаловать в главное меню.")
            await back_to_main(callback, state, session)
        else:
            await callback.answer("❌ Вы ещё не подписались на канал!", show_alert=True)
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        await callback.answer("⚠️ Не удалось проверить подписку. Убедитесь, что бот добавлен в канал как администратор.", show_alert=True)

# ---------- Авторизация ----------
@router.message(StateFilter(AuthState.waiting_for_password), F.text)
async def process_password(message: Message, state: FSMContext, session: AsyncSession):
    if message.text == BOT_PASSWORD:
        user_id = message.from_user.id
        user = await get_user(user_id, session)
        if user and user.is_authorized:
            await message.answer(f"👋 Вы уже авторизованы, {user.full_name}!", reply_markup=main_menu())
            await state.clear()
            return
        await state.update_data(user_id=user_id)
        await message.answer("✅ Пароль верный! Введите ваше Имя и Фамилию (например: Иван Иванов):")
        await state.set_state(AuthState.waiting_for_fullname)
    else:
        await message.answer("❌ Неверный пароль. Попробуйте ещё раз.")

@router.message(StateFilter(AuthState.waiting_for_fullname), F.text)
async def process_fullname(message: Message, state: FSMContext, session: AsyncSession):
    name_parts = message.text.strip().split()
    if len(name_parts) < 2:
        await message.answer("Пожалуйста, введите и имя, и фамилию через пробел.")
        return
    
    full_name = " ".join(name_parts[:2]).title()
    data = await state.get_data()
    user_id = data["user_id"]
    user = await get_user(user_id, session)
    if not user:
        await message.answer("Ошибка: пользователь не найден.")
        return
    
    existing = await get_user_by_name(full_name, session)
    if existing and existing.telegram_id != user_id:
        await message.answer("❌ Это имя уже занято. Пожалуйста, введите другое Имя и Фамилию.")
        return
    
    user.full_name = full_name
    user.is_authorized = True
    await session.commit()
    
    if not user.channel_subscribed:
        await check_channel_subscription(message, user, state)
        return
    
    await message.answer(
        f"🎊✨ Добро пожаловать в нашу экономическую Rpg-игру, {full_name}! ✨🎊\n"
        f"📅 Сегодня {get_current_date()}\n"
        f"💰 Ваш стартовый баланс: {format_balance(START_BALANCE)} ₽\n\n"
        f"🏦 Зарабатывайте, играйте в казино, получайте звания и медали!\n"
        f"🎁 Приглашайте друзей и получайте бонусы!\n\n"
        f"Вы в главном меню:",
        reply_markup=main_menu()
    )
    await state.clear()
    if user.referrer_id and not user.referrer_id == user_id:
        referrer = await get_user(user.referrer_id, session)
        if referrer:
            referrer.balance += 25000
            referrer.total_earned += 25000
            referrer.invited_count += 1
            await add_transaction(session, referrer.id, 25000, "referral_bonus", f"Бонус за приглашение {user.full_name}")
            await add_medal(referrer, "🤝 Реферер 🤝", session, give_bonus=True)
            await notify_user(message.bot, referrer.telegram_id, "🎉 Вы получили бонус 25 000 ₽ за приглашение друга!")
            await send_news_to_channel(message.bot, f"🤝 {referrer.full_name} пригласил друга и получил 25 000 ₽")
        await session.commit()

# ---------- Главное меню ----------
@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.clear()
    user = await get_user(callback.from_user.id, session)
    text = MAIN_MENU_TEXT.replace("{name}", user.full_name).replace("{date}", get_current_date())
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

# ---------- Меню банка ----------
@router.callback_query(F.data == "bank_menu")
async def bank_menu(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    text = f"🏦✨ {user.full_name}, добро пожаловать в СберБанк! ✨🏦\n💰 Ваш баланс: {format_balance(user.balance)} ₽"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Обновить баланс", callback_data="refresh_balance"))
    builder.attach(InlineKeyboardBuilder.from_markup(bank_menu_keyboard()))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data == "refresh_balance")
async def refresh_balance(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    await session.refresh(user)
    text = f"🏦✨ {user.full_name}, добро пожаловать в СберБанк! ✨🏦\n💰 Ваш баланс: {format_balance(user.balance)} ₽"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Обновить баланс", callback_data="refresh_balance"))
    builder.attach(InlineKeyboardBuilder.from_markup(bank_menu_keyboard()))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer("Баланс обновлён")

# ---------- Ежечасный бонус ----------
@router.callback_query(F.data == "hourly_bonus")
async def hourly_bonus(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    
    now = datetime.now()
    if user.last_bonus and (now - user.last_bonus).total_seconds() < 3600:
        await callback.answer("Вы уже получали бонус в этом часу.", show_alert=True)
        return
    
    multiplier = RANK_BONUS_MULTIPLIER.get(user.rank, 1)
    bonus = DAILY_BONUS_BASE * multiplier
    user.balance += bonus
    user.total_earned += bonus
    user.last_bonus = now
    user.hourly_bonus_count += 1
    await session.commit()
    await add_transaction(session, user.id, bonus, "hourly_bonus", f"Ежечасный бонус ({user.rank})")
    
    if user.hourly_bonus_count >= 10:
        added = await add_medal(user, "❇️Бонус❇️", session, give_bonus=True)
        if added:
            await notify_user(callback.bot, user.telegram_id, f"🎉 Поздравляем! Вы получили медаль '❇️Бонус❇️' и {MEDAL_BONUSES['❇️Бонус❇️']:,} ₽!")
            await send_news_to_channel(callback.bot, f"🏅 {user.full_name} получил медаль '❇️Бонус❇️'")
    
    await callback.message.edit_text(
        f"🎁✨ Вы получили ежечасный бонус {format_balance(bonus)} ₽! ✨🎁\n"
        f"💰 Ваш новый баланс: {format_balance(user.balance)} ₽",
        reply_markup=back_keyboard("back_to_main")
    )
    await send_news_to_channel(callback.bot, f"🎁 {user.full_name} получил ежечасный бонус {format_balance(bonus)} ₽")
    await callback.answer()

# ---------- Казино ----------
@router.callback_query(F.data == "casino_menu")
async def casino_menu(callback: CallbackQuery):
    await callback.message.edit_text("🎰✨ Выберите игру: ✨🎰", reply_markup=casino_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data == "casino_rating")
async def casino_rating(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(User.full_name, func.sum(CasinoGame.payout).label("total_win"))
        .join(CasinoGame, User.id == CasinoGame.user_id)
        .where(CasinoGame.won == True)
        .group_by(User.id)
        .order_by(desc("total_win"))
        .limit(10)
    )
    rating = result.all()
    text = "🏆✨ Рейтинг казино (по выигрышам): ✨🏆\n"
    for i, row in enumerate(rating, 1):
        text += f"{i}. {row[0]} — {format_balance(row[1])} ₽\n"
    await callback.message.edit_text(text, reply_markup=back_keyboard("casino_menu"))
    await callback.answer()

# --- Кубик ---
@router.callback_query(F.data == "casino_dice")
async def dice_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🎲 Выберите сумму ставки:", reply_markup=dice_bet_keyboard())
    await state.set_state(CasinoState.waiting_for_dice_bet)
    await callback.answer()

@router.callback_query(StateFilter(CasinoState.waiting_for_dice_bet), F.data == "casino_menu")
async def back_from_dice_bet(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await casino_menu(callback)

@router.callback_query(StateFilter(CasinoState.waiting_for_dice_bet), F.data.startswith("dice_"))
async def dice_bet_set(callback: CallbackQuery, state: FSMContext):
    data = callback.data
    if data == "dice_custom":
        await callback.message.edit_text("Введите сумму ставки (целое число):")
        await state.set_state(CasinoState.waiting_for_bet)
        await state.update_data(game="dice")
        await callback.answer()
        return
    bet = int(data.split("_")[1])
    await state.update_data(bet=bet, game="dice")
    await callback.message.edit_text(
        f"🎲 Ставка: {format_balance(bet)} ₽. Загадайте число от 1 до 6:",
        reply_markup=dice_guess_keyboard()
    )
    await state.set_state(CasinoState.waiting_for_dice_guess)
    await callback.answer()

@router.callback_query(StateFilter(CasinoState.waiting_for_dice_guess), F.data == "casino_dice")
async def back_from_dice_guess(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await dice_start(callback, state)

@router.callback_query(StateFilter(CasinoState.waiting_for_dice_guess), F.data.startswith("dice_guess_"))
async def dice_guess(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    guess = int(callback.data.split("_")[-1])
    data = await state.get_data()
    bet = data["bet"]
    user = await get_user(callback.from_user.id, session)
    if user.balance < bet:
        await callback.answer("Недостаточно средств!", show_alert=True)
        return
    
    dice_msg = await callback.message.answer_dice(emoji="🎲")
    await asyncio.sleep(3.5)
    dice_value = dice_msg.dice.value
    
    won = (guess == dice_value)
    if won:
        payout = bet * 6
        await update_balance(user, payout - bet, session, "casino_win", f"Кубик: угадал {guess}, выпало {dice_value}", callback.bot)
        text = f"🎉✨ Вы угадали! Выпало {dice_value}. Выигрыш x6: {format_balance(payout)} ₽! ✨🎉"
    else:
        await update_balance(user, -bet, session, "casino_loss", f"Кубик: не угадал (загадано {guess}, выпало {dice_value})", callback.bot)
        text = f"😢 Не угадали. Загадано {guess}, выпало {dice_value}. Проигрыш {format_balance(bet)} ₽."
    
    user.casino_bets_count += 1
    if user.casino_bets_count == 30:
        added = await add_medal(user, "🎰Лудоман🎰", session, give_bonus=True)
        if added:
            await notify_user(callback.bot, user.telegram_id, f"🎉 Поздравляем! Вы получили медаль '🎰Лудоман🎰' и {MEDAL_BONUSES['🎰Лудоман🎰']:,} ₽!")
            await send_news_to_channel(callback.bot, f"🏅 {user.full_name} получил медаль '🎰Лудоман🎰'")
    
    game = CasinoGame(
        user_id=user.id,
        bet_amount=bet,
        game_type="dice",
        result=f"guess={guess}, dice={dice_value}",
        won=won,
        payout=payout if won else 0
    )
    session.add(game)
    await session.commit()
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎲 Играть снова", callback_data="casino_dice"))
    builder.row(InlineKeyboardButton(text="🏠 В меню казино", callback_data="casino_menu"))
    
    await callback.message.edit_text(
        f"{text}\n💰 Баланс: {format_balance(user.balance)} ₽",
        reply_markup=builder.as_markup()
    )
    await state.clear()
    await callback.answer()

# --- Слоты ---
@router.callback_query(F.data == "casino_slots")
async def slots_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🎰 Выберите сумму ставки:", reply_markup=slots_bet_keyboard())
    await state.set_state(CasinoState.waiting_for_slots_bet)
    await callback.answer()

@router.callback_query(StateFilter(CasinoState.waiting_for_slots_bet), F.data == "casino_menu")
async def back_from_slots_bet(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await casino_menu(callback)

@router.callback_query(StateFilter(CasinoState.waiting_for_slots_bet), F.data.startswith("slots_"))
async def slots_bet_set(callback: CallbackQuery, state: FSMContext):
    data = callback.data
    if data == "slots_custom":
        await callback.message.edit_text("Введите сумму ставки (целое число):")
        await state.set_state(CasinoState.waiting_for_bet)
        await state.update_data(game="slots")
        await callback.answer()
        return
    bet = int(data.split("_")[1])
    await state.update_data(bet=bet, game="slots")
    await callback.message.edit_text(
        f"🎰 Ставка: {format_balance(bet)} ₽. Запускайте слоты!",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="🎰 Крутить", callback_data="spin_slots")
        ).row(InlineKeyboardButton(text="🔙 Назад", callback_data="casino_slots")).as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "spin_slots")
async def slots_spin(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    bet = data["bet"]
    user = await get_user(callback.from_user.id, session)
    if user.balance < bet:
        await callback.answer("Недостаточно средств!", show_alert=True)
        return
    
    slot_msg = await callback.message.answer_dice(emoji="🎰")
    await asyncio.sleep(3.5)
    slot_value = slot_msg.dice.value
    
    if slot_value in [1, 22, 43, 64]:
        multiplier = 7
        combo = "три одинаковых"
    elif slot_value in [2, 3, 4, 21, 23, 42, 44, 63]:
        multiplier = 3
        combo = "два одинаковых"
    else:
        multiplier = 0
        combo = "без совпадений"
    
    won = multiplier > 0
    if won:
        payout = bet * multiplier
        await update_balance(user, payout - bet, session, "casino_win", f"Слоты: {combo}", callback.bot)
        text = f"🎉✨ Слоты! Комбинация {slot_value} ({combo}). Выигрыш x{multiplier}: {format_balance(payout)} ₽ ✨🎉"
    else:
        await update_balance(user, -bet, session, "casino_loss", f"Слоты: {combo}", callback.bot)
        text = f"😢 Слоты! Комбинация {slot_value} ({combo}). Проигрыш {format_balance(bet)} ₽."
    
    user.casino_bets_count += 1
    if user.casino_bets_count == 30:
        added = await add_medal(user, "🎰Лудоман🎰", session, give_bonus=True)
        if added:
            await notify_user(callback.bot, user.telegram_id, f"🎉 Поздравляем! Вы получили медаль '🎰Лудоман🎰' и {MEDAL_BONUSES['🎰Лудоман🎰']:,} ₽!")
            await send_news_to_channel(callback.bot, f"🏅 {user.full_name} получил медаль '🎰Лудоман🎰'")
    
    game = CasinoGame(
        user_id=user.id,
        bet_amount=bet,
        game_type="slots",
        result=str(slot_value),
        won=won,
        payout=payout if won else 0
    )
    session.add(game)
    await session.commit()
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎰 Играть снова", callback_data="casino_slots"))
    builder.row(InlineKeyboardButton(text="🏠 В меню казино", callback_data="casino_menu"))
    
    await callback.message.edit_text(
        f"{text}\n💰 Баланс: {format_balance(user.balance)} ₽",
        reply_markup=builder.as_markup()
    )
    await state.clear()
    await callback.answer()

@router.message(StateFilter(CasinoState.waiting_for_bet), F.text.isdigit())
async def custom_bet_input(message: Message, state: FSMContext):
    bet = int(message.text)
    if bet <= 0:
        await message.answer("Ставка должна быть больше 0.")
        return
    data = await state.get_data()
    game = data["game"]
    await state.update_data(bet=bet)
    if game == "dice":
        await message.answer(
            f"🎲 Ставка: {format_balance(bet)} ₽. Загадайте число от 1 до 6:",
            reply_markup=dice_guess_keyboard()
        )
        await state.set_state(CasinoState.waiting_for_dice_guess)
    else:
        await message.answer(
            f"🎰 Ставка: {format_balance(bet)} ₽. Запускайте слоты!",
            reply_markup=InlineKeyboardBuilder().row(
                InlineKeyboardButton(text="🎰 Крутить", callback_data="spin_slots")
            ).row(InlineKeyboardButton(text="🔙 Назад", callback_data="casino_slots")).as_markup()
        )
        await state.set_state(None)

# ---------- Тест IQ ----------
@router.callback_query(F.data == "iq_test")
async def iq_test_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    existing_result = await session.execute(
        select(IQResult).where(IQResult.user_id == user.id)
    )
    if existing_result.scalar_one_or_none():
        await callback.answer("Вы уже проходили тест IQ. Рейтинг учитывает только первую попытку.", show_alert=True)
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Отменить тест", callback_data="cancel_iq")
    await callback.message.edit_text(
        "🧠✨ Тест IQ. 15 вопросов. Нажмите 'Отменить тест' чтобы выйти. Деньги не списываются, медали не выдаются при повторном прохождении. ✨🧠",
        reply_markup=builder.as_markup()
    )
    await state.update_data(iq_answers=[], iq_index=0)
    await state.set_state(IQState.answering)
    await asyncio.sleep(1)
    await send_iq_question(callback.message, state, 0)
    await callback.answer()

async def send_iq_question(message: Message, state: FSMContext, index: int):
    q = IQ_QUESTIONS[index]
    builder = InlineKeyboardBuilder()
    for i, opt in enumerate(q["o"]):
        builder.button(text=opt, callback_data=f"iq_ans_{index}_{i}")
    builder.button(text="🚫 Отменить тест", callback_data="cancel_iq")
    builder.adjust(1)
    await message.edit_text(
        f"🧠 Вопрос {index+1}/15:\n{q['q']}",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "cancel_iq")
async def cancel_iq(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Тест IQ отменён.", reply_markup=main_menu())
    await callback.answer()

@router.callback_query(StateFilter(IQState.answering), F.data.startswith("iq_ans_"))
async def iq_answer(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    index = data["iq_index"]
    answers = data["iq_answers"]
    _, _, q_idx, ans_idx = callback.data.split("_")
    q_idx = int(q_idx)
    ans_idx = int(ans_idx)
    
    correct = IQ_QUESTIONS[q_idx]["a"]
    answers.append(1 if ans_idx == correct else 0)
    
    if q_idx + 1 < len(IQ_QUESTIONS):
        await state.update_data(iq_answers=answers, iq_index=q_idx+1)
        await send_iq_question(callback.message, state, q_idx+1)
    else:
        await finish_iq_test(callback, state, answers, session)
    await callback.answer()

async def finish_iq_test(callback: CallbackQuery, state: FSMContext, answers: list, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    correct = sum(answers)
    total = len(answers)
    
    existing_result = await session.execute(
        select(IQResult).where(IQResult.user_id == user.id)
    )
    first_time = existing_result.scalar_one_or_none() is None
    
    medal = ""
    bonus = 0
    detail = ""
    if correct == 15:
        medal = "✅15 из 15 iq✅"
        detail = "15/15"
    elif correct >= 9:
        medal = "💚Хорошист iq💚"
        detail = f"{correct}/15"
    elif correct < 5:
        medal = "❌Все плохо iq❌"
        detail = f"{correct}/15"
    
    if first_time and medal:
        added = await add_medal(user, medal, session, give_bonus=True)
        if added:
            bonus = MEDAL_BONUSES.get(medal, 0)
            await notify_user(callback.bot, user.telegram_id, f"🎉 Поздравляем! Вы получили медаль '{medal}' и {bonus:,} ₽!")
            await send_news_to_channel(callback.bot, f"🏅 {user.full_name} получил медаль '{medal}'")
        iq_result = IQResult(
            user_id=user.id,
            correct_answers=correct,
            medal=medal,
            bonus=bonus
        )
        session.add(iq_result)
        await session.commit()
    
    if first_time:
        text = f"🧠✨ Тест завершён! ✨🧠\nПравильных ответов: {correct} из {total}\n"
        if medal:
            text += f"Медаль: {medal} ({detail})\n"
            if bonus:
                text += f"Бонус: {format_balance(bonus)} ₽\n"
        text += f"💰 Текущий баланс: {format_balance(user.balance)} ₽"
    else:
        text = f"🧠✨ Тест завершён! ✨🧠\nПравильных ответов: {correct} из {total}\n(Повторное прохождение, медаль и бонус не начислены)"
    
    await callback.message.edit_text(text, reply_markup=back_keyboard("back_to_main"))
    await state.clear()

# ---------- Кредит ----------
@router.callback_query(F.data == "credit_menu")
async def credit_menu(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if user.credit_amount > 0:
        now = datetime.now()
        hours_passed = (now - user.credit_start_date).total_seconds() / 3600
        current_debt = calculate_credit_debt(user.credit_original, hours_passed)
        due = user.credit_due_date.strftime("%d.%m.%Y %H:%M")
        text = (
            f"💵✨ Ваш текущий кредит: ✨💵\n"
            f"Взято: {format_balance(user.credit_original)} ₽\n"
            f"Текущий долг: {format_balance(current_debt)} ₽\n"
            f"Срок: {user.credit_term_hours} часов (до {due})\n"
            f"Ставка: 30% каждые 5 часов"
        )
        await callback.message.edit_text(text, reply_markup=credit_menu_keyboard())
    else:
        await callback.message.edit_text(
            "💵✨ Кредит. Вы можете взять кредит на срок 5-25 часов.\n"
            "Процентная ставка: 30% каждые 5 часов от суммы кредита. ✨💵",
            reply_markup=credit_menu_keyboard()
        )
    await callback.answer()

@router.callback_query(F.data == "take_credit")
async def take_credit_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if user.credit_amount > 0:
        await callback.answer("У вас уже есть непогашенный кредит!", show_alert=True)
        return
    
    max_credit = user.balance * 10
    await callback.message.edit_text(
        f"💰 Ваш баланс: {format_balance(user.balance)} ₽\n"
        f"Максимальная сумма кредита: {format_balance(max_credit)} ₽\n"
        f"Введите желаемую сумму:",
        reply_markup=back_keyboard("credit_menu")
    )
    await state.set_state(CreditState.waiting_for_amount)
    await state.update_data(max_credit=max_credit)
    await callback.answer()

@router.callback_query(StateFilter(CreditState.waiting_for_amount), F.data == "credit_menu")
async def back_from_credit_amount(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await credit_menu(callback)

@router.message(StateFilter(CreditState.waiting_for_amount), F.text)
async def credit_amount_input(message: Message, state: FSMContext, session: AsyncSession):
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введите число.")
        return
    
    data = await state.get_data()
    max_credit = data["max_credit"]
    if amount <= 0 or amount > max_credit:
        await message.answer(f"Сумма должна быть от 1 до {format_balance(max_credit)} ₽.")
        return
    
    await state.update_data(credit_amount=amount)
    await message.answer(
        "Выберите срок кредита (в часах):",
        reply_markup=credit_term_keyboard()
    )
    await state.set_state(CreditState.waiting_for_term)

@router.callback_query(StateFilter(CreditState.waiting_for_term), F.data == "credit_menu")
async def back_from_credit_term(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await credit_menu(callback)

@router.callback_query(StateFilter(CreditState.waiting_for_term), F.data.startswith("credit_term_"))
async def credit_term_chosen(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    term = int(callback.data.split("_")[2])
    data = await state.get_data()
    amount = data["credit_amount"]
    user = await get_user(callback.from_user.id, session)
    
    now = datetime.now()
    due_date = now + timedelta(hours=term)
    
    user.credit_original = amount
    user.credit_amount = amount
    user.credit_term_hours = term
    user.credit_start_date = now
    user.credit_due_date = due_date
    user.has_taken_credit = True
    user.loans_taken += 1
    user.balance += amount
    user.total_earned += amount
    await session.commit()
    await add_transaction(session, user.id, amount, "credit", f"Взят кредит {format_balance(amount)} ₽ на {term} ч")
    
    if user.loans_taken > 2:
        added = await add_medal(user, "❌Любитель кредитов❌", session, give_bonus=True)
        if added:
            await notify_user(callback.bot, user.telegram_id, f"🎉 Поздравляем! Вы получили медаль '❌Любитель кредитов❌' и {MEDAL_BONUSES['❌Любитель кредитов❌']:,} ₽!")
            await send_news_to_channel(callback.bot, f"🏅 {user.full_name} получил медаль '❌Любитель кредитов❌'")
    
    await callback.message.edit_text(
        f"✅ Кредит одобрен!\n"
        f"Получено: {format_balance(amount)} ₽\n"
        f"Срок: {term} часов (до {due_date.strftime('%d.%m.%Y %H:%M')})\n"
        f"Ставка: 30% каждые 5 часов",
        reply_markup=back_keyboard("bank_menu")
    )
    await state.clear()
    await callback.answer()

# ---------- Погашение кредита ----------
@router.callback_query(F.data == "repay_credit")
async def repay_credit_start(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if user.credit_amount <= 0:
        await callback.answer("У вас нет непогашенного кредита.", show_alert=True)
        return
    
    now = datetime.now()
    hours_passed = (now - user.credit_start_date).total_seconds() / 3600
    current_debt = calculate_credit_debt(user.credit_original, hours_passed)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Погасить полностью", callback_data="confirm_repay")
    builder.button(text="🔙 Назад", callback_data="credit_menu")
    
    await callback.message.edit_text(
        f"💵 Погашение кредита\n"
        f"Текущий долг: {format_balance(current_debt)} ₽\n"
        f"Ваш баланс: {format_balance(user.balance)} ₽\n\n"
        f"Нажмите «Погасить полностью» для оплаты.",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "confirm_repay")
async def confirm_repay(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if user.credit_amount <= 0:
        await callback.answer("Кредит уже погашен.", show_alert=True)
        return
    
    now = datetime.now()
    hours_passed = (now - user.credit_start_date).total_seconds() / 3600
    current_debt = calculate_credit_debt(user.credit_original, hours_passed)
    
    if user.balance < current_debt:
        await callback.answer("Недостаточно средств для полного погашения.", show_alert=True)
        return
    
    user.balance -= current_debt
    user.credit_amount = 0
    user.credit_original = 0
    user.credit_term_hours = 0
    user.credit_start_date = None
    user.credit_due_date = None
    user.credit_overdue_notified = False
    await session.commit()
    await add_transaction(session, user.id, -current_debt, "credit_repay", f"Погашение кредита")
    
    await callback.message.edit_text(
        f"✅ Кредит полностью погашен!\n"
        f"Списано: {format_balance(current_debt)} ₽\n"
        f"Остаток на балансе: {format_balance(user.balance)} ₽",
        reply_markup=back_keyboard("bank_menu")
    )
    await callback.answer()

# ---------- Вклад ----------
@router.callback_query(F.data == "deposit_menu")
async def deposit_menu(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if user.deposit_amount > 0:
        now = datetime.now()
        hours_passed = (now - user.deposit_start_date).total_seconds() / 3600
        current = calculate_deposit_payout(user.deposit_amount, hours_passed)
        text = (
            f"💰✨ Ваш вклад: ✨💰\n"
            f"Сумма вклада: {format_balance(user.deposit_amount)} ₽\n"
            f"Текущая сумма с процентами: {format_balance(current)} ₽\n"
            f"Процент: 20% каждый час"
        )
    else:
        text = "💰✨ Вклад. Вы можете открыть вклад под 20% в час. Снять можно в любой момент. ✨💰"
    await callback.message.edit_text(text, reply_markup=deposit_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data == "open_deposit")
async def deposit_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if user.deposit_amount > 0:
        await callback.answer("У вас уже открыт вклад. Закройте его, чтобы открыть новый.", show_alert=True)
        return
    
    await callback.message.edit_text("Введите сумму вклада:", reply_markup=back_keyboard("deposit_menu"))
    await state.set_state(DepositState.waiting_for_amount)
    await callback.answer()

@router.callback_query(StateFilter(DepositState.waiting_for_amount), F.data == "deposit_menu")
async def back_from_deposit_amount(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await deposit_menu(callback)

@router.message(StateFilter(DepositState.waiting_for_amount), F.text)
async def deposit_amount_input(message: Message, state: FSMContext, session: AsyncSession):
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("Введите число.")
        return
    
    user = await get_user(message.from_user.id, session)
    if amount <= 0 or amount > user.balance:
        await message.answer("Недостаточно средств или некорректная сумма.")
        return
    
    user.balance -= amount
    user.deposit_amount = amount
    user.deposit_start_date = datetime.now()
    user.has_made_deposit = True
    user.deposits_made += 1
    await session.commit()
    await add_transaction(session, user.id, -amount, "deposit_open", f"Открыт вклад {format_balance(amount)} ₽")
    
    if user.deposits_made > 2:
        added = await add_medal(user, "🤑🤑Вкладчик🤑🤑", session, give_bonus=True)
        if added:
            await notify_user(message.bot, user.telegram_id, f"🎉 Поздравляем! Вы получили медаль '🤑🤑Вкладчик🤑🤑' и {MEDAL_BONUSES['🤑🤑Вкладчик🤑🤑']:,} ₽!")
            await send_news_to_channel(message.bot, f"🏅 {user.full_name} получил медаль '🤑🤑Вкладчик🤑🤑'")
    
    await message.answer(
        f"✅✨ Вклад открыт! ✨✅\nСумма: {format_balance(amount)} ₽\nПроцент: 20% каждый час.",
        reply_markup=main_menu()
    )
    await state.clear()

@router.callback_query(F.data == "close_deposit")
async def close_deposit(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if user.deposit_amount <= 0:
        await callback.answer("У вас нет открытого вклада.", show_alert=True)
        return
    
    now = datetime.now()
    hours_passed = (now - user.deposit_start_date).total_seconds() / 3600
    total = calculate_deposit_payout(user.deposit_amount, hours_passed)
    
    user.balance += total
    user.total_earned += total - user.deposit_amount
    await add_transaction(session, user.id, total - user.deposit_amount, "deposit_interest", f"Проценты по вкладу за {hours_passed:.1f} ч")
    await add_transaction(session, user.id, user.deposit_amount, "deposit_close", "Закрытие вклада")
    
    user.deposit_amount = 0
    user.deposit_start_date = None
    await session.commit()
    
    await callback.message.edit_text(
        f"✅✨ Вклад закрыт! ✨✅\n"
        f"Вы получили: {format_balance(total)} ₽\n"
        f"Текущий баланс: {format_balance(user.balance)} ₽",
        reply_markup=back_keyboard("bank_menu")
    )
    await callback.answer()

# ---------- Переводы ----------
@router.callback_query(F.data == "transfer")
async def transfer_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "💸 Введите Имя и Фамилию получателя (как в боте):",
        reply_markup=back_keyboard("bank_menu")
    )
    await state.set_state(TransferState.waiting_for_recipient_name)
    await callback.answer()

@router.callback_query(StateFilter(TransferState.waiting_for_recipient_name), F.data == "bank_menu")
async def back_from_transfer_name(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.clear()
    await bank_menu(callback, session)

@router.message(StateFilter(TransferState.waiting_for_recipient_name), F.text)
async def transfer_recipient(message: Message, state: FSMContext, session: AsyncSession):
    recip_name = message.text.strip().title()
    recip = await get_user_by_name(recip_name, session)
    if not recip:
        await message.answer("❌ Пользователь с таким именем не найден в боте.")
        return
    
    await state.update_data(recip_id=recip.telegram_id, recip_name=recip.full_name)
    await message.answer(f"Получатель: {recip.full_name}\nВведите сумму перевода:", reply_markup=back_keyboard("bank_menu"))
    await state.set_state(TransferState.waiting_for_amount)

@router.callback_query(StateFilter(TransferState.waiting_for_amount), F.data == "bank_menu")
async def back_from_transfer_amount(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.clear()
    await bank_menu(callback, session)

@router.message(StateFilter(TransferState.waiting_for_amount), F.text)
async def transfer_amount(message: Message, state: FSMContext, session: AsyncSession):
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("Введите число.")
        return
    
    user = await get_user(message.from_user.id, session)
    if amount <= 0 or amount > user.balance:
        await message.answer("Недостаточно средств или некорректная сумма.")
        return
    
    data = await state.get_data()
    recip_id = data["recip_id"]
    recip_name = data["recip_name"]
    recip = await get_user(recip_id, session)
    
    user.balance -= amount
    recip.balance += amount
    recip.total_earned += amount
    await session.commit()
    await add_transaction(session, user.id, -amount, "transfer_out", f"Перевод пользователю {recip_name}")
    await add_transaction(session, recip.id, amount, "transfer_in", f"Получено от {user.full_name}")
    
    result = await session.execute(
        select(func.sum(Transaction.amount)).where(
            Transaction.user_id == user.id,
            Transaction.type == "transfer_out"
        )
    )
    total_transferred = abs(result.scalar() or 0)
    if total_transferred >= 50000:
        added = await add_medal(user, "😍💰Денежная щедрость💰😍", session, give_bonus=True)
        if added:
            await notify_user(message.bot, user.telegram_id, f"🎉 Поздравляем! Вы получили медаль '😍💰Денежная щедрость💰😍' и {MEDAL_BONUSES['😍💰Денежная щедрость💰😍']:,} ₽!")
            await send_news_to_channel(message.bot, f"🏅 {user.full_name} получил медаль '😍💰Денежная щедрость💰😍'")
    
    local_time = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
    await notify_user(
        message.bot,
        recip.telegram_id,
        f"💰✨ Вам поступил перевод! ✨💰\n"
        f"Отправитель: {user.full_name}\n"
        f"Сумма: {format_balance(amount)} ₽\n"
        f"Время: {local_time.strftime('%d.%m.%Y %H:%M')}\n"
        f"Ваш текущий баланс: {format_balance(recip.balance)} ₽"
    )
    
    await message.answer(
        f"✅✨ Перевод выполнен! ✨✅\nПолучатель: {recip_name}\nСумма: {format_balance(amount)} ₽",
        reply_markup=main_menu()
    )
    await send_news_to_channel(message.bot, f"💸 {user.full_name} перевёл {format_balance(amount)} ₽ пользователю {recip_name}")
    await state.clear()

# ---------- Магазин ----------
@router.callback_query(F.data == "shop_menu")
async def shop_menu(callback: CallbackQuery):
    await callback.message.edit_text("🛍️✨ Добро пожаловать в магазин! ✨🛍️\nВыберите товар:", reply_markup=shop_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("shop_item_"))
async def shop_item_view(callback: CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split("_")[2]) - 1
    item = SHOP_ITEMS[item_id]
    can_gift = True
    await state.update_data(shop_item=item, shop_item_id=item_id)
    await callback.message.edit_text(
        f"{item['name']}\n💰 Цена: {format_balance(item['price'])} ₽\n\n📝 {item['description']}",
        reply_markup=shop_item_keyboard(item_id+1, can_gift)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("buy_item_"))
async def buy_item(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    item_id = int(callback.data.split("_")[2]) - 1
    item = SHOP_ITEMS[item_id]
    user = await get_user(callback.from_user.id, session)
    
    if user.balance < item["price"]:
        await callback.answer("Недостаточно средств!", show_alert=True)
        return
    
    user.balance -= item["price"]
    purchases = json.loads(user.purchases) if user.purchases else []
    purchases.append({"name": item["name"], "message": item["message"], "date": datetime.now().isoformat()})
    user.purchases = json.dumps(purchases)
    
    if item.get("is_vip"):
        user.is_vip = True
        old_rank = user.rank
        ranks = ["Рядовой", "Ефрейтор", "Младший сержант", "Сержант", "Старший сержант", "Лейтенант", "Старший лейтенант"]
        current_idx = ranks.index(user.rank)
        if current_idx < len(ranks) - 1:
            user.rank = ranks[current_idx + 1]
        user.rank_manual = True
        added = await add_medal(user, "💜Premium клиент💜", session, give_bonus=True)
        if added:
            await notify_user(callback.bot, user.telegram_id, f"🎉 Поздравляем! Вы получили медаль '💜Premium клиент💜' и {MEDAL_BONUSES['💜Premium клиент💜']:,} ₽!")
            await send_news_to_channel(callback.bot, f"🏅 {user.full_name} получил медаль '💜Premium клиент💜'")
        if old_rank != user.rank:
            await notify_user(callback.bot, user.telegram_id, f"🎉 Поздравляем! Ваше звание повышено с {old_rank} до {user.rank}!")
            await send_news_to_channel(callback.bot, f"🎉 {user.full_name} повышен до {user.rank} (Vip)")
    
    await session.commit()
    await add_transaction(session, user.id, -item["price"], "shop_purchase", f"Покупка {item['name']}")
    
    await callback.message.edit_text(
        f"✅ Покупка совершена!\n\n{item['message']}",
        reply_markup=back_keyboard("shop_menu")
    )
    await notify_user(callback.bot, user.telegram_id, f"🎉 Вы приобрели {item['name']}!")
    await send_news_to_channel(callback.bot, f"🛍️ {user.full_name} приобрёл {item['name']} за {format_balance(item['price'])} ₽")
    await callback.answer()

@router.callback_query(F.data.startswith("gift_item_"))
async def gift_item_start(callback: CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split("_")[2]) - 1
    item = SHOP_ITEMS[item_id]
    await state.update_data(gift_item=item, gift_item_id=item_id)
    await callback.message.edit_text(
        "🎁 Введите Имя и Фамилию получателя подарка:",
        reply_markup=back_keyboard("shop_menu")
    )
    await state.set_state(ShopState.choosing_recipient_name)
    await callback.answer()

@router.message(StateFilter(ShopState.choosing_recipient_name), F.text)
async def gift_item_finish(message: Message, state: FSMContext, session: AsyncSession):
    recip_name = message.text.strip().title()
    recip = await get_user_by_name(recip_name, session)
    if not recip:
        await message.answer("Пользователь с таким именем не найден.")
        return
    
    data = await state.get_data()
    item = data["gift_item"]
    user = await get_user(message.from_user.id, session)
    
    if user.balance < item["price"]:
        await message.answer("Недостаточно средств для подарка.")
        return
    
    user.balance -= item["price"]
    user.gifts_sent += 1
    recip_purchases = json.loads(recip.purchases) if recip.purchases else []
    recip_purchases.append({"name": item["name"], "message": item["message"], "date": datetime.now().isoformat(), "gift_from": user.full_name})
    recip.purchases = json.dumps(recip_purchases)
    
    if item.get("is_vip"):
        recip.is_vip = True
        old_rank = recip.rank
        ranks = ["Рядовой", "Ефрейтор", "Младший сержант", "Сержант", "Старший сержант", "Лейтенант", "Старший лейтенант"]
        current_idx = ranks.index(recip.rank)
        if current_idx < len(ranks) - 1:
            recip.rank = ranks[current_idx + 1]
        recip.rank_manual = True
        added = await add_medal(recip, "💜Premium клиент💜", session, give_bonus=True)
        if added:
            await notify_user(message.bot, recip.telegram_id, f"🎉 Поздравляем! Вы получили медаль '💜Premium клиент💜' и {MEDAL_BONUSES['💜Premium клиент💜']:,} ₽ в подарок!")
            await send_news_to_channel(message.bot, f"🏅 {recip.full_name} получил медаль '💜Premium клиент💜' в подарок")
        if old_rank != recip.rank:
            await notify_user(message.bot, recip.telegram_id, f"🎉 Поздравляем! Ваше звание повышено с {old_rank} до {recip.rank}!")
            await send_news_to_channel(message.bot, f"🎉 {recip.full_name} повышен до {recip.rank} (Vip подарок)")
    
    if user.gifts_sent >= 5:
        added = await add_medal(user, "🎁💝Подарочная щедрость💝🎁", session, give_bonus=True)
        if added:
            await notify_user(message.bot, user.telegram_id, f"🎉 Вы получили медаль '🎁💝Подарочная щедрость💝🎁' и {MEDAL_BONUSES['🎁💝Подарочная щедрость💝🎁']:,} ₽!")
            await send_news_to_channel(message.bot, f"🏅 {user.full_name} получил медаль '🎁💝Подарочная щедрость💝🎁'")
    
    await session.commit()
    await add_transaction(session, user.id, -item["price"], "gift_sent", f"Подарок {item['name']} для {recip.full_name}")
    
    await notify_user(message.bot, recip.telegram_id, f"🎁 {user.full_name} подарил вам {item['name']}!\n{item['message']}")
    await message.answer(
        f"✅ Вы подарили {item['name']} пользователю {recip.full_name}!",
        reply_markup=main_menu()
    )
    await send_news_to_channel(message.bot, f"🎁 {user.full_name} подарил {item['name']} пользователю {recip.full_name}")
    await state.clear()

# ---------- Реферальная ссылка ----------
@router.callback_query(F.data == "profile_referral")
async def profile_referral(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    link = generate_referral_link(user.telegram_id)
    text = (
        f"🔗✨ Ваша реферальная ссылка: ✨🔗\n"
        f"{link}\n\n"
        f"🤝 Приглашено друзей: {user.invited_count}\n"
        f"💰 За каждого друга вы получаете 25 000 ₽!"
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("profile"))
    await callback.answer()

# ---------- Семья ----------
@router.callback_query(F.data == "family")
async def family_list(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(User).where(User.full_name != "Не указано")
    )
    users = result.scalars().all()
    if not users:
        await callback.answer("Нет зарегистрированных пользователей.", show_alert=True)
        return
    
    text = "👨‍👩‍👧‍👦✨ Семья: ✨👨‍👩‍👧‍👦\n"
    for u in users:
        text += f"• {u.full_name} — {u.rank} (доход: {format_balance(u.total_earned)} ₽)\n"
    
    builder = InlineKeyboardBuilder()
    for u in users:
        builder.button(text=u.full_name, callback_data=f"family_profile_{u.telegram_id}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("family_profile_"))
async def family_profile_main(callback: CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split("_")[2])
    user = await get_user(user_id, session)
    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    
    text = (
        f"📋✨ Личное дело {user.full_name} ✨📋\n"
        f"🆔 Id: {user.telegram_id}\n"
        f"📅 В боте с: {user.registered_at.strftime('%d.%m.%Y')}"
    )
    if user.is_vip:
        text = f"💜 Vip 💜\n{text}"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Баланс", callback_data=f"fam_balance_{user_id}")
    builder.button(text="🏅 Звания", callback_data=f"fam_rank_{user_id}")
    builder.button(text="🎁 Подарки", callback_data=f"fam_gifts_{user_id}")
    builder.button(text="🏅 Медали", callback_data=f"fam_medals_{user_id}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="family"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("fam_balance_"))
async def fam_balance(callback: CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split("_")[2])
    user = await get_user(user_id, session)
    text = f"💰✨ Баланс {user.full_name}: {format_balance(user.balance)} ₽\n📈 Доход: {format_balance(user.total_earned)} ₽ ✨💰"
    await callback.message.edit_text(text, reply_markup=back_keyboard(f"family_profile_{user_id}"))
    await callback.answer()

@router.callback_query(F.data.startswith("fam_rank_"))
async def fam_rank(callback: CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split("_")[2])
    user = await get_user(user_id, session)
    text = f"🎖✨ Звание {user.full_name}: {user.rank} ✨🎖"
    await callback.message.edit_text(text, reply_markup=back_keyboard(f"family_profile_{user_id}"))
    await callback.answer()

@router.callback_query(F.data.startswith("fam_gifts_"))
async def fam_gifts(callback: CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split("_")[2])
    user = await get_user(user_id, session)
    purchases = json.loads(user.purchases) if user.purchases else []
    if purchases:
        text = f"🎁✨ Подарки/покупки {user.full_name}: ✨🎁\n"
        for p in purchases:
            text += f"• {p.get('name', 'Товар')}"
            if p.get('gift_from'):
                text += f" (от {p['gift_from']})"
            text += "\n"
    else:
        text = "У пользователя пока нет подарков."
    await callback.message.edit_text(text, reply_markup=back_keyboard(f"family_profile_{user_id}"))
    await callback.answer()

@router.callback_query(F.data.startswith("fam_medals_"))
async def fam_medals(callback: CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split("_")[2])
    user = await get_user(user_id, session)
    medals = json.loads(user.medals) if user.medals else []
    text = f"🏅✨ Медали {user.full_name}: ✨🏅\n" + "\n".join(medals) if medals else "Нет медалей."
    await callback.message.edit_text(text, reply_markup=back_keyboard(f"family_profile_{user_id}"))
    await callback.answer()

# ---------- Профиль ----------
@router.callback_query(F.data == "profile")
async def profile_main(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    text = (
        f"🫆✨ Профиль {user.full_name} ✨🫆\n"
        f"📅 Дата регистрации: {user.registered_at.strftime('%d.%m.%Y')}\n"
        f"💰 Баланс: {format_balance(user.balance)} ₽\n"
        f"📈 Общий доход: {format_balance(user.total_earned)} ₽"
    )
    if user.is_vip:
        text = f"💜 Vip 💜\n{text}"
    await callback.message.edit_text(text, reply_markup=profile_sections_keyboard())
    await callback.answer()

@router.callback_query(F.data == "profile_ranks")
async def profile_ranks(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    text = f"🎖✨ Ваше звание: {user.rank} ✨🎖"
    await callback.message.edit_text(text, reply_markup=back_keyboard("profile"))
    await callback.answer()

@router.callback_query(F.data == "profile_gifts")
async def profile_gifts(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    purchases = json.loads(user.purchases) if user.purchases else []
    if purchases:
        text = "🎁✨ Ваши подарки/покупки: ✨🎁\n"
        for p in purchases:
            text += f"• {p.get('name', 'Товар')}"
            if p.get('gift_from'):
                text += f" (от {p['gift_from']})"
            text += f"\n{p.get('message', '')}\n\n"
    else:
        text = "У вас пока нет подарков."
    await callback.message.edit_text(text, reply_markup=back_keyboard("profile"))
    await callback.answer()

@router.callback_query(F.data == "profile_medals")
async def profile_medals(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    medals = json.loads(user.medals) if user.medals else []
    text = "🏅✨ Ваши медали: ✨🏅\n" + "\n".join(medals) if medals else "У вас пока нет медалей."
    await callback.message.edit_text(text, reply_markup=back_keyboard("profile"))
    await callback.answer()

# ---------- Благотворительность ----------
@router.callback_query(F.data == "charity")
async def charity_menu(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(User).where(User.full_name != "Не указано").order_by(User.balance).limit(1)
    )
    poorest = result.scalar_one_or_none()
    if not poorest:
        await callback.answer("Нет пользователей для помощи.", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Пожертвовать", callback_data="charity_donate")
    builder.button(text="🏆 Рейтинг щедрых", callback_data="charity_rating")
    builder.button(text="🔙 Назад", callback_data="bank_menu")
    await callback.message.edit_text(
        f"💕✨ Благотворительный фонд ✨💕\n\n"
        f"Ваше пожертвование будет полностью анонимным. Никто не узнает, кто отправил и кто получил помощь.",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "charity_donate")
async def charity_donate_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💕 Введите сумму пожертвования:", reply_markup=back_keyboard("charity"))
    await state.set_state(CharityState.waiting_for_amount)
    await callback.answer()

@router.callback_query(StateFilter(CharityState.waiting_for_amount), F.data == "charity")
async def back_from_charity_amount(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await state.clear()
    await charity_menu(callback, session)

@router.message(StateFilter(CharityState.waiting_for_amount), F.text)
async def charity_donate_amount(message: Message, state: FSMContext, session: AsyncSession):
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("Введите число.")
        return
    
    user = await get_user(message.from_user.id, session)
    if amount <= 0 or amount > user.balance:
        await message.answer("Недостаточно средств или некорректная сумма.")
        return
    
    result = await session.execute(
        select(User).where(User.full_name != "Не указано").order_by(User.balance).limit(1)
    )
    poorest = result.scalar_one_or_none()
    if not poorest:
        await message.answer("Ошибка: не найден получатель.")
        return
    
    user.balance -= amount
    poorest.balance += amount
    poorest.total_earned += amount
    user.total_donated += amount
    await session.commit()
    await add_transaction(session, user.id, -amount, "charity", "Анонимное пожертвование в фонд")
    await add_transaction(session, poorest.id, amount, "charity_received", "Получена анонимная помощь из фонда")
    
    if user.total_donated >= 20000:
        added = await add_medal(user, "🎗️🎗️Помощь бедным🎗️🎗️", session, give_bonus=True)
        if added:
            await notify_user(message.bot, user.telegram_id, f"🎉 Вы получили медаль '🎗️🎗️Помощь бедным🎗️🎗️' и {MEDAL_BONUSES['🎗️🎗️Помощь бедным🎗️🎗️']:,} ₽!")
            await send_news_to_channel(message.bot, f"🏅 {user.full_name} получил медаль '🎗️🎗️Помощь бедным🎗️🎗️'")
    
    await notify_user(
        message.bot,
        poorest.telegram_id,
        f"💰✨ Вам поступило анонимное пожертвование {format_balance(amount)} ₽ из благотворительного фонда! ✨💰\n"
        f"Ваш текущий баланс: {format_balance(poorest.balance)} ₽"
    )
    
    await message.answer(
        f"✅✨ Вы анонимно пожертвовали {format_balance(amount)} ₽ нуждающемуся члену семьи. ✨✅",
        reply_markup=main_menu()
    )
    await send_news_to_channel(message.bot, f"💕 Анонимное пожертвование {format_balance(amount)} ₽ в фонд")
    await state.clear()

@router.callback_query(F.data == "charity_rating")
async def charity_rating(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(User.full_name, User.total_donated)
        .where(User.total_donated > 0)
        .order_by(desc(User.total_donated))
        .limit(10)
    )
    rating = result.all()
    text = "🏆✨ Рейтинг благотворителей (анонимный для получателей): ✨🏆\n"
    for i, row in enumerate(rating, 1):
        text += f"{i}. {row[0]} — {format_balance(row[1])} ₽\n"
    await callback.message.edit_text(text, reply_markup=back_keyboard("charity"))
    await callback.answer()

# ---------- Обучение ----------
@router.callback_query(F.data == "learning_menu")
async def learning_menu(callback: CallbackQuery):
    await callback.message.edit_text("📚✨ Выберите раздел обучения: ✨📚", reply_markup=learning_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data == "learn_ranks")
async def learn_ranks(callback: CallbackQuery):
    text = get_rank_conditions()
    await callback.message.edit_text(text, reply_markup=back_keyboard("learning_menu"))
    await callback.answer()

@router.callback_query(F.data == "learn_medals")
async def learn_medals(callback: CallbackQuery):
    text = get_medals_info()
    await callback.message.edit_text(text, reply_markup=back_keyboard("learning_menu"))
    await callback.answer()

@router.callback_query(F.data == "learn_other")
async def learn_other(callback: CallbackQuery):
    await callback.message.edit_text("📖✨ Выберите тему: ✨📖", reply_markup=learning_other_keyboard())
    await callback.answer()

@router.callback_query(F.data == "learn_work")
async def learn_work(callback: CallbackQuery):
    text = (
        "💼✨ Работа ✨💼\n"
        "• Умственный труд — решайте задачи и получайте 3 112 ₽ за правильный ответ.\n"
        "• Физический труд — нажимайте 'Положить кирпич' и получайте 57 ₽ за каждое нажатие.\n"
        "• Заработок суммируется, и если вы не работаете 5 минут, новость о вашем доходе попадает в канал.\n"
        "• Рейтинги по каждому виду работы показывают лучших работников."
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("learn_other"))
    await callback.answer()

@router.callback_query(F.data == "learn_bank")
async def learn_bank(callback: CallbackQuery):
    text = (
        "🏦✨ Банк ✨🏦\n"
        "• Перевод — отправляйте деньги другим игрокам по имени.\n"
        "• Вклад — положите деньги под 20% в час. Снять можно в любое время.\n"
        "• Кредит — возьмите до x10 от баланса на 5-25 часов под 30% каждые 5 часов.\n"
        "• Благотворительность — анонимно помогите самому бедному игроку."
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("learn_other"))
    await callback.answer()

@router.callback_query(F.data == "learn_shop")
async def learn_shop(callback: CallbackQuery):
    text = (
        "🛍️✨ Магазин ✨🛍️\n"
        "• Покупайте полезные товары за внутриигровую валюту.\n"
        "• Товар 'Семья premium' даёт Vip-статус, фиолетовые кнопки, повышение звания и уникальную медаль.\n"
        "• Все товары можно дарить другим игрокам.\n"
        "• Купленные товары отображаются в профиле."
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("learn_other"))
    await callback.answer()

# ---------- Рейтинг IQ ----------
@router.callback_query(F.data == "iq_rating")
async def iq_rating(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(User.full_name, IQResult.correct_answers, IQResult.medal)
        .join(IQResult, User.id == IQResult.user_id)
        .order_by(desc(IQResult.correct_answers))
        .limit(10)
    )
    rating = result.all()
    text = "🏆✨ Рейтинг IQ (по количеству правильных ответов): ✨🏆\n"
    for i, row in enumerate(rating, 1):
        text += f"{i}. {row[0]} — {row[1]}/15 ({row[2]})\n"
    if not rating:
        text += "Пока никто не прошёл тест IQ."
    await callback.message.edit_text(text, reply_markup=back_keyboard("back_to_main"))
    await callback.answer()

# ---------- Работа ----------
@router.callback_query(F.data == "work_menu")
async def work_menu(callback: CallbackQuery):
    await callback.message.edit_text("🚧✨ Выберите тип работы: ✨🚧", reply_markup=work_menu_keyboard())
    await callback.answer()

# --- Физический труд ---
@router.callback_query(F.data == "work_physical")
async def work_physical_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🔨✨ Физический труд — стройка дома ✨🔨\n"
        "Нажимайте «Положить кирпич», чтобы заработать 57 ₽.\n"
        "Стройте бесконечно!",
        reply_markup=physical_work_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "physical_work_brick")
async def physical_work_brick(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    user.balance += 57
    user.total_earned += 57
    user.work_physical_earned += 57
    await session.commit()
    await add_transaction(session, user.id, 57, "work_physical", "Физический труд: кирпич")
    update_work_activity(user.telegram_id, 57, "physical")
    await callback.answer("+57 ₽! Кирпич уложен.", show_alert=False)
    await callback.message.edit_text(
        f"🔨✨ Физический труд — стройка дома ✨🔨\n"
        f"💰 Баланс: {format_balance(user.balance)} ₽\n"
        f"🧱 Заработано на стройке: {format_balance(user.work_physical_earned)} ₽",
        reply_markup=physical_work_keyboard()
    )

@router.callback_query(F.data == "physical_rating")
async def physical_rating(callback: CallbackQuery, session: AsyncSession):
    rating = await get_work_rating(session, "physical")
    text = "🏆✨ Рейтинг строителей: ✨🏆\n"
    for i, row in enumerate(rating, 1):
        text += f"{i}. {row[0]} — {format_balance(row[1])} ₽\n"
    if not rating:
        text += "Пока никто не работал на стройке."
    await callback.message.edit_text(text, reply_markup=back_keyboard("work_physical"))
    await callback.answer()

# --- Умственный труд ---
@router.callback_query(F.data == "work_mental")
async def work_mental_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(MentalWorkState.answering)
    task = get_random_mental_task()
    await state.update_data(mental_task=task, mental_earned=0)
    builder = InlineKeyboardBuilder()
    builder.attach(InlineKeyboardBuilder.from_markup(mental_work_keyboard()))
    await callback.message.edit_text(
        f"🧠✨ Умственный труд ✨🧠\n\n"
        f"Задача: {task['q']}\n\n"
        f"Введите ваш ответ (число или слово):",
        reply_markup=mental_work_keyboard()
    )
    await callback.answer()

@router.message(StateFilter(MentalWorkState.answering), F.text)
async def mental_work_answer(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    task = data["mental_task"]
    user = await get_user(message.from_user.id, session)
    earned = data.get("mental_earned", 0)
    
    is_correct, response_text = check_mental_answer(task, message.text.strip())
    if is_correct:
        user.balance += 3112
        user.total_earned += 3112
        user.work_mental_earned += 3112
        earned += 3112
        await add_transaction(session, user.id, 3112, "work_mental", "Умственный труд: правильный ответ")
        await session.commit()
        update_work_activity(user.telegram_id, 3112, "mental")
    
    new_task = get_random_mental_task()
    await state.update_data(mental_task=new_task, mental_earned=earned)
    
    builder = InlineKeyboardBuilder()
    builder.attach(InlineKeyboardBuilder.from_markup(mental_work_keyboard()))
    await message.answer(
        f"{response_text}\n\n"
        f"Следующая задача: {new_task['q']}\n\n"
        f"Введите ваш ответ:",
        reply_markup=mental_work_keyboard()
    )

@router.callback_query(StateFilter(MentalWorkState.answering), F.data == "mental_next_task")
async def mental_next_task(callback: CallbackQuery, state: FSMContext):
    task = get_random_mental_task()
    await state.update_data(mental_task=task)
    await callback.message.edit_text(
        f"🧠✨ Новая задача: ✨🧠\n\n{task['q']}\n\nВведите ответ:",
        reply_markup=mental_work_keyboard()
    )
    await callback.answer()

@router.callback_query(StateFilter(MentalWorkState.answering), F.data == "mental_rating")
async def mental_rating(callback: CallbackQuery, session: AsyncSession):
    rating = await get_work_rating(session, "mental")
    text = "🏆✨ Рейтинг умников: ✨🏆\n"
    for i, row in enumerate(rating, 1):
        text += f"{i}. {row[0]} — {format_balance(row[1])} ₽\n"
    if not rating:
        text += "Пока никто не решал задачи."
    await callback.message.edit_text(text, reply_markup=back_keyboard("work_mental"))
    await callback.answer()

@router.callback_query(StateFilter(MentalWorkState.answering), F.data == "work_menu")
async def mental_work_finish(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    earned = data.get("mental_earned", 0)
    user = await get_user(callback.from_user.id, session)
    if earned > 0:
        await send_news_to_channel(callback.bot, f"🧠 {user.full_name} завершил умственный труд, заработав {format_balance(earned)} ₽")
    await state.clear()
    await work_menu(callback)

# ---------- Обработчик неизвестных callback ----------
@router.callback_query()
async def unknown_callback(callback: CallbackQuery):
    await callback.answer("Действие не распознано", show_alert=True)

# ---------- Обработчик неизвестных сообщений ----------
@router.message()
async def unknown_message(message: Message):
    user = await get_user(message.from_user.id, next(get_db()))
    name = user.full_name if user else "пользователь"
    await message.answer(
        f"😐 Я вас не понимаю 😐\n"
        f"{name}, вы делаете что-то не так, нажмите команду /start для перезапуска вашего бота."
    )
