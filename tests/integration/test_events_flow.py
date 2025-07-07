import pytest
import httpx
import html
from unittest.mock import AsyncMock, MagicMock, patch
from sqlmodel import Session, select

# Импорт из нового модуля
from app.bot.handlers.info_requests import process_events_command

from app.database.models import Log
from app.database.crud import create_user
from aiogram.types import Message, User as AiogramUser, Chat
from aiogram.filters import CommandObject


@pytest.mark.asyncio
async def test_events_command_api_error_flow(integration_session: Session):
    """
    Интеграционный тест: команда /events, API KudaGo возвращает ошибку.
    """
    city_argument = "Санкт-Петербург"
    telegram_user_id = 45678
    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = MagicMock(spec=AiogramUser, id=telegram_user_id, full_name="Error Events User")
    mock_message.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message.reply = AsyncMock()
    mock_command_obj = MagicMock(spec=CommandObject, args=city_argument)
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)
    error_detail_from_api = "KudaGo service unavailable"
    mock_api_error_response_data = {"detail": error_detail_from_api}
    mock_httpx_response = MagicMock(spec=httpx.Response)
    mock_httpx_response.status_code = 503
    mock_httpx_response.json.return_value = mock_api_error_response_data
    mock_httpx_response.text = f'{{"detail": "{error_detail_from_api}"}}'
    mock_httpx_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        message="Service Unavailable", request=MagicMock(), response=mock_httpx_response
    )
    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = integration_session
    mock_session_context_manager.__exit__.return_value = None

    # Обновляем цели для patch
    with patch("app.api_clients.events.httpx.AsyncClient") as MockAsyncEventsClient, patch(
        "app.bot.handlers.info_requests.get_session", return_value=mock_session_context_manager
    ):
        mock_events_client_instance = AsyncMock()
        mock_events_client_instance.get.return_value = mock_httpx_response
        MockAsyncEventsClient.return_value.__aenter__.return_value = (
            mock_events_client_instance
        )
        await process_events_command(mock_message, mock_command_obj)

    mock_message.reply.assert_any_call(
        f"Запрашиваю события для города <b>{html.escape(city_argument)}</b>..."
    )
    mock_message.reply.assert_any_call(
        f"Не удалось получить события: {html.escape(error_detail_from_api)}"
    )
    log_entry = integration_session.exec(
        select(Log).where(Log.command == "/events").where(Log.user_id == db_user.id)
    ).first()
    assert log_entry is not None
    assert log_entry.details.startswith(f"город: {city_argument}, ошибка API:")