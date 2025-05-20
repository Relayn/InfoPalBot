import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from typing import List, Dict, Any, Optional

from app.api_clients.news import get_latest_news, get_top_headlines, BASE_NEWSAPI_EVERYTHING_URL, \
    BASE_NEWSAPI_TOP_HEADLINES_URL
from app.config import Settings


# --- Тесты для get_latest_news (эндпоинт /everything) ---

@pytest.mark.asyncio
async def test_get_latest_news_success_with_from_date():
    """Тест успешного получения с параметром 'from'."""
    query = "AI"
    api_key = "test_news_api_key"
    expected_articles_data = {
        "status": "ok",
        "totalResults": 1,
        "articles": [{"title": "AI is amazing", "source": {"name": "Tech News"}}],
    }
    mock_settings = MagicMock(spec=Settings);
    mock_settings.NEWS_API_KEY = api_key
    mock_response = MagicMock(spec=httpx.Response);
    mock_response.status_code = 200
    mock_response.json.return_value = expected_articles_data

    with patch('app.api_clients.news.settings', mock_settings), \
            patch('httpx.AsyncClient') as MockAsyncClient:
        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get.return_value = mock_response
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance

        result = await get_latest_news(query=query, page_size=1, use_from_date=True)  # Явно указываем use_from_date

        assert result == expected_articles_data["articles"]
        call_args = mock_async_client_instance.get.call_args
        assert call_args is not None;
        assert 'params' in call_args.kwargs
        assert 'from' in call_args.kwargs['params']  # Проверяем наличие 'from'
        assert call_args.kwargs['params']['q'] == query


@pytest.mark.asyncio
async def test_get_latest_news_success_without_from_date():
    """Тест успешного получения БЕЗ параметра 'from'."""
    query = "AI"
    api_key = "test_news_api_key"
    expected_articles_data = {"status": "ok", "articles": [{"title": "AI is amazing"}]}
    mock_settings = MagicMock(spec=Settings);
    mock_settings.NEWS_API_KEY = api_key
    mock_response = MagicMock(spec=httpx.Response);
    mock_response.status_code = 200
    mock_response.json.return_value = expected_articles_data

    with patch('app.api_clients.news.settings', mock_settings), \
            patch('httpx.AsyncClient') as MockAsyncClient:
        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get.return_value = mock_response
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance

        result = await get_latest_news(query=query, page_size=1, use_from_date=False)  # Явно НЕ используем from_date

        assert result == expected_articles_data["articles"]
        call_args = mock_async_client_instance.get.call_args
        assert call_args is not None;
        assert 'params' in call_args.kwargs
        assert 'from' not in call_args.kwargs['params']  # Проверяем ОТСУТСТВИЕ 'from'
        assert call_args.kwargs['params']['q'] == query


@pytest.mark.asyncio
async def test_get_latest_news_api_returns_error_status():
    query = "error_query";
    api_key = "test_news_api_key"
    error_response_data = {"status": "error", "code": "apiKeyInvalid", "message": "Your API key is invalid."}
    mock_settings = MagicMock(spec=Settings);
    mock_settings.NEWS_API_KEY = api_key
    mock_response = MagicMock(spec=httpx.Response);
    mock_response.status_code = 200
    mock_response.json.return_value = error_response_data
    with patch('app.api_clients.news.settings', mock_settings), \
            patch('httpx.AsyncClient') as MockAsyncClient:
        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get.return_value = mock_response
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance
        result = await get_latest_news(query=query)
        expected_error = {"error": True, "code": "apiKeyInvalid", "message": "Your API key is invalid.",
                          "source": "NewsAPI/HTTP"}
        assert result == expected_error


@pytest.mark.asyncio
async def test_get_latest_news_no_api_key():
    mock_settings = MagicMock(spec=Settings);
    mock_settings.NEWS_API_KEY = ""
    with patch('app.api_clients.news.settings', mock_settings):
        result = await get_latest_news(query="test")
        assert result is None


# --- Тесты для get_top_headlines (эндпоинт /top-headlines) ---

