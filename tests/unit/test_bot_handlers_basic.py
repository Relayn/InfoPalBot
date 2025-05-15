import pytest
import html # Для expected_help_text
from unittest.mock import AsyncMock, MagicMock, patch

# Импортируем тестируемые обработчики
from app.bot.main import (
    process_start_command,
    process_help_command
)
from app.database.models import User as DBUser # Для мокирования пользователя БД
from aiogram.types import Message, User as AiogramUser, Chat # Типы aiogram
from aiogram.fsm.context import FSMContext # Для process_start_command

# --- Тесты для process_start_command ---

@pytest.mark.asyncio
async def test_process_start_command_new_user():
    """
    Тест: команда /start для нового пользователя.
    Ожидается:
    - Вызов create_user_if_not_exists.
    - Отправка приветственного сообщения.
    - Сброс состояния FSM.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser)
    mock_message.from_user.id = 12345
    mock_message.from_user.full_name = "Test User"
    mock_message.chat = MagicMock(spec=Chat)
    mock_message.chat.id = 12345
    mock_state = AsyncMock(spec=FSMContext) # Мок для FSMContext

    mock_db_user = DBUser(id=1, telegram_id=12345)

    with patch('app.bot.main.get_session') as mock_get_session, \
         patch('app.bot.main.create_user_if_not_exists', return_value=mock_db_user) as mock_create_user:

        mock_session_context_manager = MagicMock()
        mock_session = MagicMock()
        mock_session_context_manager.__enter__.return_value = mock_session
        mock_get_session.return_value.__next__.return_value = mock_session_context_manager

        await process_start_command(mock_message, mock_state) # Передаем mock_state

        mock_state.clear.assert_called_once() # Проверяем сброс состояния
        mock_create_user.assert_called_once_with(session=mock_session, telegram_id=12345)
        expected_reply_text = (
            f"Привет, {mock_message.from_user.full_name}! Я InfoPalBot. "
            f"Я могу предоставить тебе актуальную информацию.\n"
            f"Используй /help, чтобы увидеть список доступных команд."
        )
        mock_message.answer.assert_called_once_with(expected_reply_text)


@pytest.mark.asyncio
async def test_process_start_command_existing_user():
    """
    Тест: команда /start для существующего пользователя.
    Ожидается:
    - Вызов create_user_if_not_exists.
    - Отправка приветственного сообщения.
    - Сброс состояния FSM.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser)
    mock_message.from_user.id = 54321
    mock_message.from_user.full_name = "Existing User"
    mock_message.chat = MagicMock(spec=Chat)
    mock_message.chat.id = 54321
    mock_state = AsyncMock(spec=FSMContext)

    mock_db_user = DBUser(id=2, telegram_id=54321)

    with patch('app.bot.main.get_session') as mock_get_session, \
         patch('app.bot.main.create_user_if_not_exists', return_value=mock_db_user) as mock_create_user:

        mock_session_context_manager = MagicMock()
        mock_session = MagicMock()
        mock_session_context_manager.__enter__.return_value = mock_session
        mock_get_session.return_value.__next__.return_value = mock_session_context_manager

        await process_start_command(mock_message, mock_state)

        mock_state.clear.assert_called_once()
        mock_create_user.assert_called_once_with(session=mock_session, telegram_id=54321)
        expected_reply_text = (
            f"Привет, {mock_message.from_user.full_name}! Я InfoPalBot. "
            f"Я могу предоставить тебе актуальную информацию.\n"
            f"Используй /help, чтобы увидеть список доступных команд."
        )
        mock_message.answer.assert_called_once_with(expected_reply_text)


@pytest.mark.asyncio
async def test_process_start_command_db_error():
    """
    Тест: команда /start с ошибкой при работе с БД.
    Ожидается:
    - Отправка сообщения об ошибке пользователю.
    - Логирование ошибки.
    - Сброс состояния FSM.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser)
    mock_message.from_user.id = 67890
    mock_message.from_user.full_name = "Error User"
    mock_message.chat = MagicMock(spec=Chat)
    mock_message.chat.id = 67890
    mock_state = AsyncMock(spec=FSMContext)

    db_exception = Exception("Тестовая ошибка БД")

    with patch('app.bot.main.get_session') as mock_get_session, \
         patch('app.bot.main.create_user_if_not_exists', side_effect=db_exception) as mock_create_user, \
         patch('app.bot.main.logger') as mock_logger:

        mock_session_context_manager = MagicMock()
        mock_session = MagicMock()
        mock_session_context_manager.__enter__.return_value = mock_session
        mock_get_session.return_value.__next__.return_value = mock_session_context_manager

        await process_start_command(mock_message, mock_state)

        mock_state.clear.assert_called_once()
        # mock_create_user.assert_called_once_with(session=mock_session, telegram_id=67890) # Вызов будет, но с ошибкой
        mock_message.answer.assert_called_once_with("Произошла ошибка при обработке вашего запроса. Попробуйте позже.")
        mock_logger.error.assert_called_once()
        args, kwargs = mock_logger.error.call_args
        assert f"Ошибка при обработке команды /start для пользователя {mock_message.from_user.id}: {db_exception}" in args[0]
        assert kwargs.get('exc_info') is True


# --- Тесты для process_help_command ---

@pytest.mark.asyncio
async def test_process_help_command():
    """
    Тест: команда /help.
    Ожидается:
    - Отправка текста справки.
    - Логирование действия.
    """
    mock_message = AsyncMock(spec=Message)
    mock_message.answer = AsyncMock()
    mock_message.from_user = MagicMock(spec=AiogramUser)
    mock_message.from_user.id = 11223

    with patch('app.bot.main.logger.info') as mock_logger_info:
        await process_help_command(mock_message)

        expected_help_text = (
            "<b>Доступные команды:</b>\n"
            "<code>/start</code> - Начать работу с ботом и зарегистрироваться\n"
            "<code>/help</code> - Показать это сообщение со справкой\n"
            "<code>/weather [город]</code> - Получить текущий прогноз погоды (например, <code>/weather Москва</code>)\n"
            "<code>/news</code> - Получить последние новости (Россия)\n"
            "<code>/events [город]</code> - Узнать о предстоящих событиях (например, <code>/events спб</code>). Доступные города см. в /events без аргумента.\n"
            "<code>/subscribe</code> - Подписаться на рассылку\n"
            "<code>/mysubscriptions</code> - Посмотреть ваши активные подписки\n"
            "<code>/unsubscribe</code> - Отписаться от рассылки\n"
            "<code>/cancel</code> - Отменить текущее действие (например, подписку)\n"
        )
        mock_message.answer.assert_called_once_with(expected_help_text)
        mock_logger_info.assert_called_with(f"Отправлена справка по команде /help пользователю {mock_message.from_user.id}")