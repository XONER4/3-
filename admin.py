from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_ID, BOT_PASSWORD, MAIN_MENU_TEXT, TIMEZONE_OFFSET, NEWS_CHANNEL_ID
from models import User
from keyboards import admin_panel_keyboard, back_keyboard
from handlers import (
    AdminState, BroadcastState, get_user, get_user_by_name,
    custom_buttons, ALL_MEDALS, back_to_main, send_news_to_channel
)
from utils import notify_user, add_medal

import asyncio
from datetime import datetime, timedelta

admin_router = Router()

# ---------- Вспомогательная функция для возврата в админ-панель ----------
async def back_to_admin_panel(callback: CallbackQuery, state: FSMContext = None):
    if state:
        await state.clear()
    await callback.message.edit_text("🔧 АДМИН-ПАНЕЛЬ", reply_markup=admin_panel_keyboard())

# ---------- Команда /admin ----------
@admin_router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ ДОСТУП ЗАПРЕЩЁН.")
        return
    await message.answer("🔧 АДМИН-ПАНЕЛЬ", reply_markup=admin_panel_keyboard())

# ---------- Кнопка "Назад" в админ-панель ----------
@admin_router.callback_query(F.data == "admin")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

# --- Пополнение баланса (по имени) ---
@admin_router.callback_query(F.data == "admin_add_balance")
async def admin_add_balance(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "ВВЕДИТЕ ИМЯ И ФАМИЛИЮ ПОЛЬЗОВАТЕЛЯ:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_user_id_balance)
    await callback.answer()

@admin_router.callback_query(StateFilter(AdminState.waiting_for_user_id_balance), F.data == "admin")
async def back_from_balance_name(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_user_id_balance))
async def admin_balance_user_name(message: Message, state: FSMContext, session: AsyncSession):
    user = await get_user_by_name(message.text.strip(), session)
    if not user:
        await message.answer("ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН. ПОПРОБУЙТЕ ЕЩЁ РАЗ ИЛИ НАЖМИТЕ «НАЗАД».")
        return
    await state.update_data(target_id=user.telegram_id)
    await message.answer(
        "ВВЕДИТЕ СУММУ ДЛЯ ПОПОЛНЕНИЯ:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_amount_balance)

@admin_router.callback_query(StateFilter(AdminState.waiting_for_amount_balance), F.data == "admin")
async def back_from_balance_amount(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_amount_balance))
async def admin_balance_amount(message: Message, state: FSMContext, session: AsyncSession):
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("ВВЕДИТЕ ЧИСЛО.")
        return
    
    data = await state.get_data()
    target_id = data["target_id"]
    user = await get_user(target_id, session)
    if not user:
        await message.answer("ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН.")
        await state.clear()
        return
    
    user.balance += amount
    user.total_earned += amount
    await session.commit()
    await message.answer(
        f"✅ БАЛАНС ПОЛЬЗОВАТЕЛЯ {user.full_name} ПОПОЛНЕН НА {amount:,.0f} ₽.",
        reply_markup=admin_panel_keyboard()
    )
    await notify_user(message.bot, target_id, f"💰 АДМИНИСТРАТОР ПОПОЛНИЛ ВАШ БАЛАНС НА {amount:,.0f} ₽.")
    await send_news_to_channel(message.bot, f"🔧 АДМИН ПОПОЛНИЛ БАЛАНС {user.full_name} НА {amount:,.0f} ₽")
    await state.clear()

