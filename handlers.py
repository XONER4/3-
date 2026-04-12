import json
import random
import asyncio
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, update, delete, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import BOT_PASSWORD, START_BALANCE, DAILY_BONUS, CREDIT_PERCENT, CREDIT_MAX_DAYS, ADMIN_ID
from database import get_db
from models import User, Transaction, CasinoGame, IQResult
from keyboards import *
from utils import check_rank_upgrade, add_medal, calculate_deposit_payout, get_rank_conditions

router = Router()

# ---------- FSM Состояния ----------
class AuthState(StatesGroup):
    waiting_for_password = State()

class CasinoState(StatesGroup):
    waiting_for_bet = State()
    waiting_for_guess = State()

class IQState(StatesGroup):
    answering = State()

class CreditState(StatesGroup):
    waiting_for_amount = State()

class DepositState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_days = State()

class TransferState(StatesGroup):
    waiting_for_recipient_id = State()
    waiting_for_amount = State()

class ShopState(StatesGroup):
    choosing_category = State()
    choosing_item = State()
    choosing_action = State()
    choosing_recipient = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

# ---------- Вспомогательные функции ----------
async def get_user(user_id: int, session: AsyncSession) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == user_id))
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
    await add_transaction(session, user.id, amount, type_, description)
    await session.commit()
    await check_rank_upgrade(user, session)

# ---------- Обработчик команды /start ----------
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession = next(get_db())):
    user_id = message.from_user.id
    user = await get_user(user_id, session)
    
    if not user:
        user = User(
            telegram_id=user_id,
            full_name=message.from_user.full_name or "Не указано",
            balance=START_BALANCE,
            is_authorized=False,
            rank="Рядовой",
            medals="[]",
            max_balance_achieved=START_BALANCE,
            has_taken_credit=False,
            has_made_deposit=False,
            gifts_sent=0,
            purchases="[]"
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
            "👋 С возвращением! Вы в главном меню.",
            reply_markup=main_menu()
        )

# ---------- Авторизация ----------
@router.message(AuthState.waiting_for_password, F.text)
async def process_password(message: Message, state: FSMContext, session: AsyncSession = next(get_db())):
    if message.text == BOT_PASSWORD:
        user = await get_user(message.from_user.id, session)
        user.is_authorized = True
        await session.commit()
        await message.answer(
            "✅ Пароль верный! Добро пожаловать в семейный бот.",
            reply_markup=main_menu()
        )
        await state.clear()
    else:
        await message.answer("❌ Неверный пароль. Попробуйте ещё раз.")

# ---------- Главное меню (колбэки) ----------
@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🏠 Главное меню", reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "balance")
async def show_balance(callback: CallbackQuery, session: AsyncSession = next(get_db())):
    user = await get_user(callback.from_user.id, session)
    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    await callback.message.edit_text(
        f"💰 Ваш текущий баланс: {user.balance:.2f} ₽",
        reply_markup=back_keyboard()
    )
    await callback.answer()

# ---------- Ежедневный бонус ----------
@router.callback_query(F.data == "daily_bonus")
async def daily_bonus(callback: CallbackQuery, session: AsyncSession = next(get_db())):
    user = await get_user(callback.from_user.id, session)
    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    
    now = datetime.now()
    if user.last_bonus and user.last_bonus.date() == now.date():
        await callback.answer("Вы уже получали бонус сегодня.", show_alert=True)
        return
    
    user.balance += DAILY_BONUS
    user.last_bonus = now
    await session.commit()
    await add_transaction(session, user.id, DAILY_BONUS, "daily_bonus", "Ежедневный бонус")
    await check_rank_upgrade(user, session)
    
    await callback.message.edit_text(
        f"🎁 Вы получили ежедневный бонус {DAILY_BONUS} ₽!\n"
        f"💰 Ваш новый баланс: {user.balance:.2f} ₽",
        reply_markup=back_keyboard()
    )
    await callback.answer()

# ---------- Казино ----------
@router.callback_query(F.data == "casino_menu")
async def casino_menu(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🎰 Выберите сумму ставки:",
        reply_markup=casino_bet_keyboard()
    )
    await state.set_state(CasinoState.waiting_for_bet)
    await callback.answer()

