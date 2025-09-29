# api/routes.py
"""API routes for users, news, and feedback."""

import logging
from datetime import date, timedelta  # <-- Добавлен импорт date
from typing import Dict  # <-- Добавлен импорт Dict

from fastapi import (  # <-- Form для /login
    APIRouter,
    Depends,
    Form,
    HTTPException,
    status,
)

# --- Исправленные импорты ---
from sqlalchemy import select  # <-- Добавлен импорт select
from sqlalchemy.ext.asyncio import AsyncSession

# --- Импорты из api ---
from api.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)

# --- Исправленный импорт: добавлен NewsItem из schemas ---
from api.schemas import (  # <-- Упрощен и исправлен импорт
    FeedbackCreate,
    NewsBundleResponse,
    NewsItem,
    Token,
    UserCreate,
    UserProfile,
    UserProfileCreate,
)

# --- Импорты из src ---
from src.database import (  # <-- Добавлен импорт AsyncSessionFactory
    AsyncSessionFactory,
    get_db_session,
)
from src.models import Feedback as DBFeedback
from src.models import User as DBUser  # <-- Добавлен импорт UserNewsCache
from src.models import UserNewsCache
from src.models import UserProfile as DBUserProfile

# --- Импорт NewsProcessingPipeline ---
from src.news_pipeline import NewsProcessingPipeline

# --- КОНЕЦ Исправленных импортов ---


# --- КОНЕЦ Импортов ---

logger = logging.getLogger(__name__)
router = APIRouter()

# --- Инициализация пайплайна ---
# Создаем один экземпляр пайплайна для всего приложения
news_pipeline = NewsProcessingPipeline()
# --- КОНЕЦ Инициализации ---


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register_user(user: UserCreate, db: AsyncSession = Depends(get_db_session)):
    """Register a new user."""
    logger.info(f"Attempting to register user: {user.email}")

    # Проверка, существует ли пользователь
    result = await db.execute(select(DBUser).where(DBUser.email == user.email))
    db_user = result.scalar_one_or_none()
    if db_user:
        logger.warning(f"Registration failed: Email {user.email} already registered")
        raise HTTPException(status_code=400, detail="Email already registered")

    # Хэширование пароля
    hashed_password = get_password_hash(user.password)
    logger.debug("Password hashed successfully")

    # Создание пользователя в БД
    db_user = DBUser(email=user.email, hashed_password=hashed_password)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    logger.info(f"User {user.email} registered successfully with ID {db_user.id}")

    # Создание токена
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.email}, expires_delta=access_token_expires
    )
    logger.debug("Access token created for new user")
    return {"access_token": access_token, "token_type": "bearer"}


