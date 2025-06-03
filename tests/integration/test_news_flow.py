import pytest # pytest остается
import httpx
import html
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from sqlmodel import Session, select # Session и select остаются

from app.bot.main import process_news_command
from app.config import settings as app_settings
from app.database.models import Log, User as DBUser
from app.database.crud import create_user
from aiogram.types import Message, User as AiogramUser, Chat

@pytest.mark.asyncio
async def test_news_command_successful_flow(integration_session: Session):
    """
    Интеграционный тест: успешное выполнение команды /news.
    Проверяет взаимодействие: бот -> API клиент -> мок API -> БД лог.
    """
    # 1. Настройка
    telegram_user_id = 23456
    api_key = "fake_news_key_success"

    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id, full_name="News User")
    mock_message.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message.reply = AsyncMock()
    mock_message.answer = AsyncMock()

    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)

    mock_api_response_data = {
        "status": "ok",
        "totalResults": 2,
        "articles": [
            {"title": "Новость 1 <script>alert(0)</script>", "url": "http://example.com/news1", "source": {"name": "Источник 1"}},
            {"title": "Новость 2", "url": "http://example.com/news2", "source": {"name": "Источник 2"}},
        ]
    }

    # 2. Патчинг
    mock_httpx_response = MagicMock(spec=httpx.Response)
    mock_httpx_response.status_code = 200
    mock_httpx_response.json.return_value = mock_api_response_data
    # Для NewsAPI raise_for_status не всегда вызывается, т.к. ошибки могут быть в JSON
    # Но лучше его оставить, если вдруг будет реальный HTTP error

    original_news_key = app_settings.NEWS_API_KEY
    app_settings.NEWS_API_KEY = api_key

    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = integration_session
    mock_session_context_manager.__exit__ = MagicMock(return_value=None)
    mock_generator = MagicMock()
    mock_generator.__next__.return_value = mock_session_context_manager

    with patch('app.api_clients.news.httpx.AsyncClient') as MockAsyncNewsClient, \
         patch('app.bot.main.get_session', return_value=mock_generator):

        mock_news_client_instance = AsyncMock()
        mock_news_client_instance.get.return_value = mock_httpx_response
        MockAsyncNewsClient.return_value.__aenter__.return_value = mock_news_client_instance

        # 3. Вызов
        await process_news_command(mock_message)

    # 4. Проверки
    mock_message.reply.assert_called_once_with("Запрашиваю последние главные новости для России...")

    # Проверяем вызов NewsAPI клиента (эндпоинт /top-headlines)
    expected_news_api_url = "https://newsapi.org/v2/top-headlines"
    expected_news_api_params = {"country": "ru", "pageSize": 5, "apiKey": api_key}
    mock_news_client_instance.get.assert_called_once_with(expected_news_api_url, params=expected_news_api_params)

    expected_lines = ["<b>📰 Последние главные новости (Россия):</b>"]
    title1_escaped = html.escape("Новость 1 <script>alert(0)</script>")
    expected_lines.append(f"1. <a href='http://example.com/news1'>{title1_escaped}</a> (Источник 1)")
    expected_lines.append("2. <a href='http://example.com/news2'>Новость 2</a> (Источник 2)")
    expected_text = "\n".join(expected_lines)
    mock_message.answer.assert_called_once_with(expected_text, disable_web_page_preview=True)

    log_entry = integration_session.exec(
        select(Log).where(Log.command == "/news").where(Log.user_id == db_user.id)
    ).first()
    assert log_entry is not None
    assert log_entry.details == "success"

    app_settings.NEWS_API_KEY = original_news_key


