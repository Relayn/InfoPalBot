import pytest
from unittest.mock import AsyncMock, patch, MagicMock
# ИЗМЕНЕНО: импортируем timezone
from datetime import datetime, timedelta, timezone
import httpx

from app.api_clients.news import get_latest_news, get_top_headlines
from app.config import settings


@pytest.mark.asyncio
async def test_get_latest_news_success_with_from_date():
    """Тест: успешное получение новостей с указанной датой."""
    query = "test"
    # ИЗМЕНЕНО: используем timezone-aware datetime
    from_date = datetime.now(timezone.utc) - timedelta(days=5)
    mock_response_data = {
        "status": "ok",
        "articles": [{"title": "Test Article"}],
    }
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data

    with patch("app.api_clients.news.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        articles = await get_latest_news(query=query, from_date=from_date)

    assert isinstance(articles, list)
    assert articles[0]["title"] == "Test Article"

# ... (остальной код без изменений, так как другие тесты не используют from_date напрямую) ...
@pytest.mark.asyncio
async def test_get_latest_news_success_without_from_date():
    """Тест: успешное получение новостей без указания даты (по умолчанию за последние 24 часа)."""
    query = "test"
    mock_response_data = {"status": "ok", "articles": [{"title": "Recent Article"}]}
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data

    with patch("app.api_clients.news.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        articles = await get_latest_news(query=query)

    assert isinstance(articles, list)
    assert articles[0]["title"] == "Recent Article"


@pytest.mark.asyncio
async def test_get_latest_news_api_returns_error_status():
    """Тест: API возвращает статус 'error'."""
    query = "error_query"
    mock_response_data = {"status": "error", "message": "API key invalid"}
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data

    with patch("app.api_clients.news.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        result = await get_latest_news(query=query)

    assert result == {"error": True, "message": "API key invalid"}


@pytest.mark.asyncio
async def test_get_latest_news_no_api_key():
    """Тест: ключ API не установлен в настройках."""
    original_key = settings.NEWS_API_KEY
    settings.NEWS_API_KEY = None
    result = await get_latest_news(query="any")
    settings.NEWS_API_KEY = original_key
    assert result == {"error": True, "message": "Ключ API для новостей не настроен."}


@pytest.mark.asyncio
async def test_get_latest_news_no_articles_with_from_date():
    """Тест: API возвращает пустой список статей для запроса с датой."""
    query = "no_results"
    # ИЗМЕНЕНО: используем timezone-aware datetime
    from_date = datetime.now(timezone.utc) - timedelta(days=1)
    mock_response_data = {"status": "ok", "articles": []}
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data

    with patch("app.api_clients.news.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        articles = await get_latest_news(query=query, from_date=from_date)

    assert articles == []


@pytest.mark.asyncio
async def test_get_latest_news_no_articles_without_from_date():
    """Тест: API возвращает пустой список статей для запроса без даты."""
    query = "no_results"
    mock_response_data = {"status": "ok", "articles": []}
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data

    with patch("app.api_clients.news.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        articles = await get_latest_news(query=query)

    assert articles == []


@pytest.mark.asyncio
async def test_get_latest_news_http_status_error():
    """Тест: возникает ошибка HTTP (например, 500 Internal Server Error)."""
    query = "http_error"
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        message="Server error", request=MagicMock(), response=mock_response
    )

    with patch("app.api_clients.news.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        result = await get_latest_news(query=query)

    assert result == {
        "error": True,
        "message": "Ошибка сервера новостей (статус 500).",
        "status_code": 500,
    }


@pytest.mark.asyncio
async def test_get_latest_news_request_error():
    """Тест: возникает ошибка сети (например, нет подключения)."""
    query = "network_error"
    with patch("app.api_clients.news.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.side_effect = httpx.RequestError(
            "Network error", request=MagicMock()
        )
        result = await get_latest_news(query=query)

    assert result == {"error": True, "message": "Ошибка сети при запросе новостей."}


@pytest.mark.asyncio
async def test_get_latest_news_json_decode_error():
    """Тест: ответ от API не является валидным JSON."""
    query = "json_error"
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("Invalid JSON")

    with patch("app.api_clients.news.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        result = await get_latest_news(query=query)

    assert result == {"error": True, "message": "Произошла непредвиденная ошибка."}


# --- Тесты для get_top_headlines ---


@pytest.mark.asyncio
async def test_get_top_headlines_success():
    """Тест: успешное получение главных новостей."""
    mock_response_data = {"status": "ok", "articles": [{"title": "Top Headline"}]}
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data

    with patch("app.api_clients.news.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        articles = await get_top_headlines(country="us")

    assert isinstance(articles, list)
    assert articles[0]["title"] == "Top Headline"


@pytest.mark.asyncio
async def test_get_top_headlines_no_category():
    """Тест: успешное получение главных новостей без указания категории."""
    mock_response_data = {"status": "ok", "articles": [{"title": "General Headline"}]}
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data

    with patch("app.api_clients.news.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        articles = await get_top_headlines(country="us", category=None)

    assert isinstance(articles, list)
    assert articles[0]["title"] == "General Headline"


@pytest.mark.asyncio
async def test_get_top_headlines_api_returns_error_status():
    """Тест: API возвращает статус 'error' для top-headlines."""
    mock_response_data = {"status": "error", "message": "Invalid category"}
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data

    with patch("app.api_clients.news.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        result = await get_top_headlines(country="us", category="invalid")

    assert result == {"error": True, "message": "Invalid category"}


@pytest.mark.asyncio
async def test_get_top_headlines_http_error():
    """Тест: возникает ошибка HTTP для top-headlines."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        message="Unauthorized", request=MagicMock(), response=mock_response
    )

    with patch("app.api_clients.news.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        result = await get_top_headlines(country="us")

    assert result == {
        "error": True,
        "message": "Ошибка сервера новостей (статус 401).",
        "status_code": 401,
    }


@pytest.mark.asyncio
async def test_get_top_headlines_no_api_key():
    """Тест: ключ API не установлен для top-headlines."""
    original_key = settings.NEWS_API_KEY
    settings.NEWS_API_KEY = None
    result = await get_top_headlines(country="us")
    settings.NEWS_API_KEY = original_key
    assert result == {"error": True, "message": "Ключ API для новостей не настроен."}


@pytest.mark.asyncio
async def test_get_top_headlines_request_error():
    """Тест: возникает ошибка сети для top-headlines."""
    with patch("app.api_clients.news.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.side_effect = httpx.RequestError(
            "Network error", request=MagicMock()
        )
        result = await get_top_headlines(country="us")

    assert result == {"error": True, "message": "Ошибка сети при запросе новостей."}


@pytest.mark.asyncio
async def test_get_top_headlines_json_decode_error():
    """Тест: ответ от API не является валидным JSON для top-headlines."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("Invalid JSON")

    with patch("app.api_clients.news.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
        result = await get_top_headlines(country="us")

    assert result == {"error": True, "message": "Произошла непредвиденная ошибка."}