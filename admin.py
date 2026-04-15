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
    await callback.message.edit_text("Введите Telegram ID пользователя:")
    await state.set_state(AdminState.waiting_for_user_id_rename)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_user_id_rename))
async def admin_rename_user_id(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    await state.update_data(target_id=user_id)
    await message.answer("Введите новое Имя и Фамилию:")
    await state.set_state(AdminState.waiting_for_new_name)

@admin_router.message(StateFilter(AdminState.waiting_for_new_name))
async def admin_rename_set(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    target_id = data["target_id"]
    user = await get_user(target_id, session)
    if not user:
        await message.answer("Пользователь не найден.")
        return
    old_name = user.full_name
    user.full_name = message.text.strip()
    await session.commit()
    await message.answer(f"✅ Имя пользователя изменено с {old_name} на {user.full_name}.", reply_markup=admin_panel_keyboard())
    await notify_user(target_id, f"✏️ Администратор изменил ваше имя с {old_name} на {user.full_name}.")
    await state.clear()

# --- Смена пароля ---
@admin_router.callback_query(F.data == "admin_change_password")
async def admin_change_password(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите новый пароль для бота:")
    await state.set_state(AdminState.waiting_for_new_password)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_new_password))
async def admin_password_set(message: Message, state: FSMContext):
    global BOT_PASSWORD
    BOT_PASSWORD = message.text.strip()
    import config
    config.BOT_PASSWORD = BOT_PASSWORD
    await message.answer(f"✅ Пароль бота изменён на {BOT_PASSWORD}.", reply_markup=admin_panel_keyboard())
    await state.clear()

# --- Рассылка (исправлено) ---
@admin_router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите текст для рассылки:")
    await state.set_state(BroadcastState.waiting_for_message)
    await callback.answer()

@admin_router.message(StateFilter(BroadcastState.waiting_for_message))
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
            await bot.send_message(uid, f"📢 Рассылка от администратора:\n\n{text}")
            count += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await message.answer(f"✅ Рассылка отправлена {count} пользователям.", reply_markup=admin_panel_keyboard())
    await state.clear()

# --- Создание кастомной кнопки (упрощённо: вводится текст и callback_data) ---
@admin_router.callback_query(F.data == "admin_custom_button")
async def admin_custom_button(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите текст для кнопки:")
    await state.set_state(AdminState.waiting_for_custom_button_text)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_custom_button_text))
async def custom_button_text(message: Message, state: FSMContext):
    await state.update_data(button_text=message.text)
    await message.answer("Введите callback_data для кнопки (например: my_custom_action):")
    await state.set_state(AdminState.waiting_for_custom_button_callback)

@admin_router.message(StateFilter(AdminState.waiting_for_custom_button_callback))
async def custom_button_callback(message: Message, state: FSMContext):
    data = await state.get_data()
    text = data["button_text"]
    cb_data = message.text
    # Сохраняем в глобальную переменную или файл (упростим: отправим сообщение с кнопкой)
    from bot import bot
    builder = InlineKeyboardBuilder()
    builder.button(text=text, callback_data=cb_data)
    await bot.send_message(
        ADMIN_ID,
        f"Создана кастомная кнопка:\nТекст: {text}\nCallback: {cb_data}",
        reply_markup=builder.as_markup()
    )
    await message.answer("✅ Кастомная кнопка создана (отправлена вам в ЛС).", reply_markup=admin_panel_keyboard())
    await state.clear()

# --- Статистика и пользователи ---
@admin_router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, session: AsyncSession):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    total_users = await session.scalar(select(func.count()).select_from(User))
    total_balance = await session.scalar(select(func.sum(User.balance)))
    await callback.message.edit_text(
        f"📊 Статистика:\n👥 Пользователей: {total_users}\n💰 Общий баланс: {total_balance:,.0f} ₽",
        reply_markup=back_keyboard("admin")
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
        text += f"{u.full_name} (ID: {u.telegram_id}) — {u.balance:,.0f} ₽, {u.rank}\n"
    await callback.message.edit_text(text, reply_markup=back_keyboard("admin"))
    await callback.answer()

@admin_router.callback_query(F.data == "admin")
async def back_to_admin(callback: CallbackQuery):
    await callback.message.edit_text("🔧 Админ-панель", reply_markup=admin_panel_keyboard())
    await callback.answer()
