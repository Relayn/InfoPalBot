import pytest  # pytest остается
import httpx
import html
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from sqlmodel import Session, select

from app.bot.main import process_weather_command
from app.config import settings as app_settings
from app.database.models import Log, User as DBUser
from app.database.crud import create_user
from aiogram.types import Message, User as AiogramUser, Chat
from aiogram.filters import CommandObject


@pytest.mark.asyncio
async def test_weather_command_successful_flow(integration_session: Session):
    """
    Интеграционный тест: успешное выполнение команды /weather.
    Проверяет взаимодействие: бот -> API клиент -> мок API -> БД лог.
    """
    # 1. Настройка
    city_name = "Москва"
    telegram_user_id = 12345
    api_key = "fake_weather_key_success"  # Используем отдельный ключ для теста

    # Мок сообщения от пользователя
    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = MagicMock(
        spec=AiogramUser, id=telegram_user_id, full_name="Test User"
    )
    mock_message.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message.reply = AsyncMock()
    mock_message.answer = AsyncMock()

    # Мок объекта команды
    mock_command_obj = MagicMock(spec=CommandObject, args=city_name)

    # Создадим пользователя в БД для теста логирования
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)

    # Мок ответа от API погоды
    mock_api_response_data = {
        "weather": [{"description": "ясно"}],
        "main": {"temp": 25.0, "feels_like": 24.0, "humidity": 60},
        "wind": {"speed": 5.0, "deg": 90},  # deg 90 = Восточный
        "name": "Moscow",
    }

    # 2. Патчинг
    mock_httpx_response = MagicMock(spec=httpx.Response)
    mock_httpx_response.status_code = 200
    mock_httpx_response.json.return_value = mock_api_response_data
    mock_httpx_response.raise_for_status = MagicMock()

    original_weather_key = app_settings.WEATHER_API_KEY
    app_settings.WEATHER_API_KEY = api_key

    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = integration_session
    mock_session_context_manager.__exit__.return_value = None

    with patch(
        "app.api_clients.weather.httpx.AsyncClient"
    ) as MockAsyncWeatherClient, patch(
        "app.bot.main.get_session", return_value=mock_session_context_manager
    ):
        mock_weather_client_instance = AsyncMock()
        mock_weather_client_instance.get.return_value = mock_httpx_response
        MockAsyncWeatherClient.return_value.__aenter__.return_value = (
            mock_weather_client_instance
        )

        # 3. Вызов тестируемой функции (обработчика команды)
        await process_weather_command(mock_message, mock_command_obj)

    # 4. Проверки
    mock_message.reply.assert_any_call(
        f"Запрашиваю погоду для города <b>{html.escape(city_name)}</b>..."
    )

    expected_weather_api_url = "https://api.openweathermap.org/data/2.5/weather"
    expected_weather_api_params = {
        "q": city_name,
        "appid": api_key,
        "units": "metric",
        "lang": "ru",
    }
    mock_weather_client_instance.get.assert_called_once_with(
        expected_weather_api_url, params=expected_weather_api_params
    )

    expected_response_text = (
        f"<b>Погода в городе {html.escape(mock_api_response_data['name'])}:</b>\n"
        f"🌡️ Температура: {mock_api_response_data['main']['temp']}°C (ощущается как {mock_api_response_data['main']['feels_like']}°C)\n"
        f"💧 Влажность: {mock_api_response_data['main']['humidity']}%\n"
        f"💨 Ветер: {mock_api_response_data['wind']['speed']} м/с, Восточный\n"
        f"☀️ Описание: Ясно"
    )
    mock_message.answer.assert_called_once_with(expected_response_text)

    log_entry = integration_session.exec(
        select(Log).where(Log.command == "/weather").where(Log.user_id == db_user.id)
    ).first()
    assert log_entry is not None
    assert log_entry.details == f"город: {city_name}, успех"

    app_settings.WEATHER_API_KEY = original_weather_key


@pytest.mark.asyncio
async def test_weather_command_city_not_found_flow(integration_session: Session):
    """
    Интеграционный тест: команда /weather, город не найден API.
    Проверяет взаимодействие: бот -> API клиент -> мок API (ошибка) -> БД лог.
    """
    # 1. Настройка
    city_name = "НесуществующийГород"
    telegram_user_id = 54321
    api_key = "fake_weather_key_error"

    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = MagicMock(
        spec=AiogramUser, id=telegram_user_id, full_name="Error User"
    )
    mock_message.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message.reply = AsyncMock()
    mock_message.answer = AsyncMock()

    mock_command_obj = MagicMock(spec=CommandObject, args=city_name)

    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)

    mock_api_error_response_data = {"cod": "404", "message": "city not found"}

    # 2. Патчинг
    mock_httpx_response = MagicMock(spec=httpx.Response)
    mock_httpx_response.status_code = 404
    mock_httpx_response.json.return_value = mock_api_error_response_data
    mock_httpx_response.text = '{"cod": "404", "message": "city not found"}'
    mock_httpx_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        message="Not Found", request=MagicMock(), response=mock_httpx_response
    )

    original_weather_key = app_settings.WEATHER_API_KEY
    app_settings.WEATHER_API_KEY = api_key

    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = integration_session
    mock_session_context_manager.__exit__.return_value = None

    with patch(
        "app.api_clients.weather.httpx.AsyncClient"
    ) as MockAsyncWeatherClient, patch(
        "app.bot.main.get_session", return_value=mock_session_context_manager
    ):
        mock_weather_client_instance = AsyncMock()
        mock_weather_client_instance.get.return_value = mock_httpx_response
        MockAsyncWeatherClient.return_value.__aenter__.return_value = (
            mock_weather_client_instance
        )

        # 3. Вызов
        await process_weather_command(mock_message, mock_command_obj)

    # 4. Проверки
    mock_message.reply.assert_any_call(
        f"Запрашиваю погоду для города <b>{html.escape(city_name)}</b>..."
    )

    expected_weather_api_url = "https://api.openweathermap.org/data/2.5/weather"
    expected_weather_api_params = {
        "q": city_name,
        "appid": api_key,
        "units": "metric",
        "lang": "ru",
    }
    mock_weather_client_instance.get.assert_called_once_with(
        expected_weather_api_url, params=expected_weather_api_params
    )

    mock_message.reply.assert_any_call(
        f"Город <b>{html.escape(city_name)}</b> не найден..."
    )
    mock_message.answer.assert_not_called()

    log_entry = integration_session.exec(
        select(Log).where(Log.command == "/weather").where(Log.user_id == db_user.id)
    ).first()
    assert log_entry is not None
    assert log_entry.details == f"город: {city_name}, ошибка API: city not found"

    app_settings.WEATHER_API_KEY = original_weather_key
