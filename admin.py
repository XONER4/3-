from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from config import ADMIN_ID, BOT_PASSWORD
from models import User
from keyboards import back_keyboard, admin_panel_keyboard
from handlers import BroadcastState, AdminState, get_user, notify_user
import asyncio

admin_router = Router()

@admin_router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer("🔧 Админ-панель", reply_markup=admin_panel_keyboard())

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
    await message.answer(f"✅ Баланс пользователя {user.full_name} пополнен на {amount:.2f} ₽.", reply_markup=admin_panel_keyboard())
    await notify_user(target_id, f"💰 Администратор пополнил ваш баланс на {amount:.2f} ₽.")
    await state.clear()

# ... (аналогично исправлены остальные хендлеры админки)

@admin_router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, session: AsyncSession):
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

@admin_router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery, session: AsyncSession):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    result = await session.execute(select(User).limit(20))
    users = result.scalars().all()
    text = "👥 Пользователи:\n"
    for u in users:
        text += f"{u.full_name} (ID: {u.telegram_id}) — {u.balance:.2f} ₽, {u.rank}\n"
    await callback.message.edit_text(text, reply_markup=back_keyboard())
    await callback.answer()
