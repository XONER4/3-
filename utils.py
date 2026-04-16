import json
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from models import User

RANK_BONUS_MULTIPLIER = {
    "Рядовой": 1,
    "Ефрейтор": 2,
    "Младший сержант": 4,
    "Сержант": 8,
    "Старший сержант": 16,
    "Лейтенант": 32,
    "Старший лейтенант": 64
}

RANK_REWARDS = {
    "Ефрейтор": 20000,
    "Младший сержант": 40000,
    "Сержант": 80000,
    "Старший сержант": 160000,
    "Лейтенант": 320000,
    "Старший лейтенант": 640000
}

async def notify_user(telegram_id: int, text: str):
    """Отправляет уведомление пользователю в личные сообщения."""
    try:
        from bot import bot
        await bot.send_message(telegram_id, text)
    except:
        pass

async def check_rank_upgrade(user: User, session: AsyncSession):
    """Проверяет и обновляет звание на основе total_earned"""
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

async def add_medal(user: User, medal_name: str, session: AsyncSession):
    medals = json.loads(user.medals) if user.medals else []
    if medal_name not in medals:
        medals.append(medal_name)
        user.medals = json.dumps(medals)
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
        "🎁 Также при получении нового звания вы получаете денежную награду (удваивается с каждым званием):\n"
        "   Ефрейтор — 20 000 ₽\n"
        "   Мл. сержант — 40 000 ₽\n"
        "   Сержант — 80 000 ₽\n"
        "   Ст. сержант — 160 000 ₽\n"
        "   Лейтенант — 320 000 ₽\n"
        "   Ст. лейтенант — 640 000 ₽"
    )
