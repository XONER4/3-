import json
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from models import User

async def check_rank_upgrade(user: User, session: AsyncSession):
    if user.balance > user.max_balance_achieved:
        user.max_balance_achieved = user.balance
    
    new_rank = "Рядовой"
    days_registered = (datetime.now() - user.registered_at).days
    
    if user.max_balance_achieved >= 50000:
        new_rank = "Ефрейтор"
    if user.max_balance_achieved >= 150000 and days_registered >= 3:
        new_rank = "Младший сержант"
    if user.max_balance_achieved >= 150000 and days_registered >= 7 and user.has_taken_credit and user.has_made_deposit:
        new_rank = "Сержант"
    if user.max_balance_achieved >= 300000:
        new_rank = "Старший сержант"
    
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

def calculate_deposit_payout(amount: float, days: int) -> float:
    return amount * (1 + 0.2 * days)

def get_rank_conditions():
    return (
        "🎖 Условия получения званий:\n"
        "• Рядовой — начальное звание\n"
        "• Ефрейтор — баланс достигал 50 000 ₽\n"
        "• Младший сержант — баланс 150 000+ ₽ и 3+ дня в боте\n"
        "• Сержант — баланс 150 000+ ₽, 7+ дней, брал кредит и вклад\n"
        "• Старший сержант — баланс 300 000+ ₽"
    )
