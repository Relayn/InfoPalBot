import pytest
import httpx
import html
import time
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from sqlmodel import Session, select
from app.bot.main import process_events_command
from app.config import settings as app_settings
from app.database.models import Log, User as DBUser
from app.database.crud import create_user
from app.bot.constants import KUDAGO_LOCATION_SLUGS
from aiogram.types import Message, User as AiogramUser, Chat
from aiogram.filters import CommandObject


@pytest.mark.asyncio
async def test_events_command_successful_flow(integration_session: Session):
    # ... (код этого теста, он у тебя есть и проходит) ...
    pass


@pytest.mark.asyncio
async def test_events_command_api_error_flow(integration_session: Session):
    """
    Интеграционный тест: команда /events, API KudaGo возвращает ошибку.
    """
    city_argument = "Санкт-Петербург"
    expected_location_slug = KUDAGO_LOCATION_SLUGS[city_argument.lower()]
    telegram_user_id = 45678

    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = MagicMock(
        spec=AiogramUser, id=telegram_user_id, full_name="Error Events User"
    )
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

    current_timestamp = int(time.time())

    with patch(
        "app.api_clients.events.httpx.AsyncClient"
    ) as MockAsyncEventsClient, patch(
        "app.bot.main.get_session", return_value=mock_session_context_manager
    ), patch(
        "app.api_clients.events.time.time", return_value=float(current_timestamp)
    ):
        mock_events_client_instance = AsyncMock()
        mock_events_client_instance.get.return_value = mock_httpx_response
        MockAsyncEventsClient.return_value.__aenter__.return_value = (
            mock_events_client_instance
        )

        await process_events_command(mock_message, mock_command_obj)

    mock_message.reply.assert_any_call(
        f"Запрашиваю актуальные события для города <b>{html.escape(city_argument)}</b>..."
    )
    mock_message.reply.assert_any_call(
        f"Не удалось получить события: {html.escape(error_detail_from_api)}"
    )

    log_entry = integration_session.exec(
        select(Log).where(Log.command == "/events").where(Log.user_id == db_user.id)
    ).first()
    assert log_entry is not None
    assert log_entry.details.startswith(f"город: {city_argument}, ошибка API:")
    assert error_detail_from_api in log_entry.details


@pytest.mark.asyncio
async def test_events_command_no_events_found_flow(integration_session: Session):
    """
    Интеграционный тест: команда /events, API KudaGo не находит событий.
    """
    city_argument = "Казань"
    expected_location_slug = KUDAGO_LOCATION_SLUGS[city_argument.lower()]
    telegram_user_id = 56789

    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = MagicMock(
        spec=AiogramUser, id=telegram_user_id, full_name="No Events User"
    )
    mock_message.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message.reply = AsyncMock()

    mock_command_obj = MagicMock(spec=CommandObject, args=city_argument)
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)

    mock_api_response_data = {"count": 0, "results": []}

    mock_httpx_response = MagicMock(spec=httpx.Response)
    mock_httpx_response.status_code = 200
    mock_httpx_response.json.return_value = mock_api_response_data
    mock_httpx_response.raise_for_status = MagicMock()

    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = integration_session
    mock_session_context_manager.__exit__.return_value = None

    current_timestamp = int(time.time())

    with patch(
        "app.api_clients.events.httpx.AsyncClient"
    ) as MockAsyncEventsClient, patch(
        "app.bot.main.get_session", return_value=mock_session_context_manager
    ), patch(
        "app.api_clients.events.time.time", return_value=float(current_timestamp)
    ):
        mock_events_client_instance = AsyncMock()
        mock_events_client_instance.get.return_value = mock_httpx_response
        MockAsyncEventsClient.return_value.__aenter__.return_value = (
            mock_events_client_instance
        )

        await process_events_command(mock_message, mock_command_obj)

    mock_message.reply.assert_any_call(
        f"Запрашиваю актуальные события для города <b>{html.escape(city_argument)}</b>..."
    )
    mock_message.reply.assert_any_call(
        f"Не найдено актуальных событий для города <b>{html.escape(city_argument)}</b>."
    )

    log_entry = integration_session.exec(
        select(Log).where(Log.command == "/events").where(Log.user_id == db_user.id)
    ).first()
    assert log_entry is not None
    assert log_entry.details == f"город: {city_argument}, не найдено"


@pytest.mark.asyncio
async def test_events_command_unknown_city_flow(integration_session: Session):
    """
    Интеграционный тест: команда /events с неподдерживаемым городом.
    """
    unknown_city = "Урюпинск"
    telegram_user_id = 67890

    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = MagicMock(
        spec=AiogramUser, id=telegram_user_id, full_name="Unknown City User"
    )
    mock_message.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message.reply = AsyncMock()

    mock_command_obj = MagicMock(spec=CommandObject, args=unknown_city)
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)

    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = integration_session
    mock_session_context_manager.__exit__.return_value = None

    with patch(
        "app.api_clients.events.httpx.AsyncClient"
    ) as MockAsyncEventsClient, patch(
        "app.bot.main.get_session", return_value=mock_session_context_manager
    ):
        mock_events_client_instance = (
            MockAsyncEventsClient.return_value.__aenter__.return_value
        )
        await process_events_command(mock_message, mock_command_obj)

    mock_message.reply.assert_called_once_with(
        f"К сожалению, не знаю событий для города '{html.escape(unknown_city)}'...\nПопробуйте: Москва, Санкт-Петербург..."
    )
    mock_events_client_instance.get.assert_not_called()

    log_entry = integration_session.exec(
        select(Log).where(Log.command == "/events").where(Log.user_id == db_user.id)
    ).first()
    assert log_entry is not None
    assert log_entry.details == f"город: {unknown_city}, город не поддерживается"


@pytest.mark.asyncio
async def test_events_command_no_city_argument_flow(integration_session: Session):
    """
    Интеграционный тест: команда /events без указания города.
    """
    telegram_user_id = 78901

    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = MagicMock(
        spec=AiogramUser, id=telegram_user_id, full_name="No Arg User"
    )
    mock_message.chat = MagicMock(spec=Chat, id=telegram_user_id)
    mock_message.reply = AsyncMock()

    mock_command_obj = MagicMock(spec=CommandObject, args=None)
    db_user = create_user(session=integration_session, telegram_id=telegram_user_id)

    mock_session_context_manager = MagicMock()
    mock_session_context_manager.__enter__.return_value = integration_session
    mock_session_context_manager.__exit__.return_value = None

    with patch(
        "app.api_clients.events.httpx.AsyncClient"
    ) as MockAsyncEventsClient, patch(
        "app.bot.main.get_session", return_value=mock_session_context_manager
    ):
        mock_events_client_instance = (
            MockAsyncEventsClient.return_value.__aenter__.return_value
        )
        await process_events_command(mock_message, mock_command_obj)

    mock_message.reply.assert_called_once_with(
        "Пожалуйста, укажите город...\nДоступные города: Москва, Санкт-Петербург..."
    )
    mock_events_client_instance.get.assert_not_called()

    log_entry = integration_session.exec(
        select(Log).where(Log.command == "/events").where(Log.user_id == db_user.id)
    ).first()
    assert log_entry is not None
    assert log_entry.details == "Город не указан"
