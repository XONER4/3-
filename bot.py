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
from sqlalchemy.ext.asyncio import AsyncSession

from config import BOT_TOKEN, ADMIN_ID, TIMEZONE_OFFSET
from database import init_db, AsyncSessionLocal
from handlers import router
from admin import admin_router
from models import User, Transaction
from utils import calculate_deposit_payout, calculate_credit_debt, add_medal, notify_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Middleware для автоматической передачи сессии БД в хендлеры
async def db_session_middleware(handler, event, data):
    async with AsyncSessionLocal() as session:
        data["session"] = session
        return await handler(event, data)

dp.update.middleware(db_session_middleware)

dp.include_router(admin_router)
dp.include_router(router)

# ---------- Фоновая задача для кредитов и вкладов ----------
async def background_task():
    """Периодическая проверка кредитов (начисление процентов, просрочки, автосписание)"""
    while True:
        try:
            await asyncio.sleep(600)  # каждые 10 минут
            async with AsyncSessionLocal() as session:
                now = datetime.now()
                
                # 1. Обработка кредитов
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
                                f"⚠️ Внимание! Срок погашения кредита истёк!\n"
                                f"Текущий долг: {current_debt:,.0f} ₽.\n"
                                f"Пожалуйста, погасите кредит в ближайшее время, иначе долг будет списан автоматически."
                            )
                            user.credit_overdue_notified = True
                            added = await add_medal(user, "🔴ДОЛЖНИК🔴", session)
                            if added:
                                await notify_user(
                                    bot,
                                    user.telegram_id,
                                    "🎉 Вы получили медаль '🔴ДОЛЖНИК🔴' за просрочку кредита!"
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
                                    description="Автоматическое погашение просроченного кредита"
                                )
                                session.add(trans)
                                await session.commit()
                                await notify_user(
                                    bot,
                                    user.telegram_id,
                                    f"✅ Ваш просроченный кредит автоматически погашен.\n"
                                    f"Списано: {current_debt:,.0f} ₽\n"
                                    f"Остаток на балансе: {user.balance:,.0f} ₽"
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
                                        description="Частичное погашение просроченного кредита"
                                    )
                                    session.add(trans)
                                    await session.commit()
                                    await notify_user(
                                        bot,
                                        user.telegram_id,
                                        f"⚠️ С вашего баланса списано {user.balance:,.0f} ₽ в счёт долга по кредиту.\n"
                                        f"Остаток долга: {user.credit_amount:,.0f} ₽"
                                    )
                
                await session.commit()
                logger.info("Фоновая проверка кредитов выполнена")
                
        except Exception as e:
            logger.error(f"Ошибка в фоновой задаче: {e}")

async def main():
    logger.info("Инициализация базы данных...")
    await init_db()
    logger.info("База данных инициализирована.")
    
    asyncio.create_task(background_task())
    
    logger.info("Запуск бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
