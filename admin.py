from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from config import ADMIN_ID, BOT_PASSWORD, MAIN_MENU_TEXT
from models import User
from keyboards import admin_panel_keyboard, back_keyboard
from handlers import AdminState, BroadcastState, get_user, get_user_by_name, notify_user, custom_buttons, ALL_MEDALS, add_medal
import asyncio

admin_router = Router()

@admin_router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer("🔧 Админ-панель", reply_markup=admin_panel_keyboard())

# --- Пополнение баланса (по имени) ---
@admin_router.callback_query(F.data == "admin_add_balance")
async def admin_add_balance(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите Имя и Фамилию пользователя:")
    await state.set_state(AdminState.waiting_for_user_id_balance)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_user_id_balance))
async def admin_balance_user_name(message: Message, state: FSMContext):
    user = await get_user_by_name(message.text.strip(), next(get_db()))
    if not user:
        await message.answer("Пользователь не найден.")
        return
    await state.update_data(target_id=user.telegram_id)
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

# --- Установка звания (по имени) ---
@admin_router.callback_query(F.data == "admin_set_rank")
async def admin_set_rank(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите Имя и Фамилию пользователя:")
    await state.set_state(AdminState.waiting_for_user_id_rank)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_user_id_rank))
async def admin_rank_user_name(message: Message, state: FSMContext):
    user = await get_user_by_name(message.text.strip(), next(get_db()))
    if not user:
        await message.answer("Пользователь не найден.")
        return
    await state.update_data(target_id=user.telegram_id)
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

# --- Выдача медали (по имени) ---
@admin_router.callback_query(F.data == "admin_give_medal")
async def admin_give_medal(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите Имя и Фамилию пользователя:")
    await state.set_state(AdminState.waiting_for_medal_user_name)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_medal_user_name))
async def admin_medal_user_name(message: Message, state: FSMContext):
    user = await get_user_by_name(message.text.strip(), next(get_db()))
    if not user:
        await message.answer("Пользователь не найден.")
        return
    await state.update_data(target_id=user.telegram_id)
    text = "Выберите медаль (введите номер):\n"
    for i, m in enumerate(ALL_MEDALS, 1):
        text += f"{i}. {m}\n"
    await message.answer(text)
    await state.set_state(AdminState.waiting_for_medal_name)

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
        return
    
    await add_medal(user, medal, session)
    await message.answer(f"✅ Медаль '{medal}' выдана пользователю {user.full_name}.", reply_markup=admin_panel_keyboard())
    await notify_user(target_id, f"🎉 Администратор выдал вам медаль '{medal}'!")
    await state.clear()

# --- Смена имени (по имени) ---
@admin_router.callback_query(F.data == "admin_rename")
async def admin_rename(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите Имя и Фамилию пользователя:")
    await state.set_state(AdminState.waiting_for_user_id_rename)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_user_id_rename))
async def admin_rename_user_name(message: Message, state: FSMContext):
    user = await get_user_by_name(message.text.strip(), next(get_db()))
    if not user:
        await message.answer("Пользователь не найден.")
        return
    await state.update_data(target_id=user.telegram_id)
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

# --- Рассылка (с прогрессом) ---
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
    
    await status_msg.edit_text(f"✅ Рассылка завершена! Отправлено {count} из {total} пользователям.", reply_markup=admin_panel_keyboard())
    await state.clear()

# --- Кастомная кнопка (автоматический callback) ---
@admin_router.callback_query(F.data == "admin_custom_button")
async def admin_custom_button(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите текст для кнопки:")
    await state.set_state(AdminState.waiting_for_custom_button_text)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_custom_button_text))
async def custom_button_text(message: Message, state: FSMContext):
    await state.update_data(button_text=message.text)
    await message.answer("Введите текст сообщения, которое будет отправляться при нажатии:")
    await state.set_state(AdminState.waiting_for_custom_button_callback)

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
    await callback.message.edit_text("Введите новый текст главного меню (можно использовать {name} и {date}):")
    await state.set_state(AdminState.waiting_for_main_menu_text)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_main_menu_text))
async def set_main_menu_text(message: Message, state: FSMContext):
    global MAIN_MENU_TEXT
    MAIN_MENU_TEXT = message.text
    import config
    config.MAIN_MENU_TEXT = MAIN_MENU_TEXT
    await message.answer("✅ Текст главного меню обновлён.", reply_markup=admin_panel_keyboard())
    await state.clear()

# --- Войти в общее меню ---
@admin_router.callback_query(F.data == "admin_enter_main")
async def admin_enter_main(callback: CallbackQuery):
    from handlers import back_to_main
    await back_to_main(callback, FSMContext)

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
