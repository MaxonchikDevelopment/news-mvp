# src/models.py
"""SQLAlchemy ORM models for the news application."""

from sqlalchemy import (
    SMALLINT,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB  # Используем JSONB для PostgreSQL
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.database import Base  # Импортируем Base из database.py


# ----------------------------
# Таблица: users
# ----------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    provider = Column(String(50), nullable=False, default="email")
    provider_id = Column(Text, unique=True, nullable=True)  # Для OAuth

    role = Column(String(50), nullable=False, default="basic")

    created_at = Column(DateTime, nullable=False, default=func.now())
    last_login = Column(DateTime, nullable=True)
    is_verified = Column(Boolean, nullable=False, default=False)

    # Связь один-к-одному с профилем
    profile = relationship(
        "UserProfile", back_populates="user", uselist=False, lazy="selectin"
    )
    # Связь один-ко-многим с фидбеком
    feedback = relationship("Feedback", back_populates="user", lazy="selectin")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"


# ----------------------------
# Таблица: user_profiles
# ----------------------------
class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    locale = Column(String(10), nullable=False)
    # language не храним, всегда 'en'
    # city не храним
    interests = Column(
        JSONB, nullable=False, default={}
    )  # Храним как есть: ["sports", {"sports": [...]}]
    # preferences не храним, фиксированы

    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now()
    )

    # Связь один-к-одному с пользователем
    user = relationship("User", back_populates="profile", lazy="selectin")

    def __repr__(self):
        return f"<UserProfile(user_id={self.user_id}, locale='{self.locale}')>"


# ----------------------------
# Таблица: news_items
# ----------------------------
class NewsItem(Base):
    __tablename__ = "news_items"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(
        Text, unique=True, index=True, nullable=False
    )  # Уникальный ID источника
    source_name = Column(String(255), nullable=False)
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    # description не храним
    category = Column(String(100), nullable=False)
    subcategory = Column(String(100), nullable=True)  # Может быть NULL
    importance_score = Column(
        SMALLINT, nullable=False
    )  # Глобальная оценка важности 0-100
    ai_analysis = Column(JSONB, nullable=False, default={})  # Результаты классификации
    fetched_at = Column(DateTime, nullable=False, default=func.now())

    # Связь один-ко-многим с фидбеком
    feedback_entries = relationship(
        "Feedback", back_populates="news_item", lazy="selectin"
    )

    def __repr__(self):
        return f"<NewsItem(id={self.id}, title='{self.title[:30]}...', category='{self.category}')>"


# ----------------------------
# Таблица: feedback
# ----------------------------
class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    news_item_id = Column(Integer, ForeignKey("news_items.id"), nullable=False)

    # Ограничиваем возможные значения рейтинга
    rating = Column(SMALLINT, CheckConstraint("rating IN (-1, 0, 1)"), nullable=False)

    created_at = Column(DateTime, nullable=False, default=func.now())

    # Связи
    user = relationship("User", back_populates="feedback", lazy="selectin")
    news_item = relationship(
        "NewsItem", back_populates="feedback_entries", lazy="selectin"
    )

    # Уникальность: один пользователь - одна оценка на новость
    __table_args__ = (
        UniqueConstraint("user_id", "news_item_id", name="uq_user_news_rating"),
    )

    def __repr__(self):
        return f"<Feedback(id={self.id}, user_id={self.user_id}, news_item_id={self.news_item_id}, rating={self.rating})>"


# ----------------------------
# Таблица: user_news_cache
# ----------------------------
class UserNewsCache(Base):
    __tablename__ = "user_news_cache"

    # --- ИЗМЕНЕНИЕ ЗДЕСЬ ---
    # Оба столбца, составляющие композитный PK, должны иметь primary_key=True
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True, nullable=False)
    news_date = Column(Date, primary_key=True, nullable=False)
    # ----------------------

    news_bundle = Column(JSONB, nullable=False)  # Сгенерированная лента новостей
    generated_at = Column(DateTime, nullable=False, default=func.now())

    # Уникальность и индекс теперь не обязательны, так как PK уже обеспечивает уникальность
    # Но можно оставить UniqueConstraint для ясности, если хочешь
    __table_args__ = (
        # UniqueConstraint('user_id', 'news_date', name='uq_user_news_date') # Можно удалить
        # Индекс для быстрого поиска по пользователю и дате (может быть полезен)
        Index("idx_user_news_date", "user_id", "news_date"),
    )

    def __repr__(self):
        return f"<UserNewsCache(user_id={self.user_id}, news_date={self.news_date})>"