@pytest.mark.asyncio
async def test_get_top_headlines_success():
    country = "us";
    category = "technology";
    api_key = "test_news_api_key"
    expected_articles_data = {"status": "ok", "articles": [{"title": "Top Tech Story"}]}
    mock_settings = MagicMock(spec=Settings);
    mock_settings.NEWS_API_KEY = api_key
    mock_response = MagicMock(spec=httpx.Response);
    mock_response.status_code = 200
    mock_response.json.return_value = expected_articles_data
    with patch('app.api_clients.news.settings', mock_settings), \
            patch('httpx.AsyncClient') as MockAsyncClient:
        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get.return_value = mock_response
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance
        result = await get_top_headlines(country=country, category=category, page_size=1)
        assert result == expected_articles_data["articles"]
        mock_async_client_instance.get.assert_called_once_with(
            BASE_NEWSAPI_TOP_HEADLINES_URL,
            params={"country": country, "category": category, "pageSize": 1, "apiKey": api_key}
        )


@pytest.mark.asyncio
async def test_get_top_headlines_no_category():
    country = "gb";
    api_key = "test_news_api_key"
    expected_articles_data = {"status": "ok", "articles": [{"title": "UK Top Story"}]}
    mock_settings = MagicMock(spec=Settings);
    mock_settings.NEWS_API_KEY = api_key
    mock_response = MagicMock(spec=httpx.Response);
    mock_response.status_code = 200
    mock_response.json.return_value = expected_articles_data
    with patch('app.api_clients.news.settings', mock_settings), \
            patch('httpx.AsyncClient') as MockAsyncClient:
        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get.return_value = mock_response
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance
        result = await get_top_headlines(country=country, page_size=1)
        assert result == expected_articles_data["articles"]
        mock_async_client_instance.get.assert_called_once_with(
            BASE_NEWSAPI_TOP_HEADLINES_URL,
            params={"country": country, "pageSize": 1, "apiKey": api_key}
        )


@pytest.mark.asyncio
async def test_get_top_headlines_api_returns_error_status():
    country = "de";
    api_key = "test_news_api_key"
    error_response_data = {"status": "error", "code": "sourcesUnavailable", "message": "No sources found."}
    mock_settings = MagicMock(spec=Settings);
    mock_settings.NEWS_API_KEY = api_key
    mock_response = MagicMock(spec=httpx.Response);
    mock_response.status_code = 200
    mock_response.json.return_value = error_response_data
    with patch('app.api_clients.news.settings', mock_settings), \
            patch('httpx.AsyncClient') as MockAsyncClient:
        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get.return_value = mock_response
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance
        result = await get_top_headlines(country=country)
        expected_error = {"error": True, "code": "sourcesUnavailable", "message": "No sources found.",
                          "source": "NewsAPI/HTTP"}
        assert result == expected_error


@pytest.mark.asyncio
async def test_get_top_headlines_http_error():
    country = "fr";
    api_key = "test_news_api_key"
    mock_settings = MagicMock(spec=Settings);
    mock_settings.NEWS_API_KEY = api_key
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    # Создаем ошибку, которую должен выбросить httpx.get при HTTPStatusError
    # Важно, чтобы эта ошибка была выброшена ДО вызова response.json() в коде клиента
    http_error = httpx.HTTPStatusError(
        message="Server Error", request=MagicMock(spec=httpx.Request), response=mock_response
    )

    with patch('app.api_clients.news.settings', mock_settings), \
            patch('httpx.AsyncClient') as MockAsyncClient:
        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get.side_effect = http_error  # get() теперь выбрасывает ошибку
        MockAsyncClient.return_value.__aenter__.return_value = mock_async_client_instance

        result = await get_top_headlines(country=country)

        # Ожидаем, что наш клиент поймает HTTPStatusError и вернет соответствующий словарь
        expected_error = {"error": True, "message": "Ошибка HTTP: 500", "status_code": 500, "source": "HTTP"}
        assert result == expected_error