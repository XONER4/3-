from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from config import ADMIN_ID, BOT_PASSWORD
from models import User
from keyboards import admin_panel_keyboard, back_keyboard
from handlers import AdminState, BroadcastState, get_user, notify_user
import asyncio

admin_router = Router()

@admin_router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer("🔧 Админ-панель", reply_markup=admin_panel_keyboard())

# --- Пополнение баланса ---
@admin_router.callback_query(F.data == "admin_add_balance")
async def admin_add_balance(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите Telegram ID пользователя:")
    await state.set_state(AdminState.waiting_for_user_id_balance)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_user_id_balance))
async def admin_balance_user_id(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    await state.update_data(target_id=user_id)
    await message.answer("Введите сумму для пополнения:")
    await state.set_state(AdminState.waiting_for_amount_balance)

@admin_router.message(StateFilter(AdminState.waiting_for_amount_balance))
async def admin_balance_amount(message: Message, state: FSMContext, session: AsyncSession):
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("Введите число.")
        return
    
    data = await state.get_data()
    target_id = data["target_id"]
    user = await get_user(target_id, session)
    if not user:
        await message.answer("Пользователь не найден.")
        return
    
    user.balance += amount
    user.total_earned += amount
    await session.commit()
    await message.answer(f"✅ Баланс пользователя {user.full_name} пополнен на {amount:,.0f} ₽.", reply_markup=admin_panel_keyboard())
    await notify_user(target_id, f"💰 Администратор пополнил ваш баланс на {amount:,.0f} ₽.")
    await state.clear()

# --- Установка звания ---
@admin_router.callback_query(F.data == "admin_set_rank")
async def admin_set_rank(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите Telegram ID пользователя:")
    await state.set_state(AdminState.waiting_for_user_id_rank)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_user_id_rank))
async def admin_rank_user_id(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    await state.update_data(target_id=user_id)
    ranks = ["Рядовой", "Ефрейтор", "Младший сержант", "Сержант", "Старший сержант", "Лейтенант", "Старший лейтенант"]
    await message.answer("Выберите звание (введите номер):\n" + "\n".join([f"{i+1}. {r}" for i, r in enumerate(ranks)]))
    await state.set_state(AdminState.waiting_for_rank)

@admin_router.message(StateFilter(AdminState.waiting_for_rank))
async def admin_rank_set(message: Message, state: FSMContext, session: AsyncSession):
    try:
        idx = int(message.text) - 1
        ranks = ["Рядовой", "Ефрейтор", "Младший сержант", "Сержант", "Старший сержант", "Лейтенант", "Старший лейтенант"]
        new_rank = ranks[idx]
    except:
        await message.answer("Неверный номер.")
        return
    
    data = await state.get_data()
    target_id = data["target_id"]
    user = await get_user(target_id, session)
    if not user:
        await message.answer("Пользователь не найден.")
        return
    
    user.rank = new_rank
    await session.commit()
    await message.answer(f"✅ Звание пользователя {user.full_name} изменено на {new_rank}.", reply_markup=admin_panel_keyboard())
    await notify_user(target_id, f"🎖 Администратор присвоил вам звание {new_rank}!")
    await state.clear()

# --- Смена имени ---
@admin_router.callback_query(F.data == "admin_rename")
async def admin_rename(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите Telegram ID
