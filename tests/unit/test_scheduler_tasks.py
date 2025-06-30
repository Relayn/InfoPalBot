# Файл: tests/unit/test_scheduler_tasks.py

import pytest
import html
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

# Импортируем все тестируемые функции
from app.scheduler.tasks import (
    send_single_notification,
    format_weather_message,
    format_news_message,
    format_events_message,
)
from app.database.models import Subscription, User
from app.bot.constants import INFO_TYPE_WEATHER, INFO_TYPE_NEWS, KUDAGO_LOCATION_SLUGS


# --- НОВЫЕ ТЕСТЫ ДЛЯ ФУНКЦИЙ ФОРМАТИРОВАНИЯ ---

@pytest.mark.asyncio
@patch("app.scheduler.tasks.get_weather_data")
async def test_format_weather_message_success(mock_get_weather):
    """Тест: успешное форматирование сообщения о погоде."""
    city = "Лондон"
    mock_get_weather.return_value = {
        "weather": [{"description": "переменная облачность"}],
        "main": {"temp": 15.5, "feels_like": 14.0},
        "name": "London",
    }
    result = await format_weather_message(city)
    assert result is not None
    assert "<b>Погода в городе London:</b>" in result
    assert "15.5°C" in result
    assert "Переменная облачность" in result
    mock_get_weather.assert_awaited_once_with(city)


@pytest.mark.asyncio
@patch("app.scheduler.tasks.get_weather_data")
async def test_format_weather_message_api_error(mock_get_weather):
    """Тест: форматирование погоды при ошибке от API."""
    city = "НесуществующийГород"
    mock_get_weather.return_value = {"error": True, "message": "city not found"}
    result = await format_weather_message(city)
    assert result is None
    mock_get_weather.assert_awaited_once_with(city)


@pytest.mark.asyncio
@patch("app.scheduler.tasks.get_top_headlines")
async def test_format_news_message_success(mock_get_news):
    """Тест: успешное форматирование сообщения о новостях."""
    mock_get_news.return_value = [
        {"title": "Новость 1", "url": "http://a.com"},
        {"title": "Новость 2", "url": "http://b.com"},
    ]
    result = await format_news_message()
    assert result is not None
    assert "<b>📰 Последние главные новости (США):</b>" in result
    assert "<a href='http://a.com'>Новость 1</a>" in result
    assert "<a href='http://b.com'>Новость 2</a>" in result
    mock_get_news.assert_awaited_once_with(page_size=5)


@pytest.mark.asyncio
@patch("app.scheduler.tasks.get_top_headlines")
async def test_format_news_message_no_articles(mock_get_news):
    """Тест: форматирование новостей при отсутствии статей."""
    mock_get_news.return_value = []  # API вернуло пустой список
    result = await format_news_message()
    assert result is None
    mock_get_news.assert_awaited_once_with(page_size=5)


@pytest.mark.asyncio
@patch("app.scheduler.tasks.get_kudago_events")
async def test_format_events_message_success(mock_get_events):
    """Тест: успешное форматирование сообщения о событиях."""
    location_slug = "msk"
    mock_get_events.return_value = [
        {"title": "Концерт", "site_url": "http://kudago.com/msk/concert/1"},
    ]
    result = await format_events_message(location_slug)
    city_name = "Москва"  # Ожидаем, что slug 'msk' превратится в 'Москва'
    assert result is not None
    assert f"<b>🎉 Актуальные события в городе {city_name}:</b>" in result
    assert "<a href='http://kudago.com/msk/concert/1'>Концерт</a>" in result
    mock_get_events.assert_awaited_once_with(location=location_slug, page_size=3)


@pytest.mark.asyncio
@patch("app.scheduler.tasks.get_kudago_events")
async def test_format_events_message_api_error(mock_get_events):
    """Тест: форматирование событий при ошибке от API."""
    location_slug = "spb"
    mock_get_events.return_value = None  # API вернуло None
    result = await format_events_message(location_slug)
    assert result is None
    mock_get_events.assert_awaited_once_with(location=location_slug, page_size=3)


# --- СУЩЕСТВУЮЩИЕ ТЕСТЫ ДЛЯ send_single_notification ---


