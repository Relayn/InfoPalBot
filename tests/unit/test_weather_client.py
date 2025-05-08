import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from app.api_clients.weather import get_weather_data, BASE_OPENWEATHERMAP_URL
from app.config import Settings # Нам понадобится мокать settings

# --- Тесты для get_weather_data ---

@pytest.mark.asyncio
async def test_get_weather_data_success():
    """
    Тест: успешное получение данных о погоде.
    """
    city_name = "TestCity"
    api_key = "test_api_key"
    expected_weather_data = {
        "coord": {"lon": 10.99, "lat": 44.34},
        "weather": [{"id": 800, "main": "Clear", "description": "ясно", "icon": "01d"}],
        "main": {"temp": 25.0, "feels_like": 26.0, "temp_min": 23.0, "temp_max": 27.0},
        "wind": {"speed": 1.5, "deg": 350},
        "name": city_name,
    }

    # Мокируем объект настроек
    mock_settings = MagicMock(spec=Settings)
    mock_settings.WEATHER_API_KEY = api_key

    # Мокируем ответ от httpx.AsyncClient
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = expected_weather_data
    # mock_response.raise_for_status = MagicMock() # Можно так, или убедиться, что не вызывается при 200

    # Патчим httpx.AsyncClient и settings
    with patch('app.api_clients.weather.settings', mock_settings), \
         patch('httpx.AsyncClient') as MockAsyncClient: # Патчим класс AsyncClient

        # Настраиваем экземпляр клиента, который будет возвращен
        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get.return_value = mock_response
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance # Для async with

        # Вызываем тестируемую функцию
        result = await get_weather_data(city_name)

        # Проверяем вызовы и результат
        expected_params = {"q": city_name, "appid": api_key, "units": "metric", "lang": "ru"}
        mock_async_client_instance.get.assert_called_once_with(BASE_OPENWEATHERMAP_URL, params=expected_params)
        mock_response.raise_for_status.assert_called_once() # Убедимся, что проверка статуса была
        assert result == expected_weather_data


@pytest.mark.asyncio
async def test_get_weather_data_no_api_key():
    """
    Тест: API ключ не установлен.
    """
    city_name = "TestCity"
    mock_settings = MagicMock(spec=Settings)
    mock_settings.WEATHER_API_KEY = "" # Пустой API ключ

    with patch('app.api_clients.weather.settings', mock_settings), \
         patch('app.api_clients.weather.logger.error') as mock_logger_error: # Патчим логгер
        result = await get_weather_data(city_name)

        assert result is None
        mock_logger_error.assert_called_once_with("WEATHER_API_KEY не установлен в настройках.")


@pytest.mark.asyncio
async def test_get_weather_data_http_status_error_404():
    """
    Тест: ошибка HTTP 404 (город не найден).
    """
    city_name = "NonExistentCity"
    api_key = "test_api_key"
    error_response_data = {"cod": "404", "message": "city not found"}

    mock_settings = MagicMock(spec=Settings)
    mock_settings.WEATHER_API_KEY = api_key

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.text = '{"cod": "404", "message": "city not found"}'
    mock_response.json.return_value = error_response_data
    # Настраиваем raise_for_status, чтобы он вызывал HTTPStatusError
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        message="Not Found", request=MagicMock(), response=mock_response
    )

    with patch('app.api_clients.weather.settings', mock_settings), \
         patch('httpx.AsyncClient') as MockAsyncClient, \
         patch('app.api_clients.weather.logger.error') as mock_logger_error:

        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get.return_value = mock_response
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance

        result = await get_weather_data(city_name)

        expected_error_result = {"error": True, "status_code": 404, "message": "city not found"}
        assert result == expected_error_result
        mock_logger_error.assert_called_once()
        # Проверяем, что информация об ошибке залогирована
        args, _ = mock_logger_error.call_args
        assert f"Ошибка HTTP при запросе погоды для города '{city_name}'" in args[0]
        assert "404" in args[0]
        assert "city not found" in args[0]


@pytest.mark.asyncio
async def test_get_weather_data_request_error():
    """
    Тест: ошибка сети (RequestError).
    """
    city_name = "TestCity"
    api_key = "test_api_key"

    mock_settings = MagicMock(spec=Settings)
    mock_settings.WEATHER_API_KEY = api_key

    # Настраиваем get, чтобы он вызывал RequestError
    network_error = httpx.RequestError("Network error occurred", request=MagicMock())

    with patch('app.api_clients.weather.settings', mock_settings), \
         patch('httpx.AsyncClient') as MockAsyncClient, \
         patch('app.api_clients.weather.logger.error') as mock_logger_error:

        mock_async_client_instance = AsyncMock()
        # Мокируем get, чтобы он вызывал ошибку
        mock_async_client_instance.get.side_effect = network_error
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance

        result = await get_weather_data(city_name)

        expected_error_result = {"error": True, "message": "Сетевая ошибка при запросе к сервису погоды."}
        assert result == expected_error_result
        mock_logger_error.assert_called_once_with(f"Ошибка сети при запросе погоды для города '{city_name}': {network_error}")


@pytest.mark.asyncio
async def test_get_weather_data_unexpected_error():
    """
    Тест: непредвиденная ошибка при парсинге JSON или другая.
    """
    city_name = "TestCity"
    api_key = "test_api_key"

    mock_settings = MagicMock(spec=Settings)
    mock_settings.WEATHER_API_KEY = api_key

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    # Мокируем json(), чтобы он вызывал ошибку (например, если ответ невалидный JSON)
    original_exception = Exception("JSON decode error")
    mock_response.json.side_effect = original_exception
    # mock_response.raise_for_status = MagicMock() # Можно не мокать, если status_code 200

    with patch('app.api_clients.weather.settings', mock_settings), \
         patch('httpx.AsyncClient') as MockAsyncClient, \
         patch('app.api_clients.weather.logger.error') as mock_logger_error:

        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get.return_value = mock_response
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance

        result = await get_weather_data(city_name)

        expected_error_result = {"error": True, "message": "Неизвестная ошибка при получении данных о погоде."}
        assert result == expected_error_result
        mock_logger_error.assert_called_once()
        args, kwargs = mock_logger_error.call_args
        # Проверяем, что текст оригинальной ошибки (JSON decode error) попал в сообщение лога
        assert f"Непредвиденная ошибка при запросе погоды для города '{city_name}': {original_exception}" == args[0]
        # Проверяем, что exc_info=True было передано для подробного трейсбека
        assert kwargs.get('exc_info') is True