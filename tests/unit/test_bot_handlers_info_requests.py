import pytest
import html
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from app.bot.handlers.info_requests import (
    process_weather_command,
    process_news_command,
    process_events_command,
)
from aiogram.types import Message, User as AiogramUser, Chat
from aiogram.filters import CommandObject

# ... тесты для погоды ...
@pytest.mark.asyncio
async def test_process_weather_command_success():
    city_name = "Москва"
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123, full_name="Tester")
    mock_command = MagicMock(spec=CommandObject, args=city_name)
    mock_weather_api_response = {
        "weather": [{"description": "ясно"}],
        "main": {"temp": 20.5, "feels_like": 19.0, "humidity": 50},
        "wind": {"speed": 3.0, "deg": 180},
        "name": city_name,
    }
    with patch(
        "app.bot.handlers.info_requests.get_weather_data",
        return_value=mock_weather_api_response,
    ), patch("app.bot.handlers.info_requests.get_session"), patch(
        "app.bot.handlers.info_requests.log_user_action"
    ) as mock_log_action:
        await process_weather_command(mock_message, mock_command)
        mock_message.reply.assert_any_call(
            f"Запрашиваю погоду для города <b>{html.escape(city_name)}</b>..."
        )
        expected_response_text = (
            f"<b>Погода в городе {html.escape(mock_weather_api_response.get('name', city_name))}:</b>\n"
            f"🌡️ Температура: {mock_weather_api_response['main']['temp']}°C (ощущается как {mock_weather_api_response['main']['feels_like']}°C)\n"
            f"💧 Влажность: {mock_weather_api_response['main']['humidity']}%\n"
            f"💨 Ветер: {mock_weather_api_response['wind']['speed']} м/с, Южный\n"
            f"☀️ Описание: Ясно"
        )
        mock_message.answer.assert_called_once_with(expected_response_text)
        mock_log_action.assert_called_once_with(
            ANY, mock_message.from_user.id, "/weather", f"город: {city_name}, успех"
        )


@pytest.mark.asyncio
async def test_process_weather_command_no_city():
    mock_message = AsyncMock(spec=Message)
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)
    mock_command = MagicMock(spec=CommandObject, args=None)
    with patch("app.bot.handlers.info_requests.get_session"), patch(
        "app.bot.handlers.info_requests.log_user_action"
    ) as mock_log_action:
        await process_weather_command(mock_message, mock_command)
        mock_message.reply.assert_called_once_with(
            "Пожалуйста, укажите название города..."
        )
        mock_log_action.assert_called_once_with(
            ANY, mock_message.from_user.id, "/weather", "Город не указан"
        )


# --- Тесты для process_news_command ---
@pytest.mark.asyncio
async def test_process_news_command_success():
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=123)
    mock_articles = [
        {"title": "Новость 1", "url": "http://example.com/1", "source": {"name": "Источник 1"}},
    ]
    with patch(
        "app.bot.handlers.info_requests.get_top_headlines", return_value=mock_articles
    ), patch("app.bot.handlers.info_requests.get_session"), patch(
        "app.bot.handlers.info_requests.log_user_action"
    ) as mock_log_action:
        await process_news_command(mock_message)
        # --- ИЗМЕНЕНО: проверяемый текст ---
        mock_message.reply.assert_called_once_with(
            "Запрашиваю последние главные новости для США..."
        )
        expected_text = (
            "<b>📰 Последние главные новости (США):</b>\n"
            "1. <a href='http://example.com/1'>Новость 1</a> (Источник 1)"
        )
        mock_message.answer.assert_called_once_with(
            expected_text, disable_web_page_preview=True
        )
        mock_log_action.assert_called_once_with(
            ANY, mock_message.from_user.id, "/news", "success, country=us"
        )

# ... тесты для событий ...
@pytest.mark.asyncio
async def test_process_events_command_success():
    city_arg = "Москва"
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=456)
    mock_command = MagicMock(spec=CommandObject, args=city_arg)
    mock_events = [
        {"title": "Событие 1", "description": "Описание 1", "site_url": "http://site.com/1"},
    ]
    with patch(
        "app.bot.handlers.info_requests.get_kudago_events", return_value=mock_events
    ), patch("app.bot.handlers.info_requests.get_session"), patch(
        "app.bot.handlers.info_requests.log_user_action"
    ) as mock_log_action:
        await process_events_command(mock_message, mock_command)
        mock_message.reply.assert_any_call(
            f"Запрашиваю актуальные события для города <b>{html.escape(city_arg)}</b>..."
        )
        mock_log_action.assert_called_once_with(
            ANY, mock_message.from_user.id, "/events", f"город: {city_arg}, успех"
        )