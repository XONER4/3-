from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_ID, BOT_PASSWORD, MAIN_MENU_TEXT
from models import User
from keyboards import admin_panel_keyboard, back_keyboard
from handlers import (
    AdminState, BroadcastState, get_user, get_user_by_name, notify_user,
    custom_buttons, ALL_MEDALS, add_medal, back_to_main
)
import asyncio

admin_router = Router()

# ---------- Вспомогательная функция для возврата в админ-панель ----------
async def back_to_admin_panel(callback: CallbackQuery, state: FSMContext = None):
    if state:
        await state.clear()
    await callback.message.edit_text("🔧 Админ-панель", reply_markup=admin_panel_keyboard())

# ---------- Команда /admin ----------
@admin_router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer("🔧 Админ-панель", reply_markup=admin_panel_keyboard())

# ---------- Кнопка "Назад" в админ-панель (из любых мест) ----------
@admin_router.callback_query(F.data == "admin")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

# --- Пополнение баланса (по имени) ---
@admin_router.callback_query(F.data == "admin_add_balance")
async def admin_add_balance(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите Имя и Фамилию пользователя:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_user_id_balance)
    await callback.answer()

# Кнопка "Назад" из состояния ожидания имени для пополнения
@admin_router.callback_query(StateFilter(AdminState.waiting_for_user_id_balance), F.data == "admin")
async def back_from_balance_name(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_user_id_balance))
async def admin_balance_user_name(message: Message, state: FSMContext, session: AsyncSession):
    user = await get_user_by_name(message.text.strip(), session)
    if not user:
        await message.answer("Пользователь не найден. Попробуйте ещё раз или нажмите «Назад».")
        return
    await state.update_data(target_id=user.telegram_id)
    await message.answer(
        "Введите сумму для пополнения:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_amount_balance)

# Кнопка "Назад" из состояния ожидания суммы пополнения
@admin_router.callback_query(StateFilter(AdminState.waiting_for_amount_balance), F.data == "admin")
async def back_from_balance_amount(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

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
        await state.clear()
        return
    
    user.balance += amount
    user.total_earned += amount
    await session.commit()
    await message.answer(
        f"✅ Баланс пользователя {user.full_name} пополнен на {amount:,.0f} ₽.",
        reply_markup=admin_panel_keyboard()
    )
    await notify_user(target_id, f"💰 Администратор пополнил ваш баланс на {amount:,.0f} ₽.")
    await state.clear()

# --- Установка звания (по имени) ---
@admin_router.callback_query(F.data == "admin_set_rank")
async def admin_set_rank(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите Имя и Фамилию пользователя:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_user_id_rank)
    await callback.answer()

@admin_router.callback_query(StateFilter(AdminState.waiting_for_user_id_rank), F.data == "admin")
async def back_from_rank_name(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_user_id_rank))
async def admin_rank_user_name(message: Message, state: FSMContext, session: AsyncSession):
    user = await get_user_by_name(message.text.strip(), session)
    if not user:
        await message.answer("Пользователь не найден.")
        return
    await state.update_data(target_id=user.telegram_id)
    ranks = ["Рядовой", "Ефрейтор", "Младший сержант", "Сержант", "Старший сержант", "Лейтенант", "Старший лейтенант"]
    await message.answer(
        "Выберите звание (введите номер):\n" + "\n".join([f"{i+1}. {r}" for i, r in enumerate(ranks)]),
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_rank)

@admin_router.callback_query(StateFilter(AdminState.waiting_for_rank), F.data == "admin")
async def back_from_rank_choice(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

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
        await state.clear()
        return
    
    user.rank = new_rank
    await session.commit()
    await message.answer(
        f"✅ Звание пользователя {user.full_name} изменено на {new_rank}.",
        reply_markup=admin_panel_keyboard()
    )
    await notify_user(target_id, f"🎖 Администратор присвоил вам звание {new_rank}!")
    await state.clear()

# --- Выдача медали (по имени) ---
@admin_router.callback_query(F.data == "admin_give_medal")
async def admin_give_medal(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите Имя и Фамилию пользователя:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_medal_user_name)
    await callback.answer()

@admin_router.callback_query(StateFilter(AdminState.waiting_for_medal_user_name), F.data == "admin")
async def back_from_medal_name(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_medal_user_name))
async def admin_medal_user_name(message: Message, state: FSMContext, session: AsyncSession):
    user = await get_user_by_name(message.text.strip(), session)
    if not user:
        await message.answer("Пользователь не найден.")
        return
    await state.update_data(target_id=user.telegram_id)
    text = "Выберите медаль (введите номер):\n"
    for i, m in enumerate(ALL_MEDALS, 1):
        text += f"{i}. {m}\n"
    await message.answer(text, reply_markup=back_keyboard("admin"))
    await state.set_state(AdminState.waiting_for_medal_name)

@admin_router.callback_query(StateFilter(AdminState.waiting_for_medal_name), F.data == "admin")
async def back_from_medal_choice(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_medal_name))
async def admin_medal_set(message: Message, state: FSMContext, session: AsyncSession):
    try:
        idx = int(message.text) - 1
        medal = ALL_MEDALS[idx]
    except:
        await message.answer("Неверный номер.")
        return
    
    data = await state.get_data()
    target_id = data["target_id"]
    user = await get_user(target_id, session)
    if not user:
        await message.answer("Пользователь не найден.")
        await state.clear()
        return
    
    await add_medal(user, medal, session)
    await message.answer(
        f"✅ Медаль '{medal}' выдана пользователю {user.full_name}.",
        reply_markup=admin_panel_keyboard()
    )
    await notify_user(target_id, f"🎉 Администратор выдал вам медаль '{medal}'!")
    await state.clear()

