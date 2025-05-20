import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
import time

from app.api_clients.events import get_kudago_events, BASE_KUDAGO_API_URL
# KudaGo API не требует ключа, поэтому мокировать settings не нужно

# --- Тесты для get_kudago_events ---

@pytest.mark.asyncio
async def test_get_kudago_events_success():
    location = "msk"
    page_size = 2
    fields = "id,title"
    categories = "concert"
    expected_events_data = {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [{"id": 123, "title": "Большой концерт"}],
    }

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = expected_events_data
    # mock_response.raise_for_status = MagicMock() # Вызывается, если статус не 2xx

    with patch('httpx.AsyncClient') as MockAsyncClient:
        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get.return_value = mock_response
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance

        # Мокируем time.time() для предсказуемого actual_since
        current_timestamp = int(time.time())
        with patch('app.api_clients.events.time.time', return_value=float(current_timestamp)):
            result = await get_kudago_events(
                location=location,
                page_size=page_size,
                fields=fields,
                categories=categories
            )

            assert result == expected_events_data["results"]
            expected_params = {
                "location": location,
                "page_size": page_size,
                "fields": fields,
                "actual_since": current_timestamp,
                "text_format": "text",
                "order_by": "dates",
                "categories": categories,
            }
            expected_url = f"{BASE_KUDAGO_API_URL}/events/"
            mock_async_client_instance.get.assert_called_once_with(
                expected_url,
                params=expected_params,
                headers={"Accept-Language": "ru-RU,ru;q=0.9"}
            )
            mock_response.raise_for_status.assert_called_once()


@pytest.mark.asyncio
async def test_get_kudago_events_no_categories():
    """Тест успешного получения событий без указания категорий."""
    location = "spb"
    expected_results = [{"id": 456, "title": "Выставка"}]
    mock_response_data = {"results": expected_results}
    mock_response = MagicMock(spec=httpx.Response, status_code=200)
    mock_response.json.return_value = mock_response_data

    with patch('httpx.AsyncClient') as MockAsyncClient:
        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get.return_value = mock_response
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance
        current_timestamp = int(time.time()) # Для actual_since
        with patch('app.api_clients.events.time.time', return_value=float(current_timestamp)):
            result = await get_kudago_events(location=location, page_size=1, fields="id,title") # categories=None

            assert result == expected_results
            call_args = mock_async_client_instance.get.call_args
            assert 'categories' not in call_args.kwargs['params'] # Проверяем, что categories не переданы


@pytest.mark.asyncio
async def test_get_kudago_events_api_returns_no_results_key():
    """Тест: API KudaGo вернул JSON без ключа 'results'."""
    location = "msk"
    # Ответ без ключа "results"
    malformed_response_data = {"count": 0, "next": None, "previous": None}
    mock_response = MagicMock(spec=httpx.Response, status_code=200)
    mock_response.json.return_value = malformed_response_data

    with patch('httpx.AsyncClient') as MockAsyncClient:
        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get.return_value = mock_response
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance
        result = await get_kudago_events(location=location)
        expected_error = {"error": True, "message": "Некорректный формат ответа от KudaGo API.", "source": "KudaGo API Format"}
        assert result == expected_error


@pytest.mark.asyncio
async def test_get_kudago_events_http_status_error_404_with_detail():
    """Тест: ошибка HTTP 404 от KudaGo с полем 'detail'."""
    location = "nonexistent_city_slug"
    error_response_data = {"detail": "Not found."} # Типичный ответ KudaGo при 404
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.text = '{"detail": "Not found."}'
    mock_response.json.return_value = error_response_data
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        message="Not Found", request=MagicMock(), response=mock_response
    )

    with patch('httpx.AsyncClient') as MockAsyncClient:
        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get.return_value = mock_response
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance
        result = await get_kudago_events(location=location)
        expected_error = {"error": True, "message": "Not found.", "status_code": 404, "source": "KudaGo HTTP"}
        assert result == expected_error


@pytest.mark.asyncio
async def test_get_kudago_events_request_error():
    """Тест: ошибка сети (RequestError)."""
    location = "msk"
    network_error = httpx.RequestError("Network error occurred", request=MagicMock())
    with patch('httpx.AsyncClient') as MockAsyncClient:
        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get.side_effect = network_error
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance
        result = await get_kudago_events(location=location)
        expected_error = {"error": True, "message": "Сетевая ошибка при запросе к сервису событий.", "source": "Network"}
        assert result == expected_error