@router.callback_query(CasinoState.waiting_for_bet, F.data.startswith("bet_"))
async def casino_set_bet(callback: CallbackQuery, state: FSMContext):
    data = callback.data
    if data == "bet_custom":
        await callback.message.edit_text("Введите свою сумму ставки (целое число):")
        await state.set_state(CasinoState.waiting_for_bet)
        await callback.answer()
        return
    
    bet_amount = int(data.split("_")[1])
    await state.update_data(bet=bet_amount)
    await callback.message.edit_text(
        f"🎲 Ставка: {bet_amount} ₽\nВыберите число от 1 до 6:",
        reply_markup=casino_guess_keyboard()
    )
    await state.set_state(CasinoState.waiting_for_guess)
    await callback.answer()

@router.message(CasinoState.waiting_for_bet, F.text.isdigit())
async def casino_custom_bet(message: Message, state: FSMContext):
    bet_amount = int(message.text)
    if bet_amount <= 0:
        await message.answer("Ставка должна быть больше 0. Попробуйте ещё раз.")
        return
    await state.update_data(bet=bet_amount)
    await message.answer(
        f"🎲 Ставка: {bet_amount} ₽\nВыберите число от 1 до 6:",
        reply_markup=casino_guess_keyboard()
    )
    await state.set_state(CasinoState.waiting_for_guess)

@router.callback_query(CasinoState.waiting_for_guess, F.data.startswith("guess_"))
async def casino_play(callback: CallbackQuery, state: FSMContext, session: AsyncSession = next(get_db())):
    user = await get_user(callback.from_user.id, session)
    data = await state.get_data()
    bet = data.get("bet")
    guess = int(callback.data.split("_")[1])
    
    if user.balance < bet:
        await callback.answer("❌ Недостаточно средств на балансе!", show_alert=True)
        await state.clear()
        await callback.message.edit_text("🏠 Главное меню", reply_markup=main_menu())
        return
    
    actual = random.randint(1, 6)
    won = guess == actual
    if won:
        payout = bet * 6
        await update_balance(user, payout - bet, session, "casino_win", f"Выигрыш в казино (ставка {bet})")
        result_text = f"🎉 Поздравляем! Выпало {actual}. Вы выиграли {payout} ₽!"
    else:
        await update_balance(user, -bet, session, "casino_loss", f"Проигрыш в казино (ставка {bet})")
        result_text = f"😢 Увы, выпало {actual}. Вы проиграли {bet} ₽."
    
    # Запись игры
    game = CasinoGame(
        user_id=user.id,
        bet_amount=bet,
        guessed_number=guess,
        actual_number=actual,
        won=won,
        payout=payout if won else 0
    )
    session.add(game)
    await session.commit()
    
    await callback.message.edit_text(
        f"{result_text}\n💰 Ваш баланс: {user.balance:.2f} ₽",
        reply_markup=back_keyboard()
    )
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "back_to_casino")
async def back_to_casino(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await casino_menu(callback, state)

# ---------- Тест IQ ----------
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

@router.callback_query(F.data == "iq_test")
async def iq_test_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession = next(get_db())):
    user = await get_user(callback.from_user.id, session)
    if user.balance < 1000:
        await callback.answer("Для прохождения теста нужно минимум 1000 ₽ на балансе!", show_alert=True)
        return
    
    await state.update_data(iq_answers=[], iq_index=0)
    await send_iq_question(callback.message, state, 0)
    await state.set_state(IQState.answering)
    await callback.answer()

async def send_iq_question(message: Message, state: FSMContext, index: int):
    q = IQ_QUESTIONS[index]
    builder = InlineKeyboardBuilder()
    for i, opt in enumerate(q["o"]):
        builder.button(text=opt, callback_data=f"iq_ans_{index}_{i}")
    builder.adjust(1)
    await message.edit_text(
        f"🧠 Вопрос {index+1}/15:\n{q['q']}",
        reply_markup=builder.as_markup()
    )

@router.callback_query(IQState.answering, F.data.startswith("iq_ans_"))
async def iq_answer(callback: CallbackQuery, state: FSMContext):
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
        # Завершение теста
        await finish_iq_test(callback, state, answers)
    await callback.answer()

async def finish_iq_test(callback: CallbackQuery, state: FSMContext, answers: list):
    session = next(get_db())
    user = await get_user(callback.from_user.id, session)
    correct = sum(answers)
    total = len(answers)
    
    medal = ""
    bonus = 0
    if correct == 15:
        medal = "ОТЛИЧНИК IQ"
        bonus = 5000
    elif correct >= 9:
        medal = "ХОРОШИСТ IQ"
        bonus = 2500
    elif correct >= 5:
        medal = "СРЕДНЯЧОК IQ"
        bonus = 1000
    else:
        medal = "ТЯЖЕЛЫЙ IQ"
        bonus = -1000
    
    await update_balance(user, bonus, session, "iq_bonus", f"Тест IQ: {correct}/{total}")
    if medal:
        await add_medal(user, medal, session)
    
    iq_result = IQResult(
        user_id=user.id,
        correct_answers=correct,
        medal=medal,
        bonus=bonus
    )
    session.add(iq_result)
    await session.commit()
    
    text = f"🧠 Тест завершён!\nПравильных ответов: {correct} из {total}\n"
    text += f"Медаль: {medal}\n"
    text += f"Изменение баланса: {bonus:+.0f} ₽\n"
    text += f"💰 Текущий баланс: {user.balance:.2f} ₽"
    
    await callback.message.edit_text(text, reply_markup=back_keyboard())
    await state.clear()

