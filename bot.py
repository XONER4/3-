import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select

from config import BOT_TOKEN, ADMIN_ID, TIMEZONE_OFFSET
from database import init_db, AsyncSessionLocal
from handlers import router
from admin import admin_router
from models import User, Transaction
from utils import (
    calculate_deposit_payout, calculate_credit_debt, add_medal,
    notify_user, send_news_to_channel
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

async def db_session_middleware(handler, event, data):
    async with AsyncSessionLocal() as session:
        data["session"] = session
        return await handler(event, data)

dp.update.middleware(db_session_middleware)

dp.include_router(admin_router)
dp.include_router(router)

# ---------- Фоновые задачи ----------
async def background_credit_task():
    while True:
        try:
            await asyncio.sleep(600)
            async with AsyncSessionLocal() as session:
                now = datetime.now()
                users_with_credit = await session.execute(
                    select(User).where(User.credit_amount > 0)
                )
                users = users_with_credit.scalars().all()
                
                for user in users:
                    hours_passed = (now - user.credit_start_date).total_seconds() / 3600
                    current_debt = calculate_credit_debt(user.credit_original, hours_passed)
                    user.credit_amount = current_debt
                    
                    if now > user.credit_due_date:
                        if not user.credit_overdue_notified:
                            await notify_user(
                                bot,
                                user.telegram_id,
                                f"⚠️ ВНИМАНИЕ! СРОК ПОГАШЕНИЯ КРЕДИТА ИСТЁК!\n"
                                f"ТЕКУЩИЙ ДОЛГ: {current_debt:,.0f} ₽.\n"
                                f"ПОЖАЛУЙСТА, ПОГАСИТЕ КРЕДИТ В БЛИЖАЙШЕЕ ВРЕМЯ, ИНАЧЕ ДОЛГ БУДЕТ СПИСАН АВТОМАТИЧЕСКИ."
                            )
                            user.credit_overdue_notified = True
                            added = await add_medal(user, "🔴ДОЛЖНИК🔴", session)
                            if added:
                                await notify_user(
                                    bot,
                                    user.telegram_id,
                                    "🎉 ВЫ ПОЛУЧИЛИ МЕДАЛЬ '🔴ДОЛЖНИК🔴' ЗА ПРОСРОЧКУ КРЕДИТА!"
                                )
                        
                        if now > user.credit_due_date + timedelta(hours=5):
                            if user.balance >= current_debt:
                                user.balance -= current_debt
                                user.credit_amount = 0
                                user.credit_original = 0
                                user.credit_term_hours = 0
                                user.credit_start_date = None
                                user.credit_due_date = None
                                user.credit_overdue_notified = False
                                await session.commit()
                                trans = Transaction(
                                    user_id=user.id,
                                    amount=-current_debt,
                                    type="credit_auto_repay",
                                    description="АВТОМАТИЧЕСКОЕ ПОГАШЕНИЕ ПРОСРОЧЕННОГО КРЕДИТА"
                                )
                                session.add(trans)
                                await session.commit()
                                await notify_user(
                                    bot,
                                    user.telegram_id,
                                    f"✅ ВАШ ПРОСРОЧЕННЫЙ КРЕДИТ АВТОМАТИЧЕСКИ ПОГАШЕН.\n"
                                    f"СПИСАНО: {current_debt:,.0f} ₽\n"
                                    f"ОСТАТОК НА БАЛАНСЕ: {user.balance:,.0f} ₽"
                                )
                            else:
                                if user.balance > 0:
                                    user.credit_amount -= user.balance
                                    user.balance = 0
                                    await session.commit()
                                    trans = Transaction(
                                        user_id=user.id,
                                        amount=-user.balance,
                                        type="credit_partial_repay",
                                        description="ЧАСТИЧНОЕ ПОГАШЕНИЕ ПРОСРОЧЕННОГО КРЕДИТА"
                                    )
                                    session.add(trans)
                                    await session.commit()
                                    await notify_user(
                                        bot,
                                        user.telegram_id,
                                        f"⚠️ С ВАШЕГО БАЛАНСА СПИСАНО {user.balance:,.0f} ₽ В СЧЁТ ДОЛГА ПО КРЕДИТУ.\n"
                                        f"ОСТАТОК ДОЛГА: {user.credit_amount:,.0f} ₽"
                                    )
                
                await session.commit()
                logger.info("ФОНОВАЯ ПРОВЕРКА КРЕДИТОВ ВЫПОЛНЕНА")
        except Exception as e:
            logger.error(f"ОШИБКА В ФОНОВОЙ ЗАДАЧЕ КРЕДИТОВ: {e}")

work_activity = {}

async def background_work_activity_task():
    while True:
        try:
            await asyncio.sleep(60)
            now = datetime.now()
            to_remove = []
            for user_id, data in work_activity.items():
                if (now - data["last_action"]).total_seconds() >= 300:
                    earned = data["earned"]
                    work_type = "ФИЗИЧЕСКИЙ ТРУД" if data["type"] == "physical" else "УМСТВЕННЫЙ ТРУД"
                    async with AsyncSessionLocal() as session:
                        user = await session.execute(select(User).where(User.telegram_id == user_id))
                        user = user.scalar_one_or_none()
                        if user:
                            await send_news_to_channel(
                                bot,
                                f"💼✨ {user.full_name} ЗАРАБОТАЛ {earned:,.0f} ₽ НА РАБОТЕ ({work_type})! ✨💼"
                            )
                    to_remove.append(user_id)
            for uid in to_remove:
                del work_activity[uid]
        except Exception as e:
            logger.error(f"ОШИБКА В ФОНОВОЙ ЗАДАЧЕ РАБОТЫ: {e}")

def update_work_activity(user_id: int, amount: float, work_type: str):
    now = datetime.now()
    if user_id in work_activity:
        work_activity[user_id]["last_action"] = now
        work_activity[user_id]["earned"] += amount
    else:
        work_activity[user_id] = {"last_action": now, "earned": amount, "type": work_type}

import handlers
handlers.update_work_activity = update_work_activity

async def main():
    logger.info("ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ...")
    await init_db()
    logger.info("БАЗА ДАННЫХ ИНИЦИАЛИЗИРОВАНА.")
    asyncio.create_task(background_credit_task())
    asyncio.create_task(background_work_activity_task())
    logger.info("ЗАПУСК БОТА...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
