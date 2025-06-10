"""
Модуль, содержащий unit-тесты для асинхронных задач планировщика APScheduler.
Тестирует функции рассылки уведомлений (погода, новости, события).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.enums import ParseMode  # <-- ДОБАВЛЕНО: Импорт ParseMode для проверки

from app.scheduler.tasks import (
    send_weather_updates,
    send_news_updates,
    send_events_updates,
)
from app.database.models import User as DBUser, Subscription as DBSubscription
from app.bot.constants import (
    INFO_TYPE_WEATHER,
    INFO_TYPE_NEWS,
    INFO_TYPE_EVENTS,
    KUDAGO_LOCATION_SLUGS,
)
from app.database.models import (
    User,
)  # <-- ДОБАВЛЕНО: Импорт модели User для type hinting в моках


# Фикстура для мокированного экземпляра бота Aiogram
@pytest.fixture
def mock_bot() -> AsyncMock:
    """
    Предоставляет мок-объект Aiogram Bot для тестирования функций,
    которые отправляют сообщения.
    """
    bot = AsyncMock(spec=Bot)
    # Убеждаемся, что send_message также является AsyncMock
    bot.send_message = AsyncMock()
    return bot


# Фикстура для мокированной сессии базы данных
@pytest.fixture
def mock_db_session() -> MagicMock:
    """
    Предоставляет мок-объект сессии SQLModel для тестирования функций,
    которые взаимодействуют с БД.
    """
    session = MagicMock()
    # Мокируем метод get, который используется для получения объектов по ID
    session.get = MagicMock()
    return session


# Фикстура для мокирования get_session()
@pytest.fixture
def mock_get_session_context(mock_db_session: MagicMock) -> MagicMock:
    # Мок контекстного менеджера, который возвращает mock_db_session при входе
    mock_session_cm = MagicMock()
    mock_session_cm.__enter__.return_value = mock_db_session
    # __exit__ тоже должен быть моком, чтобы with ... as работал
    mock_session_cm.__exit__ = MagicMock(return_value=None)

    # Патчим get_session в модуле tasks, чтобы он возвращал этот контекстный менеджер
    # Теперь get_session() будет возвращать объект, который можно использовать в with ... as
    # без необходимости вызова next()
    with patch(
        "app.scheduler.tasks.get_session", return_value=mock_session_cm
    ) as patched_get_session:
        yield patched_get_session


# --- Тесты для send_weather_updates ---
@pytest.mark.asyncio
async def test_send_weather_updates_sends_to_subscribed_user_first_time(
    mock_bot: AsyncMock, mock_db_session: MagicMock, mock_get_session_context: MagicMock
):
    """Тест: уведомление о погоде успешно отправляется, если last_sent_at is None."""
    user = DBUser(id=1, telegram_id=12345)
    mock_subscription = DBSubscription(
        id=1,
        user_id=user.id,
        user=user,
        info_type=INFO_TYPE_WEATHER,
        details="Москва",
        status="active",
        frequency=3,
        last_sent_at=None,
    )
    mock_weather_data = {
        "weather": [{"description": "ясно"}],
        "main": {"temp": 20.0, "feels_like": 19.5},
    }

    with patch(
        "app.scheduler.tasks.get_active_subscriptions_by_info_type",
        return_value=[mock_subscription],
    ), patch(
        "app.scheduler.tasks.get_weather_data", return_value=mock_weather_data
    ) as mock_get_weather:
        await send_weather_updates(mock_bot)

        mock_get_weather.assert_called_once_with("Москва")
        mock_bot.send_message.assert_called_once()
        mock_db_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_send_weather_updates_sends_when_time_is_due(
    mock_bot: AsyncMock, mock_db_session: MagicMock, mock_get_session_context: MagicMock
):
    """Тест: уведомление о погоде успешно отправляется, если прошло достаточно времени."""
    user = DBUser(id=1, telegram_id=12345)
    mock_subscription = DBSubscription(
        id=1,
        user_id=user.id,
        user=user,
        info_type=INFO_TYPE_WEATHER,
        details="Москва",
        status="active",
        frequency=3,
        last_sent_at=datetime.now(timezone.utc) - timedelta(hours=4),
    )
    mock_weather_data = {
        "weather": [{"description": "ясно"}],
        "main": {"temp": 20.0, "feels_like": 19.5},
    }

    with patch(
        "app.scheduler.tasks.get_active_subscriptions_by_info_type",
        return_value=[mock_subscription],
    ), patch("app.scheduler.tasks.get_weather_data", return_value=mock_weather_data):
        await send_weather_updates(mock_bot)
        mock_bot.send_message.assert_called_once()
        mock_db_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_send_weather_updates_does_not_send_when_time_not_due(
    mock_bot: AsyncMock, mock_db_session: MagicMock, mock_get_session_context: MagicMock
):
    """Тест: уведомление о погоде НЕ отправляется, если прошло недостаточно времени."""
    user = DBUser(id=1, telegram_id=12345)
    mock_subscription = DBSubscription(
        id=1,
        user_id=user.id,
        user=user,
        info_type=INFO_TYPE_WEATHER,
        details="Москва",
        status="active",
        frequency=3,
        last_sent_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )

    with patch(
        "app.scheduler.tasks.get_active_subscriptions_by_info_type",
        return_value=[mock_subscription],
    ):
        await send_weather_updates(mock_bot)
        mock_bot.send_message.assert_not_called()
        mock_db_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_send_weather_updates_no_active_subscriptions(
    mock_bot: AsyncMock, mock_db_session: MagicMock, mock_get_session_context: MagicMock
):
    """Тест: рассылка не происходит, если нет активных подписок."""
    with patch(
        "app.scheduler.tasks.get_active_subscriptions_by_info_type", return_value=[]
    ) as mock_get_subs:
        await send_weather_updates(mock_bot)
        mock_get_subs.assert_called_once_with(session=ANY, info_type=INFO_TYPE_WEATHER)
        mock_bot.send_message.assert_not_called()


# --- Тесты для send_news_updates ---
@pytest.mark.asyncio
async def test_send_news_updates_sends_to_subscribed_users(
    mock_bot: AsyncMock, mock_db_session: MagicMock, mock_get_session_context: MagicMock
):
    """Тест: новостная рассылка отправляется пользователям, для которых пришло время."""
    user1 = DBUser(id=1, telegram_id=111)
    user2 = DBUser(id=2, telegram_id=222)
    # Пользователю 1 пора отправлять, пользователю 2 - нет
    mock_subscriptions = [
        DBSubscription(
            id=1,
            user_id=user1.id,
            user=user1,
            info_type=INFO_TYPE_NEWS,
            status="active",
            frequency=6,
            last_sent_at=None,
        ),
        DBSubscription(
            id=2,
            user_id=user2.id,
            user=user2,
            info_type=INFO_TYPE_NEWS,
            status="active",
            frequency=6,
            last_sent_at=datetime.now(timezone.utc) - timedelta(hours=1),
        ),
    ]
    mock_articles = [{"title": "Новость", "url": "http://a.com"}]

    with patch(
        "app.scheduler.tasks.get_active_subscriptions_by_info_type",
        return_value=mock_subscriptions,
    ), patch("app.scheduler.tasks.get_top_headlines", return_value=mock_articles):
        await send_news_updates(mock_bot)

        # Сообщение должно быть отправлено только первому пользователю
        mock_bot.send_message.assert_called_once_with(
            chat_id=user1.telegram_id, text=ANY, disable_web_page_preview=True
        )
        # Коммит должен быть один в конце
        mock_db_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_send_news_updates_api_returns_error(
    mock_bot: AsyncMock, mock_db_session: MagicMock, mock_get_session_context: MagicMock
):
    """
    Тест: send_news_updates не отправляет сообщение при ошибке API новостей.
    """
    user1 = DBUser(id=1, telegram_id=111)
    mock_subscriptions = [
        DBSubscription(
            id=1,
            user_id=user1.id,
            user=user1,
            info_type=INFO_TYPE_NEWS,
            status="active",
            frequency=6,
            last_sent_at=None,
        )
    ]
    mock_api_error = {"error": True, "message": "News API Error"}

    with patch(
        "app.scheduler.tasks.get_active_subscriptions_by_info_type",
        return_value=mock_subscriptions,
    ), patch(
        "app.scheduler.tasks.get_top_headlines", return_value=mock_api_error
    ) as mock_get_headlines_api:
        await send_news_updates(mock_bot)
        mock_get_headlines_api.assert_called_once()
        mock_bot.send_message.assert_not_called()
        mock_db_session.commit.assert_not_called()


# --- Тесты для send_events_updates ---
@pytest.mark.asyncio
async def test_send_events_updates_sends_to_subscribed_users(
    mock_bot: AsyncMock, mock_db_session: MagicMock, mock_get_session_context: MagicMock
):
    """Тест: рассылка о событиях отправляется пользователям, для которых пришло время."""
    user1_msk = DBUser(id=1, telegram_id=111)
    user2_spb_due = DBUser(id=2, telegram_id=222)
    user3_spb_not_due = DBUser(id=3, telegram_id=333)

    mock_subscriptions = [
        DBSubscription(
            id=1,
            user_id=user1_msk.id,
            user=user1_msk,
            info_type=INFO_TYPE_EVENTS,
            details="msk",
            status="active",
            frequency=12,
            last_sent_at=datetime.now(timezone.utc) - timedelta(hours=13),
        ),
        DBSubscription(
            id=2,
            user_id=user2_spb_due.id,
            user=user2_spb_due,
            info_type=INFO_TYPE_EVENTS,
            details="spb",
            status="active",
            frequency=12,
            last_sent_at=None,
        ),
        DBSubscription(
            id=3,
            user_id=user3_spb_not_due.id,
            user=user3_spb_not_due,
            info_type=INFO_TYPE_EVENTS,
            details="spb",
            status="active",
            frequency=12,
            last_sent_at=datetime.now(timezone.utc) - timedelta(hours=1),
        ),
    ]

    mock_events_msk = {
        "results": [{"title": "Событие МСК", "site_url": "http://msk.com"}]
    }
    mock_events_spb = {
        "results": [{"title": "Событие СПБ", "site_url": "http://spb.com"}]
    }

    async def mock_get_kudago_side_effect(location_slug, **kwargs):
        if location_slug == "msk":
            return mock_events_msk
        if location_slug == "spb":
            return mock_events_spb
        return None

    with patch(
        "app.scheduler.tasks.get_active_subscriptions_by_info_type",
        return_value=mock_subscriptions,
    ), patch(
        "app.scheduler.tasks.get_kudago_events", side_effect=mock_get_kudago_side_effect
    ) as mock_get_events:

        await send_events_updates(mock_bot)

        # API должен быть вызван для обоих городов, т.к. в каждой группе есть кандидат на отправку
        assert mock_get_events.call_count == 2

        # Сообщения отправлены 2 из 3 пользователей
        assert mock_bot.send_message.call_count == 2
        mock_bot.send_message.assert_any_call(
            chat_id=user1_msk.telegram_id, text=ANY, disable_web_page_preview=True
        )
        mock_bot.send_message.assert_any_call(
            chat_id=user2_spb_due.telegram_id, text=ANY, disable_web_page_preview=True
        )

        # Коммит один в конце
        mock_db_session.commit.assert_called_once()
