"""
Unit-тесты для обработчиков из `app/bot/handlers/profile.py`.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, User as AiogramUser, CallbackQuery

from app.bot.handlers.profile import (
    cmd_profile,
    cq_back_to_profile_menu,
    cq_profile_close,
    cq_profile_subscriptions,
    cq_profile_delete_sub,
)
from app.database.models import User as DBUser, Subscription as DBSubscription
from tests.utils.mock_helpers import get_mock_session_context_manager


@pytest.fixture
def mock_db_user() -> DBUser:
    """Фикстура, возвращающая мок пользователя БД."""
    return DBUser(id=1, telegram_id=12345)


@pytest.fixture
def mock_subscription(mock_db_user: DBUser) -> DBSubscription:
    """Фикстура, возвращающая мок подписки."""
    return DBSubscription(
        id=101,
        user_id=mock_db_user.id,
        info_type="weather",
        details="Москва",
        frequency=12,
        user=mock_db_user,
    )


@pytest.mark.asyncio
async def test_cmd_profile(mock_db_user: DBUser):
    """Тест: команда /profile успешно отправляет приветственное сообщение."""
    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = MagicMock(id=mock_db_user.telegram_id)
    mock_message.answer = AsyncMock()

    mock_session = MagicMock()
    mock_session_cm = get_mock_session_context_manager(mock_session)

    with patch("app.bot.handlers.profile.get_session", return_value=mock_session_cm):
        await cmd_profile(mock_message)

        mock_message.answer.assert_called_once()
        args, kwargs = mock_message.answer.call_args
        assert "Добро пожаловать в ваш профиль!" in args[0]
        assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_cq_profile_close():
    """Тест: колбэк profile_close удаляет сообщение."""
    mock_callback = AsyncMock(spec=CallbackQuery)
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.delete = AsyncMock()
    mock_callback.answer = AsyncMock()

    await cq_profile_close(mock_callback)

    mock_callback.answer.assert_awaited_once_with("Закрываю меню...")
    mock_callback.message.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_cq_profile_close_handles_error():
    """Тест: колбэк profile_close обрабатывает ошибку удаления сообщения."""
    mock_callback = AsyncMock(spec=CallbackQuery)
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.delete.side_effect = TelegramBadRequest(
        method="deleteMessage", message="Message to delete not found"
    )
    mock_callback.answer = AsyncMock()

    with patch("app.bot.handlers.profile.logger.info") as mock_logger:
        await cq_profile_close(mock_callback)
        mock_logger.assert_called_once()


@pytest.mark.asyncio
@patch("app.bot.handlers.profile.show_profile_menu")
async def test_cq_back_to_profile_menu(mock_show_profile_menu):
    """Тест: колбэк back_to_profile_menu вызывает show_profile_menu."""
    mock_callback = AsyncMock(spec=CallbackQuery)
    # ИСПРАВЛЕНИЕ: Нужно явно создать вложенный мок для атрибута .message
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.answer = AsyncMock()

    await cq_back_to_profile_menu(mock_callback)

    mock_callback.answer.assert_awaited_once()
    mock_show_profile_menu.assert_awaited_once_with(
        mock_callback.message, "Returned to profile menu"
    )


@pytest.mark.asyncio
async def test_cq_profile_subscriptions_with_subs(
    mock_db_user: DBUser, mock_subscription: DBSubscription
):
    """Тест: отображение списка, когда у пользователя есть подписки."""
    mock_callback = AsyncMock(spec=CallbackQuery)
    mock_callback.from_user = MagicMock(id=mock_db_user.telegram_id)
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    mock_callback.answer = AsyncMock()

    mock_session = MagicMock()
    mock_session_cm = get_mock_session_context_manager(mock_session)
    mock_session.get.return_value = mock_db_user
    mock_session.query.return_value.where.return_value.all.return_value = [
        mock_subscription
    ]

    with patch(
        "app.bot.handlers.profile.get_session", return_value=mock_session_cm
    ), patch(
        "app.bot.handlers.profile.get_user_by_telegram_id", return_value=mock_db_user
    ), patch(
        "app.bot.handlers.profile.get_subscriptions_by_user_id",
        return_value=[mock_subscription],
    ):
        await cq_profile_subscriptions(mock_callback)

        mock_callback.message.edit_text.assert_called_once()
        args, kwargs = mock_callback.message.edit_text.call_args
        assert "Нажмите на подписку, чтобы удалить ее:" in args[0]


@pytest.mark.asyncio
async def test_cq_profile_subscriptions_no_subs(mock_db_user: DBUser):
    """Тест: отображение сообщения, когда у пользователя нет подписок."""
    mock_callback = AsyncMock(spec=CallbackQuery)
    mock_callback.from_user = MagicMock(id=mock_db_user.telegram_id)
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    mock_callback.answer = AsyncMock()

    mock_session = MagicMock()
    mock_session_cm = get_mock_session_context_manager(mock_session)

    with patch(
        "app.bot.handlers.profile.get_session", return_value=mock_session_cm
    ), patch(
        "app.bot.handlers.profile.get_user_by_telegram_id", return_value=mock_db_user
    ), patch(
        "app.bot.handlers.profile.get_subscriptions_by_user_id", return_value=[]
    ):
        await cq_profile_subscriptions(mock_callback)

        args, kwargs = mock_callback.message.edit_text.call_args
        assert "У вас нет активных подписок." in args[0]


@pytest.mark.asyncio
@patch("app.bot.handlers.profile.scheduler")
async def test_cq_profile_delete_sub_success(
    mock_scheduler, mock_db_user: DBUser, mock_subscription: DBSubscription
):
    """Тест: успешное удаление подписки."""
    mock_callback = AsyncMock(spec=CallbackQuery)
    mock_callback.from_user = MagicMock(id=mock_db_user.telegram_id)
    mock_callback.data = f"profile_delete_sub:{mock_subscription.id}"
    mock_callback.message = AsyncMock(spec=Message)
    mock_callback.message.edit_text = AsyncMock()
    mock_callback.answer = AsyncMock()

    mock_session = MagicMock()
    mock_session_cm = get_mock_session_context_manager(mock_session)
    mock_session.get.return_value = mock_subscription

    with patch(
        "app.bot.handlers.profile.get_session", return_value=mock_session_cm
    ), patch(
        "app.bot.handlers.profile.get_user_by_telegram_id", return_value=mock_db_user
    ), patch(
        "app.bot.handlers.profile.db_delete_subscription"
    ) as mock_db_delete, patch(
        "app.bot.handlers.profile.get_subscriptions_by_user_id", return_value=[]
    ):
        mock_scheduler.get_job.return_value = True  # Задача найдена

        await cq_profile_delete_sub(mock_callback)

        mock_db_delete.assert_called_once_with(mock_session, mock_subscription.id)
        mock_scheduler.remove_job.assert_called_once_with(f"sub_{mock_subscription.id}")
        args, _ = mock_callback.message.edit_text.call_args
        assert "Последняя подписка удалена." in args[0]


@pytest.mark.asyncio
async def test_cq_profile_delete_sub_not_owned(mock_db_user: DBUser):
    """Тест: попытка удалить чужую подписку."""
    mock_callback = AsyncMock(spec=CallbackQuery)
    mock_callback.from_user = MagicMock(id=mock_db_user.telegram_id)
    mock_callback.data = "profile_delete_sub:999"
    mock_callback.answer = AsyncMock()
    mock_callback.message = AsyncMock(spec=Message) # Добавим для полноты

    # Подписка принадлежит другому пользователю
    foreign_subscription = DBSubscription(id=999, user_id=99999)

    mock_session = MagicMock()
    mock_session_cm = get_mock_session_context_manager(mock_session)
    mock_session.get.return_value = foreign_subscription

    with patch(
        "app.bot.handlers.profile.get_session", return_value=mock_session_cm
    ), patch(
        "app.bot.handlers.profile.get_user_by_telegram_id", return_value=mock_db_user
    ), patch(
        "app.bot.handlers.profile.db_delete_subscription"
    ) as mock_db_delete:
        await cq_profile_delete_sub(mock_callback)

        # ИСПРАВЛЕНИЕ: Используем assert_any_call, так как сначала вызывается
        # answer("Удаляю подписку..."), а потом уже с ошибкой.
        mock_callback.answer.assert_any_call(
            "Ошибка: подписка не найдена.", show_alert=True
        )
        mock_db_delete.assert_not_called()