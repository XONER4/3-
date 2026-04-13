import json
import random
import asyncio
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile, InputMediaPhoto
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import BOT_PASSWORD, START_BALANCE, DAILY_BONUS_BASE, CREDIT_PERCENT, CREDIT_MAX_DAYS, ADMIN_ID, TIMEZONE_OFFSET
from models import User, Transaction, CasinoGame, IQResult
from keyboards import *
from utils import check_rank_upgrade, add_medal, calculate_deposit_payout, get_rank_conditions, RANK_BONUS_MULTIPLIER

router = Router()

# ---------- FSM Состояния ----------
class AuthState(StatesGroup):
    waiting_for_password = State()
    waiting_for_fullname = State()

class CasinoState(StatesGroup):
    waiting_for_bet = State()
    waiting_for_dice_bet = State()
    waiting_for_slots_bet = State()
    waiting_for_dice_guess = State()

class IQState(StatesGroup):
    answering = State()

class CreditState(StatesGroup):
    waiting_for_amount = State()

class DepositState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_days = State()

class TransferState(StatesGroup):
    waiting_for_recipient_name = State()
    waiting_for_amount = State()

class ShopState(StatesGroup):
    choosing_category = State()
    choosing_item = State()
    choosing_action = State()
    choosing_recipient_name = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

class AdminState(StatesGroup):
    waiting_for_user_id_balance = State()
    waiting_for_amount_balance = State()
    waiting_for_user_id_rank = State()
    waiting_for_rank = State()
    waiting_for_user_id_rename = State()
    waiting_for_new_name = State()
    waiting_for_new_password = State()

class CharityState(StatesGroup):
    waiting_for_amount = State()

class PhotoUploadState(StatesGroup):
    waiting_for_photo = State()

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

async def update_balance(user: User, amount: float, session: AsyncSession, type_: str, description: str = None):
    user.balance += amount
    if amount > 0:
        user.total_earned += amount
    await add_transaction(session, user.id, amount, type_, description)
    await session.commit()
    rank_change = await check_rank_upgrade(user, session)
    if rank_change:
        old, new = rank_change
        from bot import bot
        try:
            await bot.send_message(
                user.telegram_id,
                f"🎉 Поздравляем! Ваше звание повышено с {old} до {new}!\n"
                f"Теперь ваш ежедневный бонус составляет {DAILY_BONUS_BASE * RANK_BONUS_MULTIPLIER[new]:,} ₽!"
            )
        except:
            pass

async def notify_user(telegram_id: int, text: str):
    from bot import bot
    try:
        await bot.send_message(telegram_id, text)
    except:
        pass

def format_balance(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", ".")

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

SHOP_ITEMS = {
    "cars": [
        {"name": "Mercedes-Benz S-Class", "price": 5000000},
        {"name": "Mercedes-Benz E-Class", "price": 3500000},
        {"name": "Mercedes-Benz C-Class", "price": 2000000},
        {"name": "Жигули ВАЗ-2107", "price": 200000},
        {"name": "Лада Веста", "price": 600000},
        {"name": "Лада Гранта", "price": 400000},
    ],
    "flowers": [
        {"name": "Роза", "price": 10000},
        {"name": "Тюльпан", "price": 15000},
        {"name": "Орхидея", "price": 50000},
        {"name": "Букет пионов", "price": 100000},
    ]
}

# ---------- /start ----------
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession):
    user_id = message.from_user.id
    user = await get_user(user_id, session)
    
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
            deposits_made=0
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    
    if not user.is_authorized:
        await message.answer(
            "🔐 Добро пожаловать! Для входа в бота введите пароль.",
            reply_markup=password_keyboard()
        )
        await state.set_state(AuthState.waiting_for_password)
    else:
        await message.answer(
            f"👋 С возвращением, {user.full_name}! Вы в главном меню.",
            reply_markup=main_menu()
        )

# ---------- Авторизация ----------
@router.message(StateFilter(AuthState.waiting_for_password), F.text)
async def process_password(message: Message, state: FSMContext, session: AsyncSession):
    if message.text == BOT_PASSWORD:
        user = await get_user(message.from_user.id, session)
        if user and user.is_authorized:
            await message.answer(f"👋 Вы уже авторизованы, {user.full_name}!", reply_markup=main_menu())
            await state.clear()
            return
        await state.update_data(user=user)
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
    
    full_name = " ".join(name_parts[:2])
    data = await state.get_data()
    user = data["user"]
    user.full_name = full_name
    user.is_authorized = True
    await session.commit()
    
    await message.answer(
        f"👋 Добро пожаловать, {full_name}! Вы в главном меню.",
        reply_markup=main_menu()
    )
    await state.clear()