# ---------- Кредит ----------
@router.callback_query(F.data == "credit_menu")
async def credit_menu(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📋 Кредит", reply_markup=credit_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data == "take_credit")
async def take_credit_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession = next(get_db())):
    user = await get_user(callback.from_user.id, session)
    if user.credit_amount > 0:
        await callback.answer("У вас уже есть непогашенный кредит!", show_alert=True)
        return
    
    max_credit = user.balance * 10
    await callback.message.edit_text(
        f"💰 Ваш баланс: {user.balance:.2f} ₽\n"
        f"Максимальная сумма кредита: {max_credit:.2f} ₽ (10% ставка)\n"
        f"Введите желаемую сумму (не более {max_credit:.2f}):",
        reply_markup=back_keyboard()
    )
    await state.set_state(CreditState.waiting_for_amount)
    await state.update_data(max_credit=max_credit)
    await callback.answer()

@router.message(CreditState.waiting_for_amount, F.text)
async def credit_amount_input(message: Message, state: FSMContext, session: AsyncSession = next(get_db())):
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("Пожалуйста, введите число.")
        return
    
    data = await state.get_data()
    max_credit = data["max_credit"]
    if amount <= 0 or amount > max_credit:
        await message.answer(f"Сумма должна быть от 1 до {max_credit:.2f} ₽.")
        return
    
    user = await get_user(message.from_user.id, session)
    due_date = datetime.now() + timedelta(days=CREDIT_MAX_DAYS)
    total_repay = amount * (1 + CREDIT_PERCENT / 100)
    
    user.credit_amount = total_repay
    user.credit_due_date = due_date
    user.has_taken_credit = True
    user.balance += amount
    await session.commit()
    await add_transaction(session, user.id, amount, "credit", f"Получен кредит {amount:.2f} ₽")
    
    await message.answer(
        f"✅ Кредит одобрен!\n"
        f"Получено: {amount:.2f} ₽\n"
        f"К возврату: {total_repay:.2f} ₽ (срок до {due_date.strftime('%d.%m.%Y')})",
        reply_markup=main_menu()
    )
    await state.clear()

# ---------- Вклад ----------
@router.callback_query(F.data == "deposit_menu")
async def deposit_menu(callback: CallbackQuery):
    await callback.message.edit_text("🏦 Вклад", reply_markup=deposit_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data == "open_deposit")
async def deposit_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession = next(get_db())):
    user = await get_user(callback.from_user.id, session)
    if user.deposit_amount > 0:
        await callback.answer("У вас уже открыт вклад!", show_alert=True)
        return
    
    await callback.message.edit_text("Введите сумму вклада:")
    await state.set_state(DepositState.waiting_for_amount)
    await callback.answer()

@router.message(DepositState.waiting_for_amount, F.text)
async def deposit_amount(message: Message, state: FSMContext, session: AsyncSession = next(get_db())):
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

@router.message(DepositState.waiting_for_days, F.text)
async def deposit_days(message: Message, state: FSMContext, session: AsyncSession = next(get_db())):
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
    await session.commit()
    await add_transaction(session, user.id, -amount, "deposit", f"Открыт вклад {amount:.2f} ₽ на {days} дн.")
    
    payout = calculate_deposit_payout(amount, days)
    await message.answer(
        f"✅ Вклад открыт!\nСумма: {amount:.2f} ₽\nСрок: {days} дн.\n"
        f"К получению: {payout:.2f} ₽ (через {days} дн.)",
        reply_markup=main_menu()
    )
    await state.clear()

# ---------- Переводы ----------
@router.callback_query(F.data == "transfer")
async def transfer_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите Telegram ID получателя (можно узнать в профиле):",
        reply_markup=back_keyboard()
    )
    await state.set_state(TransferState.waiting_for_recipient_id)
    await callback.answer()

