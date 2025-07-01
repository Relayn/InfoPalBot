import pytest
import html
from unittest.mock import AsyncMock, MagicMock, patch

from app.bot.handlers.basic import (
    process_start_command,
    process_help_command,
    cmd_cancel_any_state,
)
from app.database.models import User as DBUser
from aiogram.types import Message, User as AiogramUser, Chat, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from app.bot.fsm import SubscriptionStates

# --- Тесты для process_start_command ---

@pytest.mark.asyncio
async def test_process_start_command_new_user():
    """
    Тест: команда /start для нового пользователя.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=12345, full_name="Test User")
    mock_state = AsyncMock(spec=FSMContext)

    # Обновляем цели для patch
    with patch("app.bot.handlers.basic.get_session"), patch(
        "app.bot.handlers.basic.create_user_if_not_exists"
    ) as mock_create_user, patch(
        "app.bot.handlers.basic.log_user_action"
    ) as mock_log_action:
        await process_start_command(mock_message, mock_state)

        mock_state.clear.assert_called_once()
        mock_create_user.assert_called_once()
        mock_log_action.assert_called_once()
        expected_reply_text = (
            f"Привет, {mock_message.from_user.full_name}! Я InfoPalBot. "
            f"Я могу предоставить тебе актуальную информацию.\n"
            f"Используй /help, чтобы увидеть список доступных команд."
        )
        mock_message.answer.assert_called_once_with(expected_reply_text)


# --- Тесты для process_help_command ---


@pytest.mark.asyncio
async def test_process_help_command():
    """
    Тест: команда /help.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser, id=11223)

    # Обновляем цели для patch
    with patch("app.bot.handlers.basic.get_session"), patch(
        "app.bot.handlers.basic.log_user_action"
    ), patch("app.bot.handlers.basic.logger") as mock_logger:
        await process_help_command(mock_message)

        expected_help_text = (
            "<b>Доступные команды:</b>\n\n"
            "/start - Перезапустить бота\n"
            "/profile - 👤 Мой профиль и подписки\n"
            "/weather <code>[город]</code> - ☀️ Узнать погоду\n"
            "/news - 📰 Последние новости (США)\n"
            "/events <code>[город]</code> - 🎉 События в городе\n\n"
            "<b>Управление подписками:</b>\n"
            "/subscribe - 🔔 Подписаться на рассылку\n"
            "/mysubscriptions - 📜 Посмотреть мои подписки\n"
            "/unsubscribe - 🔕 Отписаться от рассылки\n\n"
            "/cancel - ❌ Отменить текущее действие\n"
            "/help - ❓ Показать эту справку"
        )
        mock_message.answer.assert_called_once_with(expected_help_text)
        mock_logger.info.assert_called_with(
            f"Отправлена справка по команде /help пользователю {mock_message.from_user.id}"
        )


# --- Тесты для cmd_cancel_any_state ---


@pytest.mark.asyncio
async def test_cmd_cancel_any_state_with_state():
    """Тест: /cancel вызывается, когда пользователь в активном состоянии."""
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(id=123)
    mock_state = AsyncMock(spec=FSMContext)
    mock_state.get_state.return_value = SubscriptionStates.choosing_frequency.state

    with patch("app.bot.handlers.basic.get_session"), patch(
        "app.bot.handlers.basic.log_user_action"
    ):
        await cmd_cancel_any_state(mock_message, mock_state)

        mock_state.clear.assert_called_once()
        mock_message.answer.assert_called_once_with(
            "Действие отменено.", reply_markup=ReplyKeyboardRemove()
        )


@pytest.mark.asyncio
async def test_cmd_cancel_any_state_no_state():
    """Тест: /cancel вызывается, когда нет активного состояния."""
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(id=123)
    mock_state = AsyncMock(spec=FSMContext)
    mock_state.get_state.return_value = None  # Нет состояния

    with patch("app.bot.handlers.basic.get_session"), patch(
        "app.bot.handlers.basic.log_user_action"
    ):
        await cmd_cancel_any_state(mock_message, mock_state)

        mock_state.clear.assert_not_called()  # Очистка не должна вызываться
        mock_message.answer.assert_called_once_with(
            "Нет активного действия для отмены.", reply_markup=ReplyKeyboardRemove()
        )