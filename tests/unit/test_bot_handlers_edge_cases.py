import pytest
import html
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from app.bot.handlers.info_requests import process_news_command, process_events_command
from app.bot.handlers.subscription import (
    process_info_type_choice,
    process_city_for_weather_subscription,
    process_frequency_choice,
    process_unsubscribe_confirm,
)
from app.bot.fsm import SubscriptionStates
from app.bot.constants import INFO_TYPE_NEWS, INFO_TYPE_WEATHER
from app.database.models import User as DBUser, Subscription as DBSubscription
from aiogram.types import Message, User as AiogramUser, Chat, CallbackQuery
from tests.utils.mock_helpers import get_mock_fsm_context

# --- Тесты для info_requests.py ---


@pytest.mark.asyncio
@patch("app.bot.handlers.info_requests.get_top_headlines")
async def test_process_news_command_api_error_response(mock_get_headlines):
    """Тест: /news, когда API новостей возвращает словарь с ошибкой."""
    mock_message = AsyncMock(spec=Message)
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(id=123)
    error_message = "Your API key is invalid."
    mock_get_headlines.return_value = {"error": True, "message": error_message}

    with patch("app.bot.handlers.info_requests.get_session"), patch(
        "app.bot.handlers.info_requests.log_user_action"
    ):
        await process_news_command(mock_message)

        mock_message.reply.assert_any_call(
            f"Не удалось получить новости: {html.escape(error_message)}"
        )


@pytest.mark.asyncio
@patch("app.bot.handlers.info_requests.get_kudago_events")
async def test_process_events_command_no_events_found(mock_get_events):
    """Тест: /events, когда API событий возвращает пустой список."""
    mock_message = AsyncMock(spec=Message)
    mock_message.reply = AsyncMock()
    mock_message.from_user = MagicMock(id=123)
    city_arg = "Москва"
    mock_command = MagicMock(args=city_arg)
    mock_get_events.return_value = []  # Пустой список

    with patch("app.bot.handlers.info_requests.get_session"), patch(
        "app.bot.handlers.info_requests.log_user_action"
    ):
        await process_events_command(mock_message, mock_command)

        mock_message.reply.assert_any_call(
            f"Не найдено актуальных событий для города <b>{html.escape(city_arg)}</b>."
        )


# --- Тесты для subscription.py ---


@pytest.mark.asyncio
async def test_process_info_type_choice_already_subscribed_to_news():
    """Тест: Пользователь пытается подписаться на новости, на которые уже подписан."""
    mock_callback = AsyncMock(spec=CallbackQuery)
    mock_callback.from_user = MagicMock(id=456)
    mock_callback.data = f"subscribe_type:{INFO_TYPE_NEWS}"
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    fsm_context = await get_mock_fsm_context(
        initial_state=SubscriptionStates.choosing_info_type
    )

    with patch("app.bot.handlers.subscription.get_session"), patch(
        "app.bot.handlers.subscription.get_user_by_telegram_id",
        return_value=MagicMock(id=1),
    ), patch(
        "app.bot.handlers.subscription.get_subscription_by_user_and_type",
        return_value=MagicMock(),  # Имитируем, что подписка найдена
    ), patch(
        "app.bot.handlers.subscription.log_user_action"
    ):
        await process_info_type_choice(mock_callback, fsm_context)

        mock_callback.message.edit_text.assert_called_once_with(
            "Вы уже подписаны на 'Новости'."
        )
        assert await fsm_context.get_state() is None  # FSM должен быть сброшен


@pytest.mark.asyncio
async def test_process_city_for_weather_already_subscribed():
    """Тест: Пользователь вводит город для подписки на погоду, на который уже подписан."""
    city_name = "Москва"
    mock_message = AsyncMock(spec=Message, text=city_name)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(id=456)
    fsm_context = await get_mock_fsm_context(
        initial_state=SubscriptionStates.entering_city_weather
    )

    with patch("app.bot.handlers.subscription.get_session"), patch(
        "app.bot.handlers.subscription.get_user_by_telegram_id",
        return_value=MagicMock(id=1),
    ), patch(
        "app.bot.handlers.subscription.get_subscription_by_user_and_type",
        return_value=MagicMock(),  # Имитируем, что подписка найдена
    ):
        await process_city_for_weather_subscription(mock_message, fsm_context)

        mock_message.answer.assert_called_once_with(
            f"Вы уже подписаны на погоду в городе '{html.escape(city_name)}'."
        )
        assert await fsm_context.get_state() is None  # FSM должен быть сброшен


@pytest.mark.asyncio
@patch("app.bot.handlers.subscription.db_create_subscription")
@patch("app.bot.handlers.subscription.scheduler")
async def test_process_frequency_choice_scheduler_fails(
    mock_scheduler, mock_db_create
):
    """Тест: Создание подписки, но планировщик выдает ошибку при добавлении задачи."""
    mock_callback = AsyncMock(spec=CallbackQuery, data="frequency:6")
    mock_callback.from_user = MagicMock(id=789)
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    mock_callback.answer = AsyncMock()  # <--- ИСПРАВЛЕНИЕ
    fsm_context = await get_mock_fsm_context(
        initial_state=SubscriptionStates.choosing_frequency,
        initial_data={"info_type": INFO_TYPE_WEATHER, "details": "London"},
    )
    mock_db_create.return_value = MagicMock(id=55)
    mock_scheduler.add_job.side_effect = Exception("Scheduler is down")

    with patch("app.bot.handlers.subscription.get_session"), patch(
        "app.bot.handlers.subscription.get_user_by_telegram_id",
        return_value=MagicMock(id=2),
    ), patch("app.bot.handlers.subscription.log_user_action"):
        await process_frequency_choice(mock_callback, fsm_context)

        mock_callback.message.edit_text.assert_called_once_with(
            "Подписка создана, но произошла ошибка с ее активацией. Обратитесь к администратору."
        )
        assert await fsm_context.get_state() is None


@pytest.mark.asyncio
async def test_process_unsubscribe_confirm_sub_not_found():
    """Тест: Попытка отписаться от несуществующей подписки."""
    mock_callback = AsyncMock(spec=CallbackQuery, data="unsubscribe_confirm:999")
    mock_callback.from_user = MagicMock(id=101)
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    mock_callback.answer = AsyncMock()  # <--- ИСПРАВЛЕНИЕ

    with patch("app.bot.handlers.subscription.get_session") as mock_get_session, patch(
        "app.bot.handlers.subscription.get_user_by_telegram_id",
        return_value=MagicMock(id=3),
    ), patch("app.bot.handlers.subscription.scheduler") as mock_scheduler:
        # Имитируем, что sub_to_delete не найден в БД
        mock_session = MagicMock()
        mock_session.get.return_value = None
        mock_get_session.return_value.__enter__.return_value = mock_session

        await process_unsubscribe_confirm(mock_callback, ANY)

        mock_callback.message.edit_text.assert_called_with(
            "Ошибка: подписка не найдена."
        )
        mock_scheduler.remove_job.assert_not_called()