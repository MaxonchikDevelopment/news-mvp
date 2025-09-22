# api/schemas.py
"""Pydantic models for request/response data validation."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, EmailStr

# --- User Schemas ---


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


# --- UserProfile Schemas ---
# !!! ДОБАВЛЕННЫЕ СХЕМЫ !!!


class UserProfileBase(BaseModel):
    """Базовая схема профиля пользователя."""

    locale: str
    interests: List[Union[str, Dict[str, List[str]]]]


class UserProfileCreate(UserProfileBase):
    """Схема для создания или обновления профиля."""

    pass  # Наследуем все от UserProfileBase


class UserProfileUpdate(UserProfileBase):
    """Схема для обновления профиля (все поля опциональны)."""

    locale: Optional[str] = None
    interests: Optional[List[Union[str, Dict[str, List[str]]]]] = None


class UserProfile(UserProfileBase):
    """Схема для ответа с данными профиля."""

    user_id: int
    language: Optional[str] = "en"  # Фиксированное значение или из БД
    city: Optional[str] = None  # Не сохраняется, но может быть в ответе
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # Для совместимости с ORM


# --- Authentication Schemas ---


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


# --- News Schemas ---


class NewsItem(BaseModel):
    id: Optional[int] = None  # Может быть None для новых объектов
    title: str
    url: str
    category: str
    relevance_score: Optional[float] = None
    importance_score: Optional[int] = None
    ynk_summary: Optional[str] = None
    published_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class NewsBundleResponse(BaseModel):
    top_7: List[NewsItem]


# --- Feedback Schemas ---


class FeedbackCreate(BaseModel):
    news_item_id: int  # Или URL, если ID еще не присвоен
    rating: int  # Например, 1 (лайк) или -1 (дизлайк)


class FeedbackResponse(FeedbackCreate):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True
