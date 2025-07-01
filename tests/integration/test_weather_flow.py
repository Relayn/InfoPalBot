import pytest
import httpx
import html
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from sqlmodel import Session, select
from app.bot.handlers.info_requests import process_weather_command

from app.config import settings as app_settings
from app.database.models import Log, User as DBUser
from app.database.crud import create_user
from aiogram.types import Message, User as AiogramUser, Chat
from aiogram.filters import CommandObject


@pytest.mark.asyncio
async def test_weather_command_successful_flow(integration_session: Session):
    """
    Интеграционный тест: успешное выполнение команды /weather.
    """
    city_name = "Москва"
    telegram_user_id = 12345
    api_key = "fake_weather_key_success"
    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id, full_name="Test User")
    mock_message.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message.reply = AsyncMock()
    mock_message.answer = AsyncMock()
    mock_command_obj = MagicMock(spec=CommandObject, args=city_name)
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)
    mock_api_response_data = {
        "weather": [{"description": "ясно"}],
        "main": {"temp": 25.0, "feels_like": 24.0, "humidity": 60},
        "wind": {"speed": 5.0, "deg": 90},
        "name": "Moscow",
    }
    mock_httpx_response = MagicMock(spec=httpx.Response)
    mock_httpx_response.status_code = 200
    mock_httpx_response.json.return_value = mock_api_response_data
    mock_httpx_response.raise_for_status = MagicMock()
    original_weather_key = app_settings.WEATHER_API_KEY
    app_settings.WEATHER_API_KEY = api_key
    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = integration_session
    mock_session_context_manager.__exit__.return_value = None

    # Обновляем цели для patch
    with patch("app.api_clients.weather.httpx.AsyncClient") as MockAsyncWeatherClient, patch(
        "app.bot.handlers.info_requests.get_session", return_value=mock_session_context_manager
    ):
        mock_weather_client_instance = AsyncMock()
        mock_weather_client_instance.get.return_value = mock_httpx_response
        MockAsyncWeatherClient.return_value.__aenter__.return_value = (
            mock_weather_client_instance
        )
        await process_weather_command(mock_message, mock_command_obj)

    mock_message.reply.assert_any_call(
        f"Запрашиваю погоду для города <b>{html.escape(city_name)}</b>..."
    )
    log_entry = integration_session.exec(
        select(Log).where(Log.command == "/weather").where(Log.user_id == db_user.id)
    ).first()
    assert log_entry is not None
    assert log_entry.details == f"город: {city_name}, успех"
    app_settings.WEATHER_API_KEY = original_weather_key