from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from config import ADMIN_ID
from models import User
from keyboards import back_keyboard, admin_panel_keyboard
from handlers import BroadcastState
import asyncio

admin_router = Router()

@admin_router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer("🔧 Админ-панель", reply_markup=admin_panel_keyboard())

@admin_router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery, session: AsyncSession):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    result = await session.execute(select(User).limit(10))
    users = result.scalars().all()
    text = "👥 Последние 10 пользователей:\n"
    for u in users:
        text += f"{u.full_name} (ID: {u.telegram_id}) — {u.balance:.2f} ₽\n"
    await callback.message.edit_text(text, reply_markup=back_keyboard())
    await callback.answer()

@admin_router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Введите текст для рассылки:")
    await state.set_state(BroadcastState.waiting_for_message)
    await callback.answer()

@admin_router.message(BroadcastState.waiting_for_message)
async def broadcast_send(message: Message, state: FSMContext, session: AsyncSession):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text
    result = await session.execute(select(User.telegram_id))
    users = result.scalars().all()
    from bot import bot
    count = 0
    for uid in users:
        try:
            await bot.send_message(uid, f"📢 Рассылка:\n{text}")
            count += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await message.answer(f"✅ Рассылка отправлена {count} пользователям.", reply_markup=admin_panel_keyboard())
    await state.clear()

@admin_router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery):
    await callback.message.edit_text("Настройки бота (в разработке)", reply_markup=back_keyboard())
    await callback.answer()
