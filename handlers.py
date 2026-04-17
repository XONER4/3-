import json
import random
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
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
    get_random_mental_task, check_mental_answer, get_work_rating
)

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

# ---------- Глобальный словарь для кастомных кнопок ----------
custom_buttons = {}

# ---------- Вспомогательные функции ----------
async def get_user(user_id: int, session: AsyncSession) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == user_id))
    return result.scalar_one_or_none()

async def get_user_by_name(full_name: str, session: AsyncSession) -> User | None:
    result = await session.execute(select(User).where(User.full_name == full_name))
    return result.scalar_one_or_none()

async def add_transaction(session: AsyncSession, user_id: int, amount: float, type_: str, description: str = None):
    transaction = Transaction(
        user_id=user_id,
        amount=amount,
        type=type_,
        description=description
    )
    session.add(transaction)
    await session.commit()

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
                msg = f"🎉 ПОЗДРАВЛЯЕМ! ВАШЕ ЗВАНИЕ ПОВЫШЕНО С {old} ДО {new}!\n"
                msg += f"ТЕПЕРЬ ВАШ ЕЖЕЧАСНЫЙ БОНУС СОСТАВЛЯЕТ {DAILY_BONUS_BASE * RANK_BONUS_MULTIPLIER[new]:,} ₽!\n"
                if reward > 0:
                    msg += f"💰 ВЫ ПОЛУЧИЛИ НАГРАДУ {reward:,.0f} ₽!"
                await bot.send_message(user.telegram_id, msg)
                await send_news_to_channel(bot, f"🎉 {user.full_name} ПОВЫШЕН ДО ЗВАНИЯ {new} И ПОЛУЧИЛ {reward:,.0f} ₽")
            except:
                pass