# ---------- Главное меню ----------
@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🏠 Главное меню", reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "balance")
async def show_balance(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    
    result = await session.execute(
        select(Transaction).where(Transaction.user_id == user.id).order_by(desc(Transaction.timestamp)).limit(5)
    )
    trans = result.scalars().all()
    history = "\n".join([f"{t.timestamp.strftime('%d.%m %H:%M')} {t.description or t.type}: {format_balance(t.amount)} ₽" for t in trans])
    
    total_spent = await session.scalar(
        select(func.sum(Transaction.amount)).where(Transaction.user_id == user.id, Transaction.amount < 0)
    ) or 0.0
    total_earned = user.total_earned
    
    text = (
        f"💰 Ваш баланс: {format_balance(user.balance)} ₽\n"
        f"📈 Общий доход: {format_balance(total_earned)} ₽\n"
        f"📉 Общий расход: {format_balance(abs(total_spent))} ₽\n\n"
        f"📋 Последние операции:\n{history if history else 'нет операций'}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="balance"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

# ---------- Ежедневный бонус ----------
@router.callback_query(F.data == "daily_bonus")
async def daily_bonus(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    
    now = datetime.now()
    if user.last_bonus and user.last_bonus.date() == now.date():
        await callback.answer("Вы уже получали бонус сегодня.", show_alert=True)
        return
    
    multiplier = RANK_BONUS_MULTIPLIER.get(user.rank, 1)
    bonus = DAILY_BONUS_BASE * multiplier
    user.balance += bonus
    user.total_earned += bonus
    user.last_bonus = now
    await session.commit()
    await add_transaction(session, user.id, bonus, "daily_bonus", f"Ежедневный бонус ({user.rank})")
    
    await callback.message.edit_text(
        f"🎁 Вы получили ежедневный бонус {format_balance(bonus)} ₽!\n"
        f"💰 Ваш новый баланс: {format_balance(user.balance)} ₽",
        reply_markup=back_keyboard()
    )
    await callback.answer()

# ---------- Казино ----------
@router.callback_query(F.data == "casino_menu")
async def casino_menu(callback: CallbackQuery):
    await callback.message.edit_text("🎰 Выберите игру:", reply_markup=casino_menu_keyboard())
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
    text = "🏆 Рейтинг казино (по выигрышам):\n"
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
        await update_balance(user, payout - bet, session, "casino_win", f"Кубик: угадал {guess}, выпало {dice_value}")
        text = f"🎉 Вы угадали! Выпало {dice_value}. Выигрыш x6: {format_balance(payout)} ₽!"
    else:
        await update_balance(user, -bet, session, "casino_loss", f"Кубик: не угадал (загадано {guess}, выпало {dice_value})")
        text = f"😢 Не угадали. Загадано {guess}, выпало {dice_value}. Проигрыш {format_balance(bet)} ₽."
    
    user.casino_bets_count += 1
    if user.casino_bets_count == 30:
        await add_medal(user, "🎰ЛУДОМАН🎰", session)
        await notify_user(user.telegram_id, "🎉 Поздравляем! Вы получили медаль '🎰ЛУДОМАН🎰' за 30 ставок в казино!")
    
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
    
    await callback.message.edit_text(
        f"{text}\n💰 Баланс: {format_balance(user.balance)} ₽",
        reply_markup=back_keyboard("casino_dice")
    )
    await state.clear()
    await callback.answer()

# --- Слоты ---
@router.callback_query(F.data == "casino_slots")
async def slots_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🎰 Выберите сумму ставки:", reply_markup=slots_bet_keyboard())
    await state.set_state(CasinoState.waiting_for_slots_bet)
    await callback.answer()

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
    
    # Определяем комбинацию: три одинаковых? два одинаковых?
    # 1,22,43,64 - джекпот (все BAR), 2,3,4,21,23,42,44,63 - два одинаковых, остальное проигрыш
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
        await update_balance(user, payout - bet, session, "casino_win", f"Слоты: {combo}")
        text = f"🎉 Слоты! Комбинация {slot_value} ({combo}). Выигрыш x{multiplier}: {format_balance(payout)} ₽"
    else:
        await update_balance(user, -bet, session, "casino_loss", f"Слоты: {combo}")
        text = f"😢 Слоты! Комбинация {slot_value} ({combo}). Проигрыш {format_balance(bet)} ₽."
    
    user.casino_bets_count += 1
    if user.casino_bets_count == 30:
        await add_medal(user, "🎰ЛУДОМАН🎰", session)
        await notify_user(user.telegram_id, "🎉 Поздравляем! Вы получили медаль '🎰ЛУДОМАН🎰' за 30 ставок в казино!")
    
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
    
    await callback.message.edit_text(
        f"{text}\n💰 Баланс: {format_balance(user.balance)} ₽",
        reply_markup=back_keyboard("casino_slots")
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
    if user.balance < 1000:
        await callback.answer("Для прохождения теста нужно минимум 1.000 ₽ на балансе!", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Отменить тест", callback_data="cancel_iq")
    await callback.message.edit_text(
        "🧠 Тест IQ. 15 вопросов. Нажмите 'Отменить тест' чтобы выйти без последствий.",
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
    
    medal = ""
    bonus = 0
    detail = ""
    if correct == 15:
        medal = "✅15 из 15 IQ✅"
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
    
    await update_balance(user, bonus, session, "iq_bonus", f"Тест IQ: {correct}/{total}")
    if medal:
        added = await add_medal(user, medal, session)
        if added:
            await notify_user(user.telegram_id, f"🎉 Поздравляем! Вы получили медаль '{medal}' за тест IQ!")
    
    iq_result = IQResult(
        user_id=user.id,
        correct_answers=correct,
        medal=medal,
        bonus=bonus
    )
    session.add(iq_result)
    await session.commit()
    
    text = f"🧠 Тест завершён!\nПравильных ответов: {correct} из {total}\n"
    text += f"Медаль: {medal} ({detail})\n"
    text += f"Изменение баланса: {format_balance(bonus)} ₽\n"
    text += f"💰 Текущий баланс: {format_balance(user.balance)} ₽"
    
    await callback.message.edit_text(text, reply_markup=back_keyboard())
    await state.clear()

# ---------- Кредит ----------
@router.callback_query(F.data == "credit_menu")
async def credit_menu(callback: CallbackQuery):
    await callback.message.edit_text("📋 Кредит", reply_markup=credit_menu_keyboard())
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
        f"Максимальная сумма кредита: {format_balance(max_credit)} ₽ (10% ставка)\n"
        f"Введите желаемую сумму (не более {format_balance(max_credit)}):",
        reply_markup=back_keyboard("credit_menu")
    )
    await state.set_state(CreditState.waiting_for_amount)
    await state.update_data(max_credit=max_credit)
    await callback.answer()

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
    
    user = await get_user(message.from_user.id, session)
    due_date = datetime.now() + timedelta(days=CREDIT_MAX_DAYS)
    total_repay = amount * (1 + CREDIT_PERCENT / 100)
    
    user.credit_amount = total_repay
    user.credit_due_date = due_date
    user.has_taken_credit = True
    user.loans_taken += 1
    user.balance += amount
    await session.commit()
    await add_transaction(session, user.id, amount, "credit", f"Получен кредит {format_balance(amount)} ₽")
    
    if user.loans_taken > 2:
        added = await add_medal(user, "🔴ДОЛЖНИК🔴", session)
        if added:
            await notify_user(user.telegram_id, "🎉 Вы получили медаль '🔴ДОЛЖНИК🔴' за взятие более 2 кредитов!")
    
    await message.answer(
        f"✅ Кредит одобрен!\n"
        f"Получено: {format_balance(amount)} ₽\n"
        f"К возврату: {format_balance(total_repay)} ₽ (срок до {due_date.strftime('%d.%m.%Y')})",
        reply_markup=main_menu()
    )
    await state.clear()

# ---------- Вклад ----------
@router.callback_query(F.data == "deposit_menu")
async def deposit_menu(callback: CallbackQuery):
    await callback.message.edit_text("🏦 Вклад", reply_markup=deposit_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data == "open_deposit")
async def deposit_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    if user.deposit_amount > 0:
        await callback.answer("У вас уже открыт вклад!", show_alert=True)
        return
    
    await callback.message.edit_text("Введите сумму вклада:")
    await state.set_state(DepositState.waiting_for_amount)
    await callback.answer()

@router.message(StateFilter(DepositState.waiting_for_amount), F.text)
async def deposit_amount(message: Message, state: FSMContext, session: AsyncSession):
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("Введите число.")
        return
    
    user = await get_user(message.from_user.id, session)
    if amount <= 0 or amount > user.balance:
        await message.answer("Недостаточно средств или некорректная сумма.")
        return
    
    await state.update_data(deposit_amount=amount)
    await message.answer("Введите срок вклада (от 1 до 3 дней):")
    await state.set_state(DepositState.waiting_for_days)

@router.message(StateFilter(DepositState.waiting_for_days), F.text)
async def deposit_days(message: Message, state: FSMContext, session: AsyncSession):
    try:
        days = int(message.text)
    except ValueError:
        await message.answer("Введите целое число.")
        return
    
    if days < 1 or days > 3:
        await message.answer("Срок должен быть от 1 до 3 дней.")
        return
    
    data = await state.get_data()
    amount = data["deposit_amount"]
    user = await get_user(message.from_user.id, session)
    
    user.balance -= amount
    user.deposit_amount = amount
    user.deposit_days = days
    user.deposit_start_date = datetime.now()
    user.has_made_deposit = True
    user.deposits_made += 1
    await session.commit()
    await add_transaction(session, user.id, -amount, "deposit", f"Открыт вклад {format_balance(amount)} ₽ на {days} дн.")
    
    if user.deposits_made > 2:
        added = await add_medal(user, "🤑🤑ВКЛАДЧИК🤑🤑", session)
        if added:
            await notify_user(user.telegram_id, "🎉 Вы получили медаль '🤑🤑ВКЛАДЧИК🤑🤑' за открытие более 2 вкладов!")
    
    payout = calculate_deposit_payout(amount, days)
    await message.answer(
        f"✅ Вклад открыт!\nСумма: {format_balance(amount)} ₽\nСрок: {days} дн.\n"
        f"К получению: {format_balance(payout)} ₽ (через {days} дн.)",
        reply_markup=main_menu()
    )
    await state.clear()

# ---------- Переводы (по имени) ----------
@router.callback_query(F.data == "transfer")
async def transfer_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите Имя и Фамилию получателя (как в боте):",
        reply_markup=back_keyboard("back_to_main")
    )
    await state.set_state(TransferState.waiting_for_recipient_name)
    await callback.answer()

@router.message(StateFilter(TransferState.waiting_for_recipient_name), F.text)
async def transfer_recipient(message: Message, state: FSMContext, session: AsyncSession):
    recip_name = message.text.strip()
    recip = await get_user_by_name(recip_name, session)
    if not recip:
        await message.answer("Пользователь с таким именем не найден в боте.")
        return
    
    await state.update_data(recip_id=recip.telegram_id, recip_name=recip.full_name)
    await message.answer(f"Получатель: {recip.full_name}\nВведите сумму перевода:")
    await state.set_state(TransferState.waiting_for_amount)

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
        added = await add_medal(user, "😍💰ДЕНЕЖНАЯ ЩЕДРОСТЬ💰😍", session)
        if added:
            await notify_user(user.telegram_id, "🎉 Поздравляем! Вы получили медаль '😍💰ДЕНЕЖНАЯ ЩЕДРОСТЬ💰😍' за переводы на сумму от 50.000 ₽!")
    
    await message.answer(
        f"✅ Перевод выполнен!\nПолучатель: {recip_name}\nСумма: {format_balance(amount)} ₽",
        reply_markup=main_menu()
    )
    
    await notify_user(
        recip.telegram_id,
        f"💰 Вам поступил перевод {format_balance(amount)} ₽ от {user.full_name}\n"
        f"Ваш текущий баланс: {format_balance(recip.balance)} ₽"
    )
    await state.clear()

# ---------- Семья ----------
@router.callback_query(F.data == "family")
async def family_list(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(select(User).where(User.is_authorized == True))
    users = result.scalars().all()
    if not users:
        await callback.answer("Нет зарегистрированных пользователей.", show_alert=True)
        return
    
    text = "👨‍👩‍👧‍👦 Семья:\n"
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
async def family_profile_view(callback: CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split("_")[2])
    user = await get_user(user_id, session)
    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    
    medals = json.loads(user.medals) if user.medals else []
    text = (
        f"📋 Личное дело {user.full_name}\n"
        f"🆔 ID: {user.telegram_id}\n"
        f"💰 Баланс: {format_balance(user.balance)} ₽\n"
        f"📈 Общий доход: {format_balance(user.total_earned)} ₽\n"
        f"🎖 Звание: {user.rank}\n"
        f"🏅 Медали: {', '.join(medals) if medals else 'нет'}\n"
        f"📅 В боте с: {user.registered_at.strftime('%d.%m.%Y')}"
    )
    
    if user.photo_id:
        await callback.message.answer_photo(user.photo_id, caption=text, reply_markup=back_keyboard("family"))
    else:
        await callback.message.edit_text(text, reply_markup=back_keyboard("family"))
    await callback.answer()

# ---------- Личное дело ----------
@router.callback_query(F.data == "profile")
async def profile_main(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    text = (
        f"📋 Личное дело {user.full_name}\n"
        f"📅 Дата регистрации: {user.registered_at.strftime('%d.%m.%Y')}\n"
        f"💰 Баланс: {format_balance(user.balance)} ₽\n"
        f"📈 Общий доход: {format_balance(user.total_earned)} ₽"
    )
    await callback.message.edit_text(text, reply_markup=profile_sections_keyboard())
    await callback.answer()

@router.callback_query(F.data == "profile_ranks")
async def profile_ranks(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    text = f"🎖 Ваше звание: {user.rank}\n" + get_rank_conditions()
    await callback.message.edit_text(text, reply_markup=back_keyboard("profile"))
    await callback.answer()

@router.callback_query(F.data == "profile_gifts")
async def profile_gifts(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    purchases = json.loads(user.purchases) if user.purchases else []
    text = "🎁 Ваши подарки/покупки:\n" + "\n".join(purchases) if purchases else "У вас пока нет подарков."
    await callback.message.edit_text(text, reply_markup=back_keyboard("profile"))
    await callback.answer()

@router.callback_query(F.data == "profile_medals")
async def profile_medals(callback: CallbackQuery, session: AsyncSession):
    user = await get_user(callback.from_user.id, session)
    medals = json.loads(user.medals) if user.medals else []
    text = "🏅 Ваши медали:\n" + "\n".join(medals) if medals else "У вас пока нет медалей."
    await callback.message.edit_text(text, reply_markup=back_keyboard("profile"))
    await callback.answer()

@router.callback_query(F.data == "profile_upload_photo")
async def profile_upload_photo(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📸 Отправьте фотографию для профиля:")
    await state.set_state(PhotoUploadState.waiting_for_photo)
    await callback.answer()

@router.message(StateFilter(PhotoUploadState.waiting_for_photo), F.photo)
async def photo_uploaded(message: Message, state: FSMContext, session: AsyncSession):
    user = await get_user(message.from_user.id, session)
    user.photo_id = message.photo[-1].file_id
    await session.commit()
    await message.answer("✅ Фото профиля обновлено!", reply_markup=main_menu())
    await state.clear()

# ---------- Новости ----------
@router.callback_query(F.data == "news")
async def news(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(Transaction).options(selectinload(Transaction.user)).order_by(desc(Transaction.timestamp)).limit(10)
    )
    trans = result.scalars().all()
    
    text = "📰 Последние события (МСК):\n"
    for t in trans:
        local_time = t.timestamp + timedelta(hours=TIMEZONE_OFFSET)
        user_name = t.user.full_name if t.user else "Неизвестный"
        emoji = "🟢" if t.amount > 0 else "🔴"
        text += f"{emoji} {local_time.strftime('%d.%m.%Y %H:%M')} — {user_name}: {t.description or t.type} ({format_balance(t.amount)} ₽)\n"
    
    await callback.message.edit_text(text, reply_markup=back_keyboard())
    await callback.answer()

# ---------- Благотворительность ----------
@router.callback_query(F.data == "charity")
async def charity_menu(callback: CallbackQuery, session: AsyncSession):
    result = await session.execute(
        select(User).where(User.is_authorized == True).order_by(User.balance).limit(1)
    )
    poorest = result.scalar_one_or_none()
    if not poorest:
        await callback.answer("Нет пользователей для помощи.", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Пожертвовать", callback_data="charity_donate")
    builder.button(text="🏆 Рейтинг щедрых", callback_data="charity_rating")
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    await callback.message.edit_text(
        f"🆘 ПОМОГИ СЕМЬЕ 🆘\n\n"
        f"Сейчас самый низкий баланс у: {poorest.full_name} ({format_balance(poorest.balance)} ₽)\n"
        f"Ваше пожертвование будет анонимным.",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "charity_donate")
async def charity_donate_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите сумму пожертвования:")
    await state.set_state(CharityState.waiting_for_amount)
    await callback.answer()

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
        select(User).where(User.is_authorized == True).order_by(User.balance).limit(1)
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
    await add_transaction(session, user.id, -amount, "charity", "Пожертвование в фонд")
    await add_transaction(session, poorest.id, amount, "charity_received", "Получена помощь из фонда")
    
    if user.total_donated >= 20000:
        added = await add_medal(user, "🎗️🎗️ПОМОЩЬ БЕДНЫМ🎗️🎗️", session)
        if added:
            await notify_user(user.telegram_id, "🎉 Вы получили медаль '🎗️🎗️ПОМОЩЬ БЕДНЫМ🎗️🎗️' за пожертвования от 20.000 ₽!")
    
    await message.answer(
        f"✅ Вы анонимно пожертвовали {format_balance(amount)} ₽ нуждающемуся члену семьи.",
        reply_markup=main_menu()
    )
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
    text = "🏆 Рейтинг благотворителей:\n"
    for i, row in enumerate(rating, 1):
        text += f"{i}. {row[0]} — {format_balance(row[1])} ₽\n"
    await callback.message.edit_text(text, reply_markup=back_keyboard("charity"))
    await callback.answer()

# ---------- Медали ----------
@router.callback_query(F.data == "medals_info")
async def medals_info(callback: CallbackQuery):
    text = (
        "🏅 Все медали:\n"
        "• ✅15 из 15 IQ✅ — 15/15 в тесте IQ\n"
        "• 💚ХОРОШИСТ IQ💚 — 9-14 правильных\n"
        "• 😊СЛАБАК IQ😊 — 5-8 правильных\n"
        "• ❌ВСЕ ПЛОХО IQ❌ — меньше 5 правильных\n"
        "• 😍💰ДЕНЕЖНАЯ ЩЕДРОСТЬ💰😍 — перевел от 50.000 ₽\n"
        "• 🎁💝ПОДАРОЧНАЯ ЩЕДРОСТЬ💝🎁 — отправил 5+ подарков\n"
        "• 🎗️🎗️ПОМОЩЬ БЕДНЫМ🎗️🎗️ — пожертвовал от 20.000 ₽\n"
        "• 🎰ЛУДОМАН🎰 — 30+ ставок в казино\n"
        "• 🔴ДОЛЖНИК🔴 — взял более 2 кредитов\n"
        "• 🤑🤑ВКЛАДЧИК🤑🤑 — открыл более 2 вкладов\n"
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard())
    await callback.answer()

# ---------- Помощь ----------
@router.callback_query(F.data == "help")
async def help_cmd(callback: CallbackQuery):
    text = (
        "❓ Помощь:\n"
        "• Баланс — просмотр средств и истории\n"
        "• Казино — кубик (угадай число, x6) и слоты (2 одинаковых x3, 3 одинаковых x7)\n"
        "• Тест IQ — 15 вопросов, награды\n"
        "• Кредит — до x10 от баланса, на 3 дня, 10%\n"
        "• Вклад — 20% в день, от 1 до 3 дней\n"
        "• Магазин — авто и цветы, можно дарить (по имени)\n"
        "• Личное дело — статистика, можно загрузить фото\n"
        "• Новости — события с эмодзи\n"
        "• Перевод — переводы по имени и фамилии\n"
        "• Семья — профили всех\n"
        "• Благотворительность — помощь анонимно"
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard())
    await callback.answer()

# ---------- Обработчик неизвестных сообщений ----------
@router.message()
async def unknown_message(message: Message):
    await message.answer(
        "‼️ОСТАНОВИСЬ‼️\n"
        "Все хорошо, только ты делаешь что-то неправильно. Это сообщение отправляется, если кто-то из семьи отправляет параметр в бота (сообщение и т.д.) который ботом не предусмотрен."
    )