@router.message(TransferState.waiting_for_recipient_id, F.text)
async def transfer_recipient(message: Message, state: FSMContext, session: AsyncSession = next(get_db())):
    try:
        recip_id = int(message.text)
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    
    recip = await get_user(recip_id, session)
    if not recip:
        await message.answer("Пользователь с таким ID не найден в боте.")
        return
    
    await state.update_data(recip_id=recip_id, recip_name=recip.full_name)
    await message.answer(f"Получатель: {recip.full_name}\nВведите сумму перевода:")
    await state.set_state(TransferState.waiting_for_amount)

@router.message(TransferState.waiting_for_amount, F.text)
async def transfer_amount(message: Message, state: FSMContext, session: AsyncSession = next(get_db())):
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
    await session.commit()
    await add_transaction(session, user.id, -amount, "transfer_out", f"Перевод пользователю {recip_name}")
    await add_transaction(session, recip.id, amount, "transfer_in", f"Получено от {user.full_name}")
    
    await message.answer(
        f"✅ Перевод выполнен!\nПолучатель: {recip_name}\nСумма: {amount:.2f} ₽",
        reply_markup=main_menu()
    )
    
    # Уведомление получателю
    from bot import bot
    try:
        await bot.send_message(
            recip.telegram_id,
            f"💰 Вам поступил перевод {amount:.2f} ₽ от {user.full_name}"
        )
    except:
        pass
    
    await state.clear()

# ---------- Профиль (личное дело) ----------
@router.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery, session: AsyncSession = next(get_db())):
    user = await get_user(callback.from_user.id, session)
    medals = json.loads(user.medals) if user.medals else []
    purchases = json.loads(user.purchases) if user.purchases else []
    
    text = f"📋 Личное дело\n"
    text += f"👤 ФИО: {user.full_name}\n"
    text += f"🆔 ID: {user.telegram_id}\n"
    text += f"💰 Баланс: {user.balance:.2f} ₽\n"
    text += f"🎖 Звание: {user.rank}\n"
    text += f"🏅 Медали: {', '.join(medals) if medals else 'нет'}\n"
    if purchases:
        text += f"🛒 Покупки: {', '.join(purchases)}\n"
    text += f"📅 В боте с: {user.registered_at.strftime('%d.%m.%Y')}"
    
    await callback.message.edit_text(text, reply_markup=back_keyboard())
    await callback.answer()

# ---------- Новости ----------
@router.callback_query(F.data == "news")
async def news(callback: CallbackQuery, session: AsyncSession = next(get_db())):
    # Последние 10 транзакций/событий
    result = await session.execute(
        select(Transaction).options(selectinload(Transaction.user)).order_by(desc(Transaction.timestamp)).limit(10)
    )
    trans = result.scalars().all()
    
    text = "📰 Последние события:\n"
    for t in trans:
        user_name = t.user.full_name if t.user else "Неизвестный"
        text += f"{t.timestamp.strftime('%H:%M')} — {user_name}: {t.description or t.type} ({t.amount:+.2f} ₽)\n"
    
    await callback.message.edit_text(text, reply_markup=back_keyboard())
    await callback.answer()

# ---------- Медали (информация) ----------
@router.callback_query(F.data == "medals_info")
async def medals_info(callback: CallbackQuery):
    text = (
        "🎖 Медали и условия получения:\n"
        "• ОТЛИЧНИК IQ — 15/15 в тесте IQ\n"
        "• ХОРОШИСТ IQ — 9-14 правильных\n"
        "• СРЕДНЯЧОК IQ — 5-8 правильных\n"
        "• ТЯЖЕЛЫЙ IQ — меньше 5 правильных\n"
        "• ЩЕДРЫЙ — отправить 5 подарков\n"
    )
    text += "\n" + get_rank_conditions()
    await callback.message.edit_text(text, reply_markup=back_keyboard())
    await callback.answer()

# ---------- Помощь ----------
@router.callback_query(F.data == "help")
async def help_cmd(callback: CallbackQuery):
    text = (
        "❓ Помощь по боту:\n"
        "• Баланс — просмотр средств\n"
        "• Казино — угадай число от 1 до 6, выигрыш x6\n"
        "• Тест IQ — 15 вопросов, награды и медали\n"
        "• Кредит — до x10 от баланса, на 3 дня, 10%\n"
        "• Вклад — 20% в день, от 1 до 3 дней\n"
        "• Магазин — авто и цветы, можно дарить\n"
        "• Личное дело — ваша статистика\n"
        "• Новости — последние события\n"
        "• Перевод — отправка денег другим участникам"
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard())
    await callback.answer()

# ---------- Магазин (базовая структура) ----------
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