# --- Списание баланса (по имени) ---
@admin_router.callback_query(F.data == "admin_sub_balance")
async def admin_sub_balance(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "ВВЕДИТЕ ИМЯ И ФАМИЛИЮ ПОЛЬЗОВАТЕЛЯ:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_user_id_sub_balance)
    await callback.answer()

@admin_router.callback_query(StateFilter(AdminState.waiting_for_user_id_sub_balance), F.data == "admin")
async def back_from_sub_balance_name(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_user_id_sub_balance))
async def admin_sub_balance_user_name(message: Message, state: FSMContext, session: AsyncSession):
    user = await get_user_by_name(message.text.strip(), session)
    if not user:
        await message.answer("ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН.")
        return
    await state.update_data(target_id=user.telegram_id)
    await message.answer(
        "ВВЕДИТЕ СУММУ ДЛЯ СПИСАНИЯ:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_amount_sub_balance)

@admin_router.callback_query(StateFilter(AdminState.waiting_for_amount_sub_balance), F.data == "admin")
async def back_from_sub_balance_amount(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_amount_sub_balance))
async def admin_sub_balance_amount(message: Message, state: FSMContext, session: AsyncSession):
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("ВВЕДИТЕ ЧИСЛО.")
        return
    
    data = await state.get_data()
    target_id = data["target_id"]
    user = await get_user(target_id, session)
    if not user:
        await message.answer("ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН.")
        await state.clear()
        return
    
    if amount > user.balance:
        await message.answer("НЕДОСТАТОЧНО СРЕДСТВ НА БАЛАНСЕ ПОЛЬЗОВАТЕЛЯ.")
        return
    
    user.balance -= amount
    await session.commit()
    await add_transaction(session, user.id, -amount, "admin_deduct", f"АДМИН СПИСАЛ {amount:,.0f} ₽")
    await message.answer(
        f"✅ С БАЛАНСА ПОЛЬЗОВАТЕЛЯ {user.full_name} СПИСАНО {amount:,.0f} ₽.",
        reply_markup=admin_panel_keyboard()
    )
    await notify_user(message.bot, target_id, f"💰 АДМИНИСТРАТОР СПИСАЛ С ВАШЕГО БАЛАНСА {amount:,.0f} ₽.")
    await send_news_to_channel(message.bot, f"🔧 АДМИН СПИСАЛ С БАЛАНСА {user.full_name} {amount:,.0f} ₽")
    await state.clear()

# --- Блокировка пользователя ---
@admin_router.callback_query(F.data == "admin_ban_user")
async def admin_ban_user(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "ВВЕДИТЕ ИМЯ И ФАМИЛИЮ ПОЛЬЗОВАТЕЛЯ ДЛЯ БЛОКИРОВКИ:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_ban_user_name)
    await callback.answer()

@admin_router.callback_query(StateFilter(AdminState.waiting_for_ban_user_name), F.data == "admin")
async def back_from_ban_user(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_ban_user_name))
async def admin_ban_user_name(message: Message, state: FSMContext, session: AsyncSession):
    user = await get_user_by_name(message.text.strip(), session)
    if not user:
        await message.answer("ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН.")
        return
    user.is_banned = True
    await session.commit()
    await message.answer(
        f"✅ ПОЛЬЗОВАТЕЛЬ {user.full_name} ЗАБЛОКИРОВАН.",
        reply_markup=admin_panel_keyboard()
    )
    await notify_user(message.bot, user.telegram_id, "⛔ ВЫ БЫЛИ ЗАБЛОКИРОВАНЫ АДМИНИСТРАТОРОМ.")
    await send_news_to_channel(message.bot, f"🚫 АДМИН ЗАБЛОКИРОВАЛ ПОЛЬЗОВАТЕЛЯ {user.full_name}")
    await state.clear()

# --- Разблокировка пользователя ---
@admin_router.callback_query(F.data == "admin_unban_user")
async def admin_unban_user(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "ВВЕДИТЕ ИМЯ И ФАМИЛИЮ ПОЛЬЗОВАТЕЛЯ ДЛЯ РАЗБЛОКИРОВКИ:",
        reply_markup=back_keyboard("admin")
    )
    await state.set_state(AdminState.waiting_for_unban_user_name)
    await callback.answer()

@admin_router.callback_query(StateFilter(AdminState.waiting_for_unban_user_name), F.data == "admin")
async def back_from_unban_user(callback: CallbackQuery, state: FSMContext):
    await back_to_admin_panel(callback, state)
    await callback.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_unban_user_name))
