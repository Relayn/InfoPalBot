import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from aiogram.types import Message, User as AiogramUser, CallbackQuery

from app.bot.handlers.subscription import (
    process_mysubscriptions_command,
    process_unsubscribe_command_start,
)
from app.database.models import User as DBUser
from tests.utils.mock_helpers import get_mock_session_context_manager, get_mock_fsm_context
from app.bot.fsm import SubscriptionStates


@pytest.mark.asyncio
async def test_mysubscriptions_command_no_subscriptions():
    """
    Тест: /mysubscriptions, когда у пользователя нет активных подписок.
    Покрывает ветку `if not subscriptions`.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=1001)

    mock_user = DBUser(id=1, telegram_id=1001)
    mock_session = MagicMock()
    mock_session_cm = get_mock_session_context_manager(mock_session)

    with patch(
        "app.bot.handlers.subscription.get_session", return_value=mock_session_cm
    ), patch(
        "app.bot.handlers.subscription.get_user_by_telegram_id", return_value=mock_user
    ), patch(
        "app.bot.handlers.subscription.get_subscriptions_by_user_id", return_value=[]
    ) as mock_get_subs:
        await process_mysubscriptions_command(mock_message)

        mock_get_subs.assert_called_once_with(ANY, mock_user.id)
        mock_message.answer.assert_called_once_with(
            "У вас пока нет активных подписок."
        )


@pytest.mark.asyncio
async def test_unsubscribe_command_start_no_subscriptions():
    """
    Тест: /unsubscribe, когда у пользователя нет активных подписок.
    Покрывает ветку `if not subscriptions`.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=1002)
    mock_state = AsyncMock()

    mock_user = DBUser(id=2, telegram_id=1002)
    mock_session = MagicMock()
    mock_session_cm = get_mock_session_context_manager(mock_session)

    with patch(
        "app.bot.handlers.subscription.get_session", return_value=mock_session_cm
    ), patch(
        "app.bot.handlers.subscription.get_user_by_telegram_id", return_value=mock_user
    ), patch(
        "app.bot.handlers.subscription.get_subscriptions_by_user_id", return_value=[]
    ) as mock_get_subs:
        await process_unsubscribe_command_start(mock_message, mock_state)

        mock_get_subs.assert_called_once_with(ANY, mock_user.id)
        mock_message.answer.assert_called_once_with(
            "У вас нет активных подписок для отмены."
        )

@pytest.mark.asyncio
async def test_city_for_weather_subscription_empty_message():
    """
    Тест: Пользователь отправляет пустое сообщение при вводе города для подписки на погоду.
    Покрывает ветку `if not city_name`.
    """
    mock_message = AsyncMock(spec=Message, text="  ")  # Пустое сообщение с пробелами
    mock_message.reply = AsyncMock()
    # Используем реальный FSMContext для корректной проверки состояния
    mock_state = await get_mock_fsm_context(
        initial_state=SubscriptionStates.entering_city_weather
    )

    from app.bot.handlers.subscription import process_city_for_weather_subscription

    await process_city_for_weather_subscription(mock_message, mock_state)

    mock_message.reply.assert_called_once_with("Название города не может быть пустым.")
    # Проверяем, что состояние не изменилось
    assert await mock_state.get_state() == SubscriptionStates.entering_city_weather


@pytest.mark.asyncio
async def test_city_for_events_subscription_unsupported_city():
    """
    Тест: Пользователь вводит неподдерживаемый город для подписки на события.
    Покрывает ветку `if not location_slug`.
    """
    unsupported_city = "Урюпинск"
    mock_message = AsyncMock(spec=Message, text=unsupported_city)
    mock_message.reply = AsyncMock()
    mock_state = await get_mock_fsm_context(
        initial_state=SubscriptionStates.entering_city_events,
        initial_data={"category": "concert"},
    )

    from app.bot.handlers.subscription import process_city_for_events_subscription

    await process_city_for_events_subscription(mock_message, mock_state)

    mock_message.reply.assert_called_once_with(
        f"Город '{unsupported_city}' не поддерживается."
    )
    # Проверяем, что состояние не изменилось
    assert await mock_state.get_state() == SubscriptionStates.entering_city_events


@pytest.mark.asyncio
async def test_unsubscribe_confirm_job_not_in_scheduler():
    """
    Тест: Отписка от подписки, для которой нет задачи в планировщике.
    Покрывает ветку `if scheduler.get_job(job_id)`.
    """
    sub_id = 555
    telegram_id = 1003
    mock_callback = AsyncMock(
        spec=CallbackQuery,
        data=f"unsubscribe_confirm:{sub_id}",
        from_user=MagicMock(id=telegram_id),
    )
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    mock_callback.answer = AsyncMock()

    mock_user = DBUser(id=3, telegram_id=telegram_id)
    mock_sub = MagicMock(user_id=mock_user.id)
    mock_session = MagicMock()
    mock_session.get.return_value = mock_sub
    mock_session_cm = get_mock_session_context_manager(mock_session)

    with patch(
        "app.bot.handlers.subscription.get_session", return_value=mock_session_cm
    ), patch(
        "app.bot.handlers.subscription.get_user_by_telegram_id", return_value=mock_user
    ), patch(
        "app.bot.handlers.subscription.db_delete_subscription"
    ) as mock_db_delete, patch(
        "app.bot.handlers.subscription.scheduler"
    ) as mock_scheduler, patch(
        "app.bot.handlers.subscription.logger.warning"
    ) as mock_logger:
        # Имитируем, что задачи в планировщике нет
        mock_scheduler.get_job.return_value = None

        from app.bot.handlers.subscription import process_unsubscribe_confirm

        await process_unsubscribe_confirm(mock_callback, AsyncMock())

        mock_db_delete.assert_called_once_with(ANY, sub_id)
        mock_scheduler.get_job.assert_called_once_with(f"sub_{sub_id}")
        mock_scheduler.remove_job.assert_not_called()  # Удаление не должно вызываться
        mock_logger.assert_called_once_with(
            f"Задача sub_{sub_id} для удаления не найдена в планировщике."
        )
        mock_callback.message.edit_text.assert_called_once_with(
            "Вы успешно отписались."
        )