@router.callback_query(F.data == "shop_menu")
async def shop_menu(callback: CallbackQuery):
    await callback.message.edit_text("🛍 Магазин", reply_markup=shop_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data.in_(["shop_cars", "shop_flowers"]))
async def shop_category(callback: CallbackQuery, state: FSMContext):
    cat = "cars" if callback.data == "shop_cars" else "flowers"
    items = SHOP_ITEMS[cat]
    builder = InlineKeyboardBuilder()
    for i, item in enumerate(items):
        builder.button(text=f"{item['name']} — {item['price']} ₽", callback_data=f"buy_{cat}_{i}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="shop_menu"))
    await callback.message.edit_text(f"Выберите товар:", reply_markup=builder.as_markup())
    await state.set_state(ShopState.choosing_item)
    await state.update_data(category=cat)
    await callback.answer()

@router.callback_query(ShopState.choosing_item, F.data.startswith("buy_"))
async def shop_choose_action(callback: CallbackQuery, state: FSMContext):
    _, cat, idx = callback.data.split("_")
    idx = int(idx)
    item = SHOP_ITEMS[cat][idx]
    await state.update_data(item=item)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="Купить себе", callback_data="action_self")
    builder.button(text="Подарить", callback_data="action_gift")
    builder.button(text="🔙 Назад", callback_data=f"shop_{cat}")
    await callback.message.edit_text(
        f"Товар: {item['name']}\nЦена: {item['price']} ₽\nВыберите действие:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(ShopState.choosing_action)
    await callback.answer()

@router.callback_query(ShopState.choosing_action, F.data.startswith("action_"))
async def shop_action(callback: CallbackQuery, state: FSMContext, session: AsyncSession = next(get_db())):
    action = callback.data.split("_")[1]
    data = await state.get_data()
    item = data["item"]
    user = await get_user(callback.from_user.id, session)
    
    if user.balance < item["price"]:
        await callback.answer("Недостаточно средств!", show_alert=True)
        return
    
    if action == "self":
        # Покупка себе
        user.balance -= item["price"]
        purchases = json.loads(user.purchases) if user.purchases else []
        purchases.append(item["name"])
        user.purchases = json.dumps(purchases)
        await session.commit()
        await add_transaction(session, user.id, -item["price"], "shop_purchase", f"Покупка {item['name']}")
        await callback.message.edit_text(
            f"✅ Вы купили {item['name']} за {item['price']} ₽!",
            reply_markup=back_keyboard()
        )
    else:
        # Подарок
        await callback.message.edit_text("Введите Telegram ID получателя:")
        await state.set_state(ShopState.choosing_recipient)
        await state.update_data(item=item)
        await callback.answer()
        return
    
    await state.clear()
    await callback.answer()

@router.message(ShopState.choosing_recipient, F.text)
async def shop_gift(message: Message, state: FSMContext, session: AsyncSession = next(get_db())):
    try:
        recip_id = int(message.text)
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    
    recip = await get_user(recip_id, session)
    if not recip:
        await message.answer("Пользователь не найден.")
        return
    
    data = await state.get_data()
    item = data["item"]
    user = await get_user(message.from_user.id, session)
    
    user.balance -= item["price"]
    user.gifts_sent += 1
    # Добавляем получателю в покупки (подарок)
    purchases = json.loads(recip.purchases) if recip.purchases else []
    purchases.append(f"{item['name']} (подарок от {user.full_name})")
    recip.purchases = json.dumps(purchases)
    
    if user.gifts_sent >= 5:
        await add_medal(user, "ЩЕДРЫЙ", session)
    
    await session.commit()
    await add_transaction(session, user.id, -item["price"], "gift_sent", f"Подарок {item['name']} для {recip.full_name}")
    
    await message.answer(
        f"✅ Вы подарили {item['name']} пользователю {recip.full_name}!",
        reply_markup=main_menu()
    )
    # Уведомление
    from bot import bot
    try:
        await bot.send_message(
            recip.telegram_id,
            f"🎁 {user.full_name} подарил вам {item['name']}!"
        )
    except:
        pass
    
    await state.clear()

# ---------- Админ-панель (частично здесь, остальное в admin.py) ----------
@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, session: AsyncSession = next(get_db())):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    total_users = await session.scalar(select(func.count()).select_from(User))
    total_balance = await session.scalar(select(func.sum(User.balance)))
    await callback.message.edit_text(
        f"📊 Статистика:\n👥 Пользователей: {total_users}\n💰 Общий баланс: {total_balance:.2f} ₽",
        reply_markup=back_keyboard()
    )
    await callback.answer()
