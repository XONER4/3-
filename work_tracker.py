from datetime import datetime

# Словарь для отслеживания активности в работе
work_activity = {}

def update_work_activity(user_id: int, amount: float, work_type: str):
    """Обновляет данные о последней активности пользователя в работе."""
    now = datetime.now()
    if user_id in work_activity:
        work_activity[user_id]["last_action"] = now
        work_activity[user_id]["earned"] += amount
    else:
        work_activity[user_id] = {"last_action": now, "earned": amount, "type": work_type}