async def admin_unban_user_name(message: Message, state: FSMContext, session: AsyncSession):
    user = await get_user_by_name(message.text.strip(), session)
    if not user:
        await message.answer("ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН.")
        return
    user.is_banned = False
    await session.commit()
    await message.answer(
        f"✅ ПОЛЬЗОВАТЕЛЬ {user.full_name} РАЗБЛОКИРОВАН.",
        reply_markup=admin_panel_keyboard()
    )
    await notify_user(message.bot, user.telegram_id, "✅ ВЫ БЫЛИ РАЗБЛОКИРОВАНЫ АДМИНИСТРАТОРОМ.")
    await send_news_to_channel(message.bot, f"✅ АДМИН РАЗБЛОКИРОВАЛ ПОЛЬЗОВАТЕЛЯ {user.full_name}")
    await state.clear()

# --- Установка звания (по имени) ---
@admin_router.callback_query(F.data == "admin_set_rank")
async def admin_set_rank(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "ВВЕДИТЕ ИМЯ И ФАМИЛИЮ ПОЛЬЗОВАТЕЛЯ:",
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
        await message.answer("ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН.")
        return
    await state.update_data(target_id=user.telegram_id)
    ranks = ["РЯДОВОЙ", "ЕФРЕЙТОР", "МЛАДШИЙ СЕРЖАНТ", "СЕРЖАНТ", "СТАРШИЙ СЕРЖАНТ", "ЛЕЙТЕНАНТ", "СТАРШИЙ ЛЕЙТЕНАНТ"]
    await message.answer(
        "ВЫБЕРИТЕ ЗВАНИЕ (ВВЕДИТЕ НОМЕР):\n" + "\n".join([f"{i+1}. {r}" for i, r in enumerate(ranks)]),
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
        ranks = ["РЯДОВОЙ", "ЕФРЕЙТОР", "МЛАДШИЙ СЕРЖАНТ", "СЕРЖАНТ", "СТАРШИЙ СЕРЖАНТ", "ЛЕЙТЕНАНТ", "СТАРШИЙ ЛЕЙТЕНАНТ"]
        new_rank = ranks[idx]
    except:
        await message.answer("НЕВЕРНЫЙ НОМЕР.")
        return
    
    data = await state.get_data()
    target_id = data["target_id"]
    user = await get_user(target_id, session)
    if not user:
        await message.answer("ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН.")
        await state.clear()
        return
    
    old_rank = user.rank
    user.rank = new_rank
    user.rank_manual = True
    await session.commit()
    await message.answer(
        f"✅ ЗВАНИЕ ПОЛЬЗОВАТЕЛЯ {user.full_name} ИЗМЕНЕНО С {old_rank} НА {new_rank}.",
        reply_markup=admin_panel_keyboard()
    )
    await notify_user(message.bot, target_id, f"🎖 АДМИНИСТРАТОР ИЗМЕНИЛ ВАШЕ ЗВАНИЕ С {old_rank} НА {new_rank}!")
    await send_news_to_channel(message.bot, f"🔧 АДМИН ИЗМЕНИЛ ЗВАНИЕ {user.full_name} С {old_rank} НА {new_rank}")
    await state.clear()

# --- Выдача медали (по имени) ---
@admin_router.callback_query(F.data == "admin_give_medal")
async def admin_give_medal(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "ВВЕДИТЕ ИМЯ И ФАМИЛИЮ ПОЛЬЗОВАТЕЛЯ:",
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
        await message.answer("ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН.")
        return
    await state.update_data(target_id=user.telegram_id)
    text = "ВЫБЕРИТЕ МЕДАЛЬ (ВВЕДИТЕ НОМЕР):\n"
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
        await message.answer("НЕВЕРНЫЙ НОМЕР.")
        return
    
    data = await state.get_data()
    target_id = data["target_id"]
    user = await get_user(target_id, session)
    if not user:
        await message.answer("ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН.")
        await state.clear()
        return
    
    added = await add_medal(user, medal, session, give_bonus=True)
    if added:
        await message.answer(
            f"✅ МЕДАЛЬ '{medal}' ВЫДАНА ПОЛЬЗОВАТЕЛЮ {user.full_name} (НАЧИСЛЕНО 5 000 ₽).",
            reply_markup=admin_panel_keyboard()
        )
        await notify_user(message.bot, target_id, f"🎉 АДМИНИСТРАТОР ВЫДАЛ ВАМ МЕДАЛЬ '{medal}' И 5 000 ₽!")
        await send_news_to_channel(message.bot, f"🏅 АДМИН ВЫДАЛ МЕДАЛЬ '{medal}' ПОЛЬЗОВАТЕЛЮ {user.full_name}")
    else:
        await message.answer(f"У ПОЛЬЗОВАТЕЛЯ УЖЕ ЕСТЬ МЕДАЛЬ '{medal}'.")
    await state.clear()

# --- Смена имени (по имени) ---
@admin_router.callback_query(F.data == "admin_rename")
async def admin_rename(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "ВВЕДИТЕ ИМЯ И ФАМИЛИЮ ПОЛЬЗОВАТЕЛЯ:",
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
        await message.answer("ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН.")
        return
    await state.update_data(target_id=user.telegram_id)
    await message.answer(
        "ВВЕДИТЕ НОВОЕ ИМЯ И ФАМИЛИЮ:",
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
        await message.answer("ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН.")
        await state.clear()
        return
    old_name = user.full_name
    new_name = message.text.strip().upper()
    existing = await get_user_by_name(new_name, session)
    if existing and existing.telegram_id != target_id:
        await message.answer("❌ ЭТО ИМЯ УЖЕ ЗАНЯТО. ВВЕДИТЕ ДРУГОЕ.")
        return
    user.full_name = new_name
    await session.commit()
    await message.answer(
        f"✅ ИМЯ ПОЛЬЗОВАТЕЛЯ ИЗМЕНЕНО С {old_name} НА {new_name}.",
        reply_markup=admin_panel_keyboard()
    )
    await notify_user(message.bot, target_id, f"✏️ АДМИНИСТРАТОР ИЗМЕНИЛ ВАШЕ ИМЯ С {old_name} НА {new_name}.")
    await send_news_to_channel(message.bot, f"✏️ АДМИН ИЗМЕНИЛ ИМЯ {old_name} НА {new_name}")
    await state.clear()

# --- Смена пароля ---
@admin_router.callback_query(F.data == "admin_change_password")
async def admin_change_password(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "ВВЕДИТЕ НОВЫЙ ПАРОЛЬ ДЛЯ БОТА:",
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
    await message.answer(
        f"✅ ПАРОЛЬ БОТА ИЗМЕНЁН НА {new_password}. (ВНИМАНИЕ: ИЗМЕНЕНИЕ НЕ СОХРАНЯЕТСЯ ПОСЛЕ ПЕРЕЗАПУСКА)",
        reply_markup=admin_panel_keyboard()
    )
    await state.clear()

# --- Рассылка (с прогрессом) ---
@admin_router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "ВВЕДИТЕ ТЕКСТ ДЛЯ РАССЫЛКИ:",
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
        await message.answer("НЕТ ПОЛЬЗОВАТЕЛЕЙ ДЛЯ РАССЫЛКИ.", reply_markup=admin_panel_keyboard())
        await state.clear()
        return
    
    status_msg = await message.answer(f"📢 РАССЫЛКА НАЧАТА (0/{total})...")
    count = 0
    for uid in users:
        try:
            await message.bot.send_message(uid, f"📢 РАССЫЛКА ОТ АДМИНИСТРАТОРА:\n\n{text}")
            count += 1
            if count % 10 == 0:
                await status_msg.edit_text(f"📢 РАССЫЛКА... ({count}/{total})")
        except:
            pass
        await asyncio.sleep(0.05)
    
    await status_msg.edit_text(
        f"✅ РАССЫЛКА ЗАВЕРШЕНА! ОТПРАВЛЕНО {count} ИЗ {total} ПОЛЬЗОВАТЕЛЯМ.",
        reply_markup=admin_panel_keyboard()
    )
    await state.clear()

# --- Кастомная кнопка ---
@admin_router.callback_query(F.data == "admin_custom_button")
async def admin_custom_button(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "ВВЕДИТЕ ТЕКСТ ДЛЯ КНОПКИ:",
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
        "ВВЕДИТЕ ТЕКСТ СООБЩЕНИЯ, КОТОРОЕ БУДЕТ ОТПРАВЛЯТЬСЯ ПРИ НАЖАТИИ:",
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
    
    builder = InlineKeyboardBuilder()
    builder.button(text=text, callback_data=cb_data)
    await message.bot.send_message(
        ADMIN_ID,
        f"✅ КАСТОМНАЯ КНОПКА СОЗДАНА!\nТЕКСТ: {text}\nСООБЩЕНИЕ: {msg_text}",
        reply_markup=builder.as_markup()
    )
    await message.answer("КНОПКА ДОБАВЛЕНА В АДМИН-ЧАТ.", reply_markup=admin_panel_keyboard())
    await state.clear()

# --- Изменить текст главного меню ---
@admin_router.callback_query(F.data == "admin_change_main_text")
async def admin_change_main_text(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "ВВЕДИТЕ НОВЫЙ ТЕКСТ ГЛАВНОГО МЕНЮ (МОЖНО ИСПОЛЬЗОВАТЬ {name} И {date}):",
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
    await message.answer(
        "✅ ТЕКСТ ГЛАВНОГО МЕНЮ ОБНОВЛЁН. (ВНИМАНИЕ: ИЗМЕНЕНИЕ НЕ СОХРАНЯЕТСЯ ПОСЛЕ ПЕРЕЗАПУСКА)",
        reply_markup=admin_panel_keyboard()
    )
    await state.clear()

# --- Войти в общее меню ---
@admin_router.callback_query(F.data == "admin_enter_main")
async def admin_enter_main(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await back_to_main(callback, state, session)
    await callback.answer()

# --- Статистика и пользователи ---
@admin_router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, session: AsyncSession):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("НЕТ ДОСТУПА", show_alert=True)
        return
    total_users = await session.scalar(select(func.count()).select_from(User))
    total_balance = await session.scalar(select(func.sum(User.balance)))
    total_credits = await session.scalar(select(func.sum(User.credit_amount)))
    total_deposits = await session.scalar(select(func.sum(User.deposit_amount)))
    vip_count = await session.scalar(select(func.count()).where(User.is_vip == True))
    banned_count = await session.scalar(select(func.count()).where(User.is_banned == True))
    await callback.message.edit_text(
        f"📊 СТАТИСТИКА:\n"
        f"👥 ПОЛЬЗОВАТЕЛЕЙ: {total_users} (VIP: {vip_count}, ЗАБЛОКИРОВАНО: {banned_count})\n"
        f"💰 ОБЩИЙ БАЛАНС: {total_balance:,.0f} ₽\n"
        f"💵 СУММА КРЕДИТОВ: {total_credits or 0:,.0f} ₽\n"
        f"🏦 СУММА ВКЛАДОВ: {total_deposits or 0:,.0f} ₽",
        reply_markup=back_keyboard("admin")
    )
    await callback.answer()

@admin_router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery, session: AsyncSession):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("НЕТ ДОСТУПА", show_alert=True)
        return
    result = await session.execute(select(User).limit(20))
    users = result.scalars().all()
    text = "👥 ПОЛЬЗОВАТЕЛИ:\n"
    for u in users:
        credit_info = f"КРЕДИТ: {u.credit_amount:,.0f} ₽" if u.credit_amount > 0 else ""
        deposit_info = f"ВКЛАД: {u.deposit_amount:,.0f} ₽" if u.deposit_amount > 0 else ""
        vip_mark = " 💜VIP" if u.is_vip else ""
        banned_mark = " 🚫BANNED" if u.is_banned else ""
        extra = " | ".join(filter(None, [credit_info, deposit_info]))
        text += f"{u.full_name}{vip_mark}{banned_mark} (ID: {u.telegram_id}) — {u.balance:,.0f} ₽, {u.rank}"
        if extra:
            text += f" | {extra}"
        text += "\n"
    await callback.message.edit_text(text, reply_markup=back_keyboard("admin"))
    await callback.answer()