# --- Смена имени (по имени) ---
@admin_router.callback_query(F.data == "admin_rename")
async def admin_rename(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите Имя и Фамилию пользователя:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_user_id_rename)
    await callback.answer()

@admin_router.callback_query(StateFilter(AdminState.waiting_for_user_id_rename), F.data == "admin")
async def back_from_rename_name(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_user_id_rename))
async def admin_rename_user_name(message: Message, state: FSMContext, session: AsyncSession):
    user = await get_user_by_name(message.text.strip(), session)
    if not user:
        await message.answer("Пользователь не найден.")
        return
    await state.update_data(target_id=user.telegram_id)
    await message.answer(
        "Введите новое Имя и Фамилию:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_new_name)

@admin_router.callback_query(StateFilter(AdminState.waiting_for_new_name), F.data == "admin")
async def back_from_rename_new(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_new_name))
async def admin_rename_set(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    target_id = data["target_id"]
    user = await get_user(target_id, session)
    if not user:
        await message.answer("Пользователь не найден.")
        await state.clear()
        return
    old_name = user.full_name
    user.full_name = message.text.strip()
    await session.commit()
    await message.answer(
        f"✅ Имя пользователя изменено с {old_name} на {user.full_name}.",
        reply_markup=admin_panel_keyboard()
    )
    await notify_user(target_id, f"✏️ Администратор изменил ваше имя с {old_name} на {user.full_name}.")
    await state.clear()

# --- Смена пароля ---
@admin_router.callback_query(F.data == "admin_change_password")
async def admin_change_password(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите новый пароль для бота:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_new_password)
    await callback.answer()

@admin_router.callback_query(StateFilter(AdminState.waiting_for_new_password), F.data == "admin")
async def back_from_password(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_new_password))
async def admin_password_set(message: Message, state: FSMContext):
    global BOT_PASSWORD
    new_password = message.text.strip()
    BOT_PASSWORD = new_password
    import config
    config.BOT_PASSWORD = new_password
    # Внимание: пароль изменится только в памяти, после перезапуска бота вернётся значение из config.py.
    await message.answer(
        f"✅ Пароль бота изменён на {new_password}. (Внимание: изменение не сохраняется после перезапуска)",
        reply_markup=admin_panel_keyboard()
    )
    await state.clear()

