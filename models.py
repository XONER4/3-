from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    full_name = Column(String, default="Не указано")
    balance = Column(Float, default=15000.0)
    registered_at = Column(DateTime(timezone=True), server_default=func.now())
    last_bonus = Column(DateTime(timezone=True), nullable=True)
    is_authorized = Column(Boolean, default=False)
    
    credit_amount = Column(Float, default=0.0)          # текущая сумма долга с процентами
    credit_original = Column(Float, default=0.0)        # исходная сумма кредита
    credit_term_hours = Column(Integer, default=0)      # срок в часах (5,10,15,20,25)
    credit_start_date = Column(DateTime(timezone=True), nullable=True)
    credit_due_date = Column(DateTime(timezone=True), nullable=True)  # когда нужно погасить
    credit_overdue_notified = Column(Boolean, default=False)  # было ли уведомление о просрочке
    
    deposit_amount = Column(Float, default=0.0)
    deposit_start_date = Column(DateTime(timezone=True), nullable=True)
    # убираем deposit_days, теперь процент начисляется каждый час
    
    rank = Column(String, default="Рядовой")
    medals = Column(Text, default="[]")
    
    max_balance_achieved = Column(Float, default=15000.0)
    has_taken_credit = Column(Boolean, default=False)
    has_made_deposit = Column(Boolean, default=False)
    
    gifts_sent = Column(Integer, default=0)
    purchases = Column(Text, default="[]")
    
    total_earned = Column(Float, default=0.0)
    total_donated = Column(Float, default=0.0)
    casino_bets_count = Column(Integer, default=0)
    loans_taken = Column(Integer, default=0)       # количество взятых кредитов
    deposits_made = Column(Integer, default=0)
    daily_bonus_count = Column(Integer, default=0) # счётчик ежедневных бонусов
    
    photo_id = Column(String, nullable=True)
    
    transactions = relationship("Transaction", back_populates="user")
    casino_games = relationship("CasinoGame", back_populates="user")
    iq_results = relationship("IQResult", back_populates="user")

class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float)
    type = Column(String)
    description = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="transactions")

class CasinoGame(Base):
    __tablename__ = "casino_games"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    bet_amount = Column(Float)
    game_type = Column(String)
    result = Column(String)
    won = Column(Boolean)
    payout = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="casino_games")

class IQResult(Base):
    __tablename__ = "iq_results"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    correct_answers = Column(Integer)
    medal = Column(String)
    bonus = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="iq_results")