@pytest.mark.asyncio
async def test_send_single_notification_success_weather():
    """
    Тест: успешная отправка уведомления о погоде.
    """
    mock_bot = AsyncMock(spec=Bot)
    mock_bot.send_message = AsyncMock()

    user = User(id=1, telegram_id=12345)
    subscription = Subscription(
        id=10,
        user_id=1,
        info_type=INFO_TYPE_WEATHER,
        frequency=3,
        details="Moscow",
        status="active",
        user=user,
    )

    mock_session = MagicMock()
    mock_session.get.return_value = subscription

    formatted_message = "<b>Погода в городе Moscow:</b>..."

    with patch(
        "app.scheduler.tasks.get_session",
        return_value=MagicMock(__enter__=MagicMock(return_value=mock_session)),
    ), patch(
        "app.scheduler.tasks.format_weather_message", return_value=formatted_message
    ) as mock_format:
        await send_single_notification(mock_bot, subscription_id=10)

        mock_format.assert_called_once_with("Moscow")
        mock_bot.send_message.assert_called_once_with(
            chat_id=12345, text=formatted_message, disable_web_page_preview=True
        )


@pytest.mark.asyncio
async def test_send_single_notification_subscription_not_found():
    mock_bot = AsyncMock(spec=Bot)
    mock_bot.send_message = AsyncMock()

    mock_session = MagicMock()
    mock_session.get.return_value = None

    with patch(
        "app.scheduler.tasks.get_session",
        return_value=MagicMock(__enter__=MagicMock(return_value=mock_session)),
    ), patch("app.scheduler.tasks.logger.warning") as mock_logger:
        await send_single_notification(mock_bot, subscription_id=999)

        mock_logger.assert_called_once_with(
            "Подписка ID 999 не найдена или неактивна. Задача будет пропущена."
        )
        mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_single_notification_format_message_fails():
    mock_bot = AsyncMock(spec=Bot)
    mock_bot.send_message = AsyncMock()

    user = User(id=1, telegram_id=12345)
    subscription = Subscription(
        id=11,
        user_id=1,
        info_type=INFO_TYPE_NEWS,
        frequency=6,
        status="active",
        user=user,
    )

    mock_session = MagicMock()
    mock_session.get.return_value = subscription

    with patch(
        "app.scheduler.tasks.get_session",
        return_value=MagicMock(__enter__=MagicMock(return_value=mock_session)),
    ), patch(
        "app.scheduler.tasks.format_news_message", return_value=None
    ) as mock_format, patch(
        "app.scheduler.tasks.logger.warning"
    ) as mock_logger:
        await send_single_notification(mock_bot, subscription_id=11)

        mock_format.assert_called_once()
        mock_logger.assert_called_once_with(
            "Не удалось сформировать сообщение для подписки ID 11. Пропуск отправки."
        )
        mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_single_notification_bot_blocked():
    """
    Тест: пользователь заблокировал бота, его подписки деактивируются.
    """
    mock_bot = AsyncMock(spec=Bot)
    mock_bot.send_message.side_effect = TelegramAPIError(
        method="sendMessage", message="bot was blocked by the user"
    )

    user = User(id=1, telegram_id=12345)
    sub1 = Subscription(
        id=12, user_id=1, info_type=INFO_TYPE_NEWS, frequency=6, status="active", user=user
    )
    sub2 = Subscription(
        id=13,
        user_id=1,
        info_type=INFO_TYPE_WEATHER,
        details="Kyiv",
        frequency=3,
        status="active",
        user=user,
    )

    mock_session = MagicMock()
    mock_session.get.return_value = sub1
    mock_session.exec.return_value.all.return_value = [sub1, sub2]

    formatted_message = "<b>Новости...</b>"

    with patch(
        "app.scheduler.tasks.get_session",
        return_value=MagicMock(__enter__=MagicMock(return_value=mock_session)),
    ), patch(
        "app.scheduler.tasks.format_news_message", return_value=formatted_message
    ), patch(
        "app.scheduler.tasks.delete_subscription"
    ) as mock_delete_subscription, patch(
        "app.scheduler.tasks.logger.warning"
    ) as mock_logger:
        await send_single_notification(mock_bot, subscription_id=12)

        mock_bot.send_message.assert_called_once()
        assert mock_delete_subscription.call_count == 2
        mock_delete_subscription.assert_any_call(ANY, 12)
        mock_delete_subscription.assert_any_call(ANY, 13)
        mock_logger.assert_any_call(
            f"Пользователь 12345 заблокировал бота. Деактивируем все его подписки."
        )