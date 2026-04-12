from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from config import ADMIN_ID
from database import get_db
from models import User, Transaction
from keyboards import admin_panel_keyboard, back_keyboard

admin_router = Router()

# Фильтр для админа
async def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

@admin_router.message(Command("admin"))
async def admin_panel(message: Message, session: AsyncSession = next(get_db())):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен.")
        return
    await message.answer("🔧 Админ-панель", reply_markup=admin_panel_keyboard())

@admin_router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, session: AsyncSession = next(get_db())):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    
    # Получаем статистику
    total_users = await session.scalar(select(func.count()).select_from(User))
    total_balance = await session.scalar(select(func.sum(User.balance)))
    
    await callback.message.edit_text(
        f"📊 Статистика бота:\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"💰 Общий баланс: {total_balance:.2f} ₽",
        reply_markup=back_keyboard()
    )
    await callback.answer()

# ... (остальные хендлеры админки: управление пользователями, рассылка, изменение настроек)
