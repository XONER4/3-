import json
import logging
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from models import User

logger = logging.getLogger(__name__)

RANK_BONUS_MULTIPLIER = {
    "Рядовой": 1,
    "Ефрейтор": 2,
    "Младший сержант": 4,
    "Сержант": 8,
    "Старший сержант": 16,
    "Лейтенант": 32,
    "Старший лейтенант": 64
}

# Обновлённые награды за звания (база 15 000, удвоение)
RANK_REWARDS = {
    "Ефрейтор": 15000,
    "Младший сержант": 30000,
    "Сержант": 60000,
    "Старший сержант": 120000,
    "Лейтенант": 240000,
    "Старший лейтенант": 480000
}

async def notify_user(bot, telegram_id: int, text: str):
    """Отправляет уведомление пользователю в личные сообщения."""
    try:
        await bot.send_message(telegram_id, text)
        logger.info(f"Уведомление отправлено пользователю {telegram_id}")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление пользователю {telegram_id}: {e}")

async def check_rank_upgrade(user: User, session: AsyncSession):
    """
    Проверяет и обновляет звание на основе total_earned.
    Если звание выдано админом вручную (rank_manual=True), не понижаем автоматически.
    """
    if user.rank_manual:
        return None
    total = user.total_earned
    new_rank = "Рядовой"
    if total >= 1600000:
        new_rank = "Старший лейтенант"
    elif total >= 800000:
        new_rank = "Лейтенант"
    elif total >= 400000:
        new_rank = "Старший сержант"
    elif total >= 200000:
        new_rank = "Сержант"
    elif total >= 100000:
        new_rank = "Младший сержант"
    elif total >= 50000:
        new_rank = "Ефрейтор"
    
    if new_rank != user.rank:
        old_rank = user.rank
        user.rank = new_rank
        await session.commit()
        return (old_rank, new_rank)
    return None

async def add_medal(user: User, medal_name: str, session: AsyncSession, give_bonus: bool = True):
    """Добавляет медаль и начисляет бонус 5 000 ₽ (если give_bonus=True)."""
    medals = json.loads(user.medals) if user.medals else []
    if medal_name not in medals:
        medals.append(medal_name)
        user.medals = json.dumps(medals)
        if give_bonus:
            user.balance += 5000
            user.total_earned += 5000
        await session.commit()
        return True
    return False

def calculate_deposit_payout(amount: float, hours_passed: float) -> float:
    """Расчёт суммы вклада с учётом 20% за каждый час"""
    return amount * (1 + 0.2 * hours_passed)

def calculate_credit_debt(original: float, hours_passed: float) -> float:
    """Расчёт долга по кредиту: +30% каждые 5 часов"""
    periods = hours_passed / 5.0
    return original * (1 + 0.3 * periods)

def get_rank_conditions():
    return (
        "🎖 Условия получения званий (по общему доходу):\n"
        "• Рядовой — начальное звание\n"
        "• Ефрейтор — доход от 50 000 ₽\n"
        "• Младший сержант — доход от 100 000 ₽\n"
        "• Сержант — доход от 200 000 ₽\n"
        "• Старший сержант — доход от 400 000 ₽\n"
        "• Лейтенант — доход от 800 000 ₽\n"
        "• Старший лейтенант — доход от 1 600 000 ₽\n"
        "💰 Ежедневный бонус удваивается с каждым званием!\n"
        "🎁 Также при получении нового звания вы получаете денежную награду:\n"
        "   Ефрейтор — 15 000 ₽\n"
        "   Мл. сержант — 30 000 ₽\n"
        "   Сержант — 60 000 ₽\n"
        "   Ст. сержант — 120 000 ₽\n"
        "   Лейтенант — 240 000 ₽\n"
        "   Ст. лейтенант — 480 000 ₽\n"
        "🏅 За каждую новую медаль вы получаете 5 000 ₽!"
    )

def generate_referral_link(user_id: int) -> str:
    """Генерирует реферальную ссылку на бота с параметром start."""
    from config import BOT_USERNAME
    return f"https://t.me/{BOT_USERNAME}?start={user_id}"
    BOT_USERNAME = "Ruferutyretywbot"