def format_balance(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", ".")

def get_current_date() -> str:
    return datetime.now().strftime("%d.%m.%Y")

async def send_news_to_channel(bot: Bot, text: str):
    try:
        await bot.send_message(NEWS_CHANNEL_ID, f"📰 {text}")
    except Exception as e:
        logging.error(f"Не удалось отправить новость в канал: {e}")

# ---------- IQ вопросы ----------
IQ_QUESTIONS = [
    {"q": "СКОЛЬКО БУДЕТ 2+2?", "o": ["3", "4", "5", "6"], "a": 1},
    {"q": "КАКАЯ ПЛАНЕТА БЛИЖЕ ВСЕГО К СОЛНЦУ?", "o": ["ВЕНЕРА", "ЗЕМЛЯ", "МЕРКУРИЙ", "МАРС"], "a": 2},
    {"q": "СКОЛЬКО ДНЕЙ В ВИСОКОСНОМ ГОДУ?", "o": ["365", "366", "364", "367"], "a": 1},
    {"q": "КТО НАПИСАЛ 'ВОЙНУ И МИР'?", "o": ["ДОСТОЕВСКИЙ", "ТОЛСТОЙ", "ПУШКИН", "ГОГОЛЬ"], "a": 1},
    {"q": "КАКОЙ ГАЗ ПРЕОБЛАДАЕТ В АТМОСФЕРЕ ЗЕМЛИ?", "o": ["КИСЛОРОД", "УГЛЕКИСЛЫЙ", "АЗОТ", "ВОДОРОД"], "a": 2},
    {"q": "СКОЛЬКО КОНТИНЕНТОВ НА ЗЕМЛЕ?", "o": ["5", "6", "7", "8"], "a": 2},
    {"q": "КАКАЯ САМАЯ ДЛИННАЯ РЕКА В МИРЕ?", "o": ["НИЛ", "АМАЗОНКА", "ЯНЦЗЫ", "МИССИСИПИ"], "a": 1},
    {"q": "В КАКОМ ГОДУ НАЧАЛАСЬ ВТОРАЯ МИРОВАЯ ВОЙНА?", "o": ["1939", "1941", "1914", "1945"], "a": 0},
    {"q": "КТО ИЗОБРЁЛ ТЕЛЕФОН?", "o": ["ЭДИСОН", "БЕЛЛ", "ТЕСЛА", "МАРКОНИ"], "a": 1},
    {"q": "СКОЛЬКО КОСТЕЙ В ТЕЛЕ ВЗРОСЛОГО ЧЕЛОВЕКА?", "o": ["206", "205", "208", "210"], "a": 0},
    {"q": "КАКАЯ СТОЛИЦА ФРАНЦИИ?", "o": ["ЛОНДОН", "БЕРЛИН", "МАДРИД", "ПАРИЖ"], "a": 3},
    {"q": "СКОЛЬКО ЦВЕТОВ В РАДУГЕ?", "o": ["5", "6", "7", "8"], "a": 2},
    {"q": "КАКОЙ ЭЛЕМЕНТ ИМЕЕТ СИМВОЛ 'O'?", "o": ["ЗОЛОТО", "КИСЛОРОД", "СЕРЕБРО", "ОЛОВО"], "a": 1},
    {"q": "КТО НАПИСАЛ 'ПРЕСТУПЛЕНИЕ И НАКАЗАНИЕ'?", "o": ["ТОЛСТОЙ", "ДОСТОЕВСКИЙ", "ЧЕХОВ", "ГОРЬКИЙ"], "a": 1},
    {"q": "СКОЛЬКО СТОРОН У КУБА?", "o": ["4", "5", "6", "8"], "a": 2},
]

# Товары для магазина
SHOP_ITEMS = [
    {
        "id": 1,
        "name": "🧪 ПРОБИВ БОТЫ 🧪",
        "price": 50000,
        "description": "🤖 ПОСЛЕ ПОКУПКИ ТОВАРА ВЫ ПОЛУЧИТЕ ССЫЛКИ НА 2 БОТА В ТЕЛЕГРАММЕ, КОТОРЫЕ ИЩУТ ИНФОРМАЦИЮ О ПОЛЬЗОВАТЕЛЕ.\n✅ 1. БОТ ИЩЕТ ИНФОРМАЦИЮ ПО ВСЕМ СЕРВИСАМ, ВКЛЮЧАЯ УТЕЧКУ ДАННЫХ.\n✅ 2. БОТ ИЩЕТ ИНФОРМАЦИЮ ТОЛЬКО В ТЕЛЕГРАММЕ.",
        "message": "✅ 1 БОТ: @Obnalehevaem_Pyhkenskyq_bot (ИЩЕТ ИНФОРМАЦИЮ ВО ВСЕХ ИСТОЧНИКАХ)\n✅ 2 БОТ: @SKxoner_bot (ИЩЕТ ИНФОРМАЦИЮ ТОЛЬКО В ТЕЛЕГРАММЕ)"
    },
    {
        "id": 2,
        "name": "💝 TELEGRAM PREMIUM 💝",
        "price": 25000,
        "description": "🛍️ ПОСЛЕ ПОКУПКИ ВЫ ПОЛУЧАЕТЕ ТЕЛЕГРАММ БОТА, ГДЕ МОЖНО ОПЛАТИТЬ 💝TELEGRAM PREMIUM💝 БАНКОВСКОЙ КАРТОЙ «🧤МИР🧤».",
        "message": "💝 @PremiumBot 💝 - БОТ ДЛЯ ПОКУПКИ PREMIUM ФУНКЦИЙ ТЕЛЕГРАММА.\n✅ ОПЛАТА ДОСТУПНА КАРТАМИ «🧤МИР🧤»."
    },
    {
        "id": 3,
        "name": "🔹 VPN СЕРВИС 🔹",
        "price": 85000,
        "description": "🛍️ ПОСЛЕ ПОКУПКИ ВЫ ПОЛУЧАЕТЕ ТЕЛЕГРАММ БОТ ДЛЯ УСТАНОВКИ VPN СЕРВИСА ANDROID/IPHONE. 2 ДНЯ БЕСПЛАТНОГО ПРОБНОГО ПЕРИОДА, ДАЛЕЕ 299₽ В МЕСЯЦ.",
        "message": "🔹 @ultimavpnbot 🔹 - БОТ ДЛЯ УСТАНОВКИ VPN СЕРВИСА НА ВАШ СМАРТФОН 💚"
    },
    {
        "id": 4,
        "name": "🎈🔮 ВОЗДУШНЫЕ ШАРЫ 🔮🎈",
        "price": 20000,
        "description": "🎁🎈 ПОСЛЕ ПОКУПКИ ТОВАРА ВЫ ПОЛУЧАЕТЕ ССЫЛКУ НА СООБЩЕСТВО «ВКОНТАКТЕ», ГДЕ МОЖНО ЗАКАЗАТЬ ВОЗДУШНЫЕ ШАРИКИ! 🎈🎁",
        "message": "🎈 https://vk.ru/airbubblesklin 🎈\n✅ ССЫЛКА НА СООБЩЕСТВО «💙ВКОНТАКТЕ💙»."
    },
    {
        "id": 5,
        "name": "💜 СЕМЬЯ PREMIUM 💜",
        "price": 120000,
        "description": "💜 ПОСЛЕ ПОКУПКИ ТОВАРА ВЫ ПОЛУЧАЕТЕ «💟PREMIUM💟» ФУНКЦИИ В БОТЕ:\n✅ ВСЕ КНОПКИ ПЕРЕКРАСЯТСЯ В ФИОЛЕТОВЫЙ ТЕКСТ\n✅ В ЛИЧНОМ ДЕЛЕ ДОБАВИТСЯ НАДПИСЬ 💜VIP💜\n✅ ПОВЫШЕНИЕ В ЗВАНИИ БЕЗ ОГРАНИЧЕНИЙ\n✅ МЕДАЛЬ «💜PREMIUM КЛИЕНТ💜»",
        "message": "💜 ПОЗДРАВЛЯЕМ! ВЫ ПОЛУЧИЛИ СТАТУС VIP! 💜\nТЕПЕРЬ У ВАС ФИОЛЕТОВЫЕ КНОПКИ, ЗВАНИЕ ПОВЫШЕНО, МЕДАЛЬ ПОЛУЧЕНА.",
        "is_vip": True
    }
]

ALL_MEDALS = [
    "✅15 ИЗ 15 IQ✅", "💚ХОРОШИСТ IQ💚", "😊СЛАБАК IQ😊", "❌ВСЕ ПЛОХО IQ❌",
    "😍💰ДЕНЕЖНАЯ ЩЕДРОСТЬ💰😍", "🎁💝ПОДАРОЧНАЯ ЩЕДРОСТЬ💝🎁",
    "🎗️🎗️ПОМОЩЬ БЕДНЫМ🎗️🎗️", "🎰ЛУДОМАН🎰", "🔴ДОЛЖНИК🔴", "❌ЛЮБИТЕЛЬ КРЕДИТОВ❌",
    "❇️БОНУС❇️", "🤑🤑ВКЛАДЧИК🤑🤑", "💜PREMIUM КЛИЕНТ💜", "🤝 РЕФЕРЕР 🤝"
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
            full_name="НЕ УКАЗАНО",
            balance=START_BALANCE,
            is_authorized=False,
            rank="РЯДОВОЙ",
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
            await message.answer("⛔ ВЫ ЗАБЛОКИРОВАНЫ В БОТЕ.")
            return
    
    if not user.is_authorized:
        await message.answer(
            "🔐 ДОБРО ПОЖАЛОВАТЬ! ДЛЯ ВХОДА В БОТА ВВЕДИТЕ ПАРОЛЬ.",
            reply_markup=password_keyboard()
        )
        await state.set_state(AuthState.waiting_for_password)
    else:
        if not user.channel_subscribed:
            await check_channel_subscription(message, user, state)
            return
        await message.answer(
            f"👋 С ВОЗВРАЩЕНИЕМ, {user.full_name}! ВЫ В ГЛАВНОМ МЕНЮ.\n"
            f"📅 СЕГОДНЯ {get_current_date()}",
            reply_markup=main_menu()
        )

async def check_channel_subscription(message: Message, user: User, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 ПОДПИСАТЬСЯ НА КАНАЛ", url=f"https://t.me/{NEWS_CHANNEL_USERNAME}")
    builder.button(text="✅ Я ПОДПИСАЛСЯ", callback_data="check_sub")
    await message.answer(
        "📰 ДЛЯ ПРОДОЛЖЕНИЯ НЕОБХОДИМО ПОДПИСАТЬСЯ НА НАШ КАНАЛ НОВОСТЕЙ!\n"
        "ПОСЛЕ ПОДПИСКИ НАЖМИТЕ КНОПКУ «Я ПОДПИСАЛСЯ».",
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
                    await add_transaction(session, referrer.id, 25000, "referral_bonus", f"БОНУС ЗА ПРИГЛАШЕНИЕ {user.full_name}")
                    await add_medal(referrer, "🤝 РЕФЕРЕР 🤝", session, give_bonus=True)
                    await notify_user(callback.bot, referrer.telegram_id, "🎉 ВЫ ПОЛУЧИЛИ БОНУС 25 000 ₽ ЗА ПРИГЛАШЕНИЕ ДРУГА!")
                    await send_news_to_channel(callback.bot, f"🤝 {referrer.full_name} ПРИГЛАСИЛ ДРУГА И ПОЛУЧИЛ 25 000 ₽")
                await session.commit()
            await callback.message.edit_text("✅ ПОДПИСКА ПОДТВЕРЖДЕНА! ДОБРО ПОЖАЛОВАТЬ В ГЛАВНОЕ МЕНЮ.")
            await back_to_main(callback, state, session)
        else:
            await callback.answer("❌ ВЫ ЕЩЁ НЕ ПОДПИСАЛИСЬ НА КАНАЛ!", show_alert=True)
    except Exception as e:
        logging.error(f"ОШИБКА ПРОВЕРКИ ПОДПИСКИ: {e}")
        await callback.answer("⚠️ НЕ УДАЛОСЬ ПРОВЕРИТЬ ПОДПИСКУ. УБЕДИТЕСЬ, ЧТО БОТ ДОБАВЛЕН В КАНАЛ КАК АДМИНИСТРАТОР.", show_alert=True)

# ---------- Авторизация ----------
@router.message(StateFilter(AuthState.waiting_for_password), F.text)
async def process_password(message: Message, state: FSMContext, session: AsyncSession):
    if message.text == BOT_PASSWORD:
        user_id = message.from_user.id
        user = await get_user(user_id, session)
        if user and user.is_authorized:
            await message.answer(f"👋 ВЫ УЖЕ АВТОРИЗОВАНЫ, {user.full_name}!", reply_markup=main_menu())
            await state.clear()
            return
        await state.update_data(user_id=user_id)
        await message.answer("✅ ПАРОЛЬ ВЕРНЫЙ! ВВЕДИТЕ ВАШЕ ИМЯ И ФАМИЛИЮ (НАПРИМЕР: ИВАН ИВАНОВ):")
        await state.set_state(AuthState.waiting_for_fullname)
    else:
        await message.answer("❌ НЕВЕРНЫЙ ПАРОЛЬ. ПОПРОБУЙТЕ ЕЩЁ РАЗ.")

@router.message(StateFilter(AuthState.waiting_for_fullname), F.text)
async def process_fullname(message: Message, state: FSMContext, session: AsyncSession):
    name_parts = message.text.strip().split()
    if len(name_parts) < 2:
        await message.answer("ПОЖАЛУЙСТА, ВВЕДИТЕ И ИМЯ, И ФАМИЛИЮ ЧЕРЕЗ ПРОБЕЛ.")
        return
    
    full_name = " ".join(name_parts[:2]).upper()
    data = await state.get_data()
    user_id = data["user_id"]
    user = await get_user(user_id, session)
    if not user:
        await message.answer("ОШИБКА: ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН.")
        return
    
    existing = await get_user_by_name(full_name, session)
    if existing and existing.telegram_id != user_id:
        await message.answer("❌ ЭТО ИМЯ УЖЕ ЗАНЯТО. ПОЖАЛУЙСТА, ВВЕДИТЕ ДРУГОЕ ИМЯ И ФАМИЛИЮ.")
        return
    
    user.full_name = full_name
    user.is_authorized = True
    await session.commit()
    
    if not user.channel_subscribed:
        await check_channel_subscription(message, user, state)
        return
    
    await message.answer(
        f"🎊✨ ДОБРО ПОЖАЛОВАТЬ В НАШУ ЭКОНОМИЧЕСКУЮ RPG-ИГРУ, {full_name}! ✨🎊\n"
        f"📅 СЕГОДНЯ {get_current_date()}\n"
        f"💰 ВАШ СТАРТОВЫЙ БАЛАНС: {format_balance(START_BALANCE)} ₽\n\n"
        f"🏦 ЗАРАБАТЫВАЙТЕ, ИГРАЙТЕ В КАЗИНО, ПОЛУЧАЙТЕ ЗВАНИЯ И МЕДАЛИ!\n"
        f"🎁 ПРИГЛАШАЙТЕ ДРУЗЕЙ И ПОЛУЧАЙТЕ БОНУСЫ!\n\n"
        f"ВЫ В ГЛАВНОМ МЕНЮ:",
        reply_markup=main_menu()
    )
    await state.clear()
    if user.referrer_id and not user.referrer_id == user_id:
        referrer = await get_user(user.referrer_id, session)
        if referrer:
            referrer.balance += 25000
            referrer.total_earned += 25000
            referrer.invited_count += 1
            await add_transaction(session, referrer.id, 25000, "referral_bonus", f"БОНУС ЗА ПРИГЛАШЕНИЕ {user.full_name}")
            await add_medal(referrer, "🤝 РЕФЕРЕР 🤝", session, give_bonus=True)
            await notify_user(message.bot, referrer.telegram_id, "🎉 ВЫ ПОЛУЧИЛИ БОНУС 25 000 ₽ ЗА ПРИГЛАШЕНИЕ ДРУГА!")
            await send_news_to_channel(message.bot, f"🤝 {referrer.full_name} ПРИГЛАСИЛ ДРУГА И ПОЛУЧИЛ 25 000 ₽")
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
    text = f"🏦✨ {user.full_name}, ДОБРО ПОЖАЛОВАТЬ В СБЕРБАНК! ✨🏦\n💰 ВАШ БАЛАНС: {format_balance(user.balance)} ₽"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 ОБНОВИТЬ БАЛАНС", callback_data="refresh_balance"))
    builder.attach(InlineKeyboardBuilder.from_markup(bank_menu_keyboard()))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data == "refresh_balance")
async def refresh_balance(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    await session.refresh(user)
    text = f"🏦✨ {user.full_name}, ДОБРО ПОЖАЛОВАТЬ В СБЕРБАНК! ✨🏦\n💰 ВАШ БАЛАНС: {format_balance(user.balance)} ₽"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 ОБНОВИТЬ БАЛАНС", callback_data="refresh_balance"))
    builder.attach(InlineKeyboardBuilder.from_markup(bank_menu_keyboard()))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer("БАЛАНС ОБНОВЛЁН")

# ---------- Ежечасный бонус ----------
@router.callback_query(F.data == "hourly_bonus")
async def hourly_bonus(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if not user:
        await callback.answer("ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН.", show_alert=True)
        return
    
    now = datetime.now()
    if user.last_bonus and (now - user.last_bonus).total_seconds() < 3600:
        await callback.answer("ВЫ УЖЕ ПОЛУЧАЛИ БОНУС В ЭТОМ ЧАСУ.", show_alert=True)
        return
    
    multiplier = RANK_BONUS_MULTIPLIER.get(user.rank, 1)
    bonus = DAILY_BONUS_BASE * multiplier
    user.balance += bonus
    user.total_earned += bonus
    user.last_bonus = now
    user.hourly_bonus_count += 1
    await session.commit()
    await add_transaction(session, user.id, bonus, "hourly_bonus", f"ЕЖЕЧАСНЫЙ БОНУС ({user.rank})")
    
    if user.hourly_bonus_count >= 10:
        added = await add_medal(user, "❇️БОНУС❇️", session, give_bonus=True)
        if added:
            await notify_user(callback.bot, user.telegram_id, "🎉 ПОЗДРАВЛЯЕМ! ВЫ ПОЛУЧИЛИ МЕДАЛЬ '❇️БОНУС❇️' И 5 000 ₽!")
            await send_news_to_channel(callback.bot, f"🏅 {user.full_name} ПОЛУЧИЛ МЕДАЛЬ '❇️БОНУС❇️'")
    
    await callback.message.edit_text(
        f"🎁✨ ВЫ ПОЛУЧИЛИ ЕЖЕЧАСНЫЙ БОНУС {format_balance(bonus)} ₽! ✨🎁\n"
        f"💰 ВАШ НОВЫЙ БАЛАНС: {format_balance(user.balance)} ₽",
        reply_markup=back_keyboard("back_to_main")
    )
    await send_news_to_channel(callback.bot, f"🎁 {user.full_name} ПОЛУЧИЛ ЕЖЕЧАСНЫЙ БОНУС {format_balance(bonus)} ₽")
    await callback.answer()

# ---------- Казино ----------
@router.callback_query(F.data == "casino_menu")
async def casino_menu(callback: CallbackQuery):
    await callback.message.edit_text("🎰✨ ВЫБЕРИТЕ ИГРУ: ✨🎰", reply_markup=casino_menu_keyboard())
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
    text = "🏆✨ РЕЙТИНГ КАЗИНО (ПО ВЫИГРЫШАМ): ✨🏆\n"
    for i, row in enumerate(rating, 1):
        text += f"{i}. {row[0]} — {format_balance(row[1])} ₽\n"
    await callback.message.edit_text(text, reply_markup=back_keyboard("casino_menu"))
    await callback.answer()

# --- Кубик ---
@router.callback_query(F.data == "casino_dice")
async def dice_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🎲 ВЫБЕРИТЕ СУММУ СТАВКИ:", reply_markup=dice_bet_keyboard())
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
        await callback.message.edit_text("ВВЕДИТЕ СУММУ СТАВКИ (ЦЕЛОЕ ЧИСЛО):")
        await state.set_state(CasinoState.waiting_for_bet)
        await state.update_data(game="dice")
        await callback.answer()
        return
    bet = int(data.split("_")[1])
    await state.update_data(bet=bet, game="dice")
    await callback.message.edit_text(
        f"🎲 СТАВКА: {format_balance(bet)} ₽. ЗАГАДАЙТЕ ЧИСЛО ОТ 1 ДО 6:",
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
        await callback.answer("НЕДОСТАТОЧНО СРЕДСТВ!", show_alert=True)
        return
    
    dice_msg = await callback.message.answer_dice(emoji="🎲")
    await asyncio.sleep(3.5)
    dice_value = dice_msg.dice.value
    
    won = (guess == dice_value)
    if won:
        payout = bet * 6
        await update_balance(user, payout - bet, session, "casino_win", f"КУБИК: УГАДАЛ {guess}, ВЫПАЛО {dice_value}", callback.bot)
        text = f"🎉✨ ВЫ УГАДАЛИ! ВЫПАЛО {dice_value}. ВЫИГРЫШ X6: {format_balance(payout)} ₽! ✨🎉"
    else:
        await update_balance(user, -bet, session, "casino_loss", f"КУБИК: НЕ УГАДАЛ (ЗАГАДАНО {guess}, ВЫПАЛО {dice_value})", callback.bot)
        text = f"😢 НЕ УГАДАЛИ. ЗАГАДАНО {guess}, ВЫПАЛО {dice_value}. ПРОИГРЫШ {format_balance(bet)} ₽."
    
    user.casino_bets_count += 1
    if user.casino_bets_count == 30:
        added = await add_medal(user, "🎰ЛУДОМАН🎰", session, give_bonus=True)
        if added:
            await notify_user(callback.bot, user.telegram_id, "🎉 ПОЗДРАВЛЯЕМ! ВЫ ПОЛУЧИЛИ МЕДАЛЬ '🎰ЛУДОМАН🎰' И 5 000 ₽!")
            await send_news_to_channel(callback.bot, f"🏅 {user.full_name} ПОЛУЧИЛ МЕДАЛЬ '🎰ЛУДОМАН🎰'")
    
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
    builder.row(InlineKeyboardButton(text="🎲 ИГРАТЬ СНОВА", callback_data="casino_dice"))
    builder.row(InlineKeyboardButton(text="🏠 В МЕНЮ КАЗИНО", callback_data="casino_menu"))
    
    await callback.message.edit_text(
        f"{text}\n💰 БАЛАНС: {format_balance(user.balance)} ₽",
        reply_markup=builder.as_markup()
    )
    await state.clear()
    await callback.answer()

# --- Слоты ---
@router.callback_query(F.data == "casino_slots")
async def slots_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🎰 ВЫБЕРИТЕ СУММУ СТАВКИ:", reply_markup=slots_bet_keyboard())
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
        await callback.message.edit_text("ВВЕДИТЕ СУММУ СТАВКИ (ЦЕЛОЕ ЧИСЛО):")
        await state.set_state(CasinoState.waiting_for_bet)
        await state.update_data(game="slots")
        await callback.answer()
        return
    bet = int(data.split("_")[1])
    await state.update_data(bet=bet, game="slots")
    await callback.message.edit_text(
        f"🎰 СТАВКА: {format_balance(bet)} ₽. ЗАПУСКАЙТЕ СЛОТЫ!",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="🎰 КРУТИТЬ", callback_data="spin_slots")
        ).row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="casino_slots")).as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "spin_slots")
async def slots_spin(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    bet = data["bet"]
    user = await get_user(callback.from_user.id, session)
    if user.balance < bet:
        await callback.answer("НЕДОСТАТОЧНО СРЕДСТВ!", show_alert=True)
        return
    
    slot_msg = await callback.message.answer_dice(emoji="🎰")
    await asyncio.sleep(3.5)
    slot_value = slot_msg.dice.value
    
    if slot_value in [1, 22, 43, 64]:
        multiplier = 7
        combo = "ТРИ ОДИНАКОВЫХ"
    elif slot_value in [2, 3, 4, 21, 23, 42, 44, 63]:
        multiplier = 3
        combo = "ДВА ОДИНАКОВЫХ"
    else:
        multiplier = 0
        combo = "БЕЗ СОВПАДЕНИЙ"
    
    won = multiplier > 0
    if won:
        payout = bet * multiplier
        await update_balance(user, payout - bet, session, "casino_win", f"СЛОТЫ: {combo}", callback.bot)
        text = f"🎉✨ СЛОТЫ! КОМБИНАЦИЯ {slot_value} ({combo}). ВЫИГРЫШ X{multiplier}: {format_balance(payout)} ₽ ✨🎉"
    else:
        await update_balance(user, -bet, session, "casino_loss", f"СЛОТЫ: {combo}", callback.bot)
        text = f"😢 СЛОТЫ! КОМБИНАЦИЯ {slot_value} ({combo}). ПРОИГРЫШ {format_balance(bet)} ₽."
    
    user.casino_bets_count += 1
    if user.casino_bets_count == 30:
        added = await add_medal(user, "🎰ЛУДОМАН🎰", session, give_bonus=True)
        if added:
            await notify_user(callback.bot, user.telegram_id, "🎉 ПОЗДРАВЛЯЕМ! ВЫ ПОЛУЧИЛИ МЕДАЛЬ '🎰ЛУДОМАН🎰' И 5 000 ₽!")
            await send_news_to_channel(callback.bot, f"🏅 {user.full_name} ПОЛУЧИЛ МЕДАЛЬ '🎰ЛУДОМАН🎰'")
    
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
    builder.row(InlineKeyboardButton(text="🎰 ИГРАТЬ СНОВА", callback_data="casino_slots"))
    builder.row(InlineKeyboardButton(text="🏠 В МЕНЮ КАЗИНО", callback_data="casino_menu"))
    
    await callback.message.edit_text(
        f"{text}\n💰 БАЛАНС: {format_balance(user.balance)} ₽",
        reply_markup=builder.as_markup()
    )
    await state.clear()
    await callback.answer()

@router.message(StateFilter(CasinoState.waiting_for_bet), F.text.isdigit())
async def custom_bet_input(message: Message, state: FSMContext):
    bet = int(message.text)
    if bet <= 0:
        await message.answer("СТАВКА ДОЛЖНА БЫТЬ БОЛЬШЕ 0.")
        return
    data = await state.get_data()
    game = data["game"]
    await state.update_data(bet=bet)
    if game == "dice":
        await message.answer(
            f"🎲 СТАВКА: {format_balance(bet)} ₽. ЗАГАДАЙТЕ ЧИСЛО ОТ 1 ДО 6:",
            reply_markup=dice_guess_keyboard()
        )
        await state.set_state(CasinoState.waiting_for_dice_guess)
    else:
        await message.answer(
            f"🎰 СТАВКА: {format_balance(bet)} ₽. ЗАПУСКАЙТЕ СЛОТЫ!",
            reply_markup=InlineKeyboardBuilder().row(
                InlineKeyboardButton(text="🎰 КРУТИТЬ", callback_data="spin_slots")
            ).row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="casino_slots")).as_markup()
        )
        await state.set_state(None)

# ---------- Тест IQ ----------
@router.callback_query(F.data == "iq_test")
async def iq_test_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if user.balance < 1000:
        await callback.answer("ДЛЯ ПРОХОЖДЕНИЯ ТЕСТА НУЖНО МИНИМУМ 1.000 ₽ НА БАЛАНСЕ!", show_alert=True)
        return
    
    user.balance -= 1000
    await add_transaction(session, user.id, -1000, "iq_fee", "ОПЛАТА ЗА ПРОХОЖДЕНИЕ IQ ТЕСТА")
    await session.commit()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 ОТМЕНИТЬ ТЕСТ", callback_data="cancel_iq")
    await callback.message.edit_text(
        "🧠✨ ТЕСТ IQ. 15 ВОПРОСОВ. НАЖМИТЕ 'ОТМЕНИТЬ ТЕСТ' ЧТОБЫ ВЫЙТИ БЕЗ ВОЗВРАТА СРЕДСТВ. ✨🧠",
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
    builder.button(text="🚫 ОТМЕНИТЬ ТЕСТ", callback_data="cancel_iq")
    builder.adjust(1)
    await message.edit_text(
        f"🧠 ВОПРОС {index+1}/15:\n{q['q']}",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "cancel_iq")
async def cancel_iq(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ ТЕСТ IQ ОТМЕНЁН. СРЕДСТВА НЕ ВОЗВРАЩАЮТСЯ.", reply_markup=main_menu())
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
    
    medal = ""
    bonus = 0
    detail = ""
    if correct == 15:
        medal = "✅15 ИЗ 15 IQ✅"
        bonus = 5000
        detail = "15/15"
    elif correct >= 9:
        medal = "💚ХОРОШИСТ IQ💚"
        bonus = 2500
        detail = f"{correct}/15"
    elif correct >= 5:
        medal = "😊СЛАБАК IQ😊"
        bonus = 1000
        detail = f"{correct}/15"
    else:
        medal = "❌ВСЕ ПЛОХО IQ❌"
        bonus = -1000
        detail = f"{correct}/15"
    
    await update_balance(user, bonus, session, "iq_bonus", f"ТЕСТ IQ: {correct}/{total}", callback.bot)
    if medal:
        added = await add_medal(user, medal, session, give_bonus=True)
        if added:
            await notify_user(callback.bot, user.telegram_id, f"🎉 ПОЗДРАВЛЯЕМ! ВЫ ПОЛУЧИЛИ МЕДАЛЬ '{medal}' И 5 000 ₽!")
            await send_news_to_channel(callback.bot, f"🏅 {user.full_name} ПОЛУЧИЛ МЕДАЛЬ '{medal}'")
    
    iq_result = IQResult(
        user_id=user.id,
        correct_answers=correct,
        medal=medal,
        bonus=bonus
    )
    session.add(iq_result)
    await session.commit()
    
    text = f"🧠✨ ТЕСТ ЗАВЕРШЁН! ✨🧠\nПРАВИЛЬНЫХ ОТВЕТОВ: {correct} ИЗ {total}\n"
    text += f"МЕДАЛЬ: {medal} ({detail})\n"
    text += f"ИЗМЕНЕНИЕ БАЛАНСА: {format_balance(bonus)} ₽\n"
    text += f"💰 ТЕКУЩИЙ БАЛАНС: {format_balance(user.balance)} ₽"
    
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
            f"💵✨ ВАШ ТЕКУЩИЙ КРЕДИТ: ✨💵\n"
            f"ВЗЯТО: {format_balance(user.credit_original)} ₽\n"
            f"ТЕКУЩИЙ ДОЛГ: {format_balance(current_debt)} ₽\n"
            f"СРОК: {user.credit_term_hours} ЧАСОВ (ДО {due})\n"
            f"СТАВКА: 30% КАЖДЫЕ 5 ЧАСОВ"
        )
        await callback.message.edit_text(text, reply_markup=credit_menu_keyboard())
    else:
        await callback.message.edit_text(
            "💵✨ КРЕДИТ. ВЫ МОЖЕТЕ ВЗЯТЬ КРЕДИТ НА СРОК 5-25 ЧАСОВ.\n"
            "ПРОЦЕНТНАЯ СТАВКА: 30% КАЖДЫЕ 5 ЧАСОВ ОТ СУММЫ КРЕДИТА. ✨💵",
            reply_markup=credit_menu_keyboard()
        )
    await callback.answer()

@router.callback_query(F.data == "take_credit")
async def take_credit_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if user.credit_amount > 0:
        await callback.answer("У ВАС УЖЕ ЕСТЬ НЕПОГАШЕННЫЙ КРЕДИТ!", show_alert=True)
        return
    
    max_credit = user.balance * 10
    await callback.message.edit_text(
        f"💰 ВАШ БАЛАНС: {format_balance(user.balance)} ₽\n"
        f"МАКСИМАЛЬНАЯ СУММА КРЕДИТА: {format_balance(max_credit)} ₽\n"
        f"ВВЕДИТЕ ЖЕЛАЕМУЮ СУММУ:",
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
        await message.answer("ПОЖАЛУЙСТА, ВВЕДИТЕ ЧИСЛО.")
        return
    
    data = await state.get_data()
    max_credit = data["max_credit"]
    if amount <= 0 or amount > max_credit:
        await message.answer(f"СУММА ДОЛЖНА БЫТЬ ОТ 1 ДО {format_balance(max_credit)} ₽.")
        return
    
    await state.update_data(credit_amount=amount)
    await message.answer(
        "ВЫБЕРИТЕ СРОК КРЕДИТА (В ЧАСАХ):",
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
    await add_transaction(session, user.id, amount, "credit", f"ВЗЯТ КРЕДИТ {format_balance(amount)} ₽ НА {term} Ч")
    
    if user.loans_taken > 2:
        added = await add_medal(user, "❌ЛЮБИТЕЛЬ КРЕДИТОВ❌", session, give_bonus=True)
        if added:
            await notify_user(callback.bot, user.telegram_id, "🎉 ПОЗДРАВЛЯЕМ! ВЫ ПОЛУЧИЛИ МЕДАЛЬ '❌ЛЮБИТЕЛЬ КРЕДИТОВ❌' И 5 000 ₽!")
            await send_news_to_channel(callback.bot, f"🏅 {user.full_name} ПОЛУЧИЛ МЕДАЛЬ '❌ЛЮБИТЕЛЬ КРЕДИТОВ❌'")
    
    await callback.message.edit_text(
        f"✅ КРЕДИТ ОДОБРЕН!\n"
        f"ПОЛУЧЕНО: {format_balance(amount)} ₽\n"
        f"СРОК: {term} ЧАСОВ (ДО {due_date.strftime('%d.%m.%Y %H:%M')})\n"
        f"СТАВКА: 30% КАЖДЫЕ 5 ЧАСОВ",
        reply_markup=back_keyboard("bank_menu")
    )
    await state.clear()
    await callback.answer()

# ---------- Погашение кредита ----------
@router.callback_query(F.data == "repay_credit")
async def repay_credit_start(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if user.credit_amount <= 0:
        await callback.answer("У ВАС НЕТ НЕПОГАШЕННОГО КРЕДИТА.", show_alert=True)
        return
    
    now = datetime.now()
    hours_passed = (now - user.credit_start_date).total_seconds() / 3600
    current_debt = calculate_credit_debt(user.credit_original, hours_passed)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ ПОГАСИТЬ ПОЛНОСТЬЮ", callback_data="confirm_repay")
    builder.button(text="🔙 НАЗАД", callback_data="credit_menu")
    
    await callback.message.edit_text(
        f"💵 ПОГАШЕНИЕ КРЕДИТА\n"
        f"ТЕКУЩИЙ ДОЛГ: {format_balance(current_debt)} ₽\n"
        f"ВАШ БАЛАНС: {format_balance(user.balance)} ₽\n\n"
        f"НАЖМИТЕ «ПОГАСИТЬ ПОЛНОСТЬЮ» ДЛЯ ОПЛАТЫ.",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "confirm_repay")
async def confirm_repay(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if user.credit_amount <= 0:
        await callback.answer("КРЕДИТ УЖЕ ПОГАШЕН.", show_alert=True)
        return
    
    now = datetime.now()
    hours_passed = (now - user.credit_start_date).total_seconds() / 3600
    current_debt = calculate_credit_debt(user.credit_original, hours_passed)
    
    if user.balance < current_debt:
        await callback.answer("НЕДОСТАТОЧНО СРЕДСТВ ДЛЯ ПОЛНОГО ПОГАШЕНИЯ.", show_alert=True)
        return
    
    user.balance -= current_debt
    user.credit_amount = 0
    user.credit_original = 0
    user.credit_term_hours = 0
    user.credit_start_date = None
    user.credit_due_date = None
    user.credit_overdue_notified = False
    await session.commit()
    await add_transaction(session, user.id, -current_debt, "credit_repay", f"ПОГАШЕНИЕ КРЕДИТА")
    
    await callback.message.edit_text(
        f"✅ КРЕДИТ ПОЛНОСТЬЮ ПОГАШЕН!\n"
        f"СПИСАНО: {format_balance(current_debt)} ₽\n"
        f"ОСТАТОК НА БАЛАНСЕ: {format_balance(user.balance)} ₽",
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
            f"💰✨ ВАШ ВКЛАД: ✨💰\n"
            f"СУММА ВКЛАДА: {format_balance(user.deposit_amount)} ₽\n"
            f"ТЕКУЩАЯ СУММА С ПРОЦЕНТАМИ: {format_balance(current)} ₽\n"
            f"ПРОЦЕНТ: 20% КАЖДЫЙ ЧАС"
        )
    else:
        text = "💰✨ ВКЛАД. ВЫ МОЖЕТЕ ОТКРЫТЬ ВКЛАД ПОД 20% В ЧАС. СНЯТЬ МОЖНО В ЛЮБОЙ МОМЕНТ. ✨💰"
    await callback.message.edit_text(text, reply_markup=deposit_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data == "open_deposit")
async def deposit_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if user.deposit_amount > 0:
        await callback.answer("У ВАС УЖЕ ОТКРЫТ ВКЛАД. ЗАКРОЙТЕ ЕГО, ЧТОБЫ ОТКРЫТЬ НОВЫЙ.", show_alert=True)
        return
    
    await callback.message.edit_text("ВВЕДИТЕ СУММУ ВКЛАДА:", reply_markup=back_keyboard("deposit_menu"))
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
        await message.answer("ВВЕДИТЕ ЧИСЛО.")
        return
    
    user = await get_user(message.from_user.id, session)
    if amount <= 0 or amount > user.balance:
        await message.answer("НЕДОСТАТОЧНО СРЕДСТВ ИЛИ НЕКОРРЕКТНАЯ СУММА.")
        return
    
    user.balance -= amount
    user.deposit_amount = amount
    user.deposit_start_date = datetime.now()
    user.has_made_deposit = True
    user.deposits_made += 1
    await session.commit()
    await add_transaction(session, user.id, -amount, "deposit_open", f"ОТКРЫТ ВКЛАД {format_balance(amount)} ₽")
    
    if user.deposits_made > 2:
        added = await add_medal(user, "🤑🤑ВКЛАДЧИК🤑🤑", session, give_bonus=True)
        if added:
            await notify_user(message.bot, user.telegram_id, "🎉 ПОЗДРАВЛЯЕМ! ВЫ ПОЛУЧИЛИ МЕДАЛЬ '🤑🤑ВКЛАДЧИК🤑🤑' И 5 000 ₽!")
            await send_news_to_channel(message.bot, f"🏅 {user.full_name} ПОЛУЧИЛ МЕДАЛЬ '🤑🤑ВКЛАДЧИК🤑🤑'")
    
    await message.answer(
        f"✅✨ ВКЛАД ОТКРЫТ! ✨✅\nСУММА: {format_balance(amount)} ₽\nПРОЦЕНТ: 20% КАЖДЫЙ ЧАС.",
        reply_markup=main_menu()
    )
    await state.clear()

@router.callback_query(F.data == "close_deposit")
async def close_deposit(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if user.deposit_amount <= 0:
        await callback.answer("У ВАС НЕТ ОТКРЫТОГО ВКЛАДА.", show_alert=True)
        return
    
    now = datetime.now()
    hours_passed = (now - user.deposit_start_date).total_seconds() / 3600
    total = calculate_deposit_payout(user.deposit_amount, hours_passed)
    
    user.balance += total
    user.total_earned += total - user.deposit_amount
    await add_transaction(session, user.id, total - user.deposit_amount, "deposit_interest", f"ПРОЦЕНТЫ ПО ВКЛАДУ ЗА {hours_passed:.1f} Ч")
    await add_transaction(session, user.id, user.deposit_amount, "deposit_close", "ЗАКРЫТИЕ ВКЛАДА")
    
    user.deposit_amount = 0
    user.deposit_start_date = None
    await session.commit()
    
    await callback.message.edit_text(
        f"✅✨ ВКЛАД ЗАКРЫТ! ✨✅\n"
        f"ВЫ ПОЛУЧИЛИ: {format_balance(total)} ₽\n"
        f"ТЕКУЩИЙ БАЛАНС: {format_balance(user.balance)} ₽",
        reply_markup=back_keyboard("bank_menu")
    )
    await callback.answer()

# ---------- Переводы ----------
@router.callback_query(F.data == "transfer")
async def transfer_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "💸 ВВЕДИТЕ ИМЯ И ФАМИЛИЮ ПОЛУЧАТЕЛЯ (КАК В БОТЕ):",
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
    recip_name = message.text.strip().upper()
    recip = await get_user_by_name(recip_name, session)
    if not recip:
        await message.answer("❌ ПОЛЬЗОВАТЕЛЬ С ТАКИМ ИМЕНЕМ НЕ НАЙДЕН В БОТЕ.")
        return
    
    await state.update_data(recip_id=recip.telegram_id, recip_name=recip.full_name)
    await message.answer(f"ПОЛУЧАТЕЛЬ: {recip.full_name}\nВВЕДИТЕ СУММУ ПЕРЕВОДА:", reply_markup=back_keyboard("bank_menu"))
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
        await message.answer("ВВЕДИТЕ ЧИСЛО.")
        return
    
    user = await get_user(message.from_user.id, session)
    if amount <= 0 or amount > user.balance:
        await message.answer("НЕДОСТАТОЧНО СРЕДСТВ ИЛИ НЕКОРРЕКТНАЯ СУММА.")
        return
    
    data = await state.get_data()
    recip_id = data["recip_id"]
    recip_name = data["recip_name"]
    recip = await get_user(recip_id, session)
    
    user.balance -= amount
    recip.balance += amount
    recip.total_earned += amount
    await session.commit()
    await add_transaction(session, user.id, -amount, "transfer_out", f"ПЕРЕВОД ПОЛЬЗОВАТЕЛЮ {recip_name}")
    await add_transaction(session, recip.id, amount, "transfer_in", f"ПОЛУЧЕНО ОТ {user.full_name}")
    
    result = await session.execute(
        select(func.sum(Transaction.amount)).where(
            Transaction.user_id == user.id,
            Transaction.type == "transfer_out"
        )
    )
    total_transferred = abs(result.scalar() or 0)
    if total_transferred >= 50000:
        added = await add_medal(user, "😍💰ДЕНЕЖНАЯ ЩЕДРОСТЬ💰😍", session, give_bonus=True)
        if added:
            await notify_user(message.bot, user.telegram_id, "🎉 ПОЗДРАВЛЯЕМ! ВЫ ПОЛУЧИЛИ МЕДАЛЬ '😍💰ДЕНЕЖНАЯ ЩЕДРОСТЬ💰😍' И 5 000 ₽!")
            await send_news_to_channel(message.bot, f"🏅 {user.full_name} ПОЛУЧИЛ МЕДАЛЬ '😍💰ДЕНЕЖНАЯ ЩЕДРОСТЬ💰😍'")
    
    local_time = datetime.now() + timedelta(hours=TIMEZONE_OFFSET)
    await notify_user(
        message.bot,
        recip.telegram_id,
        f"💰✨ ВАМ ПОСТУПИЛ ПЕРЕВОД! ✨💰\n"
        f"ОТПРАВИТЕЛЬ: {user.full_name}\n"
        f"СУММА: {format_balance(amount)} ₽\n"
        f"ВРЕМЯ: {local_time.strftime('%d.%m.%Y %H:%M')}\n"
        f"ВАШ ТЕКУЩИЙ БАЛАНС: {format_balance(recip.balance)} ₽"
    )
    
    await message.answer(
        f"✅✨ ПЕРЕВОД ВЫПОЛНЕН! ✨✅\nПОЛУЧАТЕЛЬ: {recip_name}\nСУММА: {format_balance(amount)} ₽",
        reply_markup=main_menu()
    )
    await send_news_to_channel(message.bot, f"💸 {user.full_name} ПЕРЕВЁЛ {format_balance(amount)} ₽ ПОЛЬЗОВАТЕЛЮ {recip_name}")
    await state.clear()
    # ---------- Магазин (новый) ----------
@router.callback_query(F.data == "shop_menu")
async def shop_menu(callback: CallbackQuery):
    await callback.message.edit_text("🛍️✨ ДОБРО ПОЖАЛОВАТЬ В МАГАЗИН! ✨🛍️\nВЫБЕРИТЕ ТОВАР:", reply_markup=shop_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data.startswith("shop_item_"))
async def shop_item_view(callback: CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split("_")[2]) - 1
    item = SHOP_ITEMS[item_id]
    can_gift = True  # Теперь любой товар можно подарить
    await state.update_data(shop_item=item, shop_item_id=item_id)
    await callback.message.edit_text(
        f"{item['name']}\n💰 ЦЕНА: {format_balance(item['price'])} ₽\n\n📝 {item['description']}",
        reply_markup=shop_item_keyboard(item_id+1, can_gift)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("buy_item_"))
async def buy_item(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    item_id = int(callback.data.split("_")[2]) - 1
    item = SHOP_ITEMS[item_id]
    user = await get_user(callback.from_user.id, session)
    
    if user.balance < item["price"]:
        await callback.answer("НЕДОСТАТОЧНО СРЕДСТВ!", show_alert=True)
        return
    
    user.balance -= item["price"]
    purchases = json.loads(user.purchases) if user.purchases else []
    purchases.append({"name": item["name"], "message": item["message"], "date": datetime.now().isoformat()})
    user.purchases = json.dumps(purchases)
    
    if item.get("is_vip"):
        user.is_vip = True
        old_rank = user.rank
        ranks = ["РЯДОВОЙ", "ЕФРЕЙТОР", "МЛАДШИЙ СЕРЖАНТ", "СЕРЖАНТ", "СТАРШИЙ СЕРЖАНТ", "ЛЕЙТЕНАНТ", "СТАРШИЙ ЛЕЙТЕНАНТ"]
        current_idx = ranks.index(user.rank)
        if current_idx < len(ranks) - 1:
            user.rank = ranks[current_idx + 1]
        user.rank_manual = True
        added = await add_medal(user, "💜PREMIUM КЛИЕНТ💜", session, give_bonus=True)
        if added:
            await notify_user(callback.bot, user.telegram_id, "🎉 ПОЗДРАВЛЯЕМ! ВЫ ПОЛУЧИЛИ МЕДАЛЬ '💜PREMIUM КЛИЕНТ💜' И 5 000 ₽!")
            await send_news_to_channel(callback.bot, f"🏅 {user.full_name} ПОЛУЧИЛ МЕДАЛЬ '💜PREMIUM КЛИЕНТ💜'")
        # Уведомление о повышении звания
        if old_rank != user.rank:
            await notify_user(callback.bot, user.telegram_id, f"🎉 ПОЗДРАВЛЯЕМ! ВАШЕ ЗВАНИЕ ПОВЫШЕНО С {old_rank} ДО {user.rank}!")
            await send_news_to_channel(callback.bot, f"🎉 {user.full_name} ПОВЫШЕН ДО {user.rank} (VIP)")
    
    await session.commit()
    await add_transaction(session, user.id, -item["price"], "shop_purchase", f"ПОКУПКА {item['name']}")
    
    await callback.message.edit_text(
        f"✅ ПОКУПКА СОВЕРШЕНА!\n\n{item['message']}",
        reply_markup=back_keyboard("shop_menu")
    )
    await notify_user(callback.bot, user.telegram_id, f"🎉 ВЫ ПРИОБРЕЛИ {item['name']}!")
    await send_news_to_channel(callback.bot, f"🛍️ {user.full_name} ПРИОБРЁЛ {item['name']} ЗА {format_balance(item['price'])} ₽")
    await callback.answer()

@router.callback_query(F.data.startswith("gift_item_"))
async def gift_item_start(callback: CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split("_")[2]) - 1
    item = SHOP_ITEMS[item_id]
    await state.update_data(gift_item=item, gift_item_id=item_id)
    await callback.message.edit_text(
        "🎁 ВВЕДИТЕ ИМЯ И ФАМИЛИЮ ПОЛУЧАТЕЛЯ ПОДАРКА:",
        reply_markup=back_keyboard("shop_menu")
    )
    await state.set_state(ShopState.choosing_recipient_name)
    await callback.answer()

@router.message(StateFilter(ShopState.choosing_recipient_name), F.text)
async def gift_item_finish(message: Message, state: FSMContext, session: AsyncSession):
    recip_name = message.text.strip().upper()
    recip = await get_user_by_name(recip_name, session)
    if not recip:
        await message.answer("ПОЛЬЗОВАТЕЛЬ С ТАКИМ ИМЕНЕМ НЕ НАЙДЕН.")
        return
    
    data = await state.get_data()
    item = data["gift_item"]
    user = await get_user(message.from_user.id, session)
    
    if user.balance < item["price"]:
        await message.answer("НЕДОСТАТОЧНО СРЕДСТВ ДЛЯ ПОДАРКА.")
        return
    
    user.balance -= item["price"]
    user.gifts_sent += 1
    recip_purchases = json.loads(recip.purchases) if recip.purchases else []
    recip_purchases.append({"name": item["name"], "message": item["message"], "date": datetime.now().isoformat(), "gift_from": user.full_name})
    recip.purchases = json.dumps(recip_purchases)
    
    if item.get("is_vip"):
        recip.is_vip = True
        old_rank = recip.rank
        ranks = ["РЯДОВОЙ", "ЕФРЕЙТОР", "МЛАДШИЙ СЕРЖАНТ", "СЕРЖАНТ", "СТАРШИЙ СЕРЖАНТ", "ЛЕЙТЕНАНТ", "СТАРШИЙ ЛЕЙТЕНАНТ"]
        current_idx = ranks.index(recip.rank)
        if current_idx < len(ranks) - 1:
            recip.rank = ranks[current_idx + 1]
        recip.rank_manual = True
        added = await add_medal(recip, "💜PREMIUM КЛИЕНТ💜", session, give_bonus=True)
        if added:
            await notify_user(message.bot, recip.telegram_id, "🎉 ПОЗДРАВЛЯЕМ! ВЫ ПОЛУЧИЛИ МЕДАЛЬ '💜PREMIUM КЛИЕНТ💜' И 5 000 ₽ В ПОДАРОК!")
            await send_news_to_channel(message.bot, f"🏅 {recip.full_name} ПОЛУЧИЛ МЕДАЛЬ '💜PREMIUM КЛИЕНТ💜' В ПОДАРОК")
        # Уведомление о повышении звания
        if old_rank != recip.rank:
            await notify_user(message.bot, recip.telegram_id, f"🎉 ПОЗДРАВЛЯЕМ! ВАШЕ ЗВАНИЕ ПОВЫШЕНО С {old_rank} ДО {recip.rank}!")
            await send_news_to_channel(message.bot, f"🎉 {recip.full_name} ПОВЫШЕН ДО {recip.rank} (VIP ПОДАРОК)")
    
    if user.gifts_sent >= 5:
        added = await add_medal(user, "🎁💝ПОДАРОЧНАЯ ЩЕДРОСТЬ💝🎁", session, give_bonus=True)
        if added:
            await notify_user(message.bot, user.telegram_id, "🎉 ВЫ ПОЛУЧИЛИ МЕДАЛЬ '🎁💝ПОДАРОЧНАЯ ЩЕДРОСТЬ💝🎁' И 5 000 ₽!")
            await send_news_to_channel(message.bot, f"🏅 {user.full_name} ПОЛУЧИЛ МЕДАЛЬ '🎁💝ПОДАРОЧНАЯ ЩЕДРОСТЬ💝🎁'")
    
    await session.commit()
    await add_transaction(session, user.id, -item["price"], "gift_sent", f"ПОДАРОК {item['name']} ДЛЯ {recip.full_name}")
    
    await notify_user(message.bot, recip.telegram_id, f"🎁 {user.full_name} ПОДАРИЛ ВАМ {item['name']}!\n{item['message']}")
    await message.answer(
        f"✅ ВЫ ПОДАРИЛИ {item['name']} ПОЛЬЗОВАТЕЛЮ {recip.full_name}!",
        reply_markup=main_menu()
    )
    await send_news_to_channel(message.bot, f"🎁 {user.full_name} ПОДАРИЛ {item['name']} ПОЛЬЗОВАТЕЛЮ {recip.full_name}")
    await state.clear()

# ---------- Реферальная ссылка ----------
@router.callback_query(F.data == "profile_referral")
async def profile_referral(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    link = generate_referral_link(user.telegram_id)
    text = (
        f"🔗✨ ВАША РЕФЕРАЛЬНАЯ ССЫЛКА: ✨🔗\n"
        f"{link}\n\n"
        f"🤝 ПРИГЛАШЕНО ДРУЗЕЙ: {user.invited_count}\n"
        f"💰 ЗА КАЖДОГО ДРУГА ВЫ ПОЛУЧАЕТЕ 25 000 ₽!"
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("profile"))
    await callback.answer()

# ---------- Семья ----------
@router.callback_query(F.data == "family")
async def family_list(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(User).where(User.full_name != "НЕ УКАЗАНО")
    )
    users = result.scalars().all()
    if not users:
        await callback.answer("НЕТ ЗАРЕГИСТРИРОВАННЫХ ПОЛЬЗОВАТЕЛЕЙ.", show_alert=True)
        return
    
    text = "👨‍👩‍👧‍👦✨ СЕМЬЯ: ✨👨‍👩‍👧‍👦\n"
    for u in users:
        text += f"• {u.full_name} — {u.rank} (ДОХОД: {format_balance(u.total_earned)} ₽)\n"
    
    builder = InlineKeyboardBuilder()
    for u in users:
        builder.button(text=u.full_name, callback_data=f"family_profile_{u.telegram_id}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="back_to_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("family_profile_"))
async def family_profile_main(callback: CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split("_")[2])
    user = await get_user(user_id, session)
    if not user:
        await callback.answer("ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН.", show_alert=True)
        return
    
    text = (
        f"📋✨ ЛИЧНОЕ ДЕЛО {user.full_name} ✨📋\n"
        f"🆔 ID: {user.telegram_id}\n"
        f"📅 В БОТЕ С: {user.registered_at.strftime('%d.%m.%Y')}"
    )
    if user.is_vip:
        text = f"💜 VIP 💜\n{text}"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 БАЛАНС", callback_data=f"fam_balance_{user_id}")
    builder.button(text="🏅 ЗВАНИЯ", callback_data=f"fam_rank_{user_id}")
    builder.button(text="🎁 ПОДАРКИ", callback_data=f"fam_gifts_{user_id}")
    builder.button(text="🏅 МЕДАЛИ", callback_data=f"fam_medals_{user_id}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="family"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("fam_balance_"))
async def fam_balance(callback: CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split("_")[2])
    user = await get_user(user_id, session)
    text = f"💰✨ БАЛАНС {user.full_name}: {format_balance(user.balance)} ₽\n📈 ДОХОД: {format_balance(user.total_earned)} ₽ ✨💰"
    await callback.message.edit_text(text, reply_markup=back_keyboard(f"family_profile_{user_id}"))
    await callback.answer()

@router.callback_query(F.data.startswith("fam_rank_"))
async def fam_rank(callback: CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split("_")[2])
    user = await get_user(user_id, session)
    text = f"🎖✨ ЗВАНИЕ {user.full_name}: {user.rank} ✨🎖"
    await callback.message.edit_text(text, reply_markup=back_keyboard(f"family_profile_{user_id}"))
    await callback.answer()

@router.callback_query(F.data.startswith("fam_gifts_"))
async def fam_gifts(callback: CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split("_")[2])
    user = await get_user(user_id, session)
    purchases = json.loads(user.purchases) if user.purchases else []
    if purchases:
        text = f"🎁✨ ПОДАРКИ/ПОКУПКИ {user.full_name}: ✨🎁\n"
        for p in purchases:
            text += f"• {p.get('name', 'ТОВАР')}"
            if p.get('gift_from'):
                text += f" (ОТ {p['gift_from']})"
            text += "\n"
    else:
        text = "У ПОЛЬЗОВАТЕЛЯ ПОКА НЕТ ПОДАРКОВ."
    await callback.message.edit_text(text, reply_markup=back_keyboard(f"family_profile_{user_id}"))
    await callback.answer()

@router.callback_query(F.data.startswith("fam_medals_"))
async def fam_medals(callback: CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split("_")[2])
    user = await get_user(user_id, session)
    medals = json.loads(user.medals) if user.medals else []
    text = f"🏅✨ МЕДАЛИ {user.full_name}: ✨🏅\n" + "\n".join(medals) if medals else "НЕТ МЕДАЛЕЙ."
    await callback.message.edit_text(text, reply_markup=back_keyboard(f"family_profile_{user_id}"))
    await callback.answer()

# ---------- Профиль ----------
@router.callback_query(F.data == "profile")
async def profile_main(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    text = (
        f"🫆✨ ПРОФИЛЬ {user.full_name} ✨🫆\n"
        f"📅 ДАТА РЕГИСТРАЦИИ: {user.registered_at.strftime('%d.%m.%Y')}\n"
        f"💰 БАЛАНС: {format_balance(user.balance)} ₽\n"
        f"📈 ОБЩИЙ ДОХОД: {format_balance(user.total_earned)} ₽"
    )
    if user.is_vip:
        text = f"💜 VIP 💜\n{text}"
    await callback.message.edit_text(text, reply_markup=profile_sections_keyboard())
    await callback.answer()

@router.callback_query(F.data == "profile_ranks")
async def profile_ranks(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    text = f"🎖✨ ВАШЕ ЗВАНИЕ: {user.rank} ✨🎖"
    await callback.message.edit_text(text, reply_markup=back_keyboard("profile"))
    await callback.answer()

@router.callback_query(F.data == "profile_gifts")
async def profile_gifts(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    purchases = json.loads(user.purchases) if user.purchases else []
    if purchases:
        text = "🎁✨ ВАШИ ПОДАРКИ/ПОКУПКИ: ✨🎁\n"
        for p in purchases:
            text += f"• {p.get('name', 'ТОВАР')}"
            if p.get('gift_from'):
                text += f" (ОТ {p['gift_from']})"
            text += f"\n{p.get('message', '')}\n\n"
    else:
        text = "У ВАС ПОКА НЕТ ПОДАРКОВ."
    await callback.message.edit_text(text, reply_markup=back_keyboard("profile"))
    await callback.answer()

@router.callback_query(F.data == "profile_medals")
async def profile_medals(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    medals = json.loads(user.medals) if user.medals else []
    text = "🏅✨ ВАШИ МЕДАЛИ: ✨🏅\n" + "\n".join(medals) if medals else "У ВАС ПОКА НЕТ МЕДАЛЕЙ."
    await callback.message.edit_text(text, reply_markup=back_keyboard("profile"))
    await callback.answer()

# ---------- Благотворительность (анонимная) ----------
@router.callback_query(F.data == "charity")
async def charity_menu(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(User).where(User.full_name != "НЕ УКАЗАНО").order_by(User.balance).limit(1)
    )
    poorest = result.scalar_one_or_none()
    if not poorest:
        await callback.answer("НЕТ ПОЛЬЗОВАТЕЛЕЙ ДЛЯ ПОМОЩИ.", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 ПОЖЕРТВОВАТЬ", callback_data="charity_donate")
    builder.button(text="🏆 РЕЙТИНГ ЩЕДРЫХ", callback_data="charity_rating")
    builder.button(text="🔙 НАЗАД", callback_data="bank_menu")
    await callback.message.edit_text(
        f"💕✨ БЛАГОТВОРИТЕЛЬНЫЙ ФОНД ✨💕\n\n"
        f"ВАШЕ ПОЖЕРТВОВАНИЕ БУДЕТ ПОЛНОСТЬЮ АНОНИМНЫМ. НИКТО НЕ УЗНАЕТ, КТО ОТПРАВИЛ И КТО ПОЛУЧИЛ ПОМОЩЬ.",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "charity_donate")
async def charity_donate_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💕 ВВЕДИТЕ СУММУ ПОЖЕРТВОВАНИЯ:", reply_markup=back_keyboard("charity"))
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
        await message.answer("ВВЕДИТЕ ЧИСЛО.")
        return
    
    user = await get_user(message.from_user.id, session)
    if amount <= 0 or amount > user.balance:
        await message.answer("НЕДОСТАТОЧНО СРЕДСТВ ИЛИ НЕКОРРЕКТНАЯ СУММА.")
        return
    
    result = await session.execute(
        select(User).where(User.full_name != "НЕ УКАЗАНО").order_by(User.balance).limit(1)
    )
    poorest = result.scalar_one_or_none()
    if not poorest:
        await message.answer("ОШИБКА: НЕ НАЙДЕН ПОЛУЧАТЕЛЬ.")
        return
    
    user.balance -= amount
    poorest.balance += amount
    poorest.total_earned += amount
    user.total_donated += amount
    await session.commit()
    await add_transaction(session, user.id, -amount, "charity", "АНОНИМНОЕ ПОЖЕРТВОВАНИЕ В ФОНД")
    await add_transaction(session, poorest.id, amount, "charity_received", "ПОЛУЧЕНА АНОНИМНАЯ ПОМОЩЬ ИЗ ФОНДА")
    
    if user.total_donated >= 20000:
        added = await add_medal(user, "🎗️🎗️ПОМОЩЬ БЕДНЫМ🎗️🎗️", session, give_bonus=True)
        if added:
            await notify_user(message.bot, user.telegram_id, "🎉 ВЫ ПОЛУЧИЛИ МЕДАЛЬ '🎗️🎗️ПОМОЩЬ БЕДНЫМ🎗️🎗️' И 5 000 ₽!")
            await send_news_to_channel(message.bot, f"🏅 {user.full_name} ПОЛУЧИЛ МЕДАЛЬ '🎗️🎗️ПОМОЩЬ БЕДНЫМ🎗️🎗️'")
    
    await notify_user(
        message.bot,
        poorest.telegram_id,
        f"💰✨ ВАМ ПОСТУПИЛО АНОНИМНОЕ ПОЖЕРТВОВАНИЕ {format_balance(amount)} ₽ ИЗ БЛАГОТВОРИТЕЛЬНОГО ФОНДА! ✨💰\n"
        f"ВАШ ТЕКУЩИЙ БАЛАНС: {format_balance(poorest.balance)} ₽"
    )
    
    await message.answer(
        f"✅✨ ВЫ АНОНИМНО ПОЖЕРТВОВАЛИ {format_balance(amount)} ₽ НУЖДАЮЩЕМУСЯ ЧЛЕНУ СЕМЬИ. ✨✅",
        reply_markup=main_menu()
    )
    await send_news_to_channel(message.bot, f"💕 АНОНИМНОЕ ПОЖЕРТВОВАНИЕ {format_balance(amount)} ₽ В ФОНД")
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
    text = "🏆✨ РЕЙТИНГ БЛАГОТВОРИТЕЛЕЙ (АНОНИМНЫЙ ДЛЯ ПОЛУЧАТЕЛЕЙ): ✨🏆\n"
    for i, row in enumerate(rating, 1):
        text += f"{i}. {row[0]} — {format_balance(row[1])} ₽\n"
    await callback.message.edit_text(text, reply_markup=back_keyboard("charity"))
    await callback.answer()

# ---------- Медали ----------
@router.callback_query(F.data == "medals_info")
async def medals_info(callback: CallbackQuery):
    text = get_medals_info()
    await callback.message.edit_text(text, reply_markup=back_keyboard("back_to_main"))
    await callback.answer()

# ---------- Помощь ----------
@router.callback_query(F.data == "help")
async def help_cmd(callback: CallbackQuery):
    text = (
        "❓✨ ПОМОЩЬ: ✨❓\n"
        "• СБЕРБАНК — БАЛАНС, ПЕРЕВОДЫ, ВКЛАДЫ (20%/ЧАС), КРЕДИТЫ (30%/5Ч), БЛАГОТВОРИТЕЛЬНОСТЬ\n"
        "• КАЗИНО — КУБИК (X6) И СЛОТЫ (X3, X7)\n"
        "• ТЕСТ IQ — 15 ВОПРОСОВ, НАГРАДЫ\n"
        "• МАГАЗИН — ПОЛЕЗНЫЕ ТОВАРЫ И PREMIUM СТАТУС\n"
        "• ПРОФИЛЬ — СТАТИСТИКА, ЗВАНИЯ, МЕДАЛИ, РЕФЕРАЛЬНАЯ ССЫЛКА\n"
        "• НОВОСТИ — ПОДПИШИТЕСЬ НА НАШ КАНАЛ (КНОПКА ВЕДЁТ В КАНАЛ)\n"
        "• СЕМЬЯ — ПРОФИЛИ ВСЕХ ИГРОКОВ\n"
        "• ЕЖЕЧАСНЫЙ БОНУС — РАСТЁТ С ЗВАНИЕМ\n"
        "• РАБОТА — ФИЗИЧЕСКИЙ И УМСТВЕННЫЙ ТРУД\n"
        "• ОБУЧЕНИЕ — ПОДРОБНО О ЗВАНИЯХ, МЕДАЛЯХ И ДРУГОМ\n"
        "• ПРИГЛАШАЙТЕ ДРУЗЕЙ И ПОЛУЧАЙТЕ 25 000 ₽ ЗА КАЖДОГО!"
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("back_to_main"))
    await callback.answer()

# ---------- Обучение ----------
@router.callback_query(F.data == "learning_menu")
async def learning_menu(callback: CallbackQuery):
    await callback.message.edit_text("📚✨ ВЫБЕРИТЕ РАЗДЕЛ ОБУЧЕНИЯ: ✨📚", reply_markup=learning_menu_keyboard())
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
    await callback.message.edit_text("📖✨ ВЫБЕРИТЕ ТЕМУ: ✨📖", reply_markup=learning_other_keyboard())
    await callback.answer()

@router.callback_query(F.data == "learn_work")
async def learn_work(callback: CallbackQuery):
    text = (
        "💼✨ РАБОТА ✨💼\n"
        "• УМСТВЕННЫЙ ТРУД — РЕШАЙТЕ ЗАДАЧИ И ПОЛУЧАЙТЕ 3 112 ₽ ЗА ПРАВИЛЬНЫЙ ОТВЕТ.\n"
        "• ФИЗИЧЕСКИЙ ТРУД — НАЖИМАЙТЕ 'ПОЛОЖИТЬ КИРПИЧ' И ПОЛУЧАЙТЕ 57 ₽ ЗА КАЖДОЕ НАЖАТИЕ.\n"
        "• ЗАРАБОТОК СУММИРУЕТСЯ, И ЕСЛИ ВЫ НЕ РАБОТАЕТЕ 5 МИНУТ, НОВОСТЬ О ВАШЕМ ДОХОДЕ ПОПАДАЕТ В КАНАЛ.\n"
        "• РЕЙТИНГИ ПО КАЖДОМУ ВИДУ РАБОТЫ ПОКАЗЫВАЮТ ЛУЧШИХ РАБОТНИКОВ."
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("learn_other"))
    await callback.answer()

@router.callback_query(F.data == "learn_bank")
async def learn_bank(callback: CallbackQuery):
    text = (
        "🏦✨ БАНК ✨🏦\n"
        "• ПЕРЕВОД — ОТПРАВЛЯЙТЕ ДЕНЬГИ ДРУГИМ ИГРОКАМ ПО ИМЕНИ.\n"
        "• ВКЛАД — ПОЛОЖИТЕ ДЕНЬГИ ПОД 20% В ЧАС. СНЯТЬ МОЖНО В ЛЮБОЕ ВРЕМЯ.\n"
        "• КРЕДИТ — ВОЗЬМИТЕ ДО X10 ОТ БАЛАНСА НА 5-25 ЧАСОВ ПОД 30% КАЖДЫЕ 5 ЧАСОВ.\n"
        "• БЛАГОТВОРИТЕЛЬНОСТЬ — АНОНИМНО ПОМОГИТЕ САМОМУ БЕДНОМУ ИГРОКУ."
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("learn_other"))
    await callback.answer()

@router.callback_query(F.data == "learn_shop")
async def learn_shop(callback: CallbackQuery):
    text = (
        "🛍️✨ МАГАЗИН ✨🛍️\n"
        "• ПОКУПАЙТЕ ПОЛЕЗНЫЕ ТОВАРЫ ЗА ВНУТРИИГРОВУЮ ВАЛЮТУ.\n"
        "• ТОВАР 'СЕМЬЯ PREMIUM' ДАЁТ VIP-СТАТУС, ФИОЛЕТОВЫЕ КНОПКИ, ПОВЫШЕНИЕ ЗВАНИЯ И УНИКАЛЬНУЮ МЕДАЛЬ.\n"
        "• ВСЕ ТОВАРЫ МОЖНО ДАРИТЬ ДРУГИМ ИГРОКАМ.\n"
        "• КУПЛЕННЫЕ ТОВАРЫ ОТОБРАЖАЮТСЯ В ПРОФИЛЕ."
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard("learn_other"))
    await callback.answer()

# ---------- Работа ----------
@router.callback_query(F.data == "work_menu")
async def work_menu(callback: CallbackQuery):
    await callback.message.edit_text("🚧✨ ВЫБЕРИТЕ ТИП РАБОТЫ: ✨🚧", reply_markup=work_menu_keyboard())
    await callback.answer()

# --- Физический труд ---
@router.callback_query(F.data == "work_physical")
async def work_physical_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🔨✨ ФИЗИЧЕСКИЙ ТРУД — СТРОЙКА ДОМА ✨🔨\n"
        "НАЖИМАЙТЕ «ПОЛОЖИТЬ КИРПИЧ», ЧТОБЫ ЗАРАБОТАТЬ 57 ₽.\n"
        "СТРОЙТЕ БЕСКОНЕЧНО!",
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
    await add_transaction(session, user.id, 57, "work_physical", "ФИЗИЧЕСКИЙ ТРУД: КИРПИЧ")
    await callback.answer("+57 ₽! КИРПИЧ УЛОЖЕН.", show_alert=False)
    # Обновляем сообщение с текущим балансом
    await callback.message.edit_text(
        f"🔨✨ ФИЗИЧЕСКИЙ ТРУД — СТРОЙКА ДОМА ✨🔨\n"
        f"💰 БАЛАНС: {format_balance(user.balance)} ₽\n"
        f"🧱 ЗАРАБОТАНО НА СТРОЙКЕ: {format_balance(user.work_physical_earned)} ₽",
        reply_markup=physical_work_keyboard()
    )

@router.callback_query(F.data == "physical_rating")
async def physical_rating(callback: CallbackQuery, session: AsyncSession):
    rating = await get_work_rating(session, "physical")
    text = "🏆✨ РЕЙТИНГ СТРОИТЕЛЕЙ: ✨🏆\n"
    for i, row in enumerate(rating, 1):
        text += f"{i}. {row[0]} — {format_balance(row[1])} ₽\n"
    if not rating:
        text += "ПОКА НИКТО НЕ РАБОТАЛ НА СТРОЙКЕ."
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
        f"🧠✨ УМСТВЕННЫЙ ТРУД ✨🧠\n\n"
        f"ЗАДАЧА: {task['q']}\n\n"
        f"ВВЕДИТЕ ВАШ ОТВЕТ (ЧИСЛО ИЛИ СЛОВО):",
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
        await add_transaction(session, user.id, 3112, "work_mental", "УМСТВЕННЫЙ ТРУД: ПРАВИЛЬНЫЙ ОТВЕТ")
        await session.commit()
    
    # Генерируем следующую задачу
    new_task = get_random_mental_task()
    await state.update_data(mental_task=new_task, mental_earned=earned)
    
    builder = InlineKeyboardBuilder()
    builder.attach(InlineKeyboardBuilder.from_markup(mental_work_keyboard()))
    await message.answer(
        f"{response_text}\n\n"
        f"СЛЕДУЮЩАЯ ЗАДАЧА: {new_task['q']}\n\n"
        f"ВВЕДИТЕ ВАШ ОТВЕТ:",
        reply_markup=mental_work_keyboard()
    )
    # Отправляем новость о заработке, если пользователь не активен 5 минут (будет в фоновой задаче, пока просто сумма)
    if earned > 0:
        await send_news_to_channel(message.bot, f"🧠 {user.full_name} ЗАРАБОТАЛ {format_balance(earned)} ₽ НА УМСТВЕННОМ ТРУДЕ")

@router.callback_query(StateFilter(MentalWorkState.answering), F.data == "mental_next_task")
async def mental_next_task(callback: CallbackQuery, state: FSMContext):
    task = get_random_mental_task()
    await state.update_data(mental_task=task)
    await callback.message.edit_text(
        f"🧠✨ НОВАЯ ЗАДАЧА: ✨🧠\n\n{task['q']}\n\nВВЕДИТЕ ОТВЕТ:",
        reply_markup=mental_work_keyboard()
    )
    await callback.answer()

@router.callback_query(StateFilter(MentalWorkState.answering), F.data == "mental_rating")
async def mental_rating(callback: CallbackQuery, session: AsyncSession):
    rating = await get_work_rating(session, "mental")
    text = "🏆✨ РЕЙТИНГ УМНИКОВ: ✨🏆\n"
    for i, row in enumerate(rating, 1):
        text += f"{i}. {row[0]} — {format_balance(row[1])} ₽\n"
    if not rating:
        text += "ПОКА НИКТО НЕ РЕШАЛ ЗАДАЧИ."
    await callback.message.edit_text(text, reply_markup=back_keyboard("work_mental"))
    await callback.answer()

@router.callback_query(StateFilter(MentalWorkState.answering), F.data == "work_menu")
async def mental_work_finish(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    earned = data.get("mental_earned", 0)
    user = await get_user(callback.from_user.id, session)
    if earned > 0:
        await send_news_to_channel(callback.bot, f"🧠 {user.full_name} ЗАВЕРШИЛ УМСТВЕННЫЙ ТРУД, ЗАРАБОТАВ {format_balance(earned)} ₽")
    await state.clear()
    await work_menu(callback)

# ---------- Обработчик неизвестных callback ----------
@router.callback_query()
async def unknown_callback(callback: CallbackQuery):
    await callback.answer("ДЕЙСТВИЕ НЕ РАСПОЗНАНО", show_alert=True)

# ---------- Обработчик неизвестных сообщений ----------
@router.message()
async def unknown_message(message: Message):
    user = await get_user(message.from_user.id, next(get_db()))
    name = user.full_name if user else "ПОЛЬЗОВАТЕЛЬ"
    await message.answer(
        f"😐 Я ВАС НЕ ПОНИМАЮ 😐\n"
        f"{name}, ВЫ ДЕЛАЕТЕ ЧТО-ТО НЕ ТАК, НАЖМИТЕ КОМАНДУ /start ДЛЯ ПЕРЕЗАПУСКА ВАШЕГО БОТА."
    )
