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
    # Статус авторизации (True - ввел пароль)
    is_authorized = Column(Boolean, default=False)
    
    # Для кредита
    credit_amount = Column(Float, default=0.0)
    credit_due_date = Column(DateTime(timezone=True), nullable=True)
    
    # Для вклада
    deposit_amount = Column(Float, default=0.0)
    deposit_days = Column(Integer, default=0)
    deposit_start_date = Column(DateTime(timezone=True), nullable=True)
    
    # Звания и медали (будем хранить как строки, можно и отдельную таблицу, но для простоты так)
    rank = Column(String, default="Рядовой")
    medals = Column(Text, default="[]")  # JSON список медалей
    
    # Статистика для званий
    max_balance_achieved = Column(Float, default=15000.0)
    has_taken_credit = Column(Boolean, default=False)
    has_made_deposit = Column(Boolean, default=False)
    
    # Статистика для магазина и подарков
    gifts_sent = Column(Integer, default=0)  # количество подаренных вещей
    # Здесь могли бы быть связи с покупками, но для простоты будем хранить в JSON
    purchases = Column(Text, default="[]")  # JSON список купленных товаров
    
    # Связи с другими таблицами
    transactions = relationship("Transaction", back_populates="user")
    casino_games = relationship("CasinoGame", back_populates="user")
    iq_results = relationship("IQResult", back_populates="user")

class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float)
    type = Column(String)  # 'credit', 'deposit', 'casino_win', 'casino_loss', 'iq_bonus', 'gift', 'transfer_in', 'transfer_out', 'daily_bonus', 'shop_purchase'
    description = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="transactions")

class CasinoGame(Base):
    __tablename__ = "casino_games"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    bet_amount = Column(Float)
    guessed_number = Column(Integer)
    actual_number = Column(Integer)
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