# --- Обновлённый эндпоинт /login для работы с OAuth2 Form ---
@router.post("/login", response_model=Token)
async def login_for_access_token(
    email: str = Form(...),  # <-- Получаем email из формы
    password: str = Form(...),  # <-- Получаем password из формы
    db: AsyncSession = Depends(get_db_session),
):
    """Authenticate user and provide access token."""
    logger.info(f"Login attempt for user: {email}")

    # Поиск пользователя в БД
    result = await db.execute(select(DBUser).where(DBUser.email == email))
    db_user = result.scalar_one_or_none()

    if not db_user or not verify_password(password, db_user.hashed_password):
        logger.warning(f"Login failed for user: {email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    logger.info(f"User {email} logged in successfully")

    # Создание токена
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.email}, expires_delta=access_token_expires
    )
    logger.debug("Access token created for logged-in user")
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me", response_model=UserProfile)  # <-- Используем схему
async def read_users_me(
    current_user: DBUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get the profile of the currently authenticated user."""
    logger.info(f"Fetching profile for user ID: {current_user.id}")

    # Получение профиля из БД
    result = await db.execute(
        select(DBUserProfile).where(DBUserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        logger.warning(f"Profile not found for user ID: {current_user.id}")
        raise HTTPException(status_code=404, detail="Profile not found")

    logger.debug(f"Returning profile data for user {current_user.id}")
    # SQLAlchemy ORM объект автоматически преобразуется в Pydantic модель
    # благодаря настройке Config(from_attributes=True) в схеме UserProfile
    return profile


# --- Новый эндпоинт для создания/обновления профиля ---
@router.put(
    "/users/me/profile", response_model=UserProfile, status_code=status.HTTP_200_OK
)
async def create_or_update_profile(
    profile_update: UserProfileCreate,
    current_user: DBUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Create or update the profile of the currently authenticated user."""
    logger.info(f"Creating/Updating profile for user ID: {current_user.id}")

    # Проверяем, существует ли профиль
    result = await db.execute(
        select(DBUserProfile).where(DBUserProfile.user_id == current_user.id)
    )
    existing_profile = result.scalar_one_or_none()

    if existing_profile:
        # Обновляем существующий профиль
        logger.debug(f"Updating existing profile for user {current_user.id}")
        existing_profile.locale = profile_update.locale
        existing_profile.interests = profile_update.interests
        # updated_at обновится автоматически благодаря onupdate=func.now()
        await db.commit()
        await db.refresh(existing_profile)
        logger.info(f"Profile for user {current_user.id} updated successfully")
        return existing_profile
    else:
        # Создаем новый профиль
        logger.debug(f"Creating new profile for user {current_user.id}")
        new_profile = DBUserProfile(
            user_id=current_user.id,
            locale=profile_update.locale,
            interests=profile_update.interests,
        )
        db.add(new_profile)
        await db.commit()
        await db.refresh(new_profile)
        logger.info(f"New profile for user {current_user.id} created successfully")
        return new_profile


@router.get("/news/today", response_model=NewsBundleResponse)
async def get_personalized_news(current_user: DBUser = Depends(get_current_user)):
    """Get the personalized news bundle for the current user."""
    logger.info(f"Generating news bundle for user ID: {current_user.id}")

    # Получение профиля пользователя из БД
    async with AsyncSessionFactory() as db_session:  # <-- Используем AsyncSessionFactory напрямую
        try:
            result = await db_session.execute(
                select(DBUserProfile).where(DBUserProfile.user_id == current_user.id)
            )
            db_profile = result.scalar_one_or_none()

            if not db_profile:
                logger.warning(
                    f"Profile not found for user ID: {current_user.id} for news generation"
                )
                raise HTTPException(
                    status_code=404,
                    detail="User profile not found. Cannot generate news.",
                )

            # Подготавливаем данные профиля для пайплайна
            # Предполагаем, что модель DBUserProfile имеет атрибуты locale, interests
            user_profile_data = {
                "user_id": current_user.id,
                "locale": db_profile.locale,
                "language": "en",  # Фиксировано, как в моделях
                "city": None,  # Не хранится, как в моделях
                "interests": db_profile.interests,  # Это поле JSONB
            }
            logger.debug(f"Using profile data for news generation: {user_profile_data}")

            # --- ИСПРАВЛЕНИЕ: Используем уже инициализированный news_pipeline ---
            # Использование NewsProcessingPipeline
            try:
                # result = await news_pipeline.process_daily_news(user_profile_data) # Если асинхронный
                result = await news_pipeline.process_daily_news(
                    user_profile_data
                )  # <-- ИСПРАВЛЕНО: news_pipeline уже инициализирован
                logger.info("News pipeline executed successfully")
            except Exception as e:
                logger.error(
                    f"Error running news pipeline for user {current_user.id}: {e}",
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=500, detail="Error generating personalized news feed"
                )

            # Преобразование результата в формат NewsBundleResponse
            top_7_articles = result.get("top_7", [])
            news_items = []
            for article in top_7_articles:
                # Создаем объект NewsItem из данных статьи
                news_item = NewsItem(
                    # id=article.get('id'), # Если ID есть в статье
                    title=article["title"],
                    url=article["url"],
                    category=article["category"],
                    relevance_score=article.get("relevance_score"),
                    importance_score=article.get("importance_score"),
                    ynk_summary=article.get(
                        "ynk_summary", "Summary not available."
                    ),  # Предполагаем, что pipeline добавляет это
                )
                news_items.append(news_item)

            logger.debug(
                f"Returning {len(news_items)} news items in bundle for user {current_user.id}"
            )
            return NewsBundleResponse(top_7=news_items)
        except Exception as e:
            logger.error(
                f"Error fetching user profile or generating news for user {current_user.id}: {e}",
                exc_info=True,
            )
            raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    feedback: FeedbackCreate,
    current_user: DBUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Submit feedback (like/dislike) for a news item."""
    logger.info(
        f"Feedback submitted by user {current_user.id} for news item {feedback.news_item_id}: {feedback.rating}"
    )

    # Сохранение фидбека в БД
    new_feedback = DBFeedback(
        user_id=current_user.id,
        news_item_id=feedback.news_item_id,
        rating=feedback.rating,
    )
    db.add(new_feedback)
    await db.commit()
    await db.refresh(new_feedback)
    logger.info(f"Feedback ID {new_feedback.id} saved to database")

    return {"message": "Feedback submitted successfully"}


# --- Новый эндпоинт для получения подкаста ---
@router.get(
    "/podcast/script/today", response_model=Dict[str, str]
)  # <-- Используем Dict[str, str] для ответа
async def get_personalized_podcast_script(
    current_user: DBUser = Depends(get_current_user),
):
    """
    Get the personalized podcast script for the current premium user.
    """
    logger.info(f"🎙️  Podcast script requested for user ID: {current_user.id}")

    # --- TODO: Проверка на премиум-статус ---
    # is_premium = await check_user_premium_status(current_user.id, db) # Реальная проверка
    is_premium = True  # <-- Заглушка для теста. Заменить на реальную проверку!
    if not is_premium:
        logger.warning(
            f"🚫 User {current_user.id} is not a premium user. Access denied to podcast script."
        )
        raise HTTPException(
            status_code=403,
            detail="Access to podcast script is restricted to premium users.",
        )
    # --- КОНЕЦ TODO ---

    # --- ИСПРАВЛЕНИЕ: Используем news_pipeline для получения подкаста ---
    try:
        # Вызываем метод из NewsProcessingPipeline
        podcast_result = await news_pipeline.get_cached_podcast_script_for_user(
            current_user.id
        )

        if podcast_result and "script" in podcast_result:
            logger.info(f"✅ Found cached podcast script for user ID {current_user.id}.")
            return {"script": podcast_result["script"]}
        else:
            logger.warning(
                f"⚠️ No cached podcast script found for user ID {current_user.id}."
            )
            raise HTTPException(
                status_code=404,
                detail="Podcast script not available. It might still be generating.",
            )
    except Exception as e:
        logger.error(
            f"⚠️ Error fetching podcast script for user {current_user.id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Error retrieving podcast script.")
    # --- КОНЕЦ ИСПРАВЛЕНИЯ ---
