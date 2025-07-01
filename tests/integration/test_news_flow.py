import pytest
import httpx
import html
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from sqlmodel import Session, select

from app.bot.handlers.info_requests import process_news_command

from app.config import settings as app_settings
from app.database.models import Log, User as DBUser
from app.database.crud import create_user
from aiogram.types import Message, User as AiogramUser, Chat


@pytest.mark.asyncio
async def test_news_command_successful_flow(integration_session: Session):
    """
    Интеграционный тест: успешное выполнение команды /news.
    """
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
        "totalResults": 1,
        "articles": [{"title": "Новость 1", "url": "http://example.com/news1", "source": {"name": "Источник 1"}}],
    }
    mock_httpx_response = MagicMock(spec=httpx.Response)
    mock_httpx_response.status_code = 200
    mock_httpx_response.json.return_value = mock_api_response_data
    original_news_key = app_settings.NEWS_API_KEY
    app_settings.NEWS_API_KEY = api_key
    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = integration_session
    mock_session_context_manager.__exit__.return_value = None

    with patch("app.api_clients.news.httpx.AsyncClient") as MockAsyncNewsClient, patch(
        "app.bot.handlers.info_requests.get_session", return_value=mock_session_context_manager
    ):
        mock_news_client_instance = AsyncMock()
        mock_news_client_instance.get.return_value = mock_httpx_response
        MockAsyncNewsClient.return_value.__aenter__.return_value = (
            mock_news_client_instance
        )
        await process_news_command(mock_message)

    mock_message.reply.assert_called_once_with(
        "Запрашиваю последние главные новости для США..."
    )
    log_entry = integration_session.exec(
        select(Log).where(Log.command == "/news").where(Log.user_id == db_user.id)
    ).first()
    assert log_entry is not None
    assert log_entry.details == "success, country=us"
    app_settings.NEWS_API_KEY = original_news_key