# --- Рассылка (с прогрессом) ---
@admin_router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите текст для рассылки:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(BroadcastState.waiting_for_message)
    await callback.answer()

@admin_router.callback_query(StateFilter(BroadcastState.waiting_for_message), F.data == "admin")
async def back_from_broadcast(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(BroadcastState.waiting_for_message))
async def broadcast_send(message: Message, state: FSMContext, session: AsyncSession):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text
    result = await session.execute(select(User.telegram_id))
    users = result.scalars().all()
    total = len(users)
    if total == 0:
        await message.answer("Нет пользователей для рассылки.", reply_markup=admin_panel_keyboard())
        await state.clear()
        return
    
    status_msg = await message.answer(f"📢 Рассылка начата (0/{total})...")
    from bot import bot
    count = 0
    for uid in users:
        try:
            await bot.send_message(uid, f"📢 Рассылка от администратора:\n\n{text}")
            count += 1
            if count % 10 == 0:
                await status_msg.edit_text(f"📢 Рассылка... ({count}/{total})")
        except:
            pass
        await asyncio.sleep(0.05)
    
    await status_msg.edit_text(
        f"✅ Рассылка завершена! Отправлено {count} из {total} пользователям.",
        reply_markup=admin_panel_keyboard()
    )
    await state.clear()

# --- Кастомная кнопка (автоматический callback) ---
@admin_router.callback_query(F.data == "admin_custom_button")
async def admin_custom_button(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите текст для кнопки:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_custom_button_text)
    await callback.answer()

@admin_router.callback_query(StateFilter(AdminState.waiting_for_custom_button_text), F.data == "admin")
async def back_from_custom_text(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_custom_button_text))
async def custom_button_text(message: Message, state: FSMContext):
    await state.update_data(button_text=message.text)
    await message.answer(
        "Введите текст сообщения, которое будет отправляться при нажатии:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_custom_button_callback)

@admin_router.callback_query(StateFilter(AdminState.waiting_for_custom_button_callback), F.data == "admin")
async def back_from_custom_cb(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_custom_button_callback))
async def custom_button_callback(message: Message, state: FSMContext):
    data = await state.get_data()
    text = data["button_text"]
    msg_text = message.text
    cb_data = f"custom_{len(custom_buttons)}"
    custom_buttons[cb_data] = msg_text
    
    from bot import bot
    builder = InlineKeyboardBuilder()
    builder.button(text=text, callback_data=cb_data)
    await bot.send_message(
        ADMIN_ID,
        f"✅ Кастомная кнопка создана!\nТекст: {text}\nСообщение: {msg_text}",
        reply_markup=builder.as_markup()
    )
    await message.answer("Кнопка добавлена в админ-чат.", reply_markup=admin_panel_keyboard())
    await state.clear()

# --- Изменить текст главного меню ---
@admin_router.callback_query(F.data == "admin_change_main_text")
async def admin_change_main_text(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите новый текст главного меню (можно использовать {name} и {date}):",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_main_menu_text)
    await callback.answer()

@admin_router.callback_query(StateFilter(AdminState.waiting_for_main_menu_text), F.data == "admin")
async def back_from_main_text(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_main_menu_text))
async def set_main_menu_text(message: Message, state: FSMContext):
    global MAIN_MENU_TEXT
    new_text = message.text
    MAIN_MENU_TEXT = new_text
    import config
    config.MAIN_MENU_TEXT = new_text
    # Внимание: изменение только в памяти, после перезапуска вернётся значение из config.py.
    await message.answer(
        "✅ Текст главного меню обновлён. (Внимание: изменение не сохраняется после перезапуска)",
        reply_markup=admin_panel_keyboard()
    )
    await state.clear()

# --- Войти в общее меню ---
@admin_router.callback_query(F.data == "admin_enter_main")
async def admin_enter_main(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    # Используем исправленную функцию back_to_main из handlers
    await back_to_main(callback, state, session)
    await callback.answer()

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