@pytest.mark.asyncio
async def test_news_command_api_error_flow(integration_session: Session):
    """
    Интеграционный тест: команда /news, API возвращает ошибку.
    """
    # 1. Настройка
    telegram_user_id = 34567
    api_key = "fake_news_key_error"

    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id, full_name="Error News User")
    mock_message.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message.reply = AsyncMock()
    mock_message.answer = AsyncMock()

    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)

    # Ошибка, возвращаемая в JSON от NewsAPI
    error_message_from_api = "Your API key is invalid or incorrect."
    mock_api_error_response_data = {
        "status": "error",
        "code": "apiKeyInvalid",
        "message": error_message_from_api
    }

    # 2. Патчинг
    mock_httpx_response = MagicMock(spec=httpx.Response)
    mock_httpx_response.status_code = 200 # NewsAPI может вернуть 200 OK, но с ошибкой в JSON
    mock_httpx_response.json.return_value = mock_api_error_response_data

    original_news_key = app_settings.NEWS_API_KEY
    app_settings.NEWS_API_KEY = api_key

    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = integration_session
    mock_session_context_manager.__exit__ = MagicMock(return_value=None)
    mock_generator = MagicMock()
    mock_generator.__next__.return_value = mock_session_context_manager

    with patch('app.api_clients.news.httpx.AsyncClient') as MockAsyncNewsClient, \
         patch('app.bot.main.get_session', return_value=mock_generator):

        mock_news_client_instance = AsyncMock()
        mock_news_client_instance.get.return_value = mock_httpx_response
        MockAsyncNewsClient.return_value.__aenter__.return_value = mock_news_client_instance

        # 3. Вызов
        await process_news_command(mock_message)

    # 4. Проверки
    mock_message.reply.assert_any_call("Запрашиваю последние главные новости для России...")
    mock_message.reply.assert_any_call(f"Не удалось получить новости: {html.escape(error_message_from_api)}")
    mock_message.answer.assert_not_called()

    log_entry = integration_session.exec(
        select(Log).where(Log.command == "/news").where(Log.user_id == db_user.id)
    ).first()
    assert log_entry is not None
    assert log_entry.details == f"api_error: {error_message_from_api[:100]}"

    app_settings.NEWS_API_KEY = original_news_key


@pytest.mark.asyncio
async def test_news_command_no_articles_flow(integration_session: Session):
    """
    Интеграционный тест: команда /news, API возвращает "ok", но нет статей.
    """
    # 1. Настройка
    telegram_user_id = 45678
    api_key = "fake_news_key_no_articles"

    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id, full_name="No News User")
    mock_message.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message.reply = AsyncMock()
    mock_message.answer = AsyncMock()

    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)

    mock_api_response_data = {
        "status": "ok",
        "totalResults": 0,
        "articles": [] # Пустой список статей
    }

    # 2. Патчинг
    mock_httpx_response = MagicMock(spec=httpx.Response)
    mock_httpx_response.status_code = 200
    mock_httpx_response.json.return_value = mock_api_response_data

    original_news_key = app_settings.NEWS_API_KEY
    app_settings.NEWS_API_KEY = api_key

    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = integration_session
    mock_session_context_manager.__exit__ = MagicMock(return_value=None)
    mock_generator = MagicMock()
    mock_generator.__next__.return_value = mock_session_context_manager

    with patch('app.api_clients.news.httpx.AsyncClient') as MockAsyncNewsClient, \
         patch('app.bot.main.get_session', return_value=mock_generator):

        mock_news_client_instance = AsyncMock()
        mock_news_client_instance.get.return_value = mock_httpx_response
        MockAsyncNewsClient.return_value.__aenter__.return_value = mock_news_client_instance

        # 3. Вызов
        await process_news_command(mock_message)

    # 4. Проверки
    mock_message.reply.assert_any_call("Запрашиваю последние главные новости для России...")
    mock_message.reply.assert_any_call("На данный момент нет главных новостей для отображения.")
    mock_message.answer.assert_not_called() # Используется reply для сообщения "нет новостей"

    log_entry = integration_session.exec(
        select(Log).where(Log.command == "/news").where(Log.user_id == db_user.id)
    ).first()
    assert log_entry is not None
    assert log_entry.details == "no_articles_found"

    app_settings.NEWS_API_KEY = original_